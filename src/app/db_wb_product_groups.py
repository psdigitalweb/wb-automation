"""Persistence and read models for WB product group analytics."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import bindparam, text

from app.db import engine


def list_project_nm_ids(project_id: int) -> list[int]:
    with engine.connect() as conn:
        return [
            int(value)
            for value in conn.execute(
                text(
                    """
                    SELECT nm_id
                    FROM v_wb_product_source
                    WHERE project_id = :project_id
                      AND nm_id IS NOT NULL
                    ORDER BY nm_id
                    """
                ),
                {"project_id": int(project_id)},
            ).scalars()
        ]


def apply_membership_snapshot(
    *,
    project_id: int,
    mappings: dict[int, int],
    ingest_run_id: int | None,
    missing_runs_to_close: int = 3,
    observed_at: datetime | None = None,
) -> dict[str, int]:
    now = observed_at or datetime.now(timezone.utc)
    threshold = max(1, int(missing_runs_to_close))
    created = changed = refreshed = marked_missing = closed = 0

    with engine.begin() as conn:
        current_rows = conn.execute(
            text(
                """
                SELECT id, nm_id, wb_group_id, missing_runs
                FROM wb_product_group_memberships
                WHERE project_id = :project_id
                  AND valid_to IS NULL
                FOR UPDATE
                """
            ),
            {"project_id": int(project_id)},
        ).mappings().all()
        current = {int(row["nm_id"]): row for row in current_rows}

        for nm_id, group_id in mappings.items():
            row = current.get(int(nm_id))
            if row is None:
                conn.execute(
                    text(
                        """
                        INSERT INTO wb_product_group_memberships (
                            project_id, nm_id, wb_group_id,
                            first_seen_at, last_seen_at, missing_runs,
                            first_ingest_run_id, last_ingest_run_id
                        )
                        VALUES (
                            :project_id, :nm_id, :wb_group_id,
                            :observed_at, :observed_at, 0,
                            :ingest_run_id, :ingest_run_id
                        )
                        """
                    ),
                    {
                        "project_id": int(project_id),
                        "nm_id": int(nm_id),
                        "wb_group_id": int(group_id),
                        "observed_at": now,
                        "ingest_run_id": ingest_run_id,
                    },
                )
                created += 1
                continue

            if int(row["wb_group_id"]) == int(group_id):
                conn.execute(
                    text(
                        """
                        UPDATE wb_product_group_memberships
                        SET last_seen_at = :observed_at,
                            missing_runs = 0,
                            last_ingest_run_id = :ingest_run_id
                        WHERE id = :id
                        """
                    ),
                    {"id": int(row["id"]), "observed_at": now, "ingest_run_id": ingest_run_id},
                )
                refreshed += 1
                continue

            conn.execute(
                text(
                    """
                    UPDATE wb_product_group_memberships
                    SET valid_to = :observed_at,
                        last_ingest_run_id = :ingest_run_id
                    WHERE id = :id
                    """
                ),
                {"id": int(row["id"]), "observed_at": now, "ingest_run_id": ingest_run_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO wb_product_group_memberships (
                        project_id, nm_id, wb_group_id,
                        first_seen_at, last_seen_at, missing_runs,
                        first_ingest_run_id, last_ingest_run_id
                    )
                    VALUES (
                        :project_id, :nm_id, :wb_group_id,
                        :observed_at, :observed_at, 0,
                        :ingest_run_id, :ingest_run_id
                    )
                    """
                ),
                {
                    "project_id": int(project_id),
                    "nm_id": int(nm_id),
                    "wb_group_id": int(group_id),
                    "observed_at": now,
                    "ingest_run_id": ingest_run_id,
                },
            )
            changed += 1

        missing_nm_ids = set(current) - set(mappings)
        for nm_id in missing_nm_ids:
            row = current[nm_id]
            next_missing_runs = int(row["missing_runs"] or 0) + 1
            if next_missing_runs >= threshold:
                conn.execute(
                    text(
                        """
                        UPDATE wb_product_group_memberships
                        SET missing_runs = :missing_runs,
                            valid_to = :observed_at,
                            last_ingest_run_id = :ingest_run_id
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": int(row["id"]),
                        "missing_runs": next_missing_runs,
                        "observed_at": now,
                        "ingest_run_id": ingest_run_id,
                    },
                )
                closed += 1
            else:
                conn.execute(
                    text(
                        """
                        UPDATE wb_product_group_memberships
                        SET missing_runs = :missing_runs,
                            last_ingest_run_id = :ingest_run_id
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": int(row["id"]),
                        "missing_runs": next_missing_runs,
                        "ingest_run_id": ingest_run_id,
                    },
                )
                marked_missing += 1

    return {
        "memberships_created": created,
        "memberships_changed": changed,
        "memberships_refreshed": refreshed,
        "memberships_marked_missing": marked_missing,
        "memberships_closed": closed,
    }


def list_product_groups(
    *,
    project_id: int,
    search: str | None,
    category: str | None,
    in_stock: bool,
    page: int,
    page_size: int,
    min_members: int = 2,
) -> dict[str, Any]:
    search_value = (search or "").strip()
    category_value = (category or "").strip() or None
    params = {
        "project_id": int(project_id),
        "search": f"%{search_value}%",
        "search_num": int(search_value) if search_value.isdigit() else None,
        "category": category_value,
        "in_stock": bool(in_stock),
        "min_members": max(1, int(min_members)),
        "limit": int(page_size),
        "offset": (int(page) - 1) * int(page_size),
    }
    filters = """
        AND (
            :search = '%%'
            OR p.vendor_code ILIKE :search
            OR p.title ILIKE :search
            OR (:search_num IS NOT NULL AND (m.nm_id = :search_num OR m.wb_group_id = :search_num))
        )
        AND (:category IS NULL OR p.subject_name = :category)
        AND (
            NOT :in_stock
            OR COALESCE(fbs.qty, 0) > 0
            OR COALESCE(fbo.qty, 0) > 0
        )
    """
    base_cte = f"""
        WITH fbs_run AS (
            SELECT MAX(snapshot_at) AS run_at
            FROM stock_snapshots
            WHERE project_id = :project_id
        ),
        fbs AS (
            SELECT ss.nm_id, SUM(COALESCE(ss.quantity, 0))::bigint AS qty
            FROM stock_snapshots ss
            JOIN fbs_run r ON r.run_at = ss.snapshot_at
            WHERE ss.project_id = :project_id
            GROUP BY ss.nm_id
        ),
        fbo_wh_latest AS (
            SELECT DISTINCT ON (s.nm_id, s.warehouse_name)
                s.nm_id,
                s.warehouse_name,
                COALESCE(s.quantity, 0)::bigint AS qty
            FROM supplier_stock_snapshots s
            JOIN v_wb_product_source sp
              ON sp.project_id = :project_id
             AND sp.nm_id = s.nm_id
            WHERE s.project_id = :project_id
            ORDER BY
                s.nm_id,
                s.warehouse_name,
                COALESCE(s.last_change_date, s.snapshot_at) DESC
        ),
        fbo AS (
            SELECT nm_id, SUM(qty)::bigint AS qty
            FROM fbo_wh_latest
            GROUP BY nm_id
        ),
        matched_groups AS (
            SELECT DISTINCT m.wb_group_id
            FROM wb_product_group_memberships m
            JOIN v_wb_product_source p
              ON p.project_id = m.project_id
             AND p.nm_id = m.nm_id
            LEFT JOIN fbs ON fbs.nm_id = m.nm_id
            LEFT JOIN fbo ON fbo.nm_id = m.nm_id
            WHERE m.project_id = :project_id
              AND m.valid_to IS NULL
              {filters}
        ),
        groups AS (
            SELECT
                m.wb_group_id,
                COUNT(*)::integer AS members_count,
                MAX(m.last_seen_at) AS last_seen_at,
                SUM(COALESCE(fbs.qty, 0))::bigint AS fbs_stock_qty,
                SUM(COALESCE(fbo.qty, 0))::bigint AS fbo_stock_qty
            FROM wb_product_group_memberships m
            JOIN matched_groups mg ON mg.wb_group_id = m.wb_group_id
            LEFT JOIN fbs ON fbs.nm_id = m.nm_id
            LEFT JOIN fbo ON fbo.nm_id = m.nm_id
            WHERE m.project_id = :project_id
              AND m.valid_to IS NULL
            GROUP BY m.wb_group_id
            HAVING COUNT(*) >= :min_members
        )
    """
    with engine.connect() as conn:
        total = int(
            conn.execute(
                text(base_cte + "SELECT COUNT(*) FROM groups"),
                params,
            ).scalar_one()
        )
        rows = conn.execute(
            text(
                base_cte
                + """
                SELECT
                    g.wb_group_id,
                    g.members_count,
                    g.last_seen_at,
                    g.fbs_stock_qty,
                    g.fbo_stock_qty,
                    (
                        SELECT jsonb_agg(preview ORDER BY preview->>'nm_id')
                        FROM (
                            SELECT jsonb_build_object(
                                'nm_id', p.nm_id,
                                'title', p.title,
                                'vendor_code', p.vendor_code,
                                'image_url',
                                    CASE
                                        WHEN jsonb_typeof(p.pics) = 'array' AND jsonb_array_length(p.pics) > 0
                                        THEN COALESCE(p.pics->0->>'url', p.pics->0->>'big', p.pics->>0)
                                        ELSE NULL
                                    END
                            ) AS preview
                            FROM wb_product_group_memberships gm
                            JOIN v_wb_product_source p
                              ON p.project_id = gm.project_id
                             AND p.nm_id = gm.nm_id
                            WHERE gm.project_id = :project_id
                              AND gm.wb_group_id = g.wb_group_id
                              AND gm.valid_to IS NULL
                            ORDER BY gm.nm_id
                            LIMIT 4
                        ) previews
                    ) AS previews
                FROM groups g
                ORDER BY g.members_count DESC, g.wb_group_id
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        ).mappings().all()
    return {
        "items": [
            {
                "wb_group_id": int(row["wb_group_id"]),
                "members_count": int(row["members_count"]),
                "last_seen_at": row["last_seen_at"],
                "fbs_stock_qty": int(row["fbs_stock_qty"] or 0),
                "fbo_stock_qty": int(row["fbo_stock_qty"] or 0),
                "previews": row["previews"] or [],
            }
            for row in rows
        ],
        "total": total,
        "page": int(page),
        "page_size": int(page_size),
    }


def list_product_group_categories(project_id: int) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    p.subject_name AS name,
                    COUNT(DISTINCT m.wb_group_id)::integer AS groups_count
                FROM wb_product_group_memberships m
                JOIN v_wb_product_source p
                  ON p.project_id = m.project_id
                 AND p.nm_id = m.nm_id
                WHERE m.project_id = :project_id
                  AND m.valid_to IS NULL
                  AND p.subject_name IS NOT NULL
                  AND BTRIM(p.subject_name) <> ''
                GROUP BY p.subject_name
                ORDER BY p.subject_name
                """
            ),
            {"project_id": int(project_id)},
        ).mappings().all()
    return [{"name": str(row["name"]), "groups_count": int(row["groups_count"])} for row in rows]


def get_group_members(project_id: int, wb_group_id: int) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    m.nm_id,
                    m.wb_group_id,
                    m.last_seen_at,
                    m.missing_runs,
                    p.vendor_code,
                    p.title,
                    p.subject_name,
                    CASE
                        WHEN jsonb_typeof(p.pics) = 'array' AND jsonb_array_length(p.pics) > 0
                        THEN COALESCE(p.pics->0->>'url', p.pics->0->>'big', p.pics->>0)
                        ELSE NULL
                    END AS image_url
                FROM wb_product_group_memberships m
                JOIN v_wb_product_source p
                  ON p.project_id = m.project_id
                 AND p.nm_id = m.nm_id
                WHERE m.project_id = :project_id
                  AND m.wb_group_id = :wb_group_id
                  AND m.valid_to IS NULL
                ORDER BY m.nm_id
                """
            ),
            {"project_id": int(project_id), "wb_group_id": int(wb_group_id)},
        ).mappings().all()
    return [dict(row) for row in rows]


def get_product_group_memberships(
    project_id: int,
    nm_id: int,
) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    target.wb_group_id,
                    COUNT(member.id)::integer AS members_count,
                    MAX(member.last_seen_at) AS last_seen_at
                FROM wb_product_group_memberships target
                JOIN wb_product_group_memberships member
                  ON member.project_id = target.project_id
                 AND member.wb_group_id = target.wb_group_id
                 AND member.valid_to IS NULL
                WHERE target.project_id = :project_id
                  AND target.nm_id = :nm_id
                  AND target.valid_to IS NULL
                GROUP BY target.wb_group_id
                ORDER BY target.wb_group_id
                """
            ),
            {"project_id": int(project_id), "nm_id": int(nm_id)},
        ).mappings().all()
    return [
        {
            "wb_group_id": int(row["wb_group_id"]),
            "members_count": int(row["members_count"]),
            "last_seen_at": row["last_seen_at"],
        }
        for row in rows
    ]


def get_group_comparison(
    *,
    project_id: int,
    wb_group_id: int,
    date_from: date,
    date_to: date,
) -> list[dict[str, Any]]:
    sql = text(
        """
        WITH members AS (
            SELECT m.nm_id
            FROM wb_product_group_memberships m
            WHERE m.project_id = :project_id
              AND m.wb_group_id = :wb_group_id
              AND m.valid_to IS NULL
        ),
        fbs_run AS (
            SELECT MAX(snapshot_at) AS run_at
            FROM stock_snapshots
            WHERE project_id = :project_id
        ),
        fbs AS (
            SELECT ss.nm_id, SUM(COALESCE(ss.quantity, 0))::bigint AS qty
            FROM stock_snapshots ss
            JOIN fbs_run r ON r.run_at = ss.snapshot_at
            JOIN members m ON m.nm_id = ss.nm_id
            WHERE ss.project_id = :project_id
            GROUP BY ss.nm_id
        ),
        fbo_wh_latest AS (
            SELECT DISTINCT ON (s.nm_id, s.warehouse_name)
                s.nm_id,
                s.warehouse_name,
                COALESCE(s.quantity, 0)::bigint AS qty
            FROM supplier_stock_snapshots s
            JOIN members m ON m.nm_id = s.nm_id
            WHERE s.project_id = :project_id
            ORDER BY
                s.nm_id,
                s.warehouse_name,
                COALESCE(s.last_change_date, s.snapshot_at) DESC
        ),
        fbo AS (
            SELECT nm_id, SUM(qty)::bigint AS qty
            FROM fbo_wh_latest
            GROUP BY nm_id
        ),
        funnel AS (
            SELECT
                s.nm_id,
                SUM(s.open_count)::bigint AS opens,
                SUM(s.cart_count)::bigint AS carts,
                SUM(s.order_count)::bigint AS orders,
                SUM(s.order_sum)::numeric AS revenue
            FROM wb_card_stats_daily s
            JOIN members m ON m.nm_id = s.nm_id
            WHERE s.project_id = :project_id
              AND s.stat_date BETWEEN :date_from AND :date_to
            GROUP BY s.nm_id
        ),
        ctr AS (
            SELECT
                c.nm_id,
                SUM(c.impressions)::bigint AS impressions,
                SUM(c.card_clicks)::bigint AS card_clicks
            FROM wb_funnel_ctr_daily c
            JOIN members m ON m.nm_id = c.nm_id
            WHERE c.project_id = :project_id
              AND c.stat_date BETWEEN :date_from AND :date_to
              AND NOT c.is_deleted
            GROUP BY c.nm_id
        ),
        price_points AS (
            SELECT
                s.nm_id,
                s.snapshot_at,
                s.price_showcase,
                CASE
                    WHEN pctx.customer_price IS NULL
                      OR pctx.customer_price <= 0
                      OR s.price_showcase IS NULL
                    THEN NULL
                    ELSE GREATEST(
                        0,
                        LEAST(
                            100,
                            ROUND((1 - (s.price_showcase / pctx.customer_price)) * 100)::integer
                        )
                    )
                END AS spp_percent
            FROM wb_showcase_price_snapshots s
            JOIN members m ON m.nm_id = s.nm_id
            LEFT JOIN LATERAL (
                SELECT p.customer_price
                FROM price_snapshots p
                WHERE p.project_id = s.project_id
                  AND p.nm_id = s.nm_id
                  AND p.created_at <= s.snapshot_at + INTERVAL '1 hour'
                  AND p.customer_price IS NOT NULL
                ORDER BY p.created_at DESC
                LIMIT 1
            ) pctx ON TRUE
            WHERE s.project_id = :project_id
              AND s.snapshot_at >= CAST(:date_from AS date)
              AND s.snapshot_at < (CAST(:date_to AS date) + INTERVAL '1 day')
        ),
        price_bounds AS (
            SELECT
                nm_id,
                (ARRAY_AGG(price_showcase ORDER BY snapshot_at ASC)
                    FILTER (WHERE price_showcase IS NOT NULL))[1] AS first_price,
                (ARRAY_AGG(price_showcase ORDER BY snapshot_at DESC)
                    FILTER (WHERE price_showcase IS NOT NULL))[1] AS last_price,
                (ARRAY_AGG(spp_percent ORDER BY snapshot_at ASC)
                    FILTER (WHERE spp_percent IS NOT NULL))[1] AS first_spp,
                (ARRAY_AGG(spp_percent ORDER BY snapshot_at DESC)
                    FILTER (WHERE spp_percent IS NOT NULL))[1] AS last_spp
            FROM price_points
            GROUP BY nm_id
        )
        SELECT
            p.nm_id,
            p.vendor_code,
            p.title,
            p.subject_name,
            CASE
                WHEN jsonb_typeof(p.pics) = 'array' AND jsonb_array_length(p.pics) > 0
                THEN COALESCE(p.pics->0->>'url', p.pics->0->>'big', p.pics->>0)
                ELSE NULL
            END AS image_url,
            pb.first_price,
            pb.last_price,
            pb.first_spp,
            pb.last_spp,
            COALESCE(fbs.qty, 0) AS fbs_stock_qty,
            COALESCE(fbo.qty, 0) AS fbo_stock_qty,
            COALESCE(c.impressions, 0) AS impressions,
            COALESCE(c.card_clicks, 0) AS card_clicks,
            COALESCE(f.opens, 0) AS opens,
            COALESCE(f.carts, 0) AS carts,
            COALESCE(f.orders, 0) AS orders,
            COALESCE(f.revenue, 0) AS revenue
        FROM members m
        JOIN v_wb_product_source p
          ON p.project_id = :project_id
         AND p.nm_id = m.nm_id
        LEFT JOIN funnel f ON f.nm_id = m.nm_id
        LEFT JOIN ctr c ON c.nm_id = m.nm_id
        LEFT JOIN price_bounds pb ON pb.nm_id = m.nm_id
        LEFT JOIN fbs ON fbs.nm_id = m.nm_id
        LEFT JOIN fbo ON fbo.nm_id = m.nm_id
        ORDER BY p.nm_id
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {
                "project_id": int(project_id),
                "wb_group_id": int(wb_group_id),
                "date_from": date_from,
                "date_to": date_to,
            },
        ).mappings().all()

    result: list[dict[str, Any]] = []
    for row in rows:
        impressions = int(row["impressions"] or 0)
        clicks = int(row["card_clicks"] or 0)
        opens = int(row["opens"] or 0)
        carts = int(row["carts"] or 0)
        orders = int(row["orders"] or 0)
        first_price = float(row["first_price"]) if row["first_price"] is not None else None
        last_price = float(row["last_price"]) if row["last_price"] is not None else None
        first_spp = int(row["first_spp"]) if row["first_spp"] is not None else None
        last_spp = int(row["last_spp"]) if row["last_spp"] is not None else None
        result.append(
            {
                "nm_id": int(row["nm_id"]),
                "vendor_code": row["vendor_code"],
                "title": row["title"],
                "subject_name": row["subject_name"],
                "image_url": row["image_url"],
                "stock": {
                    "fbs": int(row["fbs_stock_qty"] or 0),
                    "fbo": int(row["fbo_stock_qty"] or 0),
                },
                "price": {
                    "first": first_price,
                    "last": last_price,
                    "delta": (last_price - first_price)
                    if first_price is not None and last_price is not None
                    else None,
                },
                "spp": {
                    "first": first_spp,
                    "last": last_spp,
                    "delta": (last_spp - first_spp)
                    if first_spp is not None and last_spp is not None
                    else None,
                },
                "funnel": {
                    "impressions": impressions,
                    "card_clicks": clicks,
                    "ctr_percent": (clicks / impressions * 100) if impressions else None,
                    "opens": opens,
                    "carts": carts,
                    "cart_rate_percent": (carts / opens * 100) if opens else None,
                    "orders": orders,
                    "cart_to_order_percent": (orders / carts * 100) if carts else None,
                    "revenue": float(row["revenue"] or 0),
                },
            }
        )
    return result


def get_group_series(
    *,
    project_id: int,
    wb_group_id: int,
    nm_ids: list[int],
    date_from: date,
    date_to: date,
) -> list[dict[str, Any]]:
    sql = (
        text(
            """
            WITH requested AS (
                SELECT m.nm_id
                FROM wb_product_group_memberships m
                WHERE m.project_id = :project_id
                  AND m.wb_group_id = :wb_group_id
                  AND m.valid_to IS NULL
                  AND m.nm_id IN :nm_ids
            ),
            days AS (
                SELECT generate_series(
                    CAST(:date_from AS date),
                    CAST(:date_to AS date),
                    INTERVAL '1 day'
                )::date AS stat_date
            ),
            funnel AS (
                SELECT
                    s.nm_id,
                    s.stat_date,
                    SUM(s.open_count)::bigint AS opens,
                    SUM(s.cart_count)::bigint AS carts,
                    SUM(s.order_count)::bigint AS orders,
                    SUM(s.order_sum)::numeric AS revenue
                FROM wb_card_stats_daily s
                JOIN requested r ON r.nm_id = s.nm_id
                WHERE s.project_id = :project_id
                  AND s.stat_date BETWEEN :date_from AND :date_to
                GROUP BY s.nm_id, s.stat_date
            ),
            ctr AS (
                SELECT
                    c.nm_id,
                    c.stat_date,
                    SUM(c.impressions)::bigint AS impressions,
                    SUM(c.card_clicks)::bigint AS card_clicks
                FROM wb_funnel_ctr_daily c
                JOIN requested r ON r.nm_id = c.nm_id
                WHERE c.project_id = :project_id
                  AND c.stat_date BETWEEN :date_from AND :date_to
                  AND NOT c.is_deleted
                GROUP BY c.nm_id, c.stat_date
            ),
            prices AS (
                SELECT DISTINCT ON (s.nm_id, s.snapshot_at::date)
                    s.nm_id,
                    s.snapshot_at::date AS stat_date,
                    s.price_showcase,
                    CASE
                        WHEN pctx.customer_price IS NULL
                          OR pctx.customer_price <= 0
                          OR s.price_showcase IS NULL
                        THEN NULL
                        ELSE GREATEST(
                            0,
                            LEAST(
                                100,
                                ROUND((1 - (s.price_showcase / pctx.customer_price)) * 100)::integer
                            )
                        )
                    END AS spp_percent
                FROM wb_showcase_price_snapshots s
                JOIN requested r ON r.nm_id = s.nm_id
                LEFT JOIN LATERAL (
                    SELECT p.customer_price
                    FROM price_snapshots p
                    WHERE p.project_id = s.project_id
                      AND p.nm_id = s.nm_id
                      AND p.created_at <= s.snapshot_at + INTERVAL '1 hour'
                      AND p.customer_price IS NOT NULL
                    ORDER BY p.created_at DESC
                    LIMIT 1
                ) pctx ON TRUE
                WHERE s.project_id = :project_id
                  AND s.snapshot_at >= CAST(:date_from AS date)
                  AND s.snapshot_at < (CAST(:date_to AS date) + INTERVAL '1 day')
                ORDER BY s.nm_id, s.snapshot_at::date, s.snapshot_at DESC
            )
            SELECT
                r.nm_id,
                p.title,
                p.vendor_code,
                d.stat_date,
                pr.price_showcase,
                pr.spp_percent,
                COALESCE(c.impressions, 0) AS impressions,
                COALESCE(c.card_clicks, 0) AS card_clicks,
                COALESCE(f.opens, 0) AS opens,
                COALESCE(f.carts, 0) AS carts,
                COALESCE(f.orders, 0) AS orders,
                COALESCE(f.revenue, 0) AS revenue
            FROM requested r
            JOIN v_wb_product_source p
              ON p.project_id = :project_id
             AND p.nm_id = r.nm_id
            CROSS JOIN days d
            LEFT JOIN funnel f ON f.nm_id = r.nm_id AND f.stat_date = d.stat_date
            LEFT JOIN ctr c ON c.nm_id = r.nm_id AND c.stat_date = d.stat_date
            LEFT JOIN prices pr ON pr.nm_id = r.nm_id AND pr.stat_date = d.stat_date
            ORDER BY r.nm_id, d.stat_date
            """
        )
        .bindparams(bindparam("nm_ids", expanding=True))
    )
    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {
                "project_id": int(project_id),
                "wb_group_id": int(wb_group_id),
                "nm_ids": [int(value) for value in nm_ids],
                "date_from": date_from,
                "date_to": date_to,
            },
        ).mappings().all()

    series_by_nm: dict[int, dict[str, Any]] = {}
    for row in rows:
        nm_id = int(row["nm_id"])
        series = series_by_nm.setdefault(
            nm_id,
            {
                "nm_id": nm_id,
                "title": row["title"],
                "vendor_code": row["vendor_code"],
                "points": [],
            },
        )
        impressions = int(row["impressions"] or 0)
        clicks = int(row["card_clicks"] or 0)
        series["points"].append(
            {
                "date": row["stat_date"].isoformat(),
                "price": float(row["price_showcase"]) if row["price_showcase"] is not None else None,
                "spp_percent": int(row["spp_percent"]) if row["spp_percent"] is not None else None,
                "impressions": impressions,
                "card_clicks": clicks,
                "ctr_percent": (clicks / impressions * 100) if impressions else None,
                "opens": int(row["opens"] or 0),
                "carts": int(row["carts"] or 0),
                "orders": int(row["orders"] or 0),
                "revenue": float(row["revenue"] or 0),
            }
        )
    return list(series_by_nm.values())

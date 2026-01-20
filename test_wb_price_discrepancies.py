from app.db import engine
from sqlalchemy import text


def test_diff_rub_and_recommended_price_computation():
    """
    Contract test for diff_rub / is_below_rrp / recommended_wb_admin_price
    and delta_recommended computations and sorting.

    This does not depend on real ingestion tables; it uses a VALUES CTE to
    verify the SQL formulas that are also used in api_wb_price_discrepancies.
    """
    sql = text(
        """
        WITH src(article, rrp_price, showcase_price, wb_admin_price) AS (
            VALUES
                -- Below RRP, diff_rub = 50, recommended = 400, delta = 100
                ('A', 200.0, 150.0, 300.0),
                -- Above RRP, diff_rub = -20, recommended will still be computed
                ('B', 100.0, 120.0, 200.0),
                -- Below RRP, diff_rub = 50, recommended = 200, delta = 0
                ('C', 100.0, 50.0, 100.0)
        ),
        computed AS (
            SELECT
                article,
                rrp_price,
                showcase_price,
                wb_admin_price,
                CASE
                    WHEN rrp_price IS NOT NULL
                     AND showcase_price IS NOT NULL
                    THEN (rrp_price - showcase_price)
                    ELSE NULL
                END AS diff_rub,
                CASE
                    WHEN rrp_price IS NOT NULL
                     AND rrp_price > 0
                     AND showcase_price IS NOT NULL
                    THEN ((rrp_price - showcase_price) / rrp_price) * 100.0
                    ELSE NULL
                END AS diff_percent,
                CASE
                    WHEN rrp_price IS NOT NULL
                     AND rrp_price > 0
                     AND wb_admin_price IS NOT NULL
                     AND wb_admin_price > 0
                     AND showcase_price IS NOT NULL
                     AND showcase_price > 0
                    THEN ROUND(rrp_price * wb_admin_price / showcase_price)
                    ELSE NULL
                END AS recommended_wb_admin_price,
                CASE
                    WHEN rrp_price IS NOT NULL
                     AND rrp_price > 0
                     AND wb_admin_price IS NOT NULL
                     AND wb_admin_price > 0
                     AND showcase_price IS NOT NULL
                     AND showcase_price > 0
                    THEN ROUND(rrp_price * wb_admin_price / showcase_price) - wb_admin_price
                    ELSE NULL
                END AS delta_recommended,
                CASE
                    WHEN rrp_price IS NOT NULL
                     AND showcase_price IS NOT NULL
                     AND showcase_price < rrp_price
                    THEN TRUE
                    ELSE FALSE
                END AS is_below_rrp
            FROM src
        )
        SELECT article, diff_rub, is_below_rrp,
               recommended_wb_admin_price, delta_recommended
        FROM computed
        WHERE is_below_rrp = TRUE
        ORDER BY diff_rub DESC, article
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(sql).fetchall()

    # Only articles A and C are below RRP; both have diff_rub = 50.
    articles = [row[0] for row in rows]
    diffs = [float(row[1]) for row in rows]
    flags = [bool(row[2]) for row in rows]

    assert articles == ["A", "C"] or articles == ["C", "A"]
    assert all(d == 50.0 for d in diffs)
    assert all(flags)

    # Check recommended price and delta for a specific article
    rec_map = {row[0]: (row[3], row[4]) for row in rows}
    # For A: rrp=200, showcase=150, wb_admin=300 => recommended=400, delta=100
    rec_a, delta_a = rec_map["A"]
    assert float(rec_a) == 400.0
    assert float(delta_a) == 100.0


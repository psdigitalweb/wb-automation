"""WB product-group ingestion orchestration."""

from __future__ import annotations

from collections import Counter
from typing import Any

from app.db_wb_product_groups import apply_membership_snapshot, list_project_nm_ids
from app.tasks.ingestion import _get_frontend_prices_proxy_config
from app.wb.product_groups_client import WBProductGroupsClient


async def ingest_wb_product_groups(project_id: int, run_id: int | None = None) -> dict[str, Any]:
    nm_ids = list_project_nm_ids(int(project_id))
    proxy_url, proxy_scheme = _get_frontend_prices_proxy_config(int(project_id))
    client = WBProductGroupsClient(proxy_url=proxy_url, batch_size=100)
    mappings, batches_total = await client.fetch_memberships(nm_ids)

    group_sizes = Counter(mappings.values())
    persistence_stats = apply_membership_snapshot(
        project_id=int(project_id),
        mappings=mappings,
        ingest_run_id=run_id,
        missing_runs_to_close=3,
    )
    return {
        "ok": True,
        "domain": "wb_product_groups",
        "project_id": int(project_id),
        "products_requested": len(nm_ids),
        "products_returned": len(mappings),
        "products_missing": max(0, len(nm_ids) - len(mappings)),
        "batches_total": batches_total,
        "groups_total": len(group_sizes),
        "groups_multi_member": sum(1 for size in group_sizes.values() if size > 1),
        "products_in_multi_member_groups": sum(size for size in group_sizes.values() if size > 1),
        "max_group_size": max(group_sizes.values(), default=0),
        "proxy_used": bool(proxy_url),
        "proxy_scheme": proxy_scheme if proxy_url else None,
        **persistence_stats,
    }

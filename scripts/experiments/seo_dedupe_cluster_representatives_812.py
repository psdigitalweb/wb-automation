#!/usr/bin/env python3
"""Read-only conservative dedupe experiment for category 812 query representatives.

The script reads SeoQueryClusterMembership rows through app.db.SessionLocal,
selects one high-ranking representative per cluster, deduplicates representatives
with deterministic text signatures, and writes experiment artifacts only.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit

from sqlalchemy import desc, func, select


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
DEFAULT_PROJECT_ID = 1
DEFAULT_CATEGORY_ID = 812
DEFAULT_FREQUENCY_THRESHOLD = Decimal("500")
DEFAULT_OUT_DIR = (
    PROJECT_ROOT
    / "tests"
    / "seo"
    / "phase1q"
    / "category_812"
    / "dedupe_cluster_representatives"
)
DOCKER_ONLY_DB_HOSTS = {"postgres", "db"}
SIGNATURE_STOPWORDS = frozenset(
    {
        "для",
        "с",
        "со",
        "и",
        "на",
        "в",
        "во",
        "под",
        "к",
        "ко",
        "из",
        "от",
        "до",
        "у",
        "без",
        "по",
    }
)
RULES_USED = (
    "exact_normalized_text_equal",
    "canonical_token_signature_equal_after_service_token_removal",
)


if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app.db import SessionLocal  # noqa: E402
from app.models import SeoQueryClusterMembership  # noqa: E402
from app.services.seo.query_pipeline.normalization import normalize_query_text  # noqa: E402


@dataclass(frozen=True)
class Representative:
    """One selected query representative for a query cluster."""

    cluster_id: int
    query: str
    ranking_value_used: Decimal


@dataclass(frozen=True)
class DuplicateGroup:
    """Deterministic dedupe group with one kept representative."""

    group_id: str
    signature: str
    kept: Representative
    removed: tuple[Representative, ...]
    rule: str
    risk_note: str


def decimal_to_json(value: Decimal) -> float | int:
    """Convert Decimal ranking values into stable compact JSON numbers."""

    if value == value.to_integral_value():
        return int(value)
    return float(value)


def canonical_signature(query: str) -> str:
    """Build conservative token signature for dedupe-only comparison."""

    normalized = normalize_query_text(query)
    tokens = [token for token in normalized.split() if token and token not in SIGNATURE_STOPWORDS]
    return " ".join(sorted(tokens))


def _group_rule(items: Iterable[Representative]) -> str:
    normalized_values = {normalize_query_text(item.query) for item in items}
    if len(normalized_values) == 1:
        return "exact_normalized_text_equal"
    return "canonical_token_signature_equal_after_service_token_removal"


def _risk_note(rule: str) -> str:
    if rule == "exact_normalized_text_equal":
        return "Low risk: normalized query text is identical."
    return (
        "Low-to-medium risk: only token order and very weak service tokens are ignored; "
        "no semantic-neighbor or category-specific merge rules were used."
    )


def dedupe_representatives(representatives: list[Representative]) -> tuple[list[Representative], list[DuplicateGroup]]:
    """Deduplicate representatives with exact-normalized and token-signature rules."""

    by_signature: dict[str, list[Representative]] = {}
    for representative in representatives:
        signature = canonical_signature(representative.query)
        if not signature:
            signature = f"__empty_signature__:{normalize_query_text(representative.query)}"
        by_signature.setdefault(signature, []).append(representative)

    kept: list[Representative] = []
    groups: list[DuplicateGroup] = []
    group_number = 1
    for signature in sorted(by_signature):
        items = sorted(
            by_signature[signature],
            key=lambda item: (-item.ranking_value_used, normalize_query_text(item.query), item.cluster_id),
        )
        winner = items[0]
        kept.append(winner)
        if len(items) > 1:
            rule = _group_rule(items)
            groups.append(
                DuplicateGroup(
                    group_id=f"dup-{group_number:04d}",
                    signature=signature,
                    kept=winner,
                    removed=tuple(items[1:]),
                    rule=rule,
                    risk_note=_risk_note(rule),
                )
            )
            group_number += 1

    kept.sort(key=lambda item: (-item.ranking_value_used, normalize_query_text(item.query), item.cluster_id))
    return kept, groups


def load_representatives(
    *,
    project_id: int,
    category_id: int,
    frequency_threshold: Decimal,
) -> list[Representative]:
    """Read representatives from DB without modifying session state."""

    session = SessionLocal()
    try:
        ranked = (
            select(
                SeoQueryClusterMembership.cluster_id.label("cluster_id"),
                SeoQueryClusterMembership.normalized_query_text.label("query"),
                SeoQueryClusterMembership.ranking_value_used.label("ranking_value_used"),
                func.row_number()
                .over(
                    partition_by=SeoQueryClusterMembership.cluster_id,
                    order_by=(
                        desc(SeoQueryClusterMembership.ranking_value_used),
                        SeoQueryClusterMembership.normalized_query_text.asc(),
                    ),
                )
                .label("rn"),
            )
            .where(
                SeoQueryClusterMembership.project_id == int(project_id),
                SeoQueryClusterMembership.category_id == int(category_id),
                SeoQueryClusterMembership.ranking_value_used > frequency_threshold,
            )
            .subquery()
        )
        rows = session.execute(
            select(ranked.c.cluster_id, ranked.c.query, ranked.c.ranking_value_used)
            .where(ranked.c.rn == 1)
            .order_by(desc(ranked.c.ranking_value_used), ranked.c.query.asc(), ranked.c.cluster_id.asc())
        ).all()
        session.rollback()
    finally:
        session.close()

    return [
        Representative(
            cluster_id=int(row.cluster_id),
            query=str(row.query),
            ranking_value_used=Decimal(str(row.ranking_value_used)),
        )
        for row in rows
    ]


def representative_to_json(item: Representative, *, cluster_key: str = "cluster_id") -> dict[str, object]:
    """Serialize a representative with a configurable cluster id field name."""

    return {
        cluster_key: item.cluster_id,
        "query": item.query,
        "ranking_value_used": decimal_to_json(item.ranking_value_used),
    }


def write_json(path: Path, payload: object) -> None:
    """Write valid UTF-8 JSON with deterministic formatting."""

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_after_payload(kept: list[Representative], groups: list[DuplicateGroup]) -> list[dict[str, object]]:
    """Build representatives_after.json payload."""

    group_by_kept_cluster = {group.kept.cluster_id: group for group in groups}
    payload: list[dict[str, object]] = []
    for item in kept:
        group = group_by_kept_cluster.get(item.cluster_id)
        payload.append(
            {
                "kept_cluster_id": item.cluster_id,
                "kept_query": item.query,
                "ranking_value_used": decimal_to_json(item.ranking_value_used),
                "duplicate_group_id": group.group_id if group else None,
                "removed_cluster_ids": [removed.cluster_id for removed in group.removed] if group else [],
            }
        )
    return payload


def build_groups_payload(groups: list[DuplicateGroup]) -> list[dict[str, object]]:
    """Build duplicate_groups.json payload."""

    return [
        {
            "group_id": group.group_id,
            "signature": group.signature,
            "kept": representative_to_json(group.kept, cluster_key="cluster_id"),
            "removed": [representative_to_json(item, cluster_key="cluster_id") for item in group.removed],
            "rule": group.rule,
            "risk_note": group.risk_note,
        }
        for group in groups
    ]


def find_intentionally_not_merged(
    representatives: list[Representative],
) -> list[dict[str, object]]:
    """Find examples from known risky intent pairs that the conservative rules keep separate."""

    examples = (
        ("кружка подруге", "кружка любимой"),
        ("кружка для чая", "кружка для кофе"),
        ("милая кружка", "красивая кружка"),
        ("кружка с крышкой", "кружка с блюдцем"),
    )
    by_query = {normalize_query_text(item.query): item for item in representatives}
    result: list[dict[str, object]] = []
    for left_raw, right_raw in examples:
        left = by_query.get(normalize_query_text(left_raw))
        right = by_query.get(normalize_query_text(right_raw))
        if not left or not right:
            continue
        result.append(
            {
                "left": representative_to_json(left, cluster_key="cluster_id"),
                "right": representative_to_json(right, cluster_key="cluster_id"),
                "reason": "different canonical signatures; treated as different intent",
                "left_signature": canonical_signature(left.query),
                "right_signature": canonical_signature(right.query),
            }
        )
    return result


def write_report(
    path: Path,
    *,
    project_id: int,
    category_id: int,
    frequency_threshold: Decimal,
    representatives: list[Representative],
    kept: list[Representative],
    groups: list[DuplicateGroup],
    not_merged: list[dict[str, object]],
) -> None:
    """Write short operator-readable Markdown report."""

    removed_count = len(representatives) - len(kept)
    reduction_pct = (removed_count / len(representatives) * 100) if representatives else 0.0
    sample_groups = groups[:10]
    lines = [
        "# Conservative dedupe of cluster representatives for category 812",
        "",
        f"- project_id: {project_id}",
        f"- category_id: {category_id}",
        f"- threshold: ranking_value_used > {decimal_to_json(frequency_threshold)}",
        f"- representatives before: {len(representatives)}",
        f"- representatives after: {len(kept)}",
        f"- removed: {removed_count} ({reduction_pct:.2f}%)",
        f"- duplicate groups: {len(groups)}",
        f"- max group size: {max((len(group.removed) + 1 for group in groups), default=1)}",
        "",
        "## What changed",
        "",
        (
            "The experiment keeps the strongest query per original cluster, then merges only representatives "
            "with identical normalized text or identical sorted significant-token signatures. It does not use "
            "LLM calls, category-specific rules, database writes, or runtime pipeline changes."
        ),
        "",
        "## Good merge examples",
        "",
    ]
    if sample_groups:
        for group in sample_groups[:5]:
            removed = ", ".join(item.query for item in group.removed[:4])
            lines.append(f"- kept `{group.kept.query}`; removed `{removed}`; rule: `{group.rule}`")
    else:
        lines.append("- No duplicate groups found by the conservative rules.")

    lines.extend(["", "## Intentionally not merged", ""])
    if not_merged:
        for item in not_merged:
            left = item["left"]["query"]
            right = item["right"]["query"]
            lines.append(f"- `{left}` vs `{right}`: different signatures, different intent.")
    else:
        lines.append(
            "- The known risky pair examples were not both present among representatives; "
            "the rules still avoid semantic-neighbor merges by requiring exact signature equality."
        )

    lines.extend(
        [
            "",
            "## False-merge risks",
            "",
            "- Token-signature groups ignore weak service tokens and word order, so some phrase-level nuance can be lost.",
            "- No inflection/singular-plural rule was added because no safe existing clustering inflector was imported.",
            "- The output should be reviewed before using the rule as a pre-LLM selector step.",
            "",
            "## Recommendation",
            "",
            (
                "Use this as a candidate pre-LLM compaction only if operator review of duplicate_groups.json "
                "confirms the token-signature merges are acceptable. The current rule is deliberately conservative "
                "and is more suitable for reducing obvious duplicates than for semantic clustering."
            ),
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def run_experiment(
    *,
    project_id: int,
    category_id: int,
    frequency_threshold: Decimal,
    out_dir: Path,
) -> dict[str, object]:
    """Run the read-only experiment and write artifacts."""

    representatives = load_representatives(
        project_id=project_id,
        category_id=category_id,
        frequency_threshold=frequency_threshold,
    )
    kept, groups = dedupe_representatives(representatives)
    not_merged = find_intentionally_not_merged(representatives)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "project_id": project_id,
        "category_id": category_id,
        "frequency_threshold": decimal_to_json(frequency_threshold),
        "input_representatives_count": len(representatives),
        "deduped_representatives_count": len(kept),
        "removed_count": len(representatives) - len(kept),
        "duplicate_group_count": len(groups),
        "max_group_size": max((len(group.removed) + 1 for group in groups), default=1),
        "rules_used": list(RULES_USED),
        "warnings": [
            "Read-only experiment; no DB writes.",
            "No LLM calls.",
            "No category-specific dedupe literals or semantic-neighbor merges.",
            "No singular/plural/inflection rule was used.",
        ],
    }

    write_json(out_dir / "summary.json", summary)
    write_json(
        out_dir / "representatives_before.json",
        [representative_to_json(item, cluster_key="cluster_id") for item in representatives],
    )
    write_json(out_dir / "representatives_after.json", build_after_payload(kept, groups))
    write_json(out_dir / "duplicate_groups.json", build_groups_payload(groups))
    write_json(out_dir / "intentionally_not_merged_examples.json", not_merged)
    write_report(
        out_dir / "dedupe_report.md",
        project_id=project_id,
        category_id=category_id,
        frequency_threshold=frequency_threshold,
        representatives=representatives,
        kept=kept,
        groups=groups,
        not_merged=not_merged,
    )
    return summary


def _running_inside_container() -> bool:
    return os.getenv("ECOMCORE_DEDUPE_EXPERIMENT_IN_DOCKER") == "1" or Path("/.dockerenv").exists()


def _load_env_defaults(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _declared_database_host() -> str | None:
    env_defaults = _load_env_defaults(PROJECT_ROOT / ".env")
    database_url = os.getenv("DATABASE_URL") or env_defaults.get("DATABASE_URL")
    if database_url:
        parsed = urlsplit(database_url)
        if parsed.hostname:
            return parsed.hostname
    return os.getenv("POSTGRES_HOST") or env_defaults.get("POSTGRES_HOST")


def _should_reroute_to_docker() -> bool:
    if _running_inside_container():
        return False
    database_host = _declared_database_host()
    return bool(database_host and database_host.lower() in DOCKER_ONLY_DB_HOSTS)


def _rerun_in_api_container(argv: list[str]) -> int:
    compose_file = PROJECT_ROOT / "infra" / "docker" / "docker-compose.yml"
    print(
        "DB host is available only inside docker-compose network. "
        "Re-running dedupe experiment in the api container...",
        file=sys.stderr,
    )
    ensure_command = ["docker", "compose", "-f", str(compose_file), "up", "-d", "postgres", "api"]
    exec_command = [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "exec",
        "-T",
        "-e",
        "ECOMCORE_DEDUPE_EXPERIMENT_IN_DOCKER=1",
        "api",
        "python",
        "scripts/experiments/seo_dedupe_cluster_representatives_812.py",
        *argv,
    ]
    try:
        ensure_result = subprocess.run(ensure_command, cwd=PROJECT_ROOT)
        if ensure_result.returncode != 0:
            return ensure_result.returncode
        return subprocess.run(exec_command, cwd=PROJECT_ROOT).returncode
    except FileNotFoundError:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "Docker CLI not found. Start Docker Desktop or run inside the api container.",
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1


def main() -> int:
    if _should_reroute_to_docker():
        return _rerun_in_api_container(sys.argv[1:])

    parser = argparse.ArgumentParser(
        description="Read-only dedupe experiment for category 812 cluster representatives."
    )
    parser.add_argument("--project-id", type=int, default=DEFAULT_PROJECT_ID)
    parser.add_argument("--category-id", type=int, default=DEFAULT_CATEGORY_ID)
    parser.add_argument("--frequency-threshold", type=Decimal, default=DEFAULT_FREQUENCY_THRESHOLD)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    summary = run_experiment(
        project_id=int(args.project_id),
        category_id=int(args.category_id),
        frequency_threshold=Decimal(args.frequency_threshold),
        out_dir=args.out_dir,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

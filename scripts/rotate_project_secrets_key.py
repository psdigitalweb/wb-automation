"""Audit or rotate encrypted project marketplace tokens.

The command is read-only unless both ``--apply`` and the exact confirmation
phrase are supplied. During rotation, the new key must be configured as the
primary key and the old key as the previous-key fallback.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Iterable

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy import text

from app.db import engine
from app.utils.secrets_encryption import get_project_secrets_fernets


CONFIRMATION_PHRASE = "ROTATE_PROJECT_SECRETS_KEY"


@dataclass(frozen=True)
class TokenRotationAudit:
    total: int
    encrypted_with_primary: int
    requires_rotation: int
    invalid: int


def audit_encrypted_tokens(
    tokens: Iterable[str],
    *,
    primary: Fernet,
    key_ring: MultiFernet,
) -> TokenRotationAudit:
    total = 0
    encrypted_with_primary = 0
    requires_rotation = 0
    invalid = 0

    for token in tokens:
        total += 1
        encoded = token.encode()
        try:
            primary.decrypt(encoded)
            encrypted_with_primary += 1
            continue
        except InvalidToken:
            pass

        try:
            key_ring.decrypt(encoded)
            requires_rotation += 1
        except InvalidToken:
            invalid += 1

    return TokenRotationAudit(
        total=total,
        encrypted_with_primary=encrypted_with_primary,
        requires_rotation=requires_rotation,
        invalid=invalid,
    )


def _load_rows(conn, *, for_update: bool) -> list[dict]:
    lock_clause = " FOR UPDATE" if for_update else ""
    rows = conn.execute(
        text(
            """
            SELECT id, api_token_encrypted
            FROM project_marketplaces
            WHERE api_token_encrypted IS NOT NULL
              AND api_token_encrypted <> ''
            ORDER BY id
            """
            + lock_clause
        )
    ).mappings().all()
    return [dict(row) for row in rows]


def _audit_rows(
    rows: list[dict],
    *,
    primary: Fernet,
    key_ring: MultiFernet,
) -> TokenRotationAudit:
    return audit_encrypted_tokens(
        (str(row["api_token_encrypted"]) for row in rows),
        primary=primary,
        key_ring=key_ring,
    )


def _print_report(mode: str, audit: TokenRotationAudit) -> None:
    print(
        json.dumps(
            {
                "mode": mode,
                **asdict(audit),
            },
            sort_keys=True,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit or rotate project marketplace tokens without printing secrets.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply rotation in one database transaction. Default is read-only.",
    )
    parser.add_argument(
        "--confirm",
        default="",
        help=f"Required with --apply: {CONFIRMATION_PHRASE}",
    )
    parser.add_argument(
        "--expected-count",
        type=int,
        help="Abort if the encrypted-token row count differs from this value.",
    )
    args = parser.parse_args()

    if args.apply and args.confirm != CONFIRMATION_PHRASE:
        parser.error(f"--apply requires --confirm {CONFIRMATION_PHRASE}")
    if args.apply and args.expected_count is None:
        parser.error("--apply requires --expected-count")
    if args.expected_count is not None and args.expected_count < 0:
        parser.error("--expected-count cannot be negative")

    fernets = get_project_secrets_fernets()
    if len(fernets) != 2:
        raise RuntimeError(
            "Configure distinct primary and previous project secrets keys before auditing rotation"
        )
    primary = fernets[0]
    key_ring = MultiFernet(fernets)

    if not args.apply:
        with engine.connect() as conn:
            rows = _load_rows(conn, for_update=False)
        audit = _audit_rows(rows, primary=primary, key_ring=key_ring)
        _print_report("dry-run", audit)
        if args.expected_count is not None and audit.total != args.expected_count:
            return 2
        return 3 if audit.invalid else 0

    with engine.begin() as conn:
        rows = _load_rows(conn, for_update=True)
        audit_before = _audit_rows(rows, primary=primary, key_ring=key_ring)
        if audit_before.total != args.expected_count:
            raise RuntimeError(
                f"Expected {args.expected_count} encrypted tokens, found {audit_before.total}"
            )
        if audit_before.invalid:
            raise RuntimeError(
                f"Refusing rotation: {audit_before.invalid} token(s) are not decryptable"
            )

        rotated_count = 0
        for row in rows:
            token = str(row["api_token_encrypted"])
            try:
                primary.decrypt(token.encode())
                continue
            except InvalidToken:
                pass

            rotated = key_ring.rotate(token.encode()).decode()
            primary.decrypt(rotated.encode())
            conn.execute(
                text(
                    """
                    UPDATE project_marketplaces
                    SET api_token_encrypted = :rotated_token,
                        updated_at = now()
                    WHERE id = :row_id
                    """
                ),
                {
                    "rotated_token": rotated,
                    "row_id": int(row["id"]),
                },
            )
            rotated_count += 1

        rows_after = _load_rows(conn, for_update=False)
        audit_after = _audit_rows(rows_after, primary=primary, key_ring=key_ring)
        if audit_after.total != args.expected_count:
            raise RuntimeError("Encrypted-token row count changed; transaction will roll back")
        if audit_after.invalid or audit_after.requires_rotation:
            raise RuntimeError("Post-rotation verification failed; transaction will roll back")
        if rotated_count != audit_before.requires_rotation:
            raise RuntimeError("Rotated-row count mismatch; transaction will roll back")

    _print_report("applied", audit_after)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

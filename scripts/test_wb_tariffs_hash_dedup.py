"""Simple checks for WB tariffs payload hash and dedup behaviour.

Run manually:
  python -m scripts.test_wb_tariffs_hash_dedup
"""

from app.db_marketplace_tariffs import _compute_payload_hash


def main() -> None:
    payload1 = {"a": 1, "b": [1, 2, 3]}
    payload2 = {"b": [1, 2, 3], "a": 1}  # different key order

    h1 = _compute_payload_hash(payload1)
    h2 = _compute_payload_hash(payload2)

    assert h1 == h2, "Hashes must be equal for semantically same JSON"

    payload3 = {"a": 2, "b": [1, 2, 3]}
    h3 = _compute_payload_hash(payload3)

    assert h1 != h3, "Hashes must differ when payload changes"

    print("WB tariffs hash/dedup tests passed")


if __name__ == "__main__":
    main()


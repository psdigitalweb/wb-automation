import json
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.engine import Engine


def ensure_schema(engine: Engine) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS tariffs_commission (
        id SERIAL PRIMARY KEY,
        fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        data JSONB NOT NULL
    );
    CREATE TABLE IF NOT EXISTS tariffs_box (
        id SERIAL PRIMARY KEY,
        fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        data JSONB NOT NULL
    );
    CREATE TABLE IF NOT EXISTS tariffs_pallet (
        id SERIAL PRIMARY KEY,
        fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        data JSONB NOT NULL
    );
    CREATE TABLE IF NOT EXISTS tariffs_return (
        id SERIAL PRIMARY KEY,
        fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        data JSONB NOT NULL
    );
    
    -- GIN indexes for JSONB data
    CREATE INDEX IF NOT EXISTS idx_tariffs_commission_data ON tariffs_commission USING gin (data);
    CREATE INDEX IF NOT EXISTS idx_tariffs_box_data ON tariffs_box USING gin (data);
    CREATE INDEX IF NOT EXISTS idx_tariffs_pallet_data ON tariffs_pallet USING gin (data);
    CREATE INDEX IF NOT EXISTS idx_tariffs_return_data ON tariffs_return USING gin (data);
    """
    with engine.begin() as conn:
        conn.execute(text(ddl))


def insert_commission(engine: Engine, payload: Dict[str, Any]) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            text("INSERT INTO tariffs_commission(data) VALUES (cast(:data as jsonb)) RETURNING id"),
            {"data": json.dumps(payload, ensure_ascii=False)}
        )
        return result.fetchone()[0]


def insert_box(engine: Engine, payload: Dict[str, Any]) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            text("INSERT INTO tariffs_box(data) VALUES (cast(:data as jsonb)) RETURNING id"),
            {"data": json.dumps(payload, ensure_ascii=False)}
        )
        return result.fetchone()[0]


def insert_pallet(engine: Engine, payload: Dict[str, Any]) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            text("INSERT INTO tariffs_pallet(data) VALUES (cast(:data as jsonb)) RETURNING id"),
            {"data": json.dumps(payload, ensure_ascii=False)}
        )
        return result.fetchone()[0]


def insert_return(engine: Engine, payload: Dict[str, Any]) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            text("INSERT INTO tariffs_return(data) VALUES (cast(:data as jsonb)) RETURNING id"),
            {"data": json.dumps(payload, ensure_ascii=False)}
        )
        return result.fetchone()[0]



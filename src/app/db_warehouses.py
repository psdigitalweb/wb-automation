import json
import logging
from typing import Any, Dict, List, Tuple

from sqlalchemy import text
from sqlalchemy.engine import Engine


def ensure_schema(engine: Engine) -> None:
    """Create tables, indexes and VIEW if they don't exist"""
    ddl = """
    -- Table for WB offices
    CREATE TABLE IF NOT EXISTS wb_offices (
        id BIGINT PRIMARY KEY,
        name TEXT NOT NULL,
        address TEXT,
        city TEXT,
        longitude DOUBLE PRECISION,
        latitude DOUBLE PRECISION,
        cargo_type INTEGER,
        delivery_type INTEGER,
        federal_district TEXT,
        selected BOOLEAN,
        data JSONB NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- Table for seller warehouses
    CREATE TABLE IF NOT EXISTS seller_warehouses (
        id BIGINT PRIMARY KEY,
        name TEXT NOT NULL,
        office_id BIGINT,
        cargo_type INTEGER,
        delivery_type INTEGER,
        is_deleting BOOLEAN,
        is_processing BOOLEAN,
        data JSONB NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- Indexes for wb_offices
    CREATE INDEX IF NOT EXISTS idx_wb_offices_city ON wb_offices(city);
    CREATE INDEX IF NOT EXISTS idx_wb_offices_data ON wb_offices USING GIN (data);

    -- Indexes for seller_warehouses
    CREATE INDEX IF NOT EXISTS idx_seller_wh_office_id ON seller_warehouses(office_id);
    CREATE INDEX IF NOT EXISTS idx_seller_wh_data ON seller_warehouses USING GIN (data);

    -- VIEW for joined warehouses data
    CREATE OR REPLACE VIEW v_warehouses_all AS
    SELECT 
        sw.id AS warehouse_id,
        sw.name AS warehouse_name,
        sw.office_id,
        sw.cargo_type AS wh_cargo_type,
        sw.delivery_type AS wh_delivery_type,
        sw.is_deleting,
        sw.is_processing,
        sw.updated_at AS wh_updated_at,
        wo.name AS office_name,
        wo.city,
        wo.address,
        wo.federal_district,
        wo.longitude,
        wo.latitude,
        wo.cargo_type AS office_cargo_type,
        wo.delivery_type AS office_delivery_type,
        wo.selected,
        wo.updated_at AS office_updated_at
    FROM seller_warehouses sw
    LEFT JOIN wb_offices wo ON sw.office_id = wo.id;
    """
    with engine.begin() as conn:
        conn.execute(text(ddl))


def upsert_wb_offices(engine: Engine, offices: List[Dict[str, Any]]) -> Tuple[int, int]:
    """Upsert offices data, returns (inserted, updated)"""
    if not offices:
        return 0, 0

    logger = logging.getLogger("wb.db.warehouses")
    inserted = 0
    updated = 0

    # Process in batches of 1000
    batch_size = 1000
    for i in range(0, len(offices), batch_size):
        batch = offices[i:i + batch_size]
        
        for office in batch:
            # Map fields from API response to DB columns
            office_id = office.get("id")
            if not office_id:
                continue
                
            name = office.get("name", "")
            address = office.get("address")
            city = office.get("city")
            longitude = office.get("longitude")
            latitude = office.get("latitude")
            cargo_type = office.get("cargoType")
            delivery_type = office.get("deliveryType")
            federal_district = office.get("federalDistrict")
            selected = office.get("selected")
            
            # Serialize full object for data column
            data_json = json.dumps(office, ensure_ascii=False)
            
            with engine.begin() as conn:
                # Check if record exists and if it needs updating
                existing = conn.execute(
                    text("""
                        SELECT name, address, city, longitude, latitude, cargo_type, 
                               delivery_type, federal_district, selected, data
                        FROM wb_offices WHERE id = :id
                    """),
                    {"id": office_id}
                ).fetchone()
                
                if existing:
                    # Check if any fields changed
                    if (existing.name != name or 
                        existing.address != address or 
                        existing.city != city or
                        existing.longitude != longitude or
                        existing.latitude != latitude or
                        existing.cargo_type != cargo_type or
                        existing.delivery_type != delivery_type or
                        existing.federal_district != federal_district or
                        existing.selected != selected or
                        existing.data != data_json):
                        
                        # Update record
                        conn.execute(
                            text("""
                                UPDATE wb_offices SET
                                    name = :name,
                                    address = :address,
                                    city = :city,
                                    longitude = :longitude,
                                    latitude = :latitude,
                                    cargo_type = :cargo_type,
                                    delivery_type = :delivery_type,
                                    federal_district = :federal_district,
                                    selected = :selected,
                                    data = cast(:data as jsonb),
                                    updated_at = NOW()
                                WHERE id = :id
                            """),
                            {
                                "id": office_id,
                                "name": name,
                                "address": address,
                                "city": city,
                                "longitude": longitude,
                                "latitude": latitude,
                                "cargo_type": cargo_type,
                                "delivery_type": delivery_type,
                                "federal_district": federal_district,
                                "selected": selected,
                                "data": data_json
                            }
                        )
                        updated += 1
                else:
                    # Insert new record
                    conn.execute(
                        text("""
                            INSERT INTO wb_offices (
                                id, name, address, city, longitude, latitude,
                                cargo_type, delivery_type, federal_district, selected, data
                            ) VALUES (
                                :id, :name, :address, :city, :longitude, :latitude,
                                :cargo_type, :delivery_type, :federal_district, :selected, cast(:data as jsonb)
                            )
                        """),
                        {
                            "id": office_id,
                            "name": name,
                            "address": address,
                            "city": city,
                            "longitude": longitude,
                            "latitude": latitude,
                            "cargo_type": cargo_type,
                            "delivery_type": delivery_type,
                            "federal_district": federal_district,
                            "selected": selected,
                            "data": data_json
                        }
                    )
                    inserted += 1

    logger.info("wb_offices upsert inserted=%s updated=%s", inserted, updated)
    return inserted, updated


def upsert_seller_warehouses(engine: Engine, warehouses: List[Dict[str, Any]]) -> Tuple[int, int]:
    """Upsert seller warehouses data, returns (inserted, updated)"""
    if not warehouses:
        return 0, 0

    logger = logging.getLogger("wb.db.warehouses")
    inserted = 0
    updated = 0

    # Process in batches of 1000
    batch_size = 1000
    for i in range(0, len(warehouses), batch_size):
        batch = warehouses[i:i + batch_size]
        
        for warehouse in batch:
            # Map fields from API response to DB columns
            warehouse_id = warehouse.get("id")
            if not warehouse_id:
                continue
                
            name = warehouse.get("name", "")
            office_id = warehouse.get("officeId")
            cargo_type = warehouse.get("cargoType")
            delivery_type = warehouse.get("deliveryType")
            is_deleting = warehouse.get("isDeleting")
            is_processing = warehouse.get("isProcessing")
            
            # Serialize full object for data column
            data_json = json.dumps(warehouse, ensure_ascii=False)
            
            with engine.begin() as conn:
                # Check if record exists and if it needs updating
                existing = conn.execute(
                    text("""
                        SELECT name, office_id, cargo_type, delivery_type, 
                               is_deleting, is_processing, data
                        FROM seller_warehouses WHERE id = :id
                    """),
                    {"id": warehouse_id}
                ).fetchone()
                
                if existing:
                    # Check if any fields changed
                    if (existing.name != name or 
                        existing.office_id != office_id or
                        existing.cargo_type != cargo_type or
                        existing.delivery_type != delivery_type or
                        existing.is_deleting != is_deleting or
                        existing.is_processing != is_processing or
                        existing.data != data_json):
                        
                        # Update record
                        conn.execute(
                            text("""
                                UPDATE seller_warehouses SET
                                    name = :name,
                                    office_id = :office_id,
                                    cargo_type = :cargo_type,
                                    delivery_type = :delivery_type,
                                    is_deleting = :is_deleting,
                                    is_processing = :is_processing,
                                    data = cast(:data as jsonb),
                                    updated_at = NOW()
                                WHERE id = :id
                            """),
                            {
                                "id": warehouse_id,
                                "name": name,
                                "office_id": office_id,
                                "cargo_type": cargo_type,
                                "delivery_type": delivery_type,
                                "is_deleting": is_deleting,
                                "is_processing": is_processing,
                                "data": data_json
                            }
                        )
                        updated += 1
                else:
                    # Insert new record
                    conn.execute(
                        text("""
                            INSERT INTO seller_warehouses (
                                id, name, office_id, cargo_type, delivery_type,
                                is_deleting, is_processing, data
                            ) VALUES (
                                :id, :name, :office_id, :cargo_type, :delivery_type,
                                :is_deleting, :is_processing, cast(:data as jsonb)
                            )
                        """),
                        {
                            "id": warehouse_id,
                            "name": name,
                            "office_id": office_id,
                            "cargo_type": cargo_type,
                            "delivery_type": delivery_type,
                            "is_deleting": is_deleting,
                            "is_processing": is_processing,
                            "data": data_json
                        }
                    )
                    inserted += 1

    logger.info("seller_warehouses upsert inserted=%s updated=%s", inserted, updated)
    return inserted, updated
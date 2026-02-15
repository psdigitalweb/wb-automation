"""API endpoints for application settings."""

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from sqlalchemy import text

from app.db import engine

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


class BrandUrlRequest(BaseModel):
    url: str


class BrandUrlResponse(BaseModel):
    url: str


@router.get("/frontend-prices/brand-url")
async def get_frontend_prices_brand_url() -> BrandUrlResponse:
    """Get frontend prices brand base URL from settings."""
    sql = text("""
        SELECT value->>'url' AS url
        FROM app_settings
        WHERE key = 'frontend_prices.brand_base_url'
    """)
    
    try:
        with engine.connect() as conn:
            result = conn.execute(sql).scalar_one_or_none()
            if not result:
                # Return default if not found
                return BrandUrlResponse(url="")
            return BrandUrlResponse(url=result)
    except Exception as e:
        print(f"get_frontend_prices_brand_url: error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get brand URL: {e}")


BRAND_ID_PLACEHOLDER = "{brand_id}"


@router.put("/frontend-prices/brand-url")
async def update_frontend_prices_brand_url(request: BrandUrlRequest = Body(...)) -> dict:
    """Update frontend prices brand base URL in settings. URL must contain placeholder {brand_id}."""
    if not request.url or not request.url.strip():
        raise HTTPException(status_code=400, detail="URL cannot be empty")
    if BRAND_ID_PLACEHOLDER not in request.url:
        raise HTTPException(
            status_code=400,
            detail="URL must contain placeholder {brand_id}. Example: https://catalog.wb.ru/brands/v4/catalog?brand={brand_id}&page=1",
        )

    sql = text("""
        INSERT INTO app_settings (key, value, updated_at)
        VALUES ('frontend_prices.brand_base_url', jsonb_build_object('url', :url), now())
        ON CONFLICT (key) 
        DO UPDATE SET 
            value = jsonb_build_object('url', :url),
            updated_at = now()
    """)
    
    try:
        with engine.begin() as conn:
            conn.execute(sql, {"url": request.url.strip()})
        return {"status": "ok", "url": request.url.strip()}
    except Exception as e:
        print(f"update_frontend_prices_brand_url: error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update brand URL: {e}")


@router.get("/frontend-prices/sleep-ms")
async def get_frontend_prices_sleep_ms() -> dict:
    """Get frontend prices sleep_ms setting."""
    sql = text("""
        SELECT value->>'value' AS value
        FROM app_settings
        WHERE key = 'frontend_prices.sleep_ms'
    """)
    
    try:
        with engine.connect() as conn:
            result = conn.execute(sql).scalar_one_or_none()
            if not result:
                return {"value": 800}  # Default
            try:
                return {"value": int(result)}
            except (ValueError, TypeError):
                return {"value": 800}
    except Exception as e:
        print(f"get_frontend_prices_sleep_ms: error: {e}")
        return {"value": 800}  # Default on error


@router.put("/frontend-prices/sleep-ms")
async def update_frontend_prices_sleep_ms(value: int = Body(..., embed=True)) -> dict:
    """Update frontend prices sleep_ms setting."""
    if value < 0:
        raise HTTPException(status_code=400, detail="sleep_ms must be >= 0")
    
    sql = text("""
        INSERT INTO app_settings (key, value, updated_at)
        VALUES ('frontend_prices.sleep_ms', jsonb_build_object('value', :value), now())
        ON CONFLICT (key) 
        DO UPDATE SET 
            value = jsonb_build_object('value', :value),
            updated_at = now()
    """)
    
    try:
        with engine.begin() as conn:
            conn.execute(sql, {"value": value})
        return {"status": "ok", "value": value}
    except Exception as e:
        print(f"update_frontend_prices_sleep_ms: error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update sleep_ms: {e}")

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


@router.get("/frontend-prices/brand-url", response_model=BrandUrlResponse)
async def get_frontend_prices_brand_url():
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
                raise HTTPException(
                    status_code=404,
                    detail="frontend_prices.brand_base_url not configured"
                )
            return {"url": result}
    except HTTPException:
        raise
    except Exception as e:
        print(f"get_frontend_prices_brand_url: error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get setting: {str(e)}"
        )


@router.put("/frontend-prices/brand-url", response_model=BrandUrlResponse)
async def update_frontend_prices_brand_url(request: BrandUrlRequest = Body(...)):
    """Update frontend prices brand base URL in settings."""
    import json
    value_json = json.dumps({"url": request.url})
    
    sql = text("""
        INSERT INTO app_settings (key, value, updated_at)
        VALUES ('frontend_prices.brand_base_url', CAST(:value AS jsonb), now())
        ON CONFLICT (key) 
        DO UPDATE SET 
            value = CAST(:value AS jsonb),
            updated_at = now()
        RETURNING value->>'url' AS url
    """)
    
    try:
        with engine.begin() as conn:
            result = conn.execute(sql, {"value": value_json}).scalar_one_or_none()
            if not result:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to update setting"
                )
            return {"url": result}
    except HTTPException:
        raise
    except Exception as e:
        print(f"update_frontend_prices_brand_url: error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update setting: {str(e)}"
        )


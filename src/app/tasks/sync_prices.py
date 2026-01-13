from decimal import Decimal, ROUND_HALF_UP
from .. import settings
from ..db import SessionLocal
from ..models import Product, PriceSnapshot
import asyncio
from ..wb.client import WBClient
from ..celery_app import celery_app

# Import tasks to register them
from . import frontend_prices  # noqa: F401

def round_to_49_99(value: Decimal) -> Decimal:
    v = int(value)
    base = (v // 100) * 100
    candidates = [base + 49, base + 99, base + 149, base + 199]
    best = min(candidates, key=lambda x: abs(x - v))
    return Decimal(best)

@celery_app.task
def sync_prices():
    db = SessionLocal()
    try:
        nm_ids = [row[0] for row in db.query(Product.nm_id).all()]
        if not nm_ids:
            return "no products"

        async def run():
            client = WBClient()
            data = await client.get_prices(nm_ids)
            for nm in nm_ids:
                raw = data.get(nm, {})
                wb_price = Decimal(str(raw.get("price", 0)))
                wb_discount = Decimal(str(raw.get("discount", 0)))
                spp = Decimal("0")
                customer_price = (wb_price * (Decimal(1) - wb_discount/Decimal(100))) * (Decimal(1) - spp/Decimal(100))
                customer_price = customer_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                rrc = round_to_49_99(wb_price)
                db.add(PriceSnapshot(nm_id=nm, wb_price=wb_price, wb_discount=wb_discount,
                                     spp=spp, customer_price=customer_price, rrc=rrc))
            db.commit()
        asyncio.run(run())
        return f"snapshots: {len(nm_ids)}"
    finally:
        db.close()

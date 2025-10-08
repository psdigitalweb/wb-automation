from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from . import settings
from .db import Base, engine, SessionLocal
from .models import Product, PriceSnapshot
from .tasks.sync_prices import sync_prices

app = FastAPI(title="WB Automation")

# создаём таблицы, если их нет
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@app.post("/sync/prices")
def sync_prices_now():
    res = sync_prices.delay()
    return {"task_id": res.id}

@app.get("/prices/latest")
def latest_prices(nm_id: int, db: Session = Depends(get_db)):
    snap = db.query(PriceSnapshot).filter(PriceSnapshot.nm_id == nm_id)\
             .order_by(PriceSnapshot.created_at.desc()).first()
    if not snap:
        return {"nm_id": nm_id, "status": "no data"}
    return {
        "nm_id": nm_id,
        "wb_price": str(snap.wb_price),
        "wb_discount": str(snap.wb_discount),
        "spp": str(snap.spp),
        "customer_price": str(snap.customer_price),
        "rrc": str(snap.rrc),
        "ts": snap.created_at.isoformat()
    }

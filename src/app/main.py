from fastapi import FastAPI
from sqlalchemy import create_engine, text
import os

from app.ingest_products import router as ingest_router
from app.ingest_stocks import router as ingest_stocks_router, stocks_router
from app.ingest_supplier_stocks import router as ingest_supplier_stocks_router, supplier_stocks_router
from app.api_prices import router as prices_router

app = FastAPI(title="WB Automation")

app.include_router(ingest_router)
app.include_router(ingest_stocks_router)
app.include_router(stocks_router)
app.include_router(ingest_supplier_stocks_router)
app.include_router(supplier_stocks_router)
app.include_router(prices_router)

# читаем URL прямо из окружения
DATABASE_URL = os.getenv("DATABASE_URL")
# Явно указываем использование psycopg2 драйвера
if DATABASE_URL:
    if "psycopg://" in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("psycopg://", "psycopg2://", 1)
    elif DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
    elif DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

@app.get("/api/v1/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}

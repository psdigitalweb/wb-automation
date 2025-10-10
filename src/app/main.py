from fastapi import FastAPI
from sqlalchemy import create_engine, text
import os

app = FastAPI(title="WB Automation")

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

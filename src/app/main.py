from fastapi import FastAPI
from sqlalchemy import create_engine, text
import os

app = FastAPI(title="WB Automation")

# читаем URL прямо из окружения
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

@app.get("/api/v1/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}

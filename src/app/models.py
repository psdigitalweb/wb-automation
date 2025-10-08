from sqlalchemy import Column, Integer, String, Numeric, DateTime
from sqlalchemy.sql import func
from .db import Base

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    nm_id = Column(Integer, unique=True, index=True, nullable=False)
    vendor_code = Column(String(64), index=True)
    category = Column(String(128))

class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"
    id = Column(Integer, primary_key=True)
    nm_id = Column(Integer, index=True, nullable=False)
    wb_price = Column(Numeric(12,2))
    wb_discount = Column(Numeric(5,2))
    spp = Column(Numeric(5,2))
    customer_price = Column(Numeric(12,2))
    rrc = Column(Numeric(12,2))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

from app.db import engine
from sqlalchemy import text

conn = engine.connect()
result = conn.execute(text("SELECT COUNT(*) FROM v_article_base"))
total = result.scalar()
print(f"Total rows: {total}")

result2 = conn.execute(text("SELECT * FROM v_article_base LIMIT 1"))
row = result2.fetchone()
if row:
    print(f"Has data: True")
    print(f"Row type: {type(row)}")
    if hasattr(row, '_mapping'):
        print(f"Keys: {list(row._mapping.keys())}")
else:
    print("Has data: False")
conn.close()

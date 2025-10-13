# WB Automation

Python 3.12, FastAPI, SQLAlchemy, Postgres, Docker Compose project for WB automation.

## Setup

1. Create `.env` file with required variables:
```bash
# Database
DATABASE_URL=postgresql+psycopg2://wb:wbpassword@postgres:5432/wb

# WB API (required)
WB_API_TOKEN=your_token_here
WB_API_BASE=https://common-api.wildberries.ru

# Logging
LOG_LEVEL=INFO

# Optional API settings
WB_API_MIN_INTERVAL=0.5
WB_API_MAX_RETRIES=7
WB_API_TIMEOUT=20

# Box tariffs date (optional)
WB_TARIFFS_BOX_DATE=2025-10-10  # if not set, uses current date

# Pallet tariffs date (optional)
WB_TARIFFS_PALLET_DATE=2025-10-10  # if not set, uses current date

# Return tariffs date (optional)
WB_TARIFFS_RETURN_DATE=2025-10-10  # if not set, uses current date
```

2. Start services:
```bash
docker compose up -d --build
```

## Tariffs Ingest

Collects and stores WB tariffs data in Postgres with dry-run, retries, and logging.

### Endpoints

- `/api/v1/tariffs/commission` - Commission tariffs
- `/api/v1/tariffs/box` - Box tariffs (requires `date` parameter, format YYYY-MM-DD)
- `/api/v1/tariffs/pallet` - Pallet tariffs (requires `date` parameter, format YYYY-MM-DD)
- `/api/v1/tariffs/return` - Return tariffs (requires `date` parameter, format YYYY-MM-DD)

### Commands

**Dry run (no DB writes):**
```bash
docker compose exec api sh -lc "python -m app.ingest_tariffs --dry-run"
```

**Full ingest (writes to DB):**
```bash
docker compose exec api sh -lc "python -m app.ingest_tariffs"
```

**Specific endpoints:**
```bash
docker compose exec api sh -lc "python -m app.ingest_tariffs --dry-run --only pallet"
docker compose exec api sh -lc "python -m app.ingest_tariffs --only commission --only box"
```

### Database Tables

- `tariffs_commission` - Commission tariff data
- `tariffs_box` - Box tariff data
- `tariffs_pallet` - Pallet tariff data
- `tariffs_return` - Return tariff data

Each table has: `id` (serial pk), `fetched_at` (timestamptz), `data` (jsonb).

### Troubleshooting

**401/403 errors:**
- Check `WB_API_TOKEN` is valid and not expired

**404 errors:**
- Verify `WB_API_BASE` is correct (should be `https://common-api.wildberries.ru`)
- Check endpoint paths are correct

**429 rate limit:**
- Increase `WB_API_MIN_INTERVAL` (default 0.3s)
- Increase `WB_API_MAX_RETRIES` (default 5)

**Database issues:**
- Check `DATABASE_URL` is correct
- Ensure `postgres` container is running
- Verify connection with: `docker compose exec api sh -lc "python -c 'from app.main import engine; print(engine.connect())'"`

### Logs

The ingest process logs:
- Request attempts with retry info
- Success/failure status per endpoint
- Final summary with bytes processed and timing
- Error details for debugging

Example log output:
```
INFO wb.tariffs: Using date parameter: 2025-10-10
INFO wb.tariffs: Using date parameter for pallet: 2025-10-10
INFO wb.tariffs: Using date parameter for return: 2025-10-10
INFO wb.tariffs: GET https://common-api.wildberries.ru/api/v1/tariffs/commission try=1/5, sleep=0.0s
INFO wb.tariffs: OK /api/v1/tariffs/commission bytes=1234
INFO wb.ingest.tariffs: Summary: commission=ok(1234), box=ok(5678), pallet=ok(9012), return=ok(3456); dry_run=False; elapsed=2.5s
```

### Date Parameters

The `/api/v1/tariffs/box`, `/api/v1/tariffs/pallet`, and `/api/v1/tariffs/return` endpoints require mandatory `date` parameters in YYYY-MM-DD format:

- If `WB_TARIFFS_BOX_DATE` is set in `.env`, that date will be used for box tariffs
- If `WB_TARIFFS_PALLET_DATE` is set in `.env`, that date will be used for pallet tariffs
- If `WB_TARIFFS_RETURN_DATE` is set in `.env`, that date will be used for return tariffs
- If not set, the current date will be automatically used
- The date parameters are logged before each request for transparency

## Warehouses Ingest

Collects and stores WB warehouses and offices data in Postgres with dry-run, retries, and logging.

### Endpoints

- `/api/v3/offices` - WB offices data
- `/api/v3/warehouses` - Seller warehouses data

### Commands

**Dry run (no DB writes):**
```bash
docker compose exec api sh -lc "python -m app.ingest_warehouses --dry-run"
```

**Full ingest (writes to DB):**
```bash
docker compose exec api sh -lc "python -m app.ingest_warehouses"
```

**Specific data types:**
```bash
docker compose exec api sh -lc "python -m app.ingest_warehouses --dry-run --only offices"
docker compose exec api sh -lc "python -m app.ingest_warehouses --only warehouses"
```

### Database Tables

- `wb_offices` - WB offices with location and metadata
- `seller_warehouses` - Seller warehouses linked to offices
- `v_warehouses_all` - VIEW joining warehouses with office data

### Environment Variables

```bash
# WB API (required)
WB_API_TOKEN=your_token_here

# API settings
WB_API_MIN_INTERVAL=0.2
WB_API_MAX_RETRIES=3
WB_API_TIMEOUT=15
LOG_LEVEL=INFO
```

### Database Tables

- `wb_offices` - WB offices with location and metadata
- `seller_warehouses` - Seller warehouses linked to offices  
- `v_warehouses_all` - VIEW joining warehouses with office data

### Environment Variables

```bash
# WB API (required) - supports both variants for backward compatibility
WB_API_TOKEN=your_token_here  # preferred
# WB_TOKEN=your_token_here    # legacy alias

# API settings
WB_API_MIN_INTERVAL=0.2
WB_API_MAX_RETRIES=3
WB_API_TIMEOUT=15
LOG_LEVEL=INFO
```

### Logs

Example log output:
```
INFO wb.api: GET /api/v3/offices try=1/3
INFO wb.api: OK /api/v3/offices bytes=1234
INFO wb.ingest.warehouses: fetched offices=123
INFO wb.db.warehouses: wb_offices upsert inserted=120 updated=3
INFO wb.ingest.warehouses: dry-run warehouses count=57
```

## Deployment

### Environment Setup

Create `.env` file in the project root with required variables:

```bash
# Database
DATABASE_URL=postgresql+psycopg2://wb:wbpassword@postgres:5432/wb

# WB API (required) - supports both variants for backward compatibility
WB_API_TOKEN=your_token_here  # preferred
# WB_TOKEN=your_token_here    # legacy alias

# API settings
WB_API_MIN_INTERVAL=0.2
WB_API_MAX_RETRIES=3
WB_API_TIMEOUT=15
LOG_LEVEL=INFO
```

### Deploy to Server

1. **Connect to server:**
```bash
ssh user@server
cd /path/to/wb-automation
```

2. **Run deployment script:**
```bash
bash scripts/deploy_pull_restart.sh
```

The script will:
- Fetch latest changes from git
- Switch to `p3/wb-ingest-warehouses` branch
- Pull latest changes
- Update Docker images
- Rebuild and restart services
- Show service status

### Testing Deployment

**Check environment variables:**
```bash
docker compose exec api sh -lc "python -c 'import os; print(\"WB_API_TOKEN:\", \"SET\" if os.getenv(\"WB_API_TOKEN\") else \"MISSING\")'"
```

**Test warehouses ingest (dry-run):**
```bash
docker compose exec api sh -lc "python -m app.ingest_warehouses --dry-run"
```

**Run full warehouses ingest:**
```bash
docker compose exec api sh -lc "python -m app.ingest_warehouses"
```

**Check service logs:**
```bash
docker compose logs api
docker compose logs postgres
```

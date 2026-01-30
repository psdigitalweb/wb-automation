from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError
import os
import logging

from app.ingest_products import router as ingest_router
from app.ingest_stocks import router as ingest_stocks_router, stocks_router
from app.ingest_supplier_stocks import router as ingest_supplier_stocks_router, supplier_stocks_router
from app.ingest_prices import router as ingest_prices_router
from app.api_prices import router as prices_router
from app.ingest_frontend_prices import router as ingest_frontend_prices_router
from app.api_frontend_prices import router as frontend_prices_router
from app.api_settings import router as settings_router
from app.api_dashboard import router as dashboard_router
from app.api_articles import router as articles_router
from app.api_rrp import router as rrp_router
from app.api_wb_price_discrepancies import router as wb_price_discrepancies_router
from app.api_wb_stock_without_photos import router as wb_stock_without_photos_router
from app.api_articles_base import router as articles_base_router
from app.routers.auth import router as auth_router
from app.routers.admin_tasks import router as admin_tasks_router
from app.routers.admin_marketplaces import router as admin_marketplaces_router
from app.routers.admin_users import router as admin_users_router
from app.routers.admin_project_members import router as admin_project_members_router
from app.routers.ingest_run import router as ingest_run_router
from app.routers.ingest import router as ingest_router
from app.routers.projects import router as projects_router
from app.routers.marketplaces import router as marketplaces_router
from app.routers.internal_data import router as internal_data_router
# Project-scoped proxy settings (frontend_prices)
from app.routers.project_proxy_settings import router as project_proxy_settings_router
# Import category import endpoints (they register on the same router)
import app.routers.internal_data_category_import  # noqa: F401
from app.routers.cogs import router as cogs_router
from app.routers.additional_costs import router as additional_costs_router
from app.routers.warehouse_labor import router as warehouse_labor_router
from app.routers.packaging import router as packaging_router
try:
    from app.routers.taxes import router as taxes_router
except Exception as e:
    raise
from app.api_example_protected import router as protected_router

app = FastAPI(title="E-com Core")

# Настройка CORS для работы с frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js dev server
        "http://localhost:80",    # Nginx proxy
        "http://localhost",       # Nginx proxy (без порта)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth router (public endpoints)
app.include_router(auth_router)

# Projects router (requires authentication and membership)
app.include_router(projects_router)

# Marketplaces router (requires authentication and membership)
app.include_router(marketplaces_router)

# Internal Data router (project-scoped)
app.include_router(internal_data_router)

# Project proxy settings router (project-scoped)
app.include_router(project_proxy_settings_router)

# COGS router (project-scoped)
app.include_router(cogs_router)

# Additional Costs router (project-scoped)
app.include_router(additional_costs_router)

# Warehouse Labor router (project-scoped)
app.include_router(warehouse_labor_router)
app.include_router(packaging_router)

# Taxes router (project-scoped)
try:
    app.include_router(taxes_router)
except Exception as e:
    raise

# Protected router (requires authentication)
app.include_router(protected_router)

# Admin tasks router (requires superuser)
app.include_router(admin_tasks_router)

# Admin marketplaces router (requires superuser)
app.include_router(admin_marketplaces_router)

# Admin users router (requires superuser)
app.include_router(admin_users_router)

# Admin project members router (requires superuser)
app.include_router(admin_project_members_router)

# Unified ingestion runner (requires authentication and membership)
app.include_router(ingest_run_router)

# Ingestion schedules & runs (cron-like)
app.include_router(ingest_router)

# Other routers
app.include_router(ingest_router)
app.include_router(ingest_stocks_router)
app.include_router(stocks_router)
app.include_router(ingest_supplier_stocks_router)
app.include_router(supplier_stocks_router)
app.include_router(ingest_prices_router)
app.include_router(prices_router)
app.include_router(ingest_frontend_prices_router)
app.include_router(frontend_prices_router)
app.include_router(settings_router)
app.include_router(dashboard_router)
app.include_router(articles_router)
app.include_router(rrp_router)
app.include_router(articles_base_router)
app.include_router(wb_price_discrepancies_router)
app.include_router(wb_stock_without_photos_router)

# Читаем URL из окружения или формируем из POSTGRES_* переменных
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Формируем из переменных окружения (используем settings для консистентности)
    from app import settings
    DATABASE_URL = settings.SQLALCHEMY_DATABASE_URL
else:
    # Явно указываем использование psycopg2 драйвера
    if "psycopg://" in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("psycopg://", "psycopg2://", 1)
    elif DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
    elif DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
    # Исправляем хост если указан неправильно (db -> postgres)
    DATABASE_URL = DATABASE_URL.replace("@db:", "@postgres:")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

logger = logging.getLogger(__name__)


@app.on_event("startup")
async def startup_event():
    """Initialize database schema and seed data on application startup.
    
    This runs AFTER the application starts, ensuring tables exist (from migrations)
    before attempting to seed data.
    
    Steps:
    1. Verifies PROJECT_SECRETS_KEY is set if encrypted tokens exist
    2. Runs bootstrap admin user if enabled (BOOTSTRAP_ADMIN=1) and users table is empty
    3. Runs full bootstrap if enabled (BOOTSTRAP_ENABLED=true)
       - Creates admin user (if ADMIN_PASSWORD is set)
       - Creates Legacy project
       - Seeds marketplaces
    """
    from app.bootstrap import run_bootstrap_on_startup, bootstrap_admin_user
    
    try:
        # Security check: PROJECT_SECRETS_KEY must be set if encrypted tokens exist
        from app.utils.secrets_encryption import has_project_secrets_key
        with engine.connect() as conn:
            # Check if any encrypted tokens exist
            result = conn.execute(text("""
                SELECT COUNT(*) FROM project_marketplaces 
                WHERE api_token_encrypted IS NOT NULL AND api_token_encrypted != ''
            """))
            encrypted_count = result.scalar_one()
            
            if encrypted_count > 0 and not has_project_secrets_key():
                logger.error("=" * 80)
                logger.error("SECURITY ERROR: Encrypted tokens found but PROJECT_SECRETS_KEY is not set!")
                logger.error(f"Found {encrypted_count} encrypted token(s) in project_marketplaces")
                logger.error("PROJECT_SECRETS_KEY must be set to decrypt tokens")
                logger.error("=" * 80)
            elif encrypted_count > 0:
                logger.info(f"Found {encrypted_count} encrypted token(s), PROJECT_SECRETS_KEY is available")
    except ProgrammingError:
        # Tables don't exist yet (migrations not applied)
        pass
    except Exception as e:
        logger.warning(f"Security check failed: {e}")

    try:
        # Security check: PROJECT_PROXY_SECRET_KEY must be set if encrypted proxy passwords exist
        from app.utils.proxy_secrets_encryption import has_project_proxy_secrets_key

        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM project_proxy_settings
                    WHERE password_encrypted IS NOT NULL AND password_encrypted != ''
                    """
                )
            )
            encrypted_count = result.scalar_one()
            if encrypted_count > 0 and not has_project_proxy_secrets_key():
                logger.error("=" * 80)
                logger.error(
                    "SECURITY WARNING: Encrypted proxy passwords found but PROJECT_PROXY_SECRET_KEY is not set!"
                )
                logger.error(f"Found {encrypted_count} encrypted password(s) in project_proxy_settings")
                logger.error("PROJECT_PROXY_SECRET_KEY must be set to use/decrypt proxy passwords")
                logger.error("=" * 80)
            elif encrypted_count > 0:
                logger.info(
                    f"Found {encrypted_count} encrypted proxy password(s), PROJECT_PROXY_SECRET_KEY is available"
                )
    except ProgrammingError:
        # Tables don't exist yet (migrations not applied)
        pass
    except Exception as e:
        logger.warning(f"Security check failed: {e}")
    
    try:
        # Bootstrap admin user if users table is empty (idempotent, safe)
        # Only runs if BOOTSTRAP_ADMIN=1 or CREATE_SUPERUSER_ON_START=true
        bootstrap_admin_user()
    except ProgrammingError as e:
        # Tables don't exist yet (migrations not applied)
        logger.debug(f"Bootstrap admin user skipped: users table not found yet: {e}")
    except Exception as e:
        # Other errors (connection issues, etc.)
        logger.warning(f"Bootstrap admin user error: {e}")
    
    try:
        # Run full bootstrap (idempotent: creates admin, Legacy project, seeds marketplaces)
        # Only runs if BOOTSTRAP_ENABLED=true
        run_bootstrap_on_startup()
    except ProgrammingError as e:
        # Tables don't exist yet (migrations not applied)
        logger.warning(f"Bootstrap skipped: tables not found yet: {e}")
    except Exception as e:
        # Other errors (connection issues, etc.)
        logger.error(f"Bootstrap error: {e}", exc_info=True)


@app.get("/api/v1/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}

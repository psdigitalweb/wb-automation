#!/usr/bin/env python3
"""Docker entrypoint script for API container.

Automatically runs migrations before starting uvicorn.
Uses PostgreSQL advisory lock to prevent concurrent migration execution.

Usage:
    python scripts/docker-entrypoint.py uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

import os
import sys
import time
import subprocess
from pathlib import Path

# PostgreSQL advisory lock ID for migrations (fixed value)
MIGRATION_LOCK_ID = 123456789

def wait_for_postgres(max_attempts=30, delay=1):
    """Wait for PostgreSQL to be ready.
    
    Tries to connect to PostgreSQL up to max_attempts times.
    Returns True on success, False only after all attempts are exhausted.
    """
    print("Waiting for PostgreSQL...")
    
    for attempt in range(1, max_attempts + 1):
        try:
            # Try to connect to database
            from app.db import engine
            from sqlalchemy import text
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print(f"PostgreSQL is ready (attempt {attempt}/{max_attempts})")
            return True
        except Exception as e:
            if attempt < max_attempts:
                print(f"  Attempt {attempt}/{max_attempts}: PostgreSQL not ready yet, waiting {delay}s...")
                time.sleep(delay)
            else:
                # Last attempt failed
                print(f"ERROR: PostgreSQL not ready after {max_attempts} attempts")
                print(f"  Error: {e}")
                return False
    
    # This should never be reached, but added for safety
    return False

def run_migrations():
    """Run Alembic migrations with advisory lock protection.
    
    Opens a single database connection, acquires advisory lock using pg_try_advisory_lock
    with explicit timeout, runs migrations, and releases lock before closing connection.
    Lock is held for entire migration duration.
    """
    from app.db import engine
    from sqlalchemy import text
    
    # Open connection that will be held for entire migration duration
    conn = None
    original_cwd = None
    
    try:
        # Wait for PostgreSQL first
        if not wait_for_postgres():
            return False
        
        # Open connection
        print(f"Acquiring migration lock (ID: {MIGRATION_LOCK_ID})...")
        conn = engine.connect()
        
        # Acquire advisory lock with explicit timeout (120 seconds)
        # Use pg_try_advisory_lock in a loop instead of blocking pg_advisory_lock
        lock_timeout = 120  # seconds
        lock_acquired = False
        start_time = time.time()
        
        while time.time() - start_time < lock_timeout:
            result = conn.execute(text(f"SELECT pg_try_advisory_lock({MIGRATION_LOCK_ID})"))
            if result.scalar_one():
                lock_acquired = True
                print("Acquired migration lock")
                break
            else:
                # Lock is held by another process, wait and retry
                time.sleep(2)
                elapsed = int(time.time() - start_time)
                if elapsed % 10 == 0:
                    print(f"  Waiting for migration lock... ({elapsed}s/{lock_timeout}s)")
        
        if not lock_acquired:
            print(f"ERROR: Failed to acquire migration lock within {lock_timeout} seconds")
            return False
        
        # Change to /app directory where alembic.ini is located (root of repo in container)
        original_cwd = os.getcwd()
        os.chdir("/app")
        
        # Set PYTHONPATH if not set (should be /app/src from docker-compose)
        env = os.environ.copy()
        if "PYTHONPATH" not in env:
            env["PYTHONPATH"] = "/app/src"
        
        # Run migrations while holding the lock
        print("Running alembic upgrade head...")
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            check=False,  # Don't raise, handle manually
            capture_output=True,  # Capture to show on error
            text=True,
            env=env
        )
        
        # Show output (stdout is usually empty for alembic, but show if present)
        if result.stdout:
            print(result.stdout)
        
        if result.returncode != 0:
            print(f"ERROR: Migration failed with exit code {result.returncode}")
            if result.stderr:
                print("STDERR:")
                print(result.stderr)
            return False
        
        print("Migration success")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Migrations failed: {e}")
        if hasattr(e, 'stdout') and e.stdout:
            print("STDOUT:", e.stdout)
        if hasattr(e, 'stderr') and e.stderr:
            print("STDERR:", e.stderr)
        return False
    except FileNotFoundError:
        print("ERROR: Alembic not found. Make sure alembic is installed.")
        return False
    except Exception as e:
        print(f"ERROR: Unexpected error during migrations: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Always release lock and close connection
        if conn is not None:
            try:
                conn.execute(text(f"SELECT pg_advisory_unlock({MIGRATION_LOCK_ID})"))
                print("Released migration lock")
            except Exception as e:
                print(f"WARNING: Failed to release migration lock: {e}")
            finally:
                conn.close()
        
        # Restore original directory
        if original_cwd is not None:
            os.chdir(original_cwd)

def main():
    """Main entrypoint."""
    print("=== Docker Entrypoint: Starting API ===")
    
    # Run migrations with lock protection (includes wait_for_postgres)
    # If migrations fail, exit with error code and don't start uvicorn
    if not run_migrations():
        print("ERROR: Migrations failed. Exiting without starting uvicorn.")
        sys.exit(1)
    
    # Execute the main command (everything after script name)
    if len(sys.argv) > 1:
        print(f"=== Executing: {' '.join(sys.argv[1:])} ===")
        os.execvp(sys.argv[1], sys.argv[1:])
    else:
        print("ERROR: No command provided, exiting")
        sys.exit(1)

if __name__ == "__main__":
    main()

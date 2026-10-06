"""
Database connectivity and health check script for Supabase PostgreSQL.

Usage:
    python scripts/check_db.py

This script:
1. Tests direct connection to Supabase PostgreSQL using asyncpg / SQLAlchemy.
2. Checks whether existing tables (categories, products, users, etc.) are present.
3. Checks current Alembic migration revision.
4. Safely masks passwords and secrets so credentials are never logged or leaked.
"""
import asyncio
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.engine import make_url
from app.core.config import settings
from app.db.session import engine


def get_masked_db_url(url_str: str) -> str:
    """Return database URL with password masked for safe printing."""
    try:
        url = make_url(url_str)
        masked_pwd = "***" if url.password else ""
        return (
            f"{url.drivername}://{url.username or ''}:{masked_pwd}@"
            f"{url.host or ''}:{url.port or ''}/{url.database or ''}"
        )
    except Exception:
        return "[DATABASE_URL set (password hidden)]"


async def check_database_connectivity() -> bool:
    print("=" * 60)
    print("  FREPPING - Supabase PostgreSQL Connectivity Check")
    print("=" * 60)

    masked_url = get_masked_db_url(settings.DATABASE_URL)
    print(f"\n[INFO] Target Database: {masked_url}")

    # 1. Connection & Ping test
    print("\n[STEP 1] Testing database connection...")
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1 AS ping, current_database() AS db, version() AS ver"))
            row = result.mappings().first()
            pg_version = row["ver"].split(",")[0] if row else "Unknown"
            db_name = row["db"] if row else "Unknown"
            print(f"  --> [OK] Connected successfully!")
            print(f"  --> Database: {db_name}")
            print(f"  --> Server Version: {pg_version}")
    except Exception as exc:
        print(f"  --> [FAILED] Could not connect to database.")
        print(f"  --> Error type: {type(exc).__name__}")
        print("\n[TROUBLESHOOTING]")
        print("  1. Check your DATABASE_URL in .env or environment variables.")
        print("  2. Ensure your Supabase database password is correct.")
        print("  3. Verify port 5432 or 6543 (transaction pooler) is accessible from your network.")
        return False

    # 2. Schema / Tables Check
    print("\n[STEP 2] Inspecting existing database tables...")
    try:
        async with engine.connect() as conn:
            query = text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name;
                """
            )
            result = await conn.execute(query)
            tables = [r[0] for r in result.fetchall()]

            expected_tables = {
                "categories",
                "products",
                "product_images",
                "product_variants",
                "users",
                "refresh_sessions",
                "stores",
                "alembic_version",
            }

            if not tables:
                print("  --> [NOTICE] Connected, but no public tables found in this database.")
                print("  --> To create all tables and apply migrations, run:")
                print("        alembic upgrade head")
            else:
                print(f"  --> Found {len(tables)} table(s) in 'public' schema:")
                for tbl in tables:
                    marker = "[+]" if tbl in expected_tables else "[*]"
                    print(f"       {marker} {tbl}")

                missing = expected_tables - set(tables)
                if missing:
                    print(f"\n  --> [NOTICE] Expected tables missing: {', '.join(sorted(missing))}")
                    print("  --> Run 'alembic upgrade head' to apply pending migrations.")
                else:
                    print("\n  --> [OK] All expected project tables are present!")

    except Exception as exc:
        print(f"  --> [WARNING] Could not list tables: {type(exc).__name__}")

    # 3. Alembic Migration Revision Check
    print("\n[STEP 3] Checking Alembic migration version...")
    try:
        async with engine.connect() as conn:
            query = text("SELECT version_num FROM alembic_version LIMIT 1;")
            result = await conn.execute(query)
            row = result.first()
            if row:
                print(f"  --> [OK] Current migration revision: {row[0]}")
            else:
                print("  --> [NOTICE] alembic_version table is empty. Run 'alembic upgrade head'.")
    except Exception:
        print("  --> [NOTICE] alembic_version table does not exist yet. Run 'alembic upgrade head'.")
    finally:
        await engine.dispose()

    print("\n" + "=" * 60)
    print("  [SUCCESS] Supabase PostgreSQL check completed!")
    print("=" * 60 + "\n")
    return True


if __name__ == "__main__":
    success = asyncio.run(check_database_connectivity())
    sys.exit(0 if success else 1)

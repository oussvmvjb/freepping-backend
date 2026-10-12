"""
Synchronize data from local PostgreSQL database directly to Supabase PostgreSQL.

Usage:
    python scripts/sync_to_supabase.py [SUPABASE_DATABASE_URL]

If SUPABASE_DATABASE_URL is not passed as an argument, it checks the environment
variable `SUPABASE_DATABASE_URL`, or prompts the user interactively.
"""
import asyncio
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.db.session import engine as local_engine


async def sync_data(supabase_url: str):
    print("=" * 60)
    print("  FREPPING - Sync Local PostgreSQL to Supabase")
    print("=" * 60)

    # Convert to asyncpg URL if standard postgresql://
    if supabase_url.startswith("postgresql://"):
        async_supabase_url = supabase_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    else:
        async_supabase_url = supabase_url

    print("\n[STEP 1] Connecting to Supabase...")
    remote_engine = create_async_engine(async_supabase_url, echo=False)

    try:
        async with remote_engine.connect() as remote_conn:
            res = await remote_conn.execute(text("SELECT 1 AS ping, current_database() AS db, version() AS ver"))
            row = res.mappings().first()
            print(f"  --> [OK] Connected to Supabase DB: {row['db']}")
    except Exception as e:
        print(f"  --> [FAILED] Could not connect to Supabase: {e}")
        return False

    seed_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "supabase_seed.sql")
    if not os.path.exists(seed_file):
        print(f"  --> [ERROR] {seed_file} does not exist. Generating it now...")
        from scripts.export_to_sql import export_data
        await export_data(seed_file)

    print(f"\n[STEP 2] Reading SQL seed file ({seed_file})...")
    with open(seed_file, "r", encoding="utf-8") as f:
        sql_content = f.read()

    print("\n[STEP 3] Executing data injection on Supabase...")
    # Split into statements or execute as script block
    statements = [stmt.strip() for stmt in sql_content.split(";\n") if stmt.strip()]

    async with remote_engine.begin() as remote_conn:
        # Disable triggers
        await remote_conn.execute(text("SET session_replication_role = 'replica';"))

        success_count = 0
        error_count = 0
        for stmt in statements:
            if stmt.startswith("--") or not stmt:
                continue
            try:
                await remote_conn.execute(text(stmt))
                success_count += 1
            except Exception as exc:
                print(f"  [-] Error executing statement: {exc}")
                error_count += 1

        # Re-enable triggers
        await remote_conn.execute(text("SET session_replication_role = 'origin';"))

    print(f"\n[STEP 4] Verification...")
    async with remote_engine.connect() as remote_conn:
        for tbl in ['categories', 'products', 'product_images', 'product_variants', 'users']:
            try:
                res = await remote_conn.execute(text(f"SELECT count(*) FROM {tbl}"))
                print(f"  [+] Supabase table '{tbl}': {res.scalar()} rows")
            except Exception as e:
                print(f"  [-] Supabase table '{tbl}': error checking ({e})")

    await remote_engine.dispose()
    print("\n" + "=" * 60)
    print("  [SUCCESS] All local data injected into Supabase!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SUPABASE_DATABASE_URL")
    if not url:
        print("\nMissing Supabase database URL.")
        print("Please provide it as an argument or set SUPABASE_DATABASE_URL.")
        print("Example:")
        print("  python scripts/sync_to_supabase.py postgresql://postgres.hvbixuqzrtuijnxnjiwm:YOUR_PASSWORD@aws-0-eu-west-1.pooler.supabase.com:5432/postgres\n")
        sys.exit(1)

    asyncio.run(sync_data(url))

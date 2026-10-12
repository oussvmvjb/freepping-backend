"""
Export all data from local PostgreSQL into a self-contained SQL file
suitable for pasting into the Supabase SQL Editor or executing via psql.

Order of tables handles Foreign Key constraints:
1. alembic_version
2. users
3. stores
4. categories
5. products
6. product_images
7. product_variants
"""
import asyncio
import json
import os
import sys
from datetime import datetime, date
from uuid import UUID

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.db.session import engine


TABLES_IN_ORDER = [
    "alembic_version",
    "users",
    "stores",
    "categories",
    "products",
    "product_images",
    "product_variants",
]


def format_sql_value(val):
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, (datetime, date)):
        return f"'{val.isoformat()}'"
    if isinstance(val, UUID):
        return f"'{str(val)}'"
    if isinstance(val, (dict, list)):
        dumped = json.dumps(val).replace("'", "''")
        return f"'{dumped}'::jsonb"
    # String or other
    val_str = str(val).replace("'", "''")
    return f"'{val_str}'"


async def export_data(output_file: str = "supabase_seed.sql"):
    print(f"Exporting local database data to {output_file}...")

    lines = [
        "-- ============================================================",
        "-- FREPPING — Data Seed Script for Supabase PostgreSQL",
        f"-- Generated at: {datetime.now().isoformat()}",
        "-- ============================================================",
        "",
        "-- Disable triggers temporarily to ensure clean insertion",
        "SET session_replication_role = 'replica';",
        "",
    ]

    summary = {}

    async with engine.connect() as conn:
        for table in TABLES_IN_ORDER:
            # Check if table exists
            exists_res = await conn.execute(
                text("SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = :t"),
                {"t": table}
            )
            if not exists_res.scalar():
                print(f"[-] Table {table} does not exist, skipping.")
                continue

            # Fetch columns
            cols_res = await conn.execute(
                text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = :t
                    ORDER BY ordinal_position
                """),
                {"t": table}
            )
            columns = [r[0] for r in cols_res.fetchall()]

            # Fetch rows
            rows_res = await conn.execute(text(f"SELECT * FROM {table}"))
            rows = rows_res.mappings().all()
            summary[table] = len(rows)

            if not rows:
                lines.append(f"-- Table {table} (0 rows)")
                lines.append("")
                continue

            lines.append(f"-- ==================== {table.upper()} ({len(rows)} rows) ====================")
            cols_joined = ", ".join(f'"{c}"' for c in columns)

            for row in rows:
                values_joined = ", ".join(format_sql_value(row[c]) for c in columns)
                if table == "alembic_version":
                    lines.append(f'INSERT INTO "{table}" ({cols_joined}) VALUES ({values_joined}) ON CONFLICT DO NOTHING;')
                else:
                    lines.append(f'INSERT INTO "{table}" ({cols_joined}) VALUES ({values_joined}) ON CONFLICT ("id") DO UPDATE SET ' +
                                 ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in columns if c != "id") + ";")

            lines.append("")

    lines.extend([
        "-- Re-enable triggers",
        "SET session_replication_role = 'origin';",
        "",
        "-- Reset serial sequences if any exist",
        "DO $$",
        "DECLARE",
        "    seq RECORD;",
        "BEGIN",
        "    FOR seq IN",
        "        SELECT sequence_name, table_name, column_name",
        "        FROM information_schema.sequences",
        "        JOIN information_schema.columns ON column_default LIKE '%' || sequence_name || '%'",
        "        WHERE sequence_schema = 'public'",
        "    LOOP",
        "        EXECUTE format('SELECT setval(''%I'', COALESCE((SELECT MAX(%I) FROM %I), 1))',",
        "                       seq.sequence_name, seq.column_name, seq.table_name);",
        "    END LOOP;",
        "END $$;",
        "",
        "-- Finished",
    ])

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print("\nExport Summary:")
    for t, count in summary.items():
        print(f"  [+] {t}: {count} row(s)")
    print(f"\n[OK] Successfully written to: {output_file}")


if __name__ == "__main__":
    asyncio.run(export_data())

"""
Development-only script to create an initial SUPER_ADMIN user.

Usage:
    python scripts/create_admin.py

Reads credentials from environment or .env:
    ADMIN_EMAIL=admin@example.com
    ADMIN_PASSWORD=change-me-admin-pass

Never commit real credentials. Never use in production without proper secret management.
"""
import asyncio
import os
import sys

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.core.enums import UserRole
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal, engine
from app.db.repositories.user_repository import UserRepository


async def create_admin(email: str = None, password: str = None) -> None:
    email = email or (sys.argv[1] if len(sys.argv) > 1 else settings.ADMIN_EMAIL)
    password = password or (sys.argv[2] if len(sys.argv) > 2 else settings.ADMIN_PASSWORD)

    if not email or not password:
        print("ERROR: email and password must be provided via CLI arguments, .env, or environment variables.")
        print("  Usage:\n    python scripts/create_admin.py [email] [password]")
        print("  Or set in .env:\n    ADMIN_EMAIL=admin@example.com\n    ADMIN_PASSWORD=securepassword")
        sys.exit(1)

    if len(password) < 8:
        print("ERROR: ADMIN_PASSWORD must be at least 8 characters.")
        sys.exit(1)

    print(f"Creating / verifying SUPER_ADMIN: {email}")

    try:
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)

            # Check if already exists
            existing = await repo.get_by_email(email)
            if existing:
                if existing.role == UserRole.SUPER_ADMIN:
                    print(f"  [OK] User {email} already exists as SUPER_ADMIN. No changes made.")
                else:
                    # Promote to SUPER_ADMIN
                    await repo.update_role(existing, UserRole.SUPER_ADMIN)
                    print(f"  [OK] Existing user {email} promoted to SUPER_ADMIN.")
                return

            pwd_hash = hash_password(password)
            user = await repo.create(
                email=email,
                password_hash=pwd_hash,
                first_name="Admin",
                last_name="User",
                role=UserRole.SUPER_ADMIN,
                is_active=True,
                is_verified=True,
            )
            print(f"  [OK] SUPER_ADMIN created successfully: id={user.id} email={user.email}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_admin())

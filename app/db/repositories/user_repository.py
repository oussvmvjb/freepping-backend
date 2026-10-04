import uuid
from typing import List, Optional, Tuple
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.db.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        normalized = email.strip().lower()
        stmt = select(User).where(User.email == normalized)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        email: str,
        password_hash: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        role: UserRole = UserRole.CUSTOMER,
        is_active: bool = True,
        is_verified: bool = False,
    ) -> User:
        normalized = email.strip().lower()
        user = User(
            email=normalized,
            password_hash=password_hash,
            first_name=first_name,
            last_name=last_name,
            role=role,
            is_active=is_active,
            is_verified=is_verified,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update_role(self, user: User, role: UserRole) -> User:
        user.role = role
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update_status(self, user: User, is_active: bool) -> User:
        user.is_active = is_active
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def list_users(
        self,
        page: int = 1,
        page_size: int = 20,
        role: Optional[UserRole] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[User], int]:
        stmt = select(User)
        count_stmt = select(func.count(User.id))

        if role:
            stmt = stmt.where(User.role == role)
            count_stmt = count_stmt.where(User.role == role)

        if search and search.strip():
            term = f"%{search.strip().lower()}%"
            filter_cond = or_(
                func.lower(User.email).like(term),
                func.lower(User.first_name).like(term),
                func.lower(User.last_name).like(term),
            )
            stmt = stmt.where(filter_cond)
            count_stmt = count_stmt.where(filter_cond)

        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar_one()

        stmt = stmt.order_by(User.created_at.desc())
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)

        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

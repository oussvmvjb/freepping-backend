import uuid
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.core.exceptions import (
    AuthorizationException,
    ResourceNotFoundException,
    ValidationErrorException,
)
from app.db.models.user import User
from app.db.repositories.user_repository import UserRepository


class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)

    async def get_user_by_id(self, user_id: uuid.UUID) -> User:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise ResourceNotFoundException("User", user_id)
        return user

    async def list_users(
        self,
        page: int = 1,
        page_size: int = 20,
        role: Optional[UserRole] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[User], int]:
        return await self.user_repo.list_users(page, page_size, role, search)

    async def update_user_role(
        self,
        target_user_id: uuid.UUID,
        new_role: UserRole,
        current_user: User,
    ) -> User:
        target_user = await self.get_user_by_id(target_user_id)

        # Rules from prompt:
        # SUPER_ADMIN can change any role.
        # ADMIN can only change CUSTOMER <-> SELLER.
        # ADMIN cannot create SUPER_ADMIN, demote SUPER_ADMIN, or change another ADMIN.
        if current_user.role == UserRole.SUPER_ADMIN:
            # Allowed full control
            pass
        elif current_user.role == UserRole.ADMIN:
            # Cannot touch SUPER_ADMIN
            if target_user.role == UserRole.SUPER_ADMIN:
                raise AuthorizationException("Only a SUPER_ADMIN can modify a SUPER_ADMIN account.")
            # Cannot promote to SUPER_ADMIN or ADMIN
            if new_role in [UserRole.SUPER_ADMIN, UserRole.ADMIN]:
                raise AuthorizationException("Admins cannot promote users to ADMIN or SUPER_ADMIN.")
            # Target must be CUSTOMER or SELLER, and new role must be CUSTOMER or SELLER
            if target_user.role not in [UserRole.CUSTOMER, UserRole.SELLER] or new_role not in [UserRole.CUSTOMER, UserRole.SELLER]:
                raise AuthorizationException("Admins may only toggle roles between CUSTOMER and SELLER.")
        else:
            raise AuthorizationException("You do not have permission to manage roles.")

        return await self.user_repo.update_role(target_user, new_role)

    async def update_user_status(
        self,
        target_user_id: uuid.UUID,
        is_active: bool,
        current_user: User,
    ) -> User:
        target_user = await self.get_user_by_id(target_user_id)

        # Protect SUPER_ADMIN deactivation
        if target_user.role == UserRole.SUPER_ADMIN and current_user.role != UserRole.SUPER_ADMIN:
            raise AuthorizationException("Only a SUPER_ADMIN can change the status of a SUPER_ADMIN.")

        # Admin cannot deactivate other admins or super admins
        if current_user.role == UserRole.ADMIN and target_user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            raise AuthorizationException("Admins cannot deactivate other administrators.")

        return await self.user_repo.update_status(target_user, is_active)

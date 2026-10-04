import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.refresh_session import RefreshSession


class RefreshSessionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        session_id: Optional[uuid.UUID] = None,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> RefreshSession:
        refresh_session = RefreshSession(
            id=session_id or uuid.uuid4(),
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        self.session.add(refresh_session)
        await self.session.commit()
        await self.session.refresh(refresh_session)
        return refresh_session

    async def get_by_id(self, session_id: uuid.UUID) -> Optional[RefreshSession]:
        stmt = select(RefreshSession).where(RefreshSession.id == session_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_token_hash(self, token_hash: str) -> Optional[RefreshSession]:
        stmt = select(RefreshSession).where(RefreshSession.token_hash == token_hash)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke(
        self,
        session: RefreshSession,
        replaced_by_session_id: Optional[uuid.UUID] = None
    ) -> RefreshSession:
        session.revoked_at = datetime.now(timezone.utc)
        if replaced_by_session_id:
            session.replaced_by_session_id = replaced_by_session_id
        self.session.add(session)
        await self.session.commit()
        await self.session.refresh(session)
        return session

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        """Revokes all active sessions for a user (used upon reuse detection or security reset)."""
        now = datetime.now(timezone.utc)
        stmt = (
            update(RefreshSession)
            .where(
                RefreshSession.user_id == user_id,
                RefreshSession.revoked_at.is_(None)
            )
            .values(revoked_at=now)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount

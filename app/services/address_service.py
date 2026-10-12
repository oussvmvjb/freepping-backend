import uuid
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundException
from app.db.models.user import User
from app.db.repositories.address_repository import AddressRepository
from app.v1.schemas.address import (
    AddressCreate,
    AddressResponse,
    AddressUpdate,
)


class AddressService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.address_repo = AddressRepository(session)

    async def list_addresses(self, user: User) -> List[AddressResponse]:
        addresses = await self.address_repo.list_by_user(user.id)
        return [AddressResponse.model_validate(a) for a in addresses]

    async def get_address(self, address_id: uuid.UUID, user: User) -> AddressResponse:
        address = await self.address_repo.get_by_id_and_user(address_id, user.id)
        if not address:
            raise ResourceNotFoundException("Address", address_id)
        return AddressResponse.model_validate(address)

    async def create_address(self, user: User, address_in: AddressCreate) -> AddressResponse:
        data = address_in.model_dump()
        address = await self.address_repo.create(user.id, data)
        return AddressResponse.model_validate(address)

    async def update_address(
        self,
        address_id: uuid.UUID,
        user: User,
        address_in: AddressUpdate,
    ) -> AddressResponse:
        address = await self.address_repo.get_by_id_and_user(address_id, user.id)
        if not address:
            raise ResourceNotFoundException("Address", address_id)

        update_data = address_in.model_dump(exclude_unset=True)
        updated = await self.address_repo.update(address, update_data)
        return AddressResponse.model_validate(updated)

    async def delete_address(self, address_id: uuid.UUID, user: User) -> None:
        address = await self.address_repo.get_by_id_and_user(address_id, user.id)
        if not address:
            raise ResourceNotFoundException("Address", address_id)
        await self.address_repo.delete(address)

    async def set_default_address(self, address_id: uuid.UUID, user: User) -> AddressResponse:
        address = await self.address_repo.get_by_id_and_user(address_id, user.id)
        if not address:
            raise ResourceNotFoundException("Address", address_id)
        updated = await self.address_repo.set_default(address)
        return AddressResponse.model_validate(updated)

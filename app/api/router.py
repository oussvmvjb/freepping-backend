from fastapi import APIRouter
from fastapi.security import HTTPBearer

from app.v1.endpoints import auth, categories, health, products, stores, users

# Global bearer security scheme for Swagger UI "Authorize" button
security_scheme = HTTPBearer()

api_router = APIRouter()

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(categories.router, prefix="/categories", tags=["Categories"])
api_router.include_router(products.router, prefix="/products", tags=["Products"])
api_router.include_router(stores.router, prefix="/stores", tags=["Stores"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])

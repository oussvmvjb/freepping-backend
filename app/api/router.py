from fastapi import APIRouter
from fastapi.security import HTTPBearer

from app.v1.endpoints import (
    admin,
    auth,
    cart,
    categories,
    checkout,
    delivery_options,
    gift_cards,
    health,
    orders,
    products,
    promos,
    seller,
    stores,
    users,
)

# Global bearer security scheme for Swagger UI "Authorize" button
security_scheme = HTTPBearer()

api_router = APIRouter()

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(categories.router, prefix="/categories", tags=["Categories"])
api_router.include_router(products.router, prefix="/products", tags=["Products"])
api_router.include_router(cart.router, prefix="/cart", tags=["Cart"])
api_router.include_router(promos.router, prefix="/promos", tags=["Promos"])
api_router.include_router(delivery_options.router, prefix="/delivery-options", tags=["Delivery"])
api_router.include_router(checkout.router, prefix="/checkout", tags=["Checkout"])
api_router.include_router(orders.router, prefix="/orders", tags=["Orders"])
api_router.include_router(gift_cards.router, prefix="/gift-cards", tags=["Gift Cards"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
api_router.include_router(seller.router, prefix="/seller", tags=["Seller"])
api_router.include_router(stores.router, prefix="/stores", tags=["Stores"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])

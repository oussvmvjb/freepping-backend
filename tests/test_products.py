import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import get_db
from app.services.category_service import CategoryService
from app.services.product_service import ProductService
from app.v1.schemas.category import CategoryResponse
from app.v1.schemas.product import ProductListResponse, ProductResponse

client = TestClient(app)


def test_get_categories():
    fake_category = CategoryResponse(
        id=uuid.uuid4(),
        name="Tops",
        slug="tops",
        description="Cool tops",
        image_url=None,
        is_active=True,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )

    async def mock_list_categories(self, is_active_only=True):
        return [fake_category]

    original_method = CategoryService.list_categories
    CategoryService.list_categories = mock_list_categories

    try:
        response = client.get("/api/v1/categories")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["slug"] == "tops"
    finally:
        CategoryService.list_categories = original_method


def test_get_products_list():
    fake_product = ProductResponse(
        id=uuid.uuid4(),
        category_id=uuid.uuid4(),
        name="Camo Hoodie",
        slug="camo-hoodie",
        description="Streetwear camo hoodie",
        price=Decimal("65.00"),
        compare_price=Decimal("85.00"),
        material="80% Cotton",
        is_active=True,
        is_featured=True,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        images=[],
        variants=[],
    )

    async def mock_list_products(self, page=1, page_size=20, category_id=None, search=None, is_featured=None):
        return ProductListResponse(
            items=[fake_product],
            page=1,
            page_size=20,
            total=1,
            pages=1,
        )

    original_method = ProductService.list_products
    ProductService.list_products = mock_list_products

    try:
        response = client.get("/api/v1/products?page=1&page_size=20")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["page"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "Camo Hoodie"
    finally:
        ProductService.list_products = original_method

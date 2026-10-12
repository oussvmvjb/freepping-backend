import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class TopProductSalesItem(BaseModel):
    product_id: uuid.UUID
    product_name: str
    units_sold: int
    total_revenue: str


class TopProductLikesItem(BaseModel):
    product_id: uuid.UUID
    product_name: str
    likes_count: int


class RevenueDailyItem(BaseModel):
    date: str
    revenue: str
    orders_count: int


class AdminDashboardSummary(BaseModel):
    total_revenue: str
    orders_count: int
    orders_by_status: Dict[str, int]
    new_users: int
    active_products: int
    low_stock_count: int
    top_products_by_sales: List[TopProductSalesItem]
    top_products_by_likes: List[TopProductLikesItem]
    revenue_daily: List[RevenueDailyItem]


class SellerDashboardSummary(BaseModel):
    total_revenue: str
    orders_count: int
    orders_by_status: Dict[str, int]
    active_products: int
    low_stock_count: int
    top_products_by_sales: List[TopProductSalesItem]
    top_products_by_likes: List[TopProductLikesItem]
    revenue_daily: List[RevenueDailyItem]


class LowStockVariantItem(BaseModel):
    variant_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    sku: str
    size: Optional[str] = None
    color: Optional[str] = None
    stock: int

    model_config = ConfigDict(from_attributes=True)


class LowStockInventoryResponse(BaseModel):
    items: List[LowStockVariantItem]
    threshold: int
    count: int


class VariantStockUpdateRequest(BaseModel):
    stock: int = Field(..., ge=0, description="New inventory quantity")

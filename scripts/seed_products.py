import asyncio
import os
import sys

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import AsyncSessionLocal
from app.db.repositories.category_repository import CategoryRepository
from app.db.repositories.product_repository import ProductRepository
from app.v1.schemas.category import CategoryCreate
from app.v1.schemas.product import ProductCreate, ProductImageCreate, ProductVariantCreate

async def seed_products() -> None:
    print("Starting database seeding...")

    async with AsyncSessionLocal() as session:
        cat_repo = CategoryRepository(session)
        prod_repo = ProductRepository(session)

        # 1. Create Categories
        categories_data = [
            {"name": "Electronics", "slug": "electronics", "description": "Gadgets and devices", "image_url": "https://images.unsplash.com/photo-1498049794561-7780e7231661?w=500&q=80"},
            {"name": "Clothing", "slug": "clothing", "description": "Apparel and fashion", "image_url": "https://images.unsplash.com/photo-1441984904996-e0b6ba687e07?w=500&q=80"},
            {"name": "Home & Kitchen", "slug": "home-kitchen", "description": "Home appliances and furniture", "image_url": "https://images.unsplash.com/photo-1556910103-1c02745a872f?w=500&q=80"}
        ]

        categories = {}
        for c_data in categories_data:
            existing = await cat_repo.get_by_slug(c_data["slug"])
            if not existing:
                cat_create = CategoryCreate(**c_data)
                cat = await cat_repo.create(cat_create)
                categories[cat.slug] = cat.id
                print(f"Created category: {cat.name}")
            else:
                categories[existing.slug] = existing.id
                print(f"Category {existing.name} already exists.")

        # 2. Create Products
        products_data = [
            {
                "name": "Wireless Noise-Cancelling Headphones",
                "slug": "wireless-headphones-nc",
                "description": "Premium noise-cancelling wireless headphones with 30-hour battery life.",
                "price": 299.99,
                "compare_price": 349.99,
                "category_id": categories["electronics"],
                "images": [{"image_url": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500&q=80", "is_primary": True, "sort_order": 0}],
                "variants": [{"sku": "WH-NC-BLK", "stock": 50, "price": 299.99}]
            },
            {
                "name": "Smartphone 12 Pro",
                "slug": "smartphone-12-pro",
                "description": "Latest flagship smartphone with stunning camera system.",
                "price": 999.00,
                "category_id": categories["electronics"],
                "images": [{"image_url": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=500&q=80", "is_primary": True, "sort_order": 0}],
                "variants": [{"sku": "SP12-PRO-128", "stock": 100, "price": 999.00}]
            },
            {
                "name": "Smart Watch Series 5",
                "slug": "smart-watch-series-5",
                "description": "Advanced smartwatch with health tracking features.",
                "price": 399.50,
                "category_id": categories["electronics"],
                "images": [{"image_url": "https://images.unsplash.com/photo-1546868871-7041f2a55e12?w=500&q=80", "is_primary": True, "sort_order": 0}],
                "variants": [{"sku": "SW5-44MM", "stock": 25, "price": 399.50}]
            },
            {
                "name": "Men's Classic T-Shirt",
                "slug": "mens-classic-tshirt",
                "description": "Comfortable 100% cotton everyday t-shirt.",
                "price": 19.99,
                "material": "100% Cotton",
                "category_id": categories["clothing"],
                "images": [{"image_url": "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=500&q=80", "is_primary": True, "sort_order": 0}],
                "variants": [
                    {"size": "M", "color": "White", "sku": "TS-M-WH", "stock": 200, "price": 19.99},
                    {"size": "L", "color": "Black", "sku": "TS-L-BK", "stock": 150, "price": 19.99}
                ]
            },
            {
                "name": "Women's Denim Jacket",
                "slug": "womens-denim-jacket",
                "description": "Classic fit denim jacket for all seasons.",
                "price": 59.99,
                "material": "Denim",
                "category_id": categories["clothing"],
                "images": [{"image_url": "https://images.unsplash.com/photo-1576995853123-5a10305d93c0?w=500&q=80", "is_primary": True, "sort_order": 0}],
                "variants": [{"size": "S", "sku": "WDJ-S", "stock": 40, "price": 59.99}]
            },
            {
                "name": "Running Sneakers",
                "slug": "running-sneakers",
                "description": "Lightweight breathable running shoes.",
                "price": 89.99,
                "compare_price": 110.00,
                "category_id": categories["clothing"],
                "images": [{"image_url": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=500&q=80", "is_primary": True, "sort_order": 0}],
                "variants": [{"size": "10", "color": "Red", "sku": "RS-10-RD", "stock": 80, "price": 89.99}]
            },
            {
                "name": "Modern Leather Sofa",
                "slug": "modern-leather-sofa",
                "description": "Premium 3-seater leather sofa for modern living rooms.",
                "price": 1299.00,
                "material": "Genuine Leather",
                "category_id": categories["home-kitchen"],
                "images": [{"image_url": "https://images.unsplash.com/photo-1493663284031-b7e3aefcae8e?w=500&q=80", "is_primary": True, "sort_order": 0}],
                "variants": [{"sku": "MLS-3S-BR", "stock": 5, "price": 1299.00}]
            },
            {
                "name": "Ceramic Coffee Mug Set",
                "slug": "ceramic-coffee-mug-set",
                "description": "Set of 4 handmade ceramic mugs.",
                "price": 34.99,
                "material": "Ceramic",
                "category_id": categories["home-kitchen"],
                "images": [{"image_url": "https://images.unsplash.com/photo-1514228742587-6b1558fcca3d?w=500&q=80", "is_primary": True, "sort_order": 0}],
                "variants": [{"sku": "CCM-SET4", "stock": 120, "price": 34.99}]
            },
            {
                "name": "Stainless Steel Cookware Set",
                "slug": "stainless-steel-cookware",
                "description": "Professional grade 10-piece cookware set.",
                "price": 249.99,
                "material": "Stainless Steel",
                "category_id": categories["home-kitchen"],
                "images": [{"image_url": "https://images.unsplash.com/photo-1584990347449-a6a96ea8a68d?w=500&q=80", "is_primary": True, "sort_order": 0}],
                "variants": [{"sku": "CW-10PC-SS", "stock": 30, "price": 249.99}]
            },
            {
                "name": "Wooden Dining Table",
                "slug": "wooden-dining-table",
                "description": "Solid oak dining table seating up to 6 people.",
                "price": 599.00,
                "material": "Solid Oak Wood",
                "category_id": categories["home-kitchen"],
                "images": [{"image_url": "https://images.unsplash.com/photo-1533090481720-856c6e3c1fdc?w=500&q=80", "is_primary": True, "sort_order": 0}],
                "variants": [{"sku": "WDT-OAK-6", "stock": 10, "price": 599.00}]
            }
        ]

        for p_data in products_data:
            existing = await prod_repo.get_by_slug(p_data["slug"])
            if not existing:
                img_data = p_data.pop("images", [])
                var_data = p_data.pop("variants", [])
                
                prod_create = ProductCreate(
                    **p_data,
                    images=[ProductImageCreate(**img) for img in img_data],
                    variants=[ProductVariantCreate(**var) for var in var_data]
                )
                
                await prod_repo.create(prod_create)
                print(f"Created product: {p_data['name']}")
            else:
                print(f"Product {existing.name} already exists.")
                
    print("Database seeding completed.")

if __name__ == "__main__":
    asyncio.run(seed_products())

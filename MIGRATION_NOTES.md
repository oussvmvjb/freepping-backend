# FREPPING Backend — Extended Features Migration Notes

This document summarizes the database schema extensions, new API endpoints, configuration variables, and architectural decisions introduced in the extended backend release.

---

## 1. Database Tables & Migrations

Alembic revision: `003_extended_features` (chained onto `002_auth_users_stores`).

### New & Modified Tables

| Table | Description | Key Columns / Constraints |
|---|---|---|
| `products` | Added denormalized column | `likes_count INT NOT NULL DEFAULT 0` |
| `product_likes` | User favorite product bookmark | `user_id` FK (CASCADE), `product_id` FK (CASCADE), `UNIQUE(user_id, product_id)` |
| `promo_codes` | Discount promo codes | `code` UNIQUE (UPPERCASE), `discount_type` (PERCENT/FIXED), `discount_value`, `min_order_amount`, `max_discount_amount`, `usage_limit`, `used_count`, `per_user_limit`, `starts_at`, `expires_at`, `is_active` |
| `promo_redemptions` | Audit log of redemptions | `promo_code_id` FK, `user_id` FK, `order_id` FK nullable |
| `carts` | User active shopping cart | `user_id` UNIQUE FK, `promo_code_id` FK nullable, `has_gift_wrap BOOL` |
| `cart_items` | Line items in cart | `cart_id` FK (CASCADE), `product_id` FK, `variant_id` FK nullable, `quantity INT >= 1`, `UNIQUE(cart_id, product_id, variant_id)` |
| `addresses` | User shipping addresses | `user_id` FK (CASCADE), `name`, `street`, `city`, `state`, `zip`, `country`, `phone`, `type` (home/office/other), `is_default BOOL` |
| `delivery_options` | Available shipping methods | `code` UNIQUE, `title`, `price Numeric`, `estimated_days_min`, `estimated_days_max`, `estimated_label`, `is_active`, `sort_order` |
| `orders` | Placed customer orders | `order_number` UNIQUE (`FRP-YYYYMMDD-XXXXXX`), `user_id` FK, `status`, `payment_method`, `payment_status`, price snapshots, full shipping address snapshot columns |
| `order_items` | Historical item snapshot | `order_id` FK (CASCADE), `product_id` (SET NULL), `variant_id` (SET NULL), `seller_id`, `product_name`, `variant_label`, `sku`, `unit_price`, `quantity >= 1`, `line_total`, `fulfillment_status` |
| `order_status_history`| Audit timeline of status transitions | `order_id` FK (CASCADE), `from_status`, `to_status`, `changed_by` FK, `note` |
| `payments` | Non-sensitive payment logs | `order_id` FK, `provider`, `provider_ref`, `amount`, `status`, `card_brand`, `card_last4` |
| `saved_payment_methods`| Tokenized payment references | `user_id` FK, `provider_token`, `brand`, `last4`, `exp_month`, `exp_year`, `is_default` |
| `gift_cards` | Digital gift cards | `code` UNIQUE (`FRP-GC-XXXX-XXXX`), `pin_hash` (Argon2id), `balance >= 0`, `currency`, `is_active`, `expires_at` |
| `gift_card_transactions`| Gift card debit/credit audit | `gift_card_id` FK, `order_id` FK nullable, `amount` (negative = redemption), `balance_after` |

---

## 2. API Endpoints

All endpoints are registered under `/api/v1` with clean OpenAPI documentation tags:

### Part 1: Product Likes / Favorites
- `POST /api/v1/products/{product_id}/like` — (Auth) Idempotent like toggle. Returns `{liked: true, likes_count}`.
- `DELETE /api/v1/products/{product_id}/like` — (Auth) Idempotent unlike toggle. Returns `{liked: false, likes_count}`.
- `GET /api/v1/users/me/favorites` — (Auth) Paginated user favorite products.
- `GET /api/v1/products` — (Public / Optional Auth) Added query parameters:
  - `sort`: `newest`, `price_asc`, `price_desc`, `popular`, `name_asc`
  - `min_price`, `max_price`
  - `in_stock_only`: boolean
  - Enriched with `likes_count`, `is_liked`, `in_stock`, `discount_percent`

### Part 2: Cart
- `GET /api/v1/cart` — (Auth) Full cart breakdown (items, subtotal, promo_discount, gift_wrap_cost, delivery_cost, total, applied_promo).
- `POST /api/v1/cart/items` — (Auth) Add item `{product_id, variant_id?, quantity}` (merges if exists).
- `PATCH /api/v1/cart/items/{item_id}` — (Auth) Update quantity `{quantity}`.
- `DELETE /api/v1/cart/items/{item_id}` — (Auth) Remove item.
- `DELETE /api/v1/cart` — (Auth) Clear cart.
- `POST /api/v1/cart/promo` — (Auth) Apply promo code `{code}`.
- `DELETE /api/v1/cart/promo` — (Auth) Remove applied promo code.
- `PATCH /api/v1/cart/gift-wrap` — (Auth) Toggle gift wrap `{enabled: bool}`.

### Part 3: Promo Codes
- `POST /api/v1/promos/validate` — (Auth) Pre-validate code against current cart items. Rate-limited.
- `GET /api/v1/promos/active` — (Public) List active public promo codes for banners.
- `POST /api/v1/admin/promos` — (Admin) Create promo code.
- `GET /api/v1/admin/promos` — (Admin) Paginated list of all promo codes.
- `GET /api/v1/admin/promos/{id}` — (Admin) Get promo code by ID.
- `PATCH /api/v1/admin/promos/{id}` — (Admin) Update promo code.
- `DELETE /api/v1/admin/promos/{id}` — (Admin) Delete promo code.

### Part 4: Addresses
- `GET /api/v1/users/me/addresses` — (Auth) List addresses (default first).
- `POST /api/v1/users/me/addresses` — (Auth) Create address.
- `PATCH /api/v1/users/me/addresses/{id}` — (Auth) Update address.
- `DELETE /api/v1/users/me/addresses/{id}` — (Auth) Delete address.
- `PATCH /api/v1/users/me/addresses/{id}/default` — (Auth) Set as default address.

### Part 5: Delivery Options
- `GET /api/v1/delivery-options` — (Public) Cached delivery options.
- `POST /api/v1/admin/delivery-options` — (Admin) Create option.
- `PATCH /api/v1/admin/delivery-options/{id}` — (Admin) Update option.
- `DELETE /api/v1/admin/delivery-options/{id}` — (Admin) Delete option.

### Part 6: Checkout / Orders / Payments
- `POST /api/v1/checkout/preview` — (Auth) Pricing preview with address & delivery option.
- `POST /api/v1/checkout/place-order` — (Auth) Atomic order placement:
  - Row locking (`FOR UPDATE`) for inventory stock integrity
  - Server-side price recalculation
  - Payment processing stub (`PaymentGateway`)
  - Stock decrement & cart clearing
  - `Idempotency-Key` header support
- `GET /api/v1/orders/my` — (Auth) Paginated order history.
- `GET /api/v1/orders/{order_id}` — (Auth) Order detail (owner, admin, or seller of contained items).
- `POST /api/v1/orders/{order_id}/cancel` — (Auth) Order cancellation with restock & refund.
- `POST /api/v1/gift-cards/check` — (Auth) Check gift card balance with PIN verification. Rate-limited.
- `GET /api/v1/users/me/payment-methods` — (Auth) List saved tokenized cards.
- `DELETE /api/v1/users/me/payment-methods/{id}` — (Auth) Remove saved card.

### Part 7: Admin & Seller Panels & Profile
- `GET /api/v1/admin/dashboard/summary` — (Admin) Cached analytics summary (`from`, `to`).
- `GET /api/v1/admin/orders` — (Admin) Paginated order management with search and filters.
- `GET /api/v1/admin/orders/{id}` — (Admin) Order inspection.
- `PATCH /api/v1/admin/orders/{id}/status` — (Admin) Status transition and tracking number update.
- `POST /api/v1/admin/orders/{id}/refund` — (Admin) Manual administrative refund.
- `GET /api/v1/admin/inventory/low-stock` — (Admin) Inventory threshold check.
- `PATCH /api/v1/admin/variants/{variant_id}/stock` — (Admin) Adjust stock.
- `POST /api/v1/admin/gift-cards` — (Admin) Generate gift card (returns plain PIN once).
- `GET /api/v1/admin/gift-cards` — (Admin) List gift cards.
- `PATCH /api/v1/admin/gift-cards/{id}` — (Admin) Activate/deactivate gift card.
- `GET /api/v1/admin/products/{id}/likes` — (Admin) Likers list and count.
- `GET /api/v1/seller/dashboard/summary` — (Seller) Analytics scoped to seller's items.
- `GET /api/v1/seller/orders` — (Seller) Orders containing seller's items.
- `PATCH /api/v1/seller/orders/{id}/items/{item_id}/status` — (Seller) Update item fulfillment.
- `GET /api/v1/seller/products/{id}/likes` — (Seller) Likes count for seller's product.
- `PATCH /api/v1/auth/me` — (Auth) Update first and last name.
- `POST /api/v1/auth/change-password` — (Auth) Change password & revoke all other refresh sessions.

---

## 3. Configuration & Environment Variables

Added to `app/core/config.py`:

```env
# Rate Limiting (per minute per IP/client)
RATE_LIMIT_LIKE_PER_MINUTE=30
RATE_LIMIT_PROMO_VALIDATE_PER_MINUTE=10
RATE_LIMIT_GIFT_CARD_CHECK_PER_MINUTE=5

# Redis Cache TTLs (in seconds)
CACHE_TTL_DELIVERY_OPTIONS=300
CACHE_TTL_DASHBOARD=60

# Cart / Order Configurations
GIFT_WRAP_COST=2.00
```

---

## 4. Architectural & Security Assumptions

1. **Security of Payment Data**: Full credit card numbers, CVVs, and expiry credentials are never stored. The payment flow uses tokenization via an abstract `PaymentGateway` interface (`MockPaymentGateway` included for local/testing environments). Only card brand and `last4` are persisted.
2. **Atomic Checkout with Concurrency Protection**: High-concurrency race conditions (such as two customers checking out the last inventory unit simultaneously) are prevented by performing `SELECT ... FOR UPDATE` row locks on the affected `product_variants` records inside the order placement transaction.
3. **Idempotent Likes & Orders**: Liking an already liked product or checking out with a duplicate `Idempotency-Key` does not duplicate data or create duplicate orders.
4. **Argon2id for Gift Card PINs**: Gift card PINs are hashed using Argon2id so plain text PINs are never readable in the database.

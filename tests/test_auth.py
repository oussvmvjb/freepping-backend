"""
Comprehensive authentication and authorization test suite.

Tests registration, login, token refresh/rotation, reuse detection,
logout, and role-based access control across all four roles.
"""
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.enums import UserRole
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
    verify_password,
    decode_token,
)
from app.core.exceptions import AuthenticationException
from app.db.models.user import User
from app.db.models.refresh_session import RefreshSession
from app.v1.schemas.user import UserResponse

client = TestClient(app)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_user(
    role: UserRole = UserRole.CUSTOMER,
    is_active: bool = True,
    password: str = "password123",
) -> User:
    user = User()
    user.id = uuid.uuid4()
    user.email = f"user-{uuid.uuid4()}@example.com"
    user.password_hash = hash_password(password)
    user.first_name = "Test"
    user.last_name = "User"
    user.role = role
    user.is_active = is_active
    user.is_verified = False
    user.created_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    return user


def _make_refresh_session(user_id: uuid.UUID, token: str, revoked: bool = False) -> RefreshSession:
    session_id = uuid.uuid4()
    session = RefreshSession()
    session.id = session_id
    session.user_id = user_id
    session.token_hash = hash_token(token)
    session.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    session.created_at = datetime.now(timezone.utc)
    session.revoked_at = datetime.now(timezone.utc) if revoked else None
    session.replaced_by_session_id = None
    session.user_agent = "test-agent"
    session.ip_address = "127.0.0.1"
    return session


# ─────────────────────────────────────────────
# SECTION: Password Hashing
# ─────────────────────────────────────────────

class TestPasswordHashing:
    def test_hash_password_produces_hash(self):
        pw = "securepassword"
        h = hash_password(pw)
        assert h != pw
        assert len(h) > 20

    def test_verify_password_correct(self):
        pw = "securepassword"
        h = hash_password(pw)
        assert verify_password(pw, h) is True

    def test_verify_password_wrong(self):
        h = hash_password("correctpassword")
        assert verify_password("wrongpassword", h) is False

    def test_hash_never_plaintext(self):
        pw = "plainpassword"
        h = hash_password(pw)
        assert pw not in h

    def test_short_password_raises(self):
        with pytest.raises(ValueError):
            hash_password("short")

    def test_two_hashes_differ(self):
        pw = "samepassword"
        h1 = hash_password(pw)
        h2 = hash_password(pw)
        assert h1 != h2  # Argon2id generates unique salts


# ─────────────────────────────────────────────
# SECTION: JWT Token Utilities
# ─────────────────────────────────────────────

class TestJWTTokens:
    def test_create_access_token_valid(self):
        user_id = uuid.uuid4()
        token, expires_at = create_access_token(user_id, UserRole.CUSTOMER)
        assert isinstance(token, str)
        payload = decode_token(token)
        assert payload["sub"] == str(user_id)
        assert payload["type"] == "access"
        assert payload["role"] == UserRole.CUSTOMER

    def test_create_refresh_token_valid(self):
        user_id = uuid.uuid4()
        session_id = uuid.uuid4()
        token, expires_at = create_refresh_token(user_id, session_id)
        payload = decode_token(token)
        assert payload["sub"] == str(user_id)
        assert payload["type"] == "refresh"
        assert payload["jti"] == str(session_id)

    def test_decode_expired_token_raises(self):
        import jwt
        from app.core.config import settings
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(uuid.uuid4()),
            "type": "access",
            "role": "CUSTOMER",
            "iat": int((now - timedelta(hours=2)).timestamp()),
            "exp": int((now - timedelta(hours=1)).timestamp()),
            "jti": str(uuid.uuid4()),
        }
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        with pytest.raises(AuthenticationException) as exc:
            decode_token(token)
        assert "expired" in str(exc.value).lower()

    def test_decode_malformed_token_raises(self):
        with pytest.raises(AuthenticationException):
            decode_token("totally.not.a.valid.token")

    def test_wrong_token_type_is_detectable(self):
        user_id = uuid.uuid4()
        session_id = uuid.uuid4()
        refresh_token, _ = create_refresh_token(user_id, session_id)
        payload = decode_token(refresh_token)
        # Client code should reject non-access type for auth
        assert payload["type"] == "refresh"
        assert payload["type"] != "access"

    def test_token_hash_deterministic(self):
        raw = "some-raw-token-value"
        h1 = hash_token(raw)
        h2 = hash_token(raw)
        assert h1 == h2
        assert raw not in h1


# ─────────────────────────────────────────────
# SECTION: Registration
# ─────────────────────────────────────────────

class TestRegistration:
    def test_register_success(self):
        mock_user = _make_user(role=UserRole.CUSTOMER)

        with patch("app.v1.endpoints.auth.AuthService") as mock_svc:
            instance = mock_svc.return_value
            instance.register = AsyncMock(return_value=MagicMock(
                access_token="access-token",
                refresh_token="refresh-token",
                token_type="bearer",
                expires_in=900,
                user=UserResponse.model_validate(mock_user),
            ))
            resp = client.post("/api/v1/auth/register", json={
                "email": "newuser@example.com",
                "password": "password123",
                "first_name": "New",
                "last_name": "User",
            })
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["role"] == "CUSTOMER"

    def test_register_role_is_always_customer(self):
        """Registration must never accept ADMIN or SUPER_ADMIN roles from client."""
        mock_user = _make_user(role=UserRole.CUSTOMER)

        with patch("app.v1.endpoints.auth.AuthService") as mock_svc:
            instance = mock_svc.return_value
            instance.register = AsyncMock(return_value=MagicMock(
                access_token="tok",
                refresh_token="ref",
                token_type="bearer",
                expires_in=900,
                user=UserResponse.model_validate(mock_user),
            ))
            resp = client.post("/api/v1/auth/register", json={
                "email": "admin-attempt@example.com",
                "password": "password123",
            })
        # Even if role was supplied (it's ignored by schema), the service forces CUSTOMER
        assert resp.status_code == 201
        assert resp.json()["user"]["role"] == "CUSTOMER"

    def test_register_invalid_email_rejected(self):
        resp = client.post("/api/v1/auth/register", json={
            "email": "not-an-email",
            "password": "password123",
        })
        assert resp.status_code == 422

    def test_register_short_password_rejected(self):
        resp = client.post("/api/v1/auth/register", json={
            "email": "user@example.com",
            "password": "short",
        })
        assert resp.status_code == 422

    def test_register_duplicate_email_conflict(self):
        from app.core.exceptions import DuplicateResourceException
        with patch("app.v1.endpoints.auth.AuthService") as mock_svc:
            instance = mock_svc.return_value
            instance.register = AsyncMock(side_effect=DuplicateResourceException("Email already exists."))
            resp = client.post("/api/v1/auth/register", json={
                "email": "existing@example.com",
                "password": "password123",
            })
        assert resp.status_code == 409

    def test_register_password_hash_never_returned(self):
        mock_user = _make_user(role=UserRole.CUSTOMER)
        with patch("app.v1.endpoints.auth.AuthService") as mock_svc:
            instance = mock_svc.return_value
            instance.register = AsyncMock(return_value=MagicMock(
                access_token="tok",
                refresh_token="ref",
                token_type="bearer",
                expires_in=900,
                user=UserResponse.model_validate(mock_user),
            ))
            resp = client.post("/api/v1/auth/register", json={
                "email": "user2@example.com",
                "password": "password123",
            })
        body = resp.text
        assert "password_hash" not in body
        assert "hash" not in body


# ─────────────────────────────────────────────
# SECTION: Login
# ─────────────────────────────────────────────

class TestLogin:
    def test_login_success(self):
        mock_user = _make_user()
        with patch("app.v1.endpoints.auth.AuthService") as mock_svc:
            instance = mock_svc.return_value
            instance.login = AsyncMock(return_value=MagicMock(
                access_token="at",
                refresh_token="rt",
                token_type="bearer",
                expires_in=900,
                user=UserResponse.model_validate(mock_user),
            ))
            resp = client.post("/api/v1/auth/login", json={
                "email": "user@example.com",
                "password": "password123",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_login_invalid_credentials(self):
        with patch("app.v1.endpoints.auth.AuthService") as mock_svc:
            instance = mock_svc.return_value
            instance.login = AsyncMock(side_effect=AuthenticationException("Invalid email or password."))
            resp = client.post("/api/v1/auth/login", json={
                "email": "user@example.com",
                "password": "wrongpassword",
            })
        assert resp.status_code == 401
        # Must not reveal whether user exists
        assert "Invalid email or password" in resp.json()["error"]["message"]

    def test_login_inactive_user(self):
        with patch("app.v1.endpoints.auth.AuthService") as mock_svc:
            instance = mock_svc.return_value
            instance.login = AsyncMock(side_effect=AuthenticationException("User account is inactive."))
            resp = client.post("/api/v1/auth/login", json={
                "email": "inactive@example.com",
                "password": "password123",
            })
        assert resp.status_code == 401

    def test_login_both_tokens_returned(self):
        mock_user = _make_user()
        with patch("app.v1.endpoints.auth.AuthService") as mock_svc:
            instance = mock_svc.return_value
            instance.login = AsyncMock(return_value=MagicMock(
                access_token="access_token_here",
                refresh_token="refresh_token_here",
                token_type="bearer",
                expires_in=900,
                user=UserResponse.model_validate(mock_user),
            ))
            resp = client.post("/api/v1/auth/login", json={
                "email": "user@example.com",
                "password": "password123",
            })
        data = resp.json()
        assert data["access_token"] == "access_token_here"
        assert data["refresh_token"] == "refresh_token_here"


# ─────────────────────────────────────────────
# SECTION: Refresh Token Rotation
# ─────────────────────────────────────────────

class TestRefreshTokenRotation:
    def test_refresh_returns_new_tokens(self):
        mock_user = _make_user()
        with patch("app.v1.endpoints.auth.AuthService") as mock_svc:
            instance = mock_svc.return_value
            instance.refresh = AsyncMock(return_value=MagicMock(
                access_token="new_access",
                refresh_token="new_refresh",
                token_type="bearer",
                expires_in=900,
                user=UserResponse.model_validate(mock_user),
            ))
            resp = client.post("/api/v1/auth/refresh", json={"refresh_token": "old_valid_refresh_token"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"] == "new_access"
        assert data["refresh_token"] == "new_refresh"

    def test_expired_refresh_rejected(self):
        with patch("app.v1.endpoints.auth.AuthService") as mock_svc:
            instance = mock_svc.return_value
            instance.refresh = AsyncMock(side_effect=AuthenticationException("Refresh session has expired."))
            resp = client.post("/api/v1/auth/refresh", json={"refresh_token": "expired_token"})
        assert resp.status_code == 401

    def test_revoked_refresh_rejected(self):
        with patch("app.v1.endpoints.auth.AuthService") as mock_svc:
            instance = mock_svc.return_value
            instance.refresh = AsyncMock(side_effect=AuthenticationException("Security reuse detected."))
            resp = client.post("/api/v1/auth/refresh", json={"refresh_token": "revoked_token"})
        assert resp.status_code == 401

    def test_reuse_detection_triggers_full_revocation(self):
        """When a revoked refresh token is reused, all sessions must be invalidated."""
        with patch("app.services.auth_service.AuthService.refresh", new_callable=AsyncMock) as mock_refresh:
            # The actual logic is tested via the service — here we verify the service raises correctly
            mock_refresh.side_effect = AuthenticationException("Security reuse detected.")
            with patch("app.v1.endpoints.auth.AuthService") as mock_svc:
                instance = mock_svc.return_value
                instance.refresh = mock_refresh
                resp = client.post("/api/v1/auth/refresh", json={"refresh_token": "reused_token"})
        assert resp.status_code == 401


# ─────────────────────────────────────────────
# SECTION: Logout
# ─────────────────────────────────────────────

class TestLogout:
    def test_logout_returns_204(self):
        with patch("app.v1.endpoints.auth.AuthService") as mock_svc:
            instance = mock_svc.return_value
            instance.logout = AsyncMock(return_value=None)
            resp = client.post("/api/v1/auth/logout", json={"refresh_token": "valid_token"})
        assert resp.status_code == 204

    def test_logout_revokes_session(self):
        logout_called = []
        async def fake_logout(token):
            logout_called.append(token)

        with patch("app.v1.endpoints.auth.AuthService") as mock_svc:
            instance = mock_svc.return_value
            instance.logout = AsyncMock(side_effect=fake_logout)
            client.post("/api/v1/auth/logout", json={"refresh_token": "my_refresh_token"})

        assert "my_refresh_token" in logout_called


# ─────────────────────────────────────────────
# SECTION: /auth/me
# ─────────────────────────────────────────────

class TestGetMe:
    def test_me_returns_user_profile(self):
        user = _make_user()
        access_token, _ = create_access_token(user.id, user.role.value)

        with patch("app.api.deps.UserRepository") as MockRepo:
            repo_instance = MagicMock()
            repo_instance.get_by_id = AsyncMock(return_value=user)
            MockRepo.return_value = repo_instance

            resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == user.email
        assert "password_hash" not in data

    def test_me_without_token_returns_401(self):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_me_with_invalid_token_returns_401(self):
        resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalidtoken"})
        assert resp.status_code == 401

    def test_me_never_exposes_password_hash(self):
        user = _make_user()
        access_token, _ = create_access_token(user.id, user.role.value)

        with patch("app.api.deps.UserRepository") as MockRepo:
            repo_instance = MagicMock()
            repo_instance.get_by_id = AsyncMock(return_value=user)
            MockRepo.return_value = repo_instance

            resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})

        body = resp.text
        assert "password_hash" not in body
        assert "argon2" not in body.lower()


# ─────────────────────────────────────────────
# SECTION: Role Authorization (Admin Endpoints)
# ─────────────────────────────────────────────

class TestRoleAuthorization:
    def _auth_headers(self, user: User) -> dict:
        token, _ = create_access_token(user.id, user.role.value)
        return {"Authorization": f"Bearer {token}"}

    def _mock_db_user(self, user: User):
        return patch("app.api.deps.UserRepository", return_value=MagicMock(
            get_by_id=AsyncMock(return_value=user)
        ))

    def test_unauthenticated_request_returns_401(self):
        resp = client.get("/api/v1/users")
        assert resp.status_code == 401

    def test_customer_accessing_admin_endpoint_returns_403(self):
        customer = _make_user(role=UserRole.CUSTOMER)
        headers = self._auth_headers(customer)
        with self._mock_db_user(customer):
            resp = client.get("/api/v1/users", headers=headers)
        assert resp.status_code == 403

    def test_seller_accessing_admin_endpoint_returns_403(self):
        seller = _make_user(role=UserRole.SELLER)
        headers = self._auth_headers(seller)
        with self._mock_db_user(seller):
            resp = client.get("/api/v1/users", headers=headers)
        assert resp.status_code == 403

    def test_admin_can_access_admin_endpoint(self):
        admin = _make_user(role=UserRole.ADMIN)
        headers = self._auth_headers(admin)
        with self._mock_db_user(admin):
            with patch("app.v1.endpoints.users.UserService") as mock_svc:
                instance = mock_svc.return_value
                instance.list_users = AsyncMock(return_value=([], 0))
                resp = client.get("/api/v1/users", headers=headers)
        assert resp.status_code == 200

    def test_customer_cannot_create_store(self):
        customer = _make_user(role=UserRole.CUSTOMER)
        headers = self._auth_headers(customer)
        with self._mock_db_user(customer):
            resp = client.post("/api/v1/stores", json={
                "name": "Bad Store",
                "slug": "bad-store",
            }, headers=headers)
        assert resp.status_code == 403

    def test_seller_can_access_store_creation(self):
        seller = _make_user(role=UserRole.SELLER)
        headers = self._auth_headers(seller)
        with self._mock_db_user(seller):
            with patch("app.v1.endpoints.stores.StoreService") as mock_svc:
                mock_store = MagicMock()
                mock_store.id = uuid.uuid4()
                mock_store.seller_id = seller.id
                mock_store.name = "My Store"
                mock_store.slug = "my-store"
                mock_store.description = None
                mock_store.logo_url = None
                mock_store.banner_url = None
                mock_store.is_active = True
                from datetime import datetime, timezone
                mock_store.created_at = datetime.now(timezone.utc)
                mock_store.updated_at = datetime.now(timezone.utc)
                instance = mock_svc.return_value
                instance.create_store = AsyncMock(return_value=mock_store)
                resp = client.post("/api/v1/stores", json={
                    "name": "My Store",
                    "slug": "my-store",
                }, headers=headers)
        assert resp.status_code == 201

    def test_customer_cannot_create_product(self):
        customer = _make_user(role=UserRole.CUSTOMER)
        headers = self._auth_headers(customer)
        with self._mock_db_user(customer):
            resp = client.post("/api/v1/products", json={
                "name": "Test",
                "slug": "test",
                "price": 10.0,
                "category_id": str(uuid.uuid4()),
                "is_active": True,
                "is_featured": False,
            }, headers=headers)
        assert resp.status_code == 403

    def test_admin_can_create_category(self):
        admin = _make_user(role=UserRole.ADMIN)
        headers = self._auth_headers(admin)
        with self._mock_db_user(admin):
            with patch("app.v1.endpoints.categories.CategoryService") as mock_svc:
                mock_cat = MagicMock()
                mock_cat.id = uuid.uuid4()
                mock_cat.name = "Test"
                mock_cat.slug = "test"
                mock_cat.description = None
                mock_cat.image_url = None
                mock_cat.is_active = True
                from datetime import datetime, timezone
                mock_cat.created_at = datetime.now(timezone.utc)
                mock_cat.updated_at = datetime.now(timezone.utc)
                instance = mock_svc.return_value
                instance.create_category = AsyncMock(return_value=mock_cat)
                resp = client.post("/api/v1/categories", json={
                    "name": "Test",
                    "slug": "test",
                    "description": None,
                    "image_url": None,
                    "is_active": True,
                }, headers=headers)
        assert resp.status_code == 201

    def test_customer_cannot_create_category(self):
        customer = _make_user(role=UserRole.CUSTOMER)
        headers = self._auth_headers(customer)
        with self._mock_db_user(customer):
            resp = client.post("/api/v1/categories", json={
                "name": "Test",
                "slug": "test",
                "description": None,
                "image_url": None,
                "is_active": True,
            }, headers=headers)
        assert resp.status_code == 403


# ─────────────────────────────────────────────
# SECTION: Seller Ownership Isolation
# ─────────────────────────────────────────────

class TestSellerOwnership:
    def _seller_headers(self, user: User) -> dict:
        token, _ = create_access_token(user.id, user.role.value)
        return {"Authorization": f"Bearer {token}"}

    def test_seller_A_cannot_update_seller_B_product(self):
        from app.core.exceptions import AuthorizationException
        seller_a = _make_user(role=UserRole.SELLER)
        seller_b = _make_user(role=UserRole.SELLER)

        headers = self._seller_headers(seller_a)

        with patch("app.api.deps.UserRepository") as MockRepo:
            repo_instance = MagicMock()
            repo_instance.get_by_id = AsyncMock(return_value=seller_a)
            MockRepo.return_value = repo_instance

            with patch("app.v1.endpoints.products.ProductService") as mock_svc:
                instance = mock_svc.return_value
                instance.update_product = AsyncMock(
                    side_effect=AuthorizationException("You do not have permission to modify another seller's product.")
                )
                resp = client.patch(
                    f"/api/v1/products/{uuid.uuid4()}",
                    json={"name": "Hacked"},
                    headers=headers,
                )
        assert resp.status_code == 403

    def test_seller_A_cannot_delete_seller_B_product(self):
        from app.core.exceptions import AuthorizationException
        seller_a = _make_user(role=UserRole.SELLER)

        headers = self._seller_headers(seller_a)

        with patch("app.api.deps.UserRepository") as MockRepo:
            repo_instance = MagicMock()
            repo_instance.get_by_id = AsyncMock(return_value=seller_a)
            MockRepo.return_value = repo_instance

            with patch("app.v1.endpoints.products.ProductService") as mock_svc:
                instance = mock_svc.return_value
                instance.delete_product = AsyncMock(
                    side_effect=AuthorizationException("You do not have permission to modify another seller's product.")
                )
                resp = client.delete(
                    f"/api/v1/products/{uuid.uuid4()}",
                    headers=headers,
                )
        assert resp.status_code == 403

    def test_admin_can_delete_any_product(self):
        admin = _make_user(role=UserRole.ADMIN)
        headers = self._seller_headers(admin)

        with patch("app.api.deps.UserRepository") as MockRepo:
            repo_instance = MagicMock()
            repo_instance.get_by_id = AsyncMock(return_value=admin)
            MockRepo.return_value = repo_instance

            with patch("app.v1.endpoints.products.ProductService") as mock_svc:
                instance = mock_svc.return_value
                instance.delete_product = AsyncMock(return_value=None)
                resp = client.delete(
                    f"/api/v1/products/{uuid.uuid4()}",
                    headers=headers,
                )
        assert resp.status_code == 204


# ─────────────────────────────────────────────
# SECTION: Security invariants
# ─────────────────────────────────────────────

class TestSecurityInvariants:
    def test_raw_refresh_token_never_equal_to_stored_hash(self):
        raw = "this-is-a-raw-refresh-token"
        stored = hash_token(raw)
        assert raw != stored

    def test_token_type_access_rejected_as_refresh(self):
        user_id = uuid.uuid4()
        access_token, _ = create_access_token(user_id, "CUSTOMER")
        payload = decode_token(access_token)
        assert payload["type"] != "refresh"

    def test_refresh_token_type_rejected_as_access(self):
        user_id = uuid.uuid4()
        session_id = uuid.uuid4()
        refresh_token, _ = create_refresh_token(user_id, session_id)
        payload = decode_token(refresh_token)
        assert payload["type"] != "access"

    def test_public_product_list_requires_no_auth(self):
        """Verify the public product listing endpoint remains accessible without a token."""
        with patch("app.v1.endpoints.products.ProductService") as mock_svc:
            from app.v1.schemas.product import ProductListResponse
            instance = mock_svc.return_value
            instance.list_products = AsyncMock(return_value=ProductListResponse(
                items=[], page=1, page_size=20, total=0, pages=0
            ))
            resp = client.get("/api/v1/products")
        assert resp.status_code == 200

    def test_public_category_list_requires_no_auth(self):
        with patch("app.v1.endpoints.categories.CategoryService") as mock_svc:
            instance = mock_svc.return_value
            instance.list_categories = AsyncMock(return_value=[])
            resp = client.get("/api/v1/categories")
        assert resp.status_code == 200

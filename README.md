# FREPPING - Backend Service

FastAPI e-commerce backend service for FREPPING.

## Environment Configuration

Configure your database and Redis settings in `.env`:

```env
# Database Configuration
DB_USER=postgres
DB_PASSWORD=root
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=db_freepping

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# CORS Configuration
CORS_ORIGINS=["http://localhost:4200"]
```

## Running the Service

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Running Migrations

```bash
alembic upgrade head
```

## Running Tests

```bash
pytest -v
```

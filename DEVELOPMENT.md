# FREPPING — Full-Stack Developer Guide

> Two clean, independent environments: **LOCAL** and **PRODUCTION**.

---

## Architecture

### Local (Development)

```
Developer
  ↓
Angular  http://localhost:4200   (ng serve)
  ↓
FastAPI  http://localhost:8000   (uvicorn)
  ↓
Local PostgreSQL  db_freepping
```

### Production

```
User
  ↓
Angular  https://freepping.netlify.app   (Netlify)
  ↓
FastAPI  https://freepping-backend.onrender.com   (Render)
  ↓
Supabase PostgreSQL  (Session Pooler, IPv4)
```

---

## Quick Start — LOCAL

### Prerequisites

- Python 3.10+
- PostgreSQL running locally (`db_freepping` database created)
- Node.js 18+ and Angular CLI (`npm install -g @angular/cli`)
- Redis (optional but recommended)

### 1. Backend

```bash
cd "freepping app"

# Copy and configure local environment
cp .env.example .env
# Edit .env — set DATABASE_URL to your local PostgreSQL

# Install dependencies
pip install -r requirements.txt

# Run migrations against local PostgreSQL
alembic upgrade head

# Start FastAPI
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend available at: http://127.0.0.1:8000  
Swagger docs: http://127.0.0.1:8000/docs

### 2. Frontend

```bash
cd frepping

npm install

# Start Angular (uses environment.ts → localhost:8000)
ng serve
```

Frontend available at: http://localhost:4200

---

## Environment Variables

### Backend — Local `.env`

```env
APP_ENV=development
DEBUG=true

DATABASE_URL=postgresql://postgres:YOUR_LOCAL_PASSWORD@127.0.0.1:5432/db_freepping

FRONTEND_URL=http://localhost:4200
CORS_ORIGINS=["http://localhost:4200"]

JWT_SECRET_KEY=dev-secret-key-change-this-in-production-32chars
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
```

### Backend — Production (Set in Render Dashboard)

```env
APP_ENV=production
DEBUG=false

DATABASE_URL=postgresql://postgres.hvbixuqzrtuijnxnjiwm:YOUR_PASSWORD@aws-0-eu-west-1.pooler.supabase.com:5432/postgres

FRONTEND_URL=https://freepping.netlify.app
CORS_ORIGINS=["https://freepping.netlify.app"]

JWT_SECRET_KEY=<generate with: openssl rand -hex 32>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
```

---

## Frontend Environment Files

| File | Used By | API Target |
|------|---------|------------|
| `src/environments/environment.ts` | `ng serve` | `http://localhost:8000/api/v1` |
| `src/environments/environment.prod.ts` | `ng build --configuration production` | `https://freepping-backend.onrender.com/api/v1` |

**Local build:**
```bash
ng serve
# Calls: http://localhost:8000
```

**Production build:**
```bash
ng build --configuration production
# Calls: https://freepping-backend.onrender.com
```

---

## Production Deployment

### Render (Backend)

1. Connect your `freepping-backend` GitHub repo to Render.
2. Set the environment variables listed above in **Render Dashboard → Environment**.
3. Build Command:
   ```bash
   pip install -r requirements.txt && alembic upgrade head
   ```
4. Start Command:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```

### Netlify (Frontend)

1. Connect your `frepping` GitHub repo to Netlify.
2. Build Command: `ng build --configuration production`
3. Publish Directory: `dist/frepping`

---

## Database Migrations

### Local

```bash
# Apply all pending migrations to local PostgreSQL
alembic upgrade head

# Check current revision
alembic current

# Generate a new migration (after model changes)
alembic revision --autogenerate -m "description"
```

### Production (Supabase)

Migrations run automatically on Render during the build step:
```bash
alembic upgrade head
```

To run manually against Supabase from your machine:
```bash
# Temporarily set DATABASE_URL in .env to the Supabase Session Pooler URL
DATABASE_URL=postgresql://postgres.hvbixuqzrtuijnxnjiwm:PASSWORD@aws-0-eu-west-1.pooler.supabase.com:5432/postgres

alembic upgrade head

# Then restore .env to local config
```

---

## Verify Connectivity

### Local health check

```bash
curl http://localhost:8000/api/v1/health
# Expected: {"status": "ok", "database": "ok"}
```

### Database check script

```bash
python scripts/check_db.py
```

---

## Security Rules

| Rule | Detail |
|------|--------|
| `.env` is gitignored | Local credentials never committed |
| `.env.*` is gitignored | No accidental staging env commits |
| `.env.example` is safe | Contains only placeholders |
| Production secrets live in Render | Never in source code |
| CORS is environment-driven | No production domains hardcoded in code |
| Supabase password not in Angular | Frontend has no database credentials |

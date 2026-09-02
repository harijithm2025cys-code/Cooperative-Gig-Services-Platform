# Cooperative Gig Services Platform - FastAPI Backend 🚀

A production-ready **FastAPI** backend powering a fair, transparent gig marketplace connecting households needing home and care services with skilled workers verified through **Labour Cooperative Societies**.

---

## 🌟 Key Capabilities & Features

- 🏛️ **Cooperative Federation Verification**: Workers are authenticated and organized under registered Labour Cooperative Societies, ensuring fair wages, social security, and verified credentials.
- 🔐 **Secure JWT Authentication & RBAC**: Role-Based Access Control (`household`, `worker`, `admin`) with bcrypt password hashing and Bearer tokens.
- ⚡ **Multi-Factor Weighted Matching Engine**: Decoupled, unit-tested matching engine in `app/services/matching.py` that computes worker suitability based on skill, proximity, rating, and load balancing.
- 🔄 **Booking Lifecycle State Machine**: Full lifecycle tracking (`pending` ➔ `accepted` ➔ `in_progress` [check-in timestamp] ➔ `completed` [check-out timestamp] / `cancelled`).
- ⭐ **Dynamic Rating Aggregator**: Two-way reviews that automatically recalculate and update worker reputation metrics.
- 📊 **Cooperative Admin & Analytics**: Society-level worker rosters, booking status distributions, and active workforce statistics.
- ☁️ **Cloud & Render Ready**: Includes `Procfile`, environment loaders, CORS support, and automatic OpenAPI documentation at `/docs`.

---

## 📐 Matching Engine Formula

Implemented in isolated module [`app/services/matching.py`](app/services/matching.py):

$$\text{Score} = (\text{skill\_match} \times 50) + \max(0, 20 - \text{distance\_km}) + (\text{rating} \times 5) - (\text{active\_bookings} \times 3)$$

| Factor | Weight / Formula | Purpose |
|---|---|---|
| **Skill Match** | $+50\text{ pts}$ (if matches), $0\text{ pts}$ otherwise | Prioritizes required vocational expertise |
| **Proximity** | $\max(0, 20 - \text{distance\_km})\text{ pts}$ | Prioritizes nearby workers up to 20 km |
| **Rating** | $\text{rating} \times 5\text{ pts}$ (up to $25\text{ pts}$) | Rewards high-quality customer satisfaction |
| **Workload Balancing** | $-(\text{active\_bookings} \times 3)\text{ pts}$ | Prevents worker overload & promotes fair job distribution |

---

## 📁 Project Architecture

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI application entrypoint, CORS, routers & exception handlers
│   ├── config.py                # Environment configuration (SUPABASE_URL, SUPABASE_KEY, JWT_SECRET)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── security.py          # Password hashing, JWT creation & token verification
│   │   └── dependencies.py      # Auth & DB dependency injection (get_current_user, require_role)
│   ├── db/
│   │   ├── __init__.py
│   │   └── supabase_client.py   # Supabase client dependency provider
│   ├── models/                  # Pydantic v2 schemas for all requests & responses
│   │   ├── __init__.py
│   │   ├── auth.py              # UserRegister, UserLogin, Token, UserMeResponse
│   │   ├── worker.py            # WorkerResponse, WorkerAvailabilityUpdate, WorkerDetailResponse
│   │   ├── booking.py           # BookingCreate, BookingStatusUpdate, BookingResponse
│   │   ├── matching.py          # MatchedWorker, MatchScoreBreakdown, MatchResponse
│   │   ├── rating.py            # RatingCreate, RatingResponse, WorkerRatingsSummaryResponse
│   │   └── admin.py             # AdminStatsResponse, CooperativeWorkersResponse
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py              # /auth/register, /auth/login, /auth/me
│   │   ├── workers.py           # /workers/available, /workers/{id}, /workers/{id}/availability
│   │   ├── bookings.py          # /bookings/, /bookings/{id}, /bookings/{id}/status, household/worker lists
│   │   ├── matching.py          # /match/{booking_request_id}
│   │   ├── ratings.py           # /ratings/, /ratings/worker/{worker_id}
│   │   ├── admin.py             # /admin/cooperative/{id}/workers, /admin/stats
│   │   └── health.py            # /health, /
│   └── services/
│       ├── __init__.py
│       └── matching.py          # Pure Python matching algorithm & ranking function
├── main.py                      # Root proxy delegating to app.main:app
├── Procfile                     # Web process definition for Render/Heroku
├── requirements.txt             # Project dependencies
├── test_matching.py             # Verification test suite for matching engine
├── .env                         # Environment variables
└── README.md
```

---

## 🗄️ Supabase PostgreSQL Database Schema

The backend directly integrates with the following existing tables:

- **`users`**: `id`, `email`, `phone`, `role` (`household` \| `worker` \| `admin`), `created_at`
- **`cooperatives`**: `id`, `name`, `district`, `federation_id`, `verified`
- **`workers`**: `id`, `user_id` (FK), `cooperative_id` (FK), `skill`, `service_area`, `rating`, `availability`, `verified_status`, `latitude`, `longitude`
- **`households`**: `id`, `user_id` (FK), `address`, `latitude`, `longitude`
- **`services`**: `id`, `name`, `category`, `base_price`
- **`bookings`**: `id`, `household_id` (FK), `worker_id` (FK), `service_id` (FK), `status` (`pending`, `accepted`, `in_progress`, `completed`, `cancelled`), `scheduled_time`, `created_at`, `check_in_time`, `check_out_time`
- **`ratings`**: `id`, `booking_id` (FK), `rating` (1-5), `review_text`, `created_at`

---

## 🚀 Quickstart & Local Setup

### 1. Environment Setup
Make sure Python 3.11+ is installed. Create and activate a virtual environment:

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure `.env`
Ensure `.env` in the `backend/` directory contains:
```env
SUPABASE_URL=https://<your-project-id>.supabase.co
SUPABASE_KEY=<your-supabase-service-role-or-anon-key>
JWT_SECRET=super_secret_cooperative_gig_platform_key_2026_sih
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
```

### 4. Run Development Server
```bash
uvicorn app.main:app --reload --port 8000
```

Open your browser to explore interactive OpenAPI documentation:
- 📖 **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- 📑 **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- 🩺 **Health Check**: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

---

## 🌐 Deploying to Render

This repository is pre-configured for zero-configuration deployment to [Render](https://render.com):

1. Create a new **Web Service** on Render connected to this repository.
2. Set the **Root Directory** to `backend` (or run from root).
3. Set **Environment** to `Python 3`.
4. Configure Build and Start commands:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Add the Environment Variables (`SUPABASE_URL`, `SUPABASE_KEY`, `JWT_SECRET`) in the Render Dashboard.

---

## 📚 API Endpoints Summary

### 1. Authentication (`/auth`)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/auth/register` | Register new household or worker user with initial profile |
| `POST` | `/auth/login` | Authenticate with email/phone & password, returns JWT |
| `GET` | `/auth/me` | Fetch currently logged-in user profile and cooperative data |

### 2. Workers (`/workers`)
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/workers/available` | Filter available workers by `skill`, `lat`, `lng`, `radius` |
| `GET` | `/workers/{id}` | Get full worker profile, cooperative details & recent reviews |
| `PATCH` | `/workers/{id}/availability` | Toggle worker availability (`true`/`false`) |

### 3. Bookings (`/bookings`)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/bookings/` | Create a new service booking request |
| `GET` | `/bookings/{id}` | Get booking details with household, worker & service metadata |
| `PATCH` | `/bookings/{id}/status` | Update booking status (`accept`, `check_in`, `complete`, etc.) |
| `GET` | `/bookings/household/{household_id}` | List all bookings for a household |
| `GET` | `/bookings/worker/{worker_id}` | List all bookings for a worker |

### 4. Matching Engine (`/match`)
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/match/{booking_request_id}` | Returns ranked list of candidate workers with score breakdown |

### 5. Ratings & Reviews (`/ratings`)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/ratings/` | Submit 1-5 star review (auto-updates worker average rating) |
| `GET` | `/ratings/worker/{worker_id}` | Get all reviews and overall score for a worker |

### 6. Cooperative Admin & Stats (`/admin`)
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/admin/cooperative/{id}/workers` | List all workers registered under a specific Cooperative |
| `GET` | `/admin/stats` | Platform metrics (booking counts by status, active workers) |

---

## 🧪 Testing the Matching Algorithm

Run the matching engine verification suite:
```bash
python test_matching.py
```
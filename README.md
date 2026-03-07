# Resale Rat

A full-stack web application for detecting and predicting fashion resale trend cycles, and classifying vintage garments by era. Built with React, FastAPI, SQLite, and Claude AI.

---

## What It Does

**Trend Forecast** — Aggregates search demand, pricing, and social signals across Google Trends, eBay, Etsy, Poshmark, Reddit, and News. Computes composite trend scores, detects lifecycle stages (Emerging → Accelerating → Peak → Saturation → Decline → Dormant → Revival), forecasts 30-day rankings, and surfaces garments to source for each trending keyword.

**Vintage** — Browse all 24 fashion eras (1700s–2000s) with style profiles, moodboard photos, and market pricing data. Classify any vintage garment by era using descriptor chips and/or uploaded photos, powered by Claude Sonnet 4.6's vision API.

**Stella** — An in-app AI chatbot (Claude Haiku) that interprets trend data, explains lifecycle stages, and answers fashion sourcing questions in context.

---

## Stack

| Layer | Tech |
|-------|------|
| Frontend | React 18 + Vite, Recharts, plain CSS |
| Backend | FastAPI (Python 3.11), APScheduler, SQLite |
| Auth | JWT (python-jose) + bcrypt, CSV user store |
| AI | Anthropic API — Claude Sonnet 4.6 (classifier) + Claude Haiku 4.5 (Stella) |
| Deployment | Docker Compose (two containers: Nginx + FastAPI) |

---

## Getting Started

### Prerequisites

- Docker + Docker Compose
- API keys (see Environment Variables below)

### Run

```bash
git clone <repo>
cd cs667

# Copy and fill in your API keys
cp .env.example .env

docker compose up --build
```

App is available at **http://localhost**.

### Environment Variables

Set these in a `.env` file at the project root (or pass directly to Docker Compose):

| Variable | Required | Description |
|----------|----------|-------------|
| `JWT_SECRET` | Yes | Secret key for signing JWT tokens |
| `ANTHROPIC_API_KEY` | Yes | Powers the garment classifier + Stella chatbot |
| `EBAY_APP_ID` | Yes | eBay Browse API — pricing data |
| `EBAY_CERT_ID` | Yes | eBay OAuth credentials |
| `ETSY_API_KEY` | Yes | Etsy v3 API — listing data |
| `REDDIT_CLIENT_ID` | Optional | Reddit mention tracking |
| `REDDIT_CLIENT_SECRET` | Optional | Reddit mention tracking |
| `PEXELS_API_KEY` | Optional | Fallback product images |
| `GOOGLE_CSE_API_KEY` | Optional | Google Custom Search images |
| `GOOGLE_CSE_CX` | Optional | Google Custom Search engine ID |

---

## Data Sources

| Source | Data Collected |
|--------|----------------|
| Google Trends | Search volume over time, US state + global region breakdowns |
| eBay Browse API | Average sold price, listing count |
| Etsy API v3 | Average price, listing count |
| Poshmark (HTML) | Listing count, prices |
| Reddit JSON API | Mention count across 6 fashion subreddits |
| Google News RSS | News mention count |
| Pinterest | Moodboard images for era pages + keyword trend cards |

Scraping runs on a background schedule via APScheduler:

| Job | Interval |
|-----|----------|
| Scrape all sources + compute scores | Every 6 hours |
| Catchup Google Trends (fill missing data) | Every 6 hours, offset +2h |
| Auto-discover new keywords | Every 24 hours |
| Expire stale user-added keywords | Every 24 hours |
| Refine keyword scale classifications | Every 7 days |

---

## Running Tests

Tests live in `tests/` and run inside the backend container. All external API calls are mocked.

```bash
# Install pytest (run once after each container rebuild)
docker exec cs667-backend-1 pip install pytest

# Run the full suite
docker exec -w /app cs667-backend-1 python -m pytest tests/ -v
```

**88 tests, 0 failures** across auth, chat, all scrapers, trends API, and vintage API.

---

## Project Structure

```
cs667/
├── frontend/
│   ├── src/
│   │   ├── components/        # React components
│   │   ├── hooks/useAuth.jsx  # JWT auth context
│   │   └── services/api.js    # Axios + Bearer token interceptor
│   ├── nginx.conf
│   └── Dockerfile
├── backend/
│   ├── app/
│   │   ├── auth/              # Register, login, JWT validation
│   │   ├── trends/            # Trend scoring, keyword management, sourcing
│   │   ├── chat/              # Stella chatbot (Claude Haiku)
│   │   ├── vintage/           # Era browser, garment classifier (Claude Sonnet)
│   │   ├── scrapers/          # One module per data source
│   │   ├── scheduler/         # APScheduler job definitions
│   │   ├── database.py        # SQLite schema + connection helper
│   │   └── config.py          # Pydantic settings from env vars
│   ├── data/                  # Persisted via Docker volume
│   │   ├── trends.db
│   │   ├── users.csv
│   │   └── seed_keywords.json
│   └── Dockerfile
├── tests/                     # pytest suite (88 tests)
├── docs/CREATE/SYSTEM.md      # Full system documentation
├── docker-compose.yml
└── README.md
```

---

## Documentation

Full architecture documentation — including Mermaid diagrams for the system architecture, data pipeline, database schema, frontend routing, and classifier sequence — is in [`docs/CREATE/SYSTEM.md`](docs/CREATE/SYSTEM.md).

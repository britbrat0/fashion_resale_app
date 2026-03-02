import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.auth.router import router as auth_router
from app.trends.router import router as trends_router
from app.compare.router import router as compare_router
from app.chat.router import router as chat_router
from app.vintage.router import router as vintage_router
from app.scrapers.discovery import load_seed_keywords, backfill_scale_classifications
from app.scheduler.jobs import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(title="Fashion Trend Forecaster", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(trends_router)
app.include_router(compare_router)
app.include_router(chat_router)
app.include_router(vintage_router)


@app.on_event("startup")
def startup():
    import threading
    init_db()
    load_seed_keywords()
    start_scheduler()
    threading.Thread(target=backfill_scale_classifications, daemon=True).start()


@app.on_event("shutdown")
def shutdown():
    stop_scheduler()


@app.get("/api/health")
def health_check():
    return {"status": "ok"}

import sqlite3
from app.config import settings

DB_PATH = settings.db_path


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trend_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            source TEXT NOT NULL,
            metric TEXT NOT NULL,
            value REAL NOT NULL,
            region TEXT,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT UNIQUE NOT NULL,
            source TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_searched_at TIMESTAMP
        )
    """)

    # Migrate: add last_searched_at if it doesn't exist yet
    try:
        cursor.execute("ALTER TABLE keywords ADD COLUMN last_searched_at TIMESTAMP")
    except Exception:
        pass  # Column already exists

    # Migrate: add scale (macro/micro) if it doesn't exist yet
    try:
        cursor.execute("ALTER TABLE keywords ADD COLUMN scale TEXT")
    except Exception:
        pass  # Column already exists

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trend_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            period_days INTEGER NOT NULL,
            volume_growth REAL,
            price_growth REAL,
            composite_score REAL,
            lifecycle_stage TEXT,
            computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            keyword TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_email, keyword)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_comparisons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            keyword TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_email, keyword)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_user ON chat_messages(user_email)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trend_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            source TEXT NOT NULL,
            image_url TEXT NOT NULL,
            title TEXT,
            price REAL,
            item_url TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(keyword, image_url)
        )
    """)

    # Migration: add listing_growth column to trend_scores for supply/demand scoring
    try:
        cursor.execute("ALTER TABLE trend_scores ADD COLUMN listing_growth REAL DEFAULT 0.0")
    except Exception:
        pass  # column already exists

    # Migration: add phash column to trend_images for perceptual deduplication
    try:
        cursor.execute("ALTER TABLE trend_images ADD COLUMN phash TEXT")
    except Exception:
        pass  # column already exists

    # Unique constraint to prevent duplicate trend_data rows (enables INSERT OR IGNORE)
    try:
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_trend_data_unique
            ON trend_data(keyword, source, metric, COALESCE(region, ''), recorded_at)
        """)
    except Exception:
        pass  # index may already exist

    # Create indexes for common queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trend_data_keyword ON trend_data(keyword)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trend_data_recorded_at ON trend_data(recorded_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trend_scores_keyword ON trend_scores(keyword)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_keywords_status ON keywords(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trend_images_keyword ON trend_images(keyword)")

    # ── Etsy keyword tags ─────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keyword_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            tag TEXT NOT NULL,
            frequency INTEGER NOT NULL DEFAULT 1,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(keyword, tag)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_keyword_tags_keyword ON keyword_tags(keyword)")

    # ── Classifier validation dataset ─────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS validation_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL DEFAULT 'etsy',
            true_era_id TEXT NOT NULL,
            true_decade TEXT NOT NULL,
            title TEXT NOT NULL,
            tags TEXT,
            price REAL,
            item_url TEXT UNIQUE,
            image_url TEXT,
            scraped_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS validation_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL REFERENCES validation_items(id),
            predicted_era_id TEXT,
            predicted_confidence REAL,
            alternate_era_ids TEXT,
            is_decade_correct INTEGER,
            is_era_correct INTEGER,
            raw_response TEXT,
            computed_at TEXT NOT NULL,
            UNIQUE(item_id)
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_val_items_era ON validation_items(true_era_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_val_results_item ON validation_results(item_id)")

    conn.commit()
    conn.close()

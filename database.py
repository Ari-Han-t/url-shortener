import psycopg2
from psycopg2 import pool
import redis
import os
from dotenv import load_dotenv

load_dotenv()

# PostgreSQL Connection Pool
db_pool = psycopg2.pool.SimpleConnectionPool(1, 20,
    user=os.getenv("POSTGRES_USER", "postgres"),
    password=os.getenv("POSTGRES_PASSWORD", "supersecretpassword"),
    host=os.getenv("POSTGRES_HOST", "postgres"),
    port=os.getenv("POSTGRES_PORT", "5432"),
    database=os.getenv("POSTGRES_DB", "url_shortener")
)

# Redis Client
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis"), 
    port=int(os.getenv("REDIS_PORT", 6379)), 
    db=0, 
    decode_responses=True
)

def init_db():
    conn = db_pool.getconn()
    cursor = conn.cursor()

    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY, 
        username TEXT UNIQUE NOT NULL, 
        password TEXT NOT NULL
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS urls(
        id SERIAL PRIMARY KEY, 
        short_id TEXT UNIQUE NOT NULL, 
        long_url TEXT NOT NULL, 
        clicks INTEGER DEFAULT 0, 
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
        user_id INTEGER REFERENCES users(id)
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS click_events(
        id SERIAL PRIMARY KEY, 
        short_id TEXT REFERENCES urls(short_id), 
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
        ip_address TEXT, 
        user_agent TEXT,
        browser TEXT,
        os TEXT,
        device_type TEXT,
        referer TEXT
    )''')
    
    # Safe migration: Add new columns if they don't exist for existing databases
    cursor.execute('''
    DO $$ 
    BEGIN 
        BEGIN
            ALTER TABLE click_events ADD COLUMN browser TEXT;
        EXCEPTION WHEN duplicate_column THEN NULL;
        END;
        BEGIN
            ALTER TABLE click_events ADD COLUMN os TEXT;
        EXCEPTION WHEN duplicate_column THEN NULL;
        END;
        BEGIN
            ALTER TABLE click_events ADD COLUMN device_type TEXT;
        EXCEPTION WHEN duplicate_column THEN NULL;
        END;
        BEGIN
            ALTER TABLE click_events ADD COLUMN referer TEXT;
        EXCEPTION WHEN duplicate_column THEN NULL;
        END;
    END $$;
    ''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS api_keys(
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        name TEXT NOT NULL,
        key_prefix TEXT NOT NULL,
        key_hash TEXT UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_used_at TIMESTAMP,
        revoked_at TIMESTAMP
    )''')

    # Expiry and edit tracking (idempotent; existing rows keep working with NULLs).
    cursor.execute("ALTER TABLE urls ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ NULL")
    cursor.execute("ALTER TABLE urls ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NULL")
    cursor.execute("ALTER TABLE urls ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now()")

    # Richer, privacy-preserving click metadata (idempotent; old rows keep NULL / false).
    for ddl in (
        "visitor_id TEXT", "country_code TEXT", "country TEXT", "region TEXT", "city TEXT",
        "language TEXT", "locale TEXT", "is_bot BOOLEAN DEFAULT false",
        "utm_source TEXT", "utm_medium TEXT", "utm_campaign TEXT",
        "referrer_host TEXT", "referrer_source TEXT",
    ):
        cursor.execute("ALTER TABLE click_events ADD COLUMN IF NOT EXISTS " + ddl)

    # Random per-day salts for anonymous visitor ids (see clicks.visitor_hash).
    cursor.execute('''CREATE TABLE IF NOT EXISTS daily_salts(
        day DATE PRIMARY KEY,
        salt BYTEA NOT NULL
    )''')

    # OAuth 2.1 authorization server for the MCP endpoint (see oauth.py). Tokens and codes are
    # stored only as SHA-256 hashes.
    cursor.execute('''CREATE TABLE IF NOT EXISTS oauth_clients(
        client_id TEXT PRIMARY KEY,
        client_info TEXT NOT NULL,
        created_at TIMESTAMPTZ DEFAULT now()
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS oauth_pending(
        id TEXT PRIMARY KEY,
        data TEXT NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS oauth_codes(
        code_hash TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        data TEXT NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS oauth_tokens(
        id SERIAL PRIMARY KEY,
        family_id TEXT NOT NULL,
        access_hash TEXT UNIQUE NOT NULL,
        refresh_hash TEXT UNIQUE NOT NULL,
        user_id INTEGER NOT NULL REFERENCES users(id),
        client_id TEXT NOT NULL,
        scope TEXT NOT NULL,
        resource TEXT,
        access_expires_at TIMESTAMPTZ NOT NULL,
        refresh_expires_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ DEFAULT now(),
        last_used_at TIMESTAMPTZ,
        revoked_at TIMESTAMPTZ
    )''')
    cursor.execute('''CREATE INDEX IF NOT EXISTS idx_oauth_tokens_user_client ON oauth_tokens(user_id, client_id)''')
    cursor.execute('''CREATE INDEX IF NOT EXISTS idx_oauth_tokens_family ON oauth_tokens(family_id)''')

    # Performance Indexes
    cursor.execute('''CREATE INDEX IF NOT EXISTS idx_urls_long_url ON urls(long_url)''')
    cursor.execute('''CREATE INDEX IF NOT EXISTS idx_urls_user_id ON urls(user_id)''')
    cursor.execute('''CREATE INDEX IF NOT EXISTS idx_click_events_short_id ON click_events(short_id)''')
    
    cursor.execute('''CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys(user_id)''')
    cursor.execute('''CREATE INDEX IF NOT EXISTS idx_click_events_short_ts ON click_events(short_id, timestamp)''')

    conn.commit()
    cursor.close()
    db_pool.putconn(conn)

def get_db():
    conn = db_pool.getconn()
    try:
        yield conn
    finally:
        db_pool.putconn(conn)


_salt_cache: dict = {}


def get_daily_salt(conn=None) -> bytes:
    """Today's (UTC) random salt, created on first use. Salts older than 2 days are deleted.

    Postgres is the source of truth so every worker shares one salt per day; the
    in-process cache only avoids a query per click.
    """
    import secrets
    from datetime import datetime, timedelta, timezone

    today = datetime.now(timezone.utc).date()
    cached = _salt_cache.get(today)
    if cached:
        return cached
    own = conn is None
    if own:
        conn = db_pool.getconn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO daily_salts (day, salt) VALUES (%s, %s) ON CONFLICT (day) DO NOTHING",
            (today, secrets.token_bytes(32)),
        )
        cursor.execute("DELETE FROM daily_salts WHERE day < %s", (today - timedelta(days=2),))
        cursor.execute("SELECT salt FROM daily_salts WHERE day = %s", (today,))
        salt = bytes(cursor.fetchone()[0])
        conn.commit()
        cursor.close()
    finally:
        if own:
            db_pool.putconn(conn)
    _salt_cache.clear()
    _salt_cache[today] = salt
    return salt

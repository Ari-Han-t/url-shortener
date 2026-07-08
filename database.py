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
    
    # Performance Indexes
    cursor.execute('''CREATE INDEX IF NOT EXISTS idx_urls_long_url ON urls(long_url)''')
    cursor.execute('''CREATE INDEX IF NOT EXISTS idx_urls_user_id ON urls(user_id)''')
    cursor.execute('''CREATE INDEX IF NOT EXISTS idx_click_events_short_id ON click_events(short_id)''')
    
    conn.commit()
    cursor.close()
    db_pool.putconn(conn)

def get_db():
    conn = db_pool.getconn()
    try:
        yield conn
    finally:
        db_pool.putconn(conn)
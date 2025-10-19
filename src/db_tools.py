import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from urllib.parse import urlparse
import os
import logging

logger = logging.getLogger(__name__)

# Connection pool for better performance
connection_pool = None


def create_database_if_not_exists():
    """Create the database if it doesn't exist."""
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    # Parse the database URL
    parsed = urlparse(database_url)
    db_name = parsed.path[1:]  # Remove leading '/'

    if not db_name:
        raise ValueError("No database name specified in DATABASE_URL")

    # Create connection URL to 'postgres' database (always exists)
    admin_url = database_url.replace(f"/{db_name}", "/postgres")

    try:
        # Connect to default 'postgres' database
        conn = psycopg2.connect(admin_url)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        # Check if database exists
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        exists = cursor.fetchone()

        if not exists:
            # Create the database
            # Use identifier to safely quote the database name
            cursor.execute(
                f"CREATE DATABASE {psycopg2.extensions.quote_ident(db_name, conn)}"
            )
            logger.info(f"Database '{db_name}' created successfully")
        else:
            logger.info(f"Database '{db_name}' already exists")

        cursor.close()
        conn.close()

    except psycopg2.Error as e:
        logger.error(f"Error creating database: {e}")
        raise


def init_db_pool():
    """Initialize database connection pool."""
    global connection_pool
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    try:
        connection_pool = psycopg2.pool.SimpleConnectionPool(
            1,
            10,
            database_url,  # min and max connections
        )
        logger.info("Database connection pool created successfully")
    except Exception as e:
        logger.error(f"Error creating connection pool: {e}")
        raise


def get_db_connection():
    """Get a connection from the pool."""
    if connection_pool is None:
        raise Exception("Connection pool not initialized. Call init_db_pool() first.")
    return connection_pool.getconn()


def return_db_connection(conn):
    """Return connection to the pool."""
    if connection_pool:
        connection_pool.putconn(conn)


def close_all_connections():
    """Close all connections in the pool."""
    global connection_pool
    if connection_pool:
        connection_pool.closeall()
        connection_pool = None
        logger.info("All database connections closed")


class DatabaseConnection:
    """Context manager for automatic connection handling."""

    def __init__(self, dict_cursor=True):
        self.conn = None
        self.cursor = None
        self.dict_cursor = dict_cursor

    def __enter__(self):
        self.conn = get_db_connection()
        if self.dict_cursor:
            self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        else:
            self.cursor = self.conn.cursor()
        return self.cursor

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                self.conn.rollback()
                logger.error(f"Database error: {exc_val}")
            else:
                self.conn.commit()
        finally:
            if self.cursor:
                self.cursor.close()
            if self.conn:
                return_db_connection(self.conn)

        # Don't suppress exceptions
        return False


def init_database():
    """Initialize the PostgreSQL database with required tables.

    This is the entry point - it ensures the database exists,
    initializes the pool, and creates tables.
    """
    # Step 1: Create database if it doesn't exist
    create_database_if_not_exists()

    # Step 2: Ensure connection pool is initialized
    if connection_pool is None:
        init_db_pool()

    try:
        with DatabaseConnection() as cursor:
            # Step 3: Create table with proper constraints
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS userdata (
                    id BIGINT NOT NULL PRIMARY KEY,
                    first_name TEXT,
                    last_name TEXT,
                    full_name TEXT,
                    username TEXT,
                    link TEXT,
                    topic TEXT,
                    language TEXT NOT NULL DEFAULT 'en',
                    location TEXT NOT NULL DEFAULT 'US',
                    automatic BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Create indexes for better performance
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_userdata_automatic 
                ON userdata(automatic) WHERE automatic = TRUE
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_userdata_username 
                ON userdata(username) WHERE username IS NOT NULL
            """
            )

            # Index for updated_at if you need to query by time
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_userdata_updated_at 
                ON userdata(updated_at DESC)
            """
            )

            logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise


def save_user_preferences(user_id, user_data, preferences):
    """Save or update user preferences in database."""
    try:
        with DatabaseConnection() as cursor:
            cursor.execute(
                """
                INSERT INTO userdata 
                (id, first_name, last_name, full_name, username, link, 
                 topic, language, location, automatic, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (id) 
                DO UPDATE SET
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    full_name = EXCLUDED.full_name,
                    username = EXCLUDED.username,
                    link = EXCLUDED.link,
                    topic = EXCLUDED.topic,
                    language = EXCLUDED.language,
                    location = EXCLUDED.location,
                    automatic = EXCLUDED.automatic,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            """,
                (
                    user_id,
                    user_data.get("first_name"),
                    user_data.get("last_name"),
                    user_data.get("full_name"),
                    user_data.get("username"),
                    user_data.get("link"),
                    preferences.get("topic"),
                    preferences.get("language", "en"),
                    preferences.get("location", "US"),
                    preferences.get("automatic", False),
                ),
            )
            result = cursor.fetchone()
            logger.info(f"Saved preferences for user {user_id}")
            return result["id"] if result else None
    except Exception as e:
        logger.error(f"Error saving user preferences for user {user_id}: {e}")
        raise


def get_user_preferences(user_id):
    """Get user preferences from database."""
    try:
        with DatabaseConnection() as cursor:
            cursor.execute(
                """
                SELECT topic, language, location, automatic 
                FROM userdata 
                WHERE id = %s
            """,
                (user_id,),
            )
            result = cursor.fetchone()

            if result:
                return {
                    "topic": result["topic"],
                    "language": result["language"],
                    "location": result["location"],
                    "automatic": bool(result["automatic"]),
                }
            return None
    except Exception as e:
        logger.error(f"Error getting user preferences for user {user_id}: {e}")
        raise


def get_users_with_automatic_updates():
    """Get all users who have automatic updates enabled."""
    try:
        with DatabaseConnection() as cursor:
            cursor.execute(
                """
                SELECT id, topic, language, location 
                FROM userdata 
                WHERE automatic = TRUE
                ORDER BY updated_at DESC
            """
            )
            results = cursor.fetchall()

            return [
                {
                    "id": r["id"],
                    "topic": r["topic"],
                    "language": r["language"],
                    "location": r["location"],
                }
                for r in results
            ]
    except Exception as e:
        logger.error(f"Error getting users with automatic updates: {e}")
        raise


def update_automatic_status(user_id, automatic):
    """Update automatic update status for a user."""
    try:
        with DatabaseConnection() as cursor:
            cursor.execute(
                """
                UPDATE userdata 
                SET automatic = %s, updated_at = CURRENT_TIMESTAMP 
                WHERE id = %s
                RETURNING id
            """,
                (automatic, user_id),
            )
            result = cursor.fetchone()
            if result:
                logger.info(f"Updated automatic status for user {user_id}: {automatic}")
                return True
            else:
                logger.warning(
                    f"User {user_id} not found when updating automatic status"
                )
                return False
    except Exception as e:
        logger.error(f"Error updating automatic status for user {user_id}: {e}")
        raise

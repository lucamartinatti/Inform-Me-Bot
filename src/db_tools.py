import sqlite3


# Database setup
DB_NAME = "news_bot.db"


def init_database():
    """Initialize the SQLite database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS userdata (
            id INTEGER NOT NULL PRIMARY KEY UNIQUE,
            first_name TEXT,
            last_name TEXT,
            full_name TEXT,
            username TEXT,
            link TEXT,
            topic TEXT,
            language TEXT,
            location TEXT,
            automatic BOOLEAN
        )
    """
    )

    conn.commit()
    conn.close()
    # logger.info("Database initialized")


def save_user_preferences(user_id, user_data, preferences):
    """Save or update user preferences in database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR REPLACE INTO userdata 
        (id, first_name, last_name, full_name, username, link, topic, language, location, automatic)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            user_id,
            user_data.get("first_name", ""),
            user_data.get("last_name", ""),
            user_data.get("full_name", ""),
            user_data.get("username", ""),
            user_data.get("link", ""),
            preferences.get("topic", ""),
            preferences.get("language", "en"),
            preferences.get("location", "US"),
            preferences.get("automatic", False),
        ),
    )

    conn.commit()
    conn.close()
    # logger.info(f"Saved preferences for user {user_id}")


def get_user_preferences(user_id):
    """Get user preferences from database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT topic, language, location, automatic FROM userdata WHERE id = ?",
        (user_id,),
    )
    result = cursor.fetchone()

    conn.close()

    if result:
        return {
            "topic": result[0],
            "language": result[1],
            "location": result[2],
            "automatic": bool(result[3]),
        }
    return None


def get_users_with_automatic_updates():
    """Get all users who have automatic updates enabled."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, topic, language, location FROM userdata WHERE automatic = 1"
    )
    results = cursor.fetchall()

    conn.close()

    return [
        {"id": r[0], "topic": r[1], "language": r[2], "location": r[3]} for r in results
    ]


def update_automatic_status(user_id, automatic):
    """Update automatic update status for a user."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE userdata SET automatic = ? WHERE id = ?", (automatic, user_id)
    )

    conn.commit()
    conn.close()
    # logger.info(f"Updated automatic status for user {user_id}: {automatic}")

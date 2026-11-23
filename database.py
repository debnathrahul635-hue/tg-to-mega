import sqlite3
from contextlib import contextmanager
from config import Config


class Database:
    def __init__(self, db_path: str = Config.DB_PATH):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    custom_folder TEXT DEFAULT '',
                    is_authorized INTEGER DEFAULT 1,
                    total_uploaded_bytes INTEGER DEFAULT 0,
                    total_files INTEGER DEFAULT 0
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS uploads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    file_name TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    mega_link TEXT NOT NULL,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def get_user(self, user_id: int):
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
            conn.commit()
            return {
                "user_id": user_id,
                "custom_folder": "",
                "is_authorized": 1,
                "total_uploaded_bytes": 0,
                "total_files": 0,
            }

    def set_custom_folder(self, user_id: int, folder_name: str):
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (user_id, custom_folder) VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET custom_folder = excluded.custom_folder
            """,
                (user_id, folder_name.strip()),
            )
            conn.commit()

    def update_stats(self, user_id: int, file_size: int):
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (user_id, total_uploaded_bytes, total_files) VALUES (?, ?, 1)
                ON CONFLICT(user_id) DO UPDATE SET 
                    total_uploaded_bytes = total_uploaded_bytes + excluded.total_uploaded_bytes,
                    total_files = total_files + 1
            """,
                (user_id, file_size),
            )
            conn.commit()

    def save_upload(self, user_id: int, file_name: str, file_size: int, mega_link: str):
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO uploads (user_id, file_name, file_size, mega_link) VALUES (?, ?, ?, ?)",
                (user_id, file_name, file_size, mega_link),
            )
            conn.commit()

    def get_recent_uploads(self, user_id: int, limit: int = 10):
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT file_name, file_size, mega_link, uploaded_at FROM uploads WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_global_stats(self):
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COALESCE(SUM(total_uploaded_bytes), 0) as total_bytes, COALESCE(SUM(total_files), 0) as total_files FROM users"
            )
            return dict(cursor.fetchone())


db = Database()

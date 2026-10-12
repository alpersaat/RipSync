import sqlite3
import os
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any

import threading

from core.paths import get_database_path

DB_PATH = get_database_path()

# Standard category mapping by extensions
CATEGORY_MAP = {
    "Video": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts"],
    "Music": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".alac"],
    "Compressed": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".dmg"],
    "Programs": [".exe", ".msi", ".iso", ".bat", ".cmd", ".apk", ".appimage", ".deb", ".rpm"],
    "Documents": [".pdf", ".docx", ".doc", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".epub", ".csv", ".rtf", ".srt", ".vtt", ".sub", ".ass"]
}

# Subfolder names inside Windows Downloads directory
CATEGORY_FOLDER_NAMES = {
    "Video": "Videolar",
    "Music": "Müzik",
    "Compressed": "Arşivler",
    "Programs": "Programlar",
    "Documents": "Belgeler",
    "Others": ""
}

def detect_category(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    for cat, extensions in CATEGORY_MAP.items():
        if ext in extensions:
            return cat
    return "Others"

def get_category_folder(category: str, base_dir: Optional[str] = None) -> str:
    """
    Returns the target folder for the given category.
    If base_dir is None, defaults to the user's Windows Downloads directory.
    Subfolders created/used:
      - Video ➔ Videolar
      - Music ➔ Müzik
      - Compressed ➔ Arşivler
      - Programs ➔ Programlar
      - Documents ➔ Belgeler
      - Others ➔ (base_dir directly)
    """
    if not base_dir:
        base_dir = os.path.join(os.path.expanduser("~"), "Downloads")

    subfolder = CATEGORY_FOLDER_NAMES.get(category, "")
    if subfolder:
        target_dir = os.path.join(base_dir, subfolder)
    else:
        target_dir = base_dir

    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception:
        pass

    return target_dir

def get_categorized_save_dir(filename: str, base_dir: Optional[str] = None, category: Optional[str] = None) -> str:
    """
    Given a filename or explicit category, resolves and creates the smart categorized target directory.
    """
    cat = category if (category and category != "Otomatik") else detect_category(filename)
    return get_category_folder(cat, base_dir)

class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.lock = threading.RLock()
        self._mem_conn = None
        if self.db_path == ":memory:":
            self._mem_conn = sqlite3.connect(":memory:", check_same_thread=False, timeout=10)
            self._mem_conn.row_factory = sqlite3.Row
        self._init_db()

    def _get_connection(self):
        if self._mem_conn is not None:
            return self._mem_conn
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self.lock:
            with self._get_connection() as conn:
                conn.execute("""
                CREATE TABLE IF NOT EXISTS downloads (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    save_path TEXT NOT NULL,
                    total_size INTEGER DEFAULT -1,
                    downloaded_size INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'Queued',
                    category TEXT DEFAULT 'Others',
                    speed INTEGER DEFAULT 0,
                    eta INTEGER DEFAULT 0,
                    connections INTEGER DEFAULT 8,
                    date_added TEXT,
                    date_completed TEXT,
                    error_message TEXT DEFAULT '',
                    headers_json TEXT DEFAULT '{}',
                    queue_order INTEGER DEFAULT 0
                )
                """)
                try:
                    conn.execute("ALTER TABLE downloads ADD COLUMN queue_order INTEGER DEFAULT 0")
                except sqlite3.OperationalError:
                    pass

                conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """)
                conn.commit()

    def add_download(self, url: str, filename: str, save_path: str, total_size: int = -1,
                     connections: int = 8, category: Optional[str] = None,
                     headers: Optional[Dict[str, str]] = None) -> str:
        download_id = str(uuid.uuid4())
        if not category:
            category = detect_category(filename)
        headers_json = json.dumps(headers or {})
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self.lock:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT COALESCE(MAX(queue_order), 0) + 1 AS next_order FROM downloads")
                row = cur.fetchone()
                next_order = row["next_order"] if row else 1

                conn.execute("""
                INSERT INTO downloads (id, url, filename, save_path, total_size, downloaded_size,
                                       status, category, connections, date_added, headers_json, queue_order)
                VALUES (?, ?, ?, ?, ?, 0, 'Queued', ?, ?, ?, ?, ?)
                """, (download_id, url, filename, save_path, total_size, category, connections, now, headers_json, next_order))
                conn.commit()
        return download_id

    ALLOWED_UPDATE_COLUMNS = {
        "url", "filename", "save_path", "total_size", "downloaded_size",
        "status", "category", "speed", "eta", "connections", "date_added",
        "date_completed", "error_message", "headers_json", "queue_order"
    }

    def update_download(self, download_id: str, **kwargs):
        if not kwargs:
            return
        fields = []
        values = []
        for key, val in kwargs.items():
            if key in self.ALLOWED_UPDATE_COLUMNS:
                fields.append(f"{key} = ?")
                values.append(val)
        if not fields:
            return
        values.append(download_id)

        query = f"UPDATE downloads SET {', '.join(fields)} WHERE id = ?"
        with self.lock:
            with self._get_connection() as conn:
                # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
                conn.execute(query, values)
                conn.commit()

    def get_download(self, download_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT * FROM downloads WHERE id = ?", (download_id,))
                row = cur.fetchone()
                if row:
                    return dict(row)
        return None

    def get_all_downloads(self, category: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM downloads"
        params = []
        conditions = []
        if category and category != "All":
            conditions.append("category = ?")
            params.append(category)
        if status:
            conditions.append("status = ?")
            params.append(status)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY date_added DESC"

        with self.lock:
            with self._get_connection() as conn:
                cur = conn.execute(query, params)
                return [dict(row) for row in cur.fetchall()]

    def delete_download(self, download_id: str):
        with self.lock:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM downloads WHERE id = ?", (download_id,))
                conn.commit()

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.lock:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
                row = cur.fetchone()
                if row:
                    try:
                        return json.loads(row["value"])
                    except Exception:
                        return row["value"]
        return default

    def set_setting(self, key: str, value: Any):
        val_str = json.dumps(value)
        with self.lock:
            with self._get_connection() as conn:
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, val_str))
                conn.commit()

    def get_queued_downloads_ordered(self) -> List[Dict[str, Any]]:
        with self.lock:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT * FROM downloads WHERE status = 'Queued' ORDER BY queue_order ASC, date_added ASC")
                return [dict(row) for row in cur.fetchall()]

    def reorder_download(self, download_id: str, direction: str) -> bool:
        """
        Reorders a download in the queue.
        direction: 'up' (higher priority) or 'down' (lower priority)
        """
        with self.lock:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT id, queue_order FROM downloads WHERE status = 'Queued' ORDER BY queue_order ASC, date_added ASC")
                rows = [dict(r) for r in cur.fetchall()]
                if not rows:
                    return False

                idx = next((i for i, r in enumerate(rows) if r["id"] == download_id), -1)
                if idx == -1:
                    return False

                if direction == "up" and idx > 0:
                    other_idx = idx - 1
                elif direction == "down" and idx < len(rows) - 1:
                    other_idx = idx + 1
                else:
                    return False

                # Swap queue_order values
                curr_item = rows[idx]
                other_item = rows[other_idx]

                # If queue_order values are identical, renumber sequentially first
                if curr_item["queue_order"] == other_item["queue_order"]:
                    for i, r in enumerate(rows, start=1):
                        conn.execute("UPDATE downloads SET queue_order = ? WHERE id = ?", (i * 10, r["id"]))
                    conn.commit()
                    # Reload rows
                    cur = conn.execute("SELECT id, queue_order FROM downloads WHERE status = 'Queued' ORDER BY queue_order ASC, date_added ASC")
                    rows = [dict(r) for r in cur.fetchall()]
                    curr_item = rows[idx]
                    other_item = rows[other_idx]

                curr_order = curr_item["queue_order"]
                other_order = other_item["queue_order"]

                conn.execute("UPDATE downloads SET queue_order = ? WHERE id = ?", (other_order, curr_item["id"]))
                conn.execute("UPDATE downloads SET queue_order = ? WHERE id = ?", (curr_order, other_item["id"]))
                conn.commit()
                return True

    def move_to_top_of_queue(self, download_id: str) -> bool:
        with self.lock:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT COALESCE(MIN(queue_order), 10) - 10 AS top_order FROM downloads WHERE status = 'Queued'")
                row = cur.fetchone()
                top_order = row["top_order"] if row else 0
                conn.execute("UPDATE downloads SET queue_order = ? WHERE id = ?", (top_order, download_id))
                conn.commit()
                return True

    def get_scheduler_settings(self) -> Dict[str, Any]:
        default = {
            "enabled": False,
            "start_time": "02:00",
            "stop_enabled": True,
            "stop_time": "07:00",
            "days": [0, 1, 2, 3, 4, 5, 6],
            "on_stop_action": "pause_all",
            "auto_start_if_in_window": True
        }
        val = self.get_setting("scheduler", None)
        if isinstance(val, dict):
            # Merge with defaults
            merged = dict(default)
            merged.update(val)
            return merged
        return default

    def save_scheduler_settings(self, settings: Dict[str, Any]):
        current = self.get_scheduler_settings()
        current.update(settings)
        self.set_setting("scheduler", current)

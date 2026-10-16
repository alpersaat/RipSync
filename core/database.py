import sqlite3
import os
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any

import threading

from core.paths import get_database_path
from core.categories import (
    CATEGORY_MAP,
    CATEGORY_FOLDER_NAMES,
    detect_category,
    get_category_folder,
    get_categorized_save_dir
)
from core.logger import get_logger
from core.notifier import notify_error

logger = get_logger("database")

DB_PATH = get_database_path()


class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.lock = threading.RLock()
        self._conn = None
        self._init_db()

    @property
    def _mem_conn(self):
        """Geriye dönük uyumluluk için bağlantı referansı."""
        return self._conn

    @_mem_conn.setter
    def _mem_conn(self, val):
        self._conn = val

    def _get_connection(self):
        """
        Tek kalıcı SQLite bağlantısı (persistent connection) döner.
        check_same_thread=False ve threading.RLock ile thread-safe çalışır.
        Dosya tabanlı SQLite için WAL modunu etkinleştirir.
        """
        with self.lock:
            if self._conn is None:
                self._conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
                self._conn.row_factory = sqlite3.Row
                if self.db_path != ":memory:":
                    try:
                        self._conn.execute("PRAGMA journal_mode=WAL;")
                        self._conn.execute("PRAGMA synchronous=NORMAL;")
                        self._conn.execute("PRAGMA busy_timeout=30000;")
                    except Exception as e:
                        logger.debug(f"SQLite PRAGMA optimizasyonları uygulanamadı: {e}")
            return self._conn

    def close(self):
        """Açık olan veritabanı bağlantısını güvenli bir şekilde kapatır."""
        with self.lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception as e:
                    logger.debug(f"Veritabanı bağlantısı kapatılırken hata: {e}")
                finally:
                    self._conn = None

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
                    queue_order INTEGER DEFAULT 0,
                    auto_open INTEGER DEFAULT 0,
                    auto_extract INTEGER DEFAULT 0,
                    priority TEXT DEFAULT 'normal'
                )
                """)
                columns_to_add = [
                    ("queue_order", "INTEGER DEFAULT 0"),
                    ("auto_open", "INTEGER DEFAULT 0"),
                    ("auto_extract", "INTEGER DEFAULT 0"),
                    ("priority", "TEXT DEFAULT 'normal'"),
                    ("tags", "TEXT DEFAULT ''"),
                    ("queue_id", "TEXT DEFAULT 'default'"),
                ]
                for col_name, col_type in columns_to_add:
                    try:
                        conn.execute(f"ALTER TABLE downloads ADD COLUMN {col_name} {col_type}")
                    except sqlite3.OperationalError as e:
                        if "duplicate column name" in str(e).lower():
                            logger.debug(f"Sütun zaten mevcut: {col_name}")
                        else:
                            logger.warning(f"Sütun eklenirken uyarı ({col_name}): {e}")

                conn.execute("""
                CREATE TABLE IF NOT EXISTS download_queues (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    max_concurrent INTEGER DEFAULT 2,
                    target_dir TEXT DEFAULT '',
                    is_default INTEGER DEFAULT 0,
                    created_at TEXT
                )
                """)
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                conn.execute("""
                INSERT OR IGNORE INTO download_queues (id, name, max_concurrent, target_dir, is_default, created_at)
                VALUES ('default', 'Ana Kuyruk', 2, '', 1, ?)
                """, (now_str,))

                conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """)
                conn.commit()

    def add_download(self, url: str, filename: str, save_path: str, total_size: int = -1,
                     connections: int = 8, category: Optional[str] = None,
                     headers: Optional[Dict[str, str]] = None, auto_open: bool = False,
                     auto_extract: bool = False, priority: str = "normal", tags: str = "",
                     queue_id: str = "default") -> str:
        download_id = str(uuid.uuid4())
        if not category:
            category = detect_category(filename)
        headers_json = json.dumps(headers or {})
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            with self.lock:
                with self._get_connection() as conn:
                    cur = conn.execute("SELECT COALESCE(MAX(queue_order), 0) + 1 AS next_order FROM downloads")
                    row = cur.fetchone()
                    next_order = row["next_order"] if row else 1

                    conn.execute("""
                    INSERT INTO downloads (id, url, filename, save_path, total_size, downloaded_size,
                                           status, category, connections, date_added, headers_json, queue_order,
                                           auto_open, auto_extract, priority, tags, queue_id)
                    VALUES (?, ?, ?, ?, ?, 0, 'Queued', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (download_id, url, filename, save_path, total_size, category, connections, now,
                          headers_json, next_order, 1 if auto_open else 0, 1 if auto_extract else 0, priority, tags, queue_id or "default"))
                    conn.commit()
            return download_id
        except sqlite3.Error as e:
            logger.error(f"İndirme veritabanına eklenemedi ({filename}): {e}", exc_info=True)
            notify_error("Veritabanı Hatası", f"İndirme kaydedilemedi: {e}")
            raise

    ALLOWED_UPDATE_COLUMNS = {
        "url", "filename", "save_path", "total_size", "downloaded_size",
        "status", "category", "speed", "eta", "connections", "date_added",
        "date_completed", "error_message", "headers_json", "queue_order",
        "auto_open", "auto_extract", "priority", "tags", "queue_id"
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
        try:
            with self.lock:
                with self._get_connection() as conn:
                    # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
                    conn.execute(query, values)
                    conn.commit()
        except sqlite3.Error as e:
            logger.error(f"İndirme veritabanında güncellenemedi ({download_id}): {e}", exc_info=True)
            if "status" not in kwargs or kwargs["status"] != "Error":
                notify_error("Veritabanı Güncelleme Hatası", f"Kayıt güncellenemedi: {e}")

    def update_downloads_batch(self, updates: List[Dict[str, Any]]):
        """
        Birden çok indirme kaydını (özellikle toplu ilerleme güncellemelerini)
        tek bir veritabanı transaction'ı içinde günceller.
        """
        if not updates:
            return
        try:
            with self.lock:
                with self._get_connection() as conn:
                    for item in updates:
                        dl_id = item.get("id")
                        if not dl_id:
                            continue
                        fields = []
                        values = []
                        for key, val in item.items():
                            if key != "id" and key in self.ALLOWED_UPDATE_COLUMNS:
                                fields.append(f"{key} = ?")
                                values.append(val)
                        if fields:
                            values.append(dl_id)
                            query = f"UPDATE downloads SET {', '.join(fields)} WHERE id = ?"
                            conn.execute(query, values)
                    conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Toplu indirme güncellenirken hata oluştu: {e}", exc_info=True)

    def get_download(self, download_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT * FROM downloads WHERE id = ?", (download_id,))
                row = cur.fetchone()
                if row:
                    return dict(row)
        return None

    def get_all_downloads(self, category: Optional[str] = None, status: Optional[str] = None,
                          tag: Optional[str] = None, queue_id: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM downloads"
        params = []
        conditions = []
        if category and category != "All":
            conditions.append("category = ?")
            params.append(category)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if tag:
            conditions.append("(tags LIKE ? OR tags = ?)")
            params.extend([f"%{tag}%", tag])
        if queue_id and queue_id != "all":
            conditions.append("queue_id = ?")
            params.append(queue_id)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY date_added DESC"

        with self.lock:
            with self._get_connection() as conn:
                cur = conn.execute(query, params)
                return [dict(row) for row in cur.fetchall()]

    def get_all_tags(self) -> List[str]:
        """Returns a sorted list of unique tags used across all downloads."""
        tags_set = set()
        with self.lock:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT tags FROM downloads WHERE tags IS NOT NULL AND tags != ''")
                for row in cur.fetchall():
                    raw = row["tags"] or ""
                    for t in raw.split(","):
                        cleaned = t.strip()
                        if cleaned:
                            tags_set.add(cleaned)
        return sorted(list(tags_set))

    def delete_download(self, download_id: str):
        try:
            with self.lock:
                with self._get_connection() as conn:
                    conn.execute("DELETE FROM downloads WHERE id = ?", (download_id,))
                    conn.commit()
        except sqlite3.Error as e:
            logger.error(f"İndirme veritabanından silinemedi ({download_id}): {e}", exc_info=True)
            notify_error("Veritabanı Hatası", f"İndirme kaydı silinemedi: {e}")

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.lock:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
                row = cur.fetchone()
                if row:
                    try:
                        return json.loads(row["value"])
                    except Exception as e:
                        logger.debug(f"Ayar JSON ayrıştırma hatası ({key}): {e}")
                        return row["value"]
        return default

    def set_setting(self, key: str, value: Any):
        val_str = json.dumps(value)
        try:
            with self.lock:
                with self._get_connection() as conn:
                    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, val_str))
                    conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Ayar veritabanına kaydedilemedi ({key}): {e}", exc_info=True)
            notify_error("Ayar Kayıt Hatası", f"Ayar kaydedilemedi: {e}")

    def get_or_create_bridge_token(self) -> str:
        token = self.get_setting("bridge_token")
        if not token:
            import secrets
            token = secrets.token_hex(24)
            self.set_setting("bridge_token", token)
        return token

    def regenerate_bridge_token(self) -> str:
        import secrets
        token = secrets.token_hex(24)
        self.set_setting("bridge_token", token)
        return token

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

    def move_to_bottom_of_queue(self, download_id: str) -> bool:
        with self.lock:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT COALESCE(MAX(queue_order), 0) + 10 AS bottom_order FROM downloads WHERE status = 'Queued'")
                row = cur.fetchone()
                bottom_order = row["bottom_order"] if row else 10
                conn.execute("UPDATE downloads SET queue_order = ? WHERE id = ?", (bottom_order, download_id))
                conn.commit()
                return True

    def get_statistics(self) -> Dict[str, Any]:
        """Calculates download traffic, completion counts, and category statistics."""
        now_date = datetime.now().strftime("%Y-%m-%d")
        with self.lock:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT COUNT(*) AS total_count FROM downloads")
                total_count = cur.fetchone()["total_count"]

                cur = conn.execute("SELECT COUNT(*) AS comp_count, COALESCE(SUM(downloaded_size), 0) AS comp_bytes FROM downloads WHERE status = 'Completed'")
                row_comp = cur.fetchone()
                completed_count = row_comp["comp_count"] if row_comp else 0
                completed_bytes = row_comp["comp_bytes"] if row_comp else 0

                cur = conn.execute("SELECT COUNT(*) AS active_count FROM downloads WHERE status IN ('Downloading', 'Probing', 'Retrying')")
                active_count = cur.fetchone()["active_count"]

                cur = conn.execute("SELECT COUNT(*) AS paused_count FROM downloads WHERE status = 'Paused'")
                paused_count = cur.fetchone()["paused_count"]

                cur = conn.execute("SELECT COUNT(*) AS error_count FROM downloads WHERE status = 'Error'")
                error_count = cur.fetchone()["error_count"]

                cur = conn.execute("SELECT COUNT(*) AS queued_count FROM downloads WHERE status = 'Queued'")
                queued_count = cur.fetchone()["queued_count"]

                cur = conn.execute("SELECT COUNT(*) AS today_count, COALESCE(SUM(downloaded_size), 0) AS today_bytes FROM downloads WHERE status = 'Completed' AND (date_completed LIKE ? OR date_added LIKE ?)", (f"{now_date}%", f"{now_date}%"))
                row_today = cur.fetchone()
                today_count = row_today["today_count"] if row_today else 0
                today_bytes = row_today["today_bytes"] if row_today else 0

                cur = conn.execute("SELECT category, COUNT(*) AS cat_count FROM downloads GROUP BY category")
                cat_rows = cur.fetchall()
                categories = {r["category"]: r["cat_count"] for r in cat_rows}

                return {
                    "total_count": total_count,
                    "completed_count": completed_count,
                    "completed_bytes": completed_bytes,
                    "active_count": active_count,
                    "paused_count": paused_count,
                    "error_count": error_count,
                    "queued_count": queued_count,
                    "today_count": today_count,
                    "today_bytes": today_bytes,
                    "categories": categories
                }


    def get_scheduler_settings(self) -> Dict[str, Any]:
        default = {
            "enabled": False,
            "start_time": "02:00",
            "stop_enabled": True,
            "stop_time": "07:00",
            "days": [0, 1, 2, 3, 4, 5, 6],
            "on_stop_action": "pause_all",
            "auto_start_if_in_window": True,
            "speed_schedule_enabled": False,
            "speed_schedule_start": "09:00",
            "speed_schedule_end": "18:00",
            "speed_schedule_limit_kb": 2048
        }
        val = self.get_setting("scheduler", None)
        if isinstance(val, dict):
            merged = dict(default)
            merged.update(val)
            return merged
        return default

    def save_scheduler_settings(self, settings: Dict[str, Any]):
        current = self.get_scheduler_settings()
        current.update(settings)
        self.set_setting("scheduler", current)

    def get_proxy_settings(self) -> Dict[str, Any]:
        default = {
            "enabled": False,
            "type": "http",  # "http", "https", "socks5"
            "host": "",
            "port": 8080,
            "username": "",
            "password": ""
        }
        val = self.get_setting("proxy", None)
        if isinstance(val, dict):
            merged = dict(default)
            merged.update(val)
            return merged
        return default

    def save_proxy_settings(self, settings: Dict[str, Any]):
        current = self.get_proxy_settings()
        current.update(settings)
        self.set_setting("proxy", current)

    def get_proxy_url(self) -> Optional[str]:
        cfg = self.get_proxy_settings()
        if not cfg.get("enabled") or not cfg.get("host"):
            return None
        ptype = (cfg.get("type") or "http").lower()
        host = cfg.get("host").strip()
        port = cfg.get("port") or 8080
        user = (cfg.get("username") or "").strip()
        pwd = (cfg.get("password") or "").strip()

        if user and pwd:
            import urllib.parse
            safe_user = urllib.parse.quote(user)
            safe_pwd = urllib.parse.quote(pwd)
            return f"{ptype}://{safe_user}:{safe_pwd}@{host}:{port}"
        elif user:
            import urllib.parse
            safe_user = urllib.parse.quote(user)
            return f"{ptype}://{safe_user}@{host}:{port}"
        return f"{ptype}://{host}:{port}"

    def get_theme_settings(self) -> Dict[str, str]:
        default = {
            "theme": "dark",      # "dark", "light"
            "accent": "blue"      # "blue", "emerald", "purple", "amber"
        }
        val = self.get_setting("appearance", None)
        if isinstance(val, dict):
            merged = dict(default)
            merged.update(val)
            return merged
        return default

    def save_theme_settings(self, theme: str = "dark", accent: str = "blue"):
        self.set_setting("appearance", {"theme": theme, "accent": accent})

    def get_conflict_setting(self) -> str:
        """Returns conflict resolution strategy: 'auto_rename', 'overwrite', or 'skip'."""
        return self.get_setting("file_conflict_action", "auto_rename")

    def save_conflict_setting(self, action: str):
        self.set_setting("file_conflict_action", action)

    def get_automation_settings(self) -> Dict[str, Any]:
        default = {
            "command_enabled": False,
            "command": "",
            "webhook_enabled": False,
            "webhook_url": "",
            "webhook_include_filepath": False
        }
        val = self.get_setting("post_download_automation", None)
        if isinstance(val, dict):
            merged = dict(default)
            merged.update(val)
            return merged
        return default

    def save_automation_settings(self, settings: Dict[str, Any]):
        current = self.get_automation_settings()
        current.update(settings)
        self.set_setting("post_download_automation", current)

    # ==========================================
    # Yinelenen (Duplicate) İndirme Koruması
    # ==========================================
    def find_duplicate_download(self, url: Optional[str] = None,
                                filename: Optional[str] = None,
                                save_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Veritabanında aynı URL'ye veya aynı dosya kayıt yoluna sahip mevcut indirmeyi bulur.
        Öncelikle Tamamlanan (Completed) veya indirilmekte/kuyrukta olan kayıtları tercih eder.
        """
        if not url and not save_path and not filename:
            return None

        clean_url = (url or "").strip()
        with self.lock:
            with self._get_connection() as conn:
                if clean_url:
                    cur = conn.execute("""
                        SELECT * FROM downloads 
                        WHERE url = ? 
                        ORDER BY 
                            CASE status 
                                WHEN 'Completed' THEN 1 
                                WHEN 'Downloading' THEN 2 
                                WHEN 'Queued' THEN 3 
                                ELSE 4 
                            END, 
                            date_added DESC 
                        LIMIT 1
                    """, (clean_url,))
                    row = cur.fetchone()
                    if row:
                        return dict(row)

                if save_path:
                    cur = conn.execute("""
                        SELECT * FROM downloads 
                        WHERE save_path = ? 
                        ORDER BY date_added DESC 
                        LIMIT 1
                    """, (save_path,))
                    row = cur.fetchone()
                    if row:
                        return dict(row)

                if filename:
                    cur = conn.execute("""
                        SELECT * FROM downloads 
                        WHERE filename = ? 
                        ORDER BY 
                            CASE status 
                                WHEN 'Completed' THEN 1 
                                WHEN 'Downloading' THEN 2 
                                ELSE 3 
                            END,
                            date_added DESC 
                        LIMIT 1
                    """, (filename,))
                    row = cur.fetchone()
                    if row:
                        return dict(row)
        return None

    def get_duplicate_warning_setting(self) -> bool:
        return bool(self.get_setting("warn_duplicate_downloads", True))

    def save_duplicate_warning_setting(self, val: bool):
        self.set_setting("warn_duplicate_downloads", bool(val))

    # ==========================================
    # Çoklu Kuyruk (Multi-Queue) Yönetimi
    # ==========================================
    def get_all_queues(self) -> List[Dict[str, Any]]:
        with self.lock:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT * FROM download_queues ORDER BY is_default DESC, name ASC")
                return [dict(row) for row in cur.fetchall()]

    def add_queue(self, name: str, max_concurrent: int = 2, target_dir: str = "") -> str:
        queue_id = str(uuid.uuid4())
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.lock:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO download_queues (id, name, max_concurrent, target_dir, is_default, created_at)
                    VALUES (?, ?, ?, ?, 0, ?)
                """, (queue_id, name.strip(), max(1, max_concurrent), target_dir.strip(), now))
                conn.commit()
        return queue_id

    def update_queue(self, queue_id: str, **kwargs):
        if not kwargs:
            return
        name = kwargs.get("name")
        max_concurrent = kwargs.get("max_concurrent")
        target_dir = kwargs.get("target_dir")

        with self.lock:
            with self._get_connection() as conn:
                if name is not None:
                    conn.execute("UPDATE download_queues SET name = ? WHERE id = ?", (str(name), queue_id))
                if max_concurrent is not None:
                    conn.execute("UPDATE download_queues SET max_concurrent = ? WHERE id = ?", (int(max_concurrent), queue_id))
                if target_dir is not None:
                    conn.execute("UPDATE download_queues SET target_dir = ? WHERE id = ?", (str(target_dir), queue_id))
                conn.commit()

    def delete_queue(self, queue_id: str) -> bool:
        if queue_id == "default":
            return False
        with self.lock:
            with self._get_connection() as conn:
                conn.execute("UPDATE downloads SET queue_id = 'default' WHERE queue_id = ?", (queue_id,))
                conn.execute("DELETE FROM download_queues WHERE id = ? AND is_default = 0", (queue_id,))
                conn.commit()
        return True

    def get_queue(self, queue_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT * FROM download_queues WHERE id = ?", (queue_id,))
                row = cur.fetchone()
                return dict(row) if row else None

    def move_download_to_queue(self, download_id: str, queue_id: str):
        with self.lock:
            with self._get_connection() as conn:
                conn.execute("UPDATE downloads SET queue_id = ? WHERE id = ?", (queue_id, download_id))
                conn.commit()

    # ==========================================
    # Pano (Clipboard) Akıllı Kuralları & Kara Liste
    # ==========================================
    def get_clipboard_settings(self) -> Dict[str, Any]:
        default = {
            "enabled": False,
            "only_media": False,
            "ignore_domains": ["google.com", "bing.com", "yandex.com", "duckduckgo.com", "localhost", "127.0.0.1"],
            "prompted": False
        }
        val = self.get_setting("clipboard_config", None)
        if isinstance(val, dict):
            merged = dict(default)
            merged.update(val)
            return merged
        # Backward compatibility check for simple boolean clipboard_enabled
        old_en = self.get_setting("clipboard_enabled", None)
        if old_en is not None:
            default["enabled"] = bool(old_en)
        old_prompted = self.get_setting("clipboard_prompted", None)
        if old_prompted is not None:
            default["prompted"] = bool(old_prompted)
        return default

    def save_clipboard_settings(self, settings: Dict[str, Any]):
        current = self.get_clipboard_settings()
        current.update(settings)
        self.set_setting("clipboard_config", current)
        if "enabled" in settings:
            self.set_setting("clipboard_enabled", bool(settings["enabled"]))
        if "prompted" in settings:
            self.set_setting("clipboard_prompted", bool(settings["prompted"]))

    # ==========================================
    # Tarifeli Bağlantı (Metered Connection) Ayarları
    # ==========================================
    def get_metered_settings(self) -> Dict[str, Any]:
        default = {
            "pause_on_metered": True
        }
        val = self.get_setting("metered_connection", None)
        if isinstance(val, dict):
            merged = dict(default)
            merged.update(val)
            return merged
        return default

    def save_metered_settings(self, settings: Dict[str, Any]):
        current = self.get_metered_settings()
        current.update(settings)
        self.set_setting("metered_connection", current)

    # ==========================================
    # Arayüz Modu (Basit / Gelişmiş) & Onboarding
    # ==========================================
    def get_ui_mode(self) -> str:
        """Returns 'simple' or 'advanced'. Defaults to 'simple'."""
        mode = self.get_setting("ui_mode", "simple")
        return mode if mode in ("simple", "advanced") else "simple"

    def save_ui_mode(self, mode: str):
        clean_mode = "advanced" if mode == "advanced" else "simple"
        self.set_setting("ui_mode", clean_mode)

    def is_onboarding_completed(self) -> bool:
        return bool(self.get_setting("onboarding_completed", False))

    def set_onboarding_completed(self, completed: bool = True):
        self.set_setting("onboarding_completed", bool(completed))



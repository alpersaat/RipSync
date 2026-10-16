import time
import threading
import sqlite3
import pytest
from core.database import Database
from core.queue_manager import QueueManager

def test_database_persistent_connection(tmp_path):
    """Test that _get_connection returns the same persistent connection instance."""
    db_file = str(tmp_path / "test_persistent.db")
    db = Database(db_file)

    conn1 = db._get_connection()
    conn2 = db._get_connection()
    assert conn1 is conn2, "Database must reuse the same persistent connection"

    # Verify write and read work through the persistent connection
    did = db.add_download(
        url="http://example.com/test.zip",
        filename="test.zip",
        save_path=str(tmp_path / "test.zip")
    )
    rec = db.get_download(did)
    assert rec is not None
    assert rec["filename"] == "test.zip"

    # Test close resets the connection
    db.close()
    assert db._conn is None

    # Reopening gets a new persistent connection
    conn3 = db._get_connection()
    assert conn3 is not None
    assert conn3 is not conn1
    rec2 = db.get_download(did)
    assert rec2 is not None
    db.close()


def test_database_batch_updates(tmp_path):
    """Test that update_downloads_batch updates multiple downloads in one transaction."""
    db_file = str(tmp_path / "test_batch.db")
    db = Database(db_file)

    d1 = db.add_download("http://example.com/1.zip", "1.zip", str(tmp_path / "1.zip"))
    d2 = db.add_download("http://example.com/2.zip", "2.zip", str(tmp_path / "2.zip"))

    updates = [
        {"id": d1, "downloaded_size": 1000, "total_size": 5000, "speed": 200, "eta": 20},
        {"id": d2, "downloaded_size": 2000, "total_size": 6000, "speed": 400, "eta": 10},
    ]
    db.update_downloads_batch(updates)

    r1 = db.get_download(d1)
    r2 = db.get_download(d2)

    assert r1["downloaded_size"] == 1000
    assert r1["speed"] == 200
    assert r2["downloaded_size"] == 2000
    assert r2["speed"] == 400
    db.close()


def test_database_thread_safety(tmp_path):
    """Test concurrent reads and writes across multiple threads with persistent connection."""
    db_file = str(tmp_path / "test_concurrency.db")
    db = Database(db_file)

    dids = []
    for i in range(5):
        did = db.add_download(f"http://example.com/{i}.zip", f"{i}.zip", str(tmp_path / f"{i}.zip"))
        dids.append(did)

    def worker(worker_id):
        for step in range(10):
            target_id = dids[worker_id % len(dids)]
            db.update_download(target_id, downloaded_size=step * 100, speed=step * 10)
            rec = db.get_download(target_id)
            assert rec is not None

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    db.close()


def test_queue_manager_progress_throttling_and_caching(tmp_path):
    """Test that QueueManager throttles DB writes while maintaining real-time UI callbacks."""
    db_file = str(tmp_path / "test_qm_throttle.db")
    db = Database(db_file)
    qm = QueueManager(db, max_concurrent=2)
    qm._progress_sync_interval = 1.0  # 1 second threshold

    did = db.add_download("http://example.com/test.zip", "test.zip", str(tmp_path / "test.zip"))

    ui_progress_events = []
    qm.on_task_progress = lambda d, down, tot, sp, eta: ui_progress_events.append((down, sp))

    # Initial call at t=0: last_sync was 0, so should sync to DB immediately
    qm._on_progress(did, downloaded=100, total=1000, speed=50.0, eta=18)
    assert len(ui_progress_events) == 1
    rec1 = db.get_download(did)
    assert rec1["downloaded_size"] == 100

    # Rapid calls immediately after (elapsed < 1.0s)
    qm._on_progress(did, downloaded=200, total=1000, speed=60.0, eta=13)
    qm._on_progress(did, downloaded=300, total=1000, speed=70.0, eta=10)
    qm._on_progress(did, downloaded=400, total=1000, speed=80.0, eta=7)

    # UI callback must have been called 4 times in total (immediate responsiveness)
    assert len(ui_progress_events) == 4

    # DB should still hold the initial value (100) because interval has not elapsed
    rec_throttled = db.get_download(did)
    assert rec_throttled["downloaded_size"] == 100

    # Memory cache must have latest value (400)
    assert qm._progress_cache[did]["downloaded_size"] == 400

    # Test explicit flush writes cached data to DB
    qm.flush_progress(did)
    rec_flushed = db.get_download(did)
    assert rec_flushed["downloaded_size"] == 400
    assert rec_flushed["speed"] == 80

    # Test status change (e.g. Completed) flushes latest progress and cleans cache
    qm._on_progress(did, downloaded=950, total=1000, speed=90.0, eta=1)
    assert qm._progress_cache[did]["downloaded_size"] == 950

    qm._on_status(did, status="Completed", error="")
    assert did not in qm._progress_cache
    rec_completed = db.get_download(did)
    assert rec_completed["status"] == "Completed"
    assert rec_completed["downloaded_size"] == 950
    assert rec_completed["speed"] == 0
    assert rec_completed["eta"] == 0

    db.close()


def test_queue_manager_flush_on_pause(tmp_path):
    """Test that pausing a download flushes buffered progress immediately."""
    db_file = str(tmp_path / "test_qm_pause.db")
    db = Database(db_file)
    qm = QueueManager(db, max_concurrent=2)
    qm._progress_sync_interval = 5.0

    did = db.add_download("http://example.com/test.zip", "test.zip", str(tmp_path / "test.zip"))

    # Initial call
    qm._on_progress(did, downloaded=100, total=1000, speed=50.0, eta=18)
    # Fast forward progress without DB sync
    qm._on_progress(did, downloaded=500, total=1000, speed=100.0, eta=5)

    rec_before_pause = db.get_download(did)
    assert rec_before_pause["downloaded_size"] == 100

    # Pause download
    qm.pause_download(did)
    rec_after_pause = db.get_download(did)
    assert rec_after_pause["downloaded_size"] == 500
    assert rec_after_pause["status"] == "Paused"

    db.close()


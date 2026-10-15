import pytest
from core.database import Database
from core.queue_manager import QueueManager
from core.metered_connection import (
    is_metered_connection,
    set_simulated_metered,
    MeteredConnectionMonitor
)


@pytest.fixture
def mem_db(tmp_path):
    db_file = str(tmp_path / "test_metered.db")
    return Database(db_file)


@pytest.fixture
def queue_mgr(mem_db):
    return QueueManager(db=mem_db, max_concurrent=2)


def test_metered_simulation():
    try:
        set_simulated_metered(True)
        assert is_metered_connection() is True

        set_simulated_metered(False)
        assert is_metered_connection() is False
    finally:
        set_simulated_metered(None)


def test_metered_settings_database(mem_db):
    cfg = mem_db.get_metered_settings()
    assert cfg["pause_on_metered"] is True

    mem_db.save_metered_settings({"pause_on_metered": False})
    cfg2 = mem_db.get_metered_settings()
    assert cfg2["pause_on_metered"] is False


def test_queue_manager_blocks_on_metered(queue_mgr, mem_db, tmp_path):
    blocked_ids = []
    queue_mgr.on_metered_blocked = lambda did: blocked_ids.append(did)

    try:
        # Simulate metered network
        set_simulated_metered(True)

        did = queue_mgr.add_download(
            url="https://example.com/large.iso",
            save_dir=str(tmp_path),
            filename="large.iso",
            start_now=True
        )

        # Download should be paused due to metered network
        rec = mem_db.get_download(did)
        assert rec["status"] == "Paused"
        assert "Tarifeli" in (rec.get("error_message") or "")
        assert len(blocked_ids) > 0

        # Enable bypass
        queue_mgr.set_metered_bypass(True)
        assert queue_mgr.metered_bypass is True
    finally:
        set_simulated_metered(None)


def test_metered_monitor_signal(qapp):
    monitor = MeteredConnectionMonitor(check_interval_ms=0)
    changed_events = []
    monitor.metered_changed.connect(lambda val: changed_events.append(val))

    try:
        set_simulated_metered(True)
        monitor.check_status()
        assert monitor.is_metered is True
        assert True in changed_events

        set_simulated_metered(False)
        monitor.check_status()
        assert monitor.is_metered is False
        assert False in changed_events
    finally:
        set_simulated_metered(None)


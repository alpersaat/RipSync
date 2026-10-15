import pytest
from unittest.mock import patch, MagicMock
from core.power_manager import set_keep_awake, is_keep_awake_active
from core.database import Database
from core.queue_manager import QueueManager

def test_set_keep_awake_state():
    # Test setting keep awake active and inactive
    assert set_keep_awake(True) is True
    assert is_keep_awake_active() is True

    assert set_keep_awake(False) is True
    assert is_keep_awake_active() is False

def test_queue_manager_keep_awake_toggle():
    db = Database(":memory:")
    qm = QueueManager(db, max_concurrent=2)

    # By default, keep_awake is enabled in settings
    db.set_setting("keep_awake_enabled", True)

    with patch("core.queue_manager.set_keep_awake") as mock_set_ka:
        # Initially no active downloaders
        qm._update_keep_awake()
        mock_set_ka.assert_called_with(False)

        # Mock an active downloader
        mock_dl = MagicMock()
        mock_dl.status = "Downloading"
        qm.active_downloaders["test-id"] = mock_dl

        qm._update_keep_awake()
        mock_set_ka.assert_called_with(True)

        # When setting is disabled
        db.set_setting("keep_awake_enabled", False)
        qm._update_keep_awake()
        mock_set_ka.assert_called_with(False)


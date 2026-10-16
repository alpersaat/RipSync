import socket
import time
import httpx
import pytest
from server.bridge_server import (
    BridgeServer,
    is_port_available,
    find_available_port,
    write_extension_config
)
from core.database import Database


def test_is_port_available_and_find_available_port():
    # Find an open port first
    test_port = 28735
    while not is_port_available("127.0.0.1", test_port):
        test_port += 1

    assert is_port_available("127.0.0.1", test_port) is True

    # Bind a socket to test_port so it becomes busy
    occupier = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        occupier.bind(("127.0.0.1", test_port))
        occupier.listen(1)

        # Now test_port should NOT be available
        assert is_port_available("127.0.0.1", test_port) is False

        # find_available_port should skip test_port and find an alternative
        free_port = find_available_port("127.0.0.1", start_port=test_port, max_attempts=5)
        assert free_port > test_port
        assert is_port_available("127.0.0.1", free_port) is True
    finally:
        occupier.close()


def test_bridge_server_auto_fallback_on_conflict(tmp_path, monkeypatch):
    from core import paths
    ext_dir = tmp_path / "extension"
    ext_dir.mkdir()
    monkeypatch.setattr(paths, "get_extension_dir", lambda: str(ext_dir))

    # Pick a base port
    base_port = 28740
    while not is_port_available("127.0.0.1", base_port):
        base_port += 2

    # Block base_port using a raw TCP socket
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", base_port))
    blocker.listen(1)

    status_events = []
    def on_status(st, p, msg):
        status_events.append((st, p, msg))

    server = BridgeServer(
        host="127.0.0.1",
        port=base_port,
        auth_token="test_token_fallback_12345",
        auto_fallback=True,
        on_status_change=on_status
    )

    try:
        started = server.start(wait_for_ready=True)
        assert started is True
        assert server.is_running is True
        assert server.conflict_detected is True
        assert server.actual_port != base_port
        assert server.actual_port > base_port

        # Verify fallback event was received
        assert any(ev[0] == "running_fallback" for ev in status_events)

        # Test request against the new fallback port
        with httpx.Client() as client:
            r = client.get(
                f"http://127.0.0.1:{server.actual_port}/api/status",
                headers={"X-RipSync-Token": "test_token_fallback_12345"}
            )
            assert r.status_code == 200
            assert r.json()["authenticated"] is True
    finally:
        server.stop()
        blocker.close()


def test_bridge_server_no_fallback_reports_conflict():
    base_port = 28750
    while not is_port_available("127.0.0.1", base_port):
        base_port += 2

    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", base_port))
    blocker.listen(1)

    status_events = []
    def on_status(st, p, msg):
        status_events.append((st, p, msg))

    server = BridgeServer(
        host="127.0.0.1",
        port=base_port,
        auth_token="test_token_no_fallback",
        auto_fallback=False,
        on_status_change=on_status
    )

    try:
        started = server.start(wait_for_ready=True)
        assert started is False
        assert server.is_running is False
        assert server.conflict_detected is True
        assert server.error_message is not None
        assert any(ev[0] == "conflict" for ev in status_events)
    finally:
        server.stop()
        blocker.close()


def test_bridge_server_restart_with_new_port():
    port1 = 28760
    while not is_port_available("127.0.0.1", port1):
        port1 += 3
    port2 = port1 + 1
    while not is_port_available("127.0.0.1", port2):
        port2 += 1

    server = BridgeServer(
        host="127.0.0.1",
        port=port1,
        auth_token="token_restart_test",
        auto_fallback=False
    )

    try:
        # 1. Start on port1
        started1 = server.start(wait_for_ready=True)
        assert started1 is True
        assert server.actual_port == port1

        with httpx.Client() as client:
            r1 = client.get(
                f"http://127.0.0.1:{port1}/api/status",
                headers={"X-RipSync-Token": "token_restart_test"}
            )
            assert r1.status_code == 200

        # 2. Restart on port2
        restarted = server.restart(new_port=port2, wait_for_ready=True)
        assert restarted is True
        assert server.actual_port == port2

        # Port1 should no longer accept connections
        with httpx.Client() as client:
            with pytest.raises(Exception):
                client.get(f"http://127.0.0.1:{port1}/api/status", timeout=0.5)

            # Port2 should answer
            r2 = client.get(
                f"http://127.0.0.1:{port2}/api/status",
                headers={"X-RipSync-Token": "token_restart_test"}
            )
            assert r2.status_code == 200
            assert r2.json()["authenticated"] is True
    finally:
        server.stop()


def test_main_window_bridge_lifecycle_and_port_restart():
    from PyQt6.QtWidgets import QApplication
    from ui.main_window import MainWindow
    from core.queue_manager import QueueManager

    app = QApplication.instance()
    if not app:
        app = QApplication([])

    db = Database(":memory:")
    qm = QueueManager(db, max_concurrent=2)
    win = MainWindow(db, qm)

    port1 = 28780
    while not is_port_available("127.0.0.1", port1):
        port1 += 2
    port2 = port1 + 1
    while not is_port_available("127.0.0.1", port2):
        port2 += 1

    token = db.get_or_create_bridge_token()
    bridge_server = BridgeServer(
        host="127.0.0.1",
        port=port1,
        auth_token=token,
        auto_fallback=True,
        on_status_change=lambda st, p, msg: win.sig_bridge_status.emit(st, p, msg or "")
    )
    win.set_bridge_server(bridge_server)

    try:
        started = bridge_server.start(wait_for_ready=True)
        assert started is True
        app.processEvents()
        assert f"Port {port1}" in win.lbl_ext_status.text()

        # Restart bridge on port2
        restarted = win.restart_bridge_server(port2)
        assert restarted is True
        app.processEvents()
        assert bridge_server.actual_port == port2
        assert f"Port {port2}" in win.lbl_ext_status.text()
    finally:
        bridge_server.stop()
        win.power_mgr.cancel()
        win.tray.hide()
        win.close()


import os
import sys
import unittest
from unittest.mock import patch, MagicMock, PropertyMock
import tempfile
import asyncio

from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from aiohttp import web

from core.power_manager import (
    PowerCountdownManager, LASTINPUTINFO,
    get_idle_duration_seconds, is_user_active,
    get_global_power_manager, set_global_power_manager
)
from core.notifier import (
    notify_power_countdown, notify_power_suspended,
    open_browser_power_alert, play_warning_sound
)
from server.bridge_server import BridgeServer


class TestUserActivityDetection(unittest.TestCase):
    """Tests for Windows Win32 user input idle detection."""

    def test_get_idle_duration_mocked(self):
        with patch("ctypes.windll.user32.GetLastInputInfo") as mock_get_last, \
             patch("ctypes.windll.kernel32.GetTickCount") as mock_tick:
            # Setup: Current tick 100,000, last input at 85,000 -> 15 seconds elapsed
            mock_tick.return_value = 100000
            def fake_get_last(byref_lii):
                # We need to simulate setting dwTime on the passed structure
                byref_lii._obj.dwTime = 85000
                return 1
            mock_get_last.side_effect = fake_get_last

            idle_sec = get_idle_duration_seconds()
            self.assertAlmostEqual(idle_sec, 15.0, places=1)

            # User is active if threshold is 60s
            self.assertTrue(is_user_active(threshold_seconds=60))
            # User is NOT active if threshold is 10s
            self.assertFalse(is_user_active(threshold_seconds=10))

    def test_get_idle_duration_fallback(self):
        # When ctypes windll is not present or fails
        with patch("ctypes.windll", create=False):
            idle = get_idle_duration_seconds()
            self.assertEqual(idle, 0.0)


class TestPowerCountdownManager(unittest.TestCase):
    """Tests for PowerCountdownManager suspend, resume, postpone and status tracking."""

    def setUp(self):
        self.mgr = PowerCountdownManager(countdown_seconds=30)

    def tearDown(self):
        self.mgr.cancel()

    def test_start_and_suspend_resume(self):
        suspended_events = []
        resumed_events = []
        self.mgr.on_suspended = lambda reason: suspended_events.append(reason)
        self.mgr.on_resumed = lambda: resumed_events.append(True)

        self.mgr.start_countdown("shutdown", seconds=30)
        self.assertTrue(self.mgr.is_active())
        self.assertFalse(self.mgr.is_suspended)
        self.assertEqual(self.mgr.action, "shutdown")

        # Suspend
        self.mgr.suspend(reason="Kullanıcı aktif kullanımda")
        self.assertTrue(self.mgr.is_suspended)
        self.assertEqual(self.mgr.suspend_reason, "Kullanıcı aktif kullanımda")
        self.assertEqual(len(suspended_events), 1)

        st = self.mgr.get_status_dict()
        self.assertTrue(st["is_active"])
        self.assertTrue(st["is_suspended"])
        self.assertEqual(st["action"], "shutdown")

        # Resume
        self.mgr.resume()
        self.assertFalse(self.mgr.is_suspended)
        self.assertEqual(len(resumed_events), 1)

        # Postpone
        self.mgr.postpone(extra_seconds=60)
        self.assertGreaterEqual(self.mgr.remaining_seconds, 60)

        # Cancel
        self.mgr.cancel()
        self.assertFalse(self.mgr.is_active())
        self.assertFalse(self.mgr.is_suspended)


class TestBridgeServerPowerAlerts(AioHTTPTestCase):
    """Tests for BridgeServer /api/power_status, /api/power_control and /power_alert web page."""

    async def get_application(self):
        self.mgr = PowerCountdownManager(countdown_seconds=30)
        set_global_power_manager(self.mgr)

        self.bridge = BridgeServer(
            host="127.0.0.1",
            port=29990,
            auth_token="secret_token_123"
        )
        app = web.Application()
        app.router.add_options("/{tail:.*}", self.bridge._handle_options)
        app.router.add_get("/api/status", self.bridge._handle_status)
        app.router.add_get("/api/power_status", self.bridge._handle_power_status)
        app.router.add_post("/api/power_control", self.bridge._handle_power_control)
        app.router.add_get("/power_alert", self.bridge._handle_power_alert_page)
        return app

    def tearDown(self):
        self.mgr.cancel()
        super().tearDown()

    @unittest_run_loop
    async def test_power_status_unauthorized(self):
        resp = await self.client.get("/api/power_status")
        self.assertEqual(resp.status, 401)

    @unittest_run_loop
    async def test_power_status_authorized(self):
        self.mgr.start_countdown("shutdown", seconds=25)
        headers = {"X-RipSync-Token": "secret_token_123"}
        resp = await self.client.get("/api/power_status", headers=headers)
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["is_active"])
        self.assertEqual(data["action"], "shutdown")
        self.assertEqual(data["remaining_seconds"], 25)

    @unittest_run_loop
    async def test_power_control_suspend_and_resume(self):
        self.mgr.start_countdown("sleep", seconds=30)
        headers = {"X-RipSync-Token": "secret_token_123", "Content-Type": "application/json"}

        # Suspend via API
        resp = await self.client.post("/api/power_control", headers=headers, json={"command": "suspend", "reason": "Tarayıcıdan durduruldu"})
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["command"], "suspend")
        self.assertTrue(self.mgr.is_suspended)

        # Resume via API
        resp = await self.client.post("/api/power_control", headers=headers, json={"command": "resume"})
        self.assertEqual(resp.status, 200)
        self.assertFalse(self.mgr.is_suspended)

        # Cancel via API
        resp = await self.client.post("/api/power_control", headers=headers, json={"command": "cancel"})
        self.assertEqual(resp.status, 200)
        self.assertFalse(self.mgr.is_active())

    @unittest_run_loop
    async def test_power_alert_html_page(self):
        resp = await self.client.get("/power_alert?token=secret_token_123")
        self.assertEqual(resp.status, 200)
        text = await resp.text()
        self.assertIn("RipSync - Bilgisayar Kapatma Uyarısı", text)
        self.assertIn("İşlemi Askıya Al", text)
        self.assertIn("Kapatmayı İptal Et", text)


class TestNotifierPowerFunctions(unittest.TestCase):
    """Tests for desktop notifications and browser alerts."""

    @patch("winotify.Notification.show")
    @patch("core.notifier.play_warning_sound")
    def test_notify_power_countdown(self, mock_sound, mock_show):
        notify_power_countdown(action="shutdown", remaining_seconds=30, sound=True)
        mock_sound.assert_called_once()

    @patch("winotify.Notification.show")
    @patch("core.notifier.play_warning_sound")
    def test_notify_power_suspended(self, mock_sound, mock_show):
        notify_power_suspended(action="sleep", reason="Aktif kullanım", sound=True)
        mock_sound.assert_called_once()

    @patch("webbrowser.open_new_tab")
    def test_open_browser_power_alert(self, mock_browser):
        open_browser_power_alert(port=28710, token="test_tok")
        import time
        time.sleep(0.1)  # wait for thread
        mock_browser.assert_called_once()
        args, _ = mock_browser.call_args
        self.assertIn("http://127.0.0.1:28710/power_alert?token=test_tok", args[0])


if __name__ == "__main__":
    unittest.main()

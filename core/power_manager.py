import os
import subprocess
import ctypes
import threading
from typing import Optional, Callable

def execute_shutdown(timeout_seconds: int = 60, message: str = "RipSync: Kuyruktaki tüm indirmeler tamamlandı. Bilgisayar kapatılıyor.") -> bool:
    """
    Schedules Windows system shutdown with a countdown.
    """
    try:
        cmd = ["shutdown", "/s", "/t", str(timeout_seconds), "/c", message]
        subprocess.run(cmd, check=True)
        return True
    except Exception as e:
        print(f"[PowerManager] Shutdown command failed: {e}")
        return False

def abort_shutdown() -> bool:
    """
    Aborts a scheduled Windows shutdown.
    """
    try:
        cmd = ["shutdown", "/a"]
        res = subprocess.run(cmd, capture_output=True)
        return res.returncode == 0
    except Exception as e:
        print(f"[PowerManager] Abort shutdown failed: {e}")
        return False

def execute_sleep() -> bool:
    """
    Puts Windows system to sleep (standby / suspend).
    Calls SetSuspendState(0, 1, 0) via powrprof.dll.
    """
    try:
        # SetSuspendState(Hibernate, ForceCritical, DisableWakeEvent)
        # Hibernate=0 -> Sleep/Standby
        # ForceCritical=1 -> Suspend immediately without broadcasting PBT_APMQUERYSUSPEND to every app
        # DisableWakeEvent=0 -> Allow wake events
        ret = ctypes.windll.powrprof.SetSuspendState(0, 1, 0)
        return bool(ret)
    except Exception as e:
        print(f"[PowerManager] Sleep command failed: {e}")
        return False

# Windows SetThreadExecutionState flags
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_AWAYMODE_REQUIRED = 0x00000040

_keep_awake_active = False
_keep_awake_lock = threading.Lock()

def set_keep_awake(enabled: bool) -> bool:
    """
    Prevents Windows from entering sleep or idle standby during active downloads.
    When enabled=True, calls SetThreadExecutionState with ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED.
    When enabled=False, resets the execution state to normal ES_CONTINUOUS.
    """
    global _keep_awake_active
    with _keep_awake_lock:
        try:
            if not hasattr(ctypes, "windll") or not hasattr(ctypes.windll, "kernel32"):
                # Non-windows platform or mock environment
                _keep_awake_active = enabled
                return True

            kernel32 = ctypes.windll.kernel32
            if enabled:
                flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
                prev = kernel32.SetThreadExecutionState(flags)
                _keep_awake_active = (prev != 0)
                return _keep_awake_active
            else:
                prev = kernel32.SetThreadExecutionState(ES_CONTINUOUS)
                _keep_awake_active = False
                return True
        except Exception as e:
            print(f"[PowerManager] SetThreadExecutionState failed: {e}")
            return False

def is_keep_awake_active() -> bool:
    """Returns True if system sleep prevention is currently active."""
    global _keep_awake_active
    return _keep_awake_active

class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("dwTime", ctypes.c_ulong),
    ]

def get_idle_duration_seconds() -> float:
    """
    Returns the time in seconds since the last user keyboard or mouse input on Windows.
    Returns 0.0 on non-Windows platforms or if the API call fails.
    """
    try:
        if not hasattr(ctypes, "windll") or not hasattr(ctypes.windll, "user32") or not hasattr(ctypes.windll, "kernel32"):
            return 0.0

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)

        if not user32.GetLastInputInfo(ctypes.byref(lii)):
            return 0.0

        # GetTickCount returns milliseconds since system startup
        tick_count = kernel32.GetTickCount()
        elapsed_ms = tick_count - lii.dwTime
        if elapsed_ms < 0:
            elapsed_ms = 0
        return float(elapsed_ms) / 1000.0
    except Exception as e:
        print(f"[PowerManager] get_idle_duration_seconds error: {e}")
        return 0.0

def is_user_active(threshold_seconds: int = 60) -> bool:
    """
    Returns True if user has interacted with keyboard or mouse within the given threshold in seconds.
    If idle duration is less than threshold_seconds, user is actively using the system.
    """
    idle_time = get_idle_duration_seconds()
    return idle_time < float(threshold_seconds)

_global_power_manager: Optional['PowerCountdownManager'] = None

def get_global_power_manager() -> Optional['PowerCountdownManager']:
    global _global_power_manager
    return _global_power_manager

def set_global_power_manager(mgr: 'PowerCountdownManager'):
    global _global_power_manager
    _global_power_manager = mgr

class PowerCountdownManager:
    """
    Manages a countdown before performing a power action (shutdown or sleep),
    allowing UI to display a prompt or dialog where user can cancel or suspend it.
    Supports user activity detection, suspension, and resumption.
    """
    def __init__(self, countdown_seconds: int = 30):
        self.countdown_seconds = countdown_seconds
        self.remaining_seconds = countdown_seconds
        self.action = "none"  # "none", "shutdown", "sleep"
        self._timer: Optional[threading.Timer] = None
        self._is_active = False
        self.is_suspended = False
        self.suspend_reason = ""

        # Callbacks
        self.on_tick: Optional[Callable[[int, str], None]] = None
        self.on_executed: Optional[Callable[[str], None]] = None
        self.on_cancelled: Optional[Callable[[], None]] = None
        self.on_suspended: Optional[Callable[[str], None]] = None
        self.on_resumed: Optional[Callable[[], None]] = None
        self.on_confirm_requested: Optional[Callable[[str], None]] = None

    def start_countdown(self, action: str, seconds: Optional[int] = None):
        if action not in ("shutdown", "sleep"):
            return
        self.cancel()
        self.action = action
        self.remaining_seconds = seconds if seconds is not None else self.countdown_seconds
        self._is_active = True
        self.is_suspended = False
        self.suspend_reason = ""
        self._schedule_tick()

    def _schedule_tick(self):
        if not self._is_active or self.is_suspended:
            return
        if self.on_tick:
            self.on_tick(self.remaining_seconds, self.action)

        if self.remaining_seconds <= 0:
            # Countdown reached zero: never execute the power action
            # automatically. Ask the UI to show an explicit confirmation
            # first; the action only runs after the user confirms.
            self._is_active = False
            self.is_suspended = False
            act = self.action
            self.action = "none"
            if self.on_confirm_requested:
                self.on_confirm_requested(act)
            return

        self._timer = threading.Timer(1.0, self._step)
        self._timer.daemon = True
        self._timer.start()

    def _step(self):
        if not self._is_active or self.is_suspended:
            return
        self.remaining_seconds -= 1
        self._schedule_tick()

    def suspend(self, reason: str = "Kullanıcı aktif kullanımda"):
        """
        Pauses the power countdown without completely cancelling it.
        Useful when user activity is detected or user clicks 'Suspend'.
        """
        if not self._is_active or self.is_suspended:
            return
        self.is_suspended = True
        self.suspend_reason = reason
        if self._timer:
            self._timer.cancel()
            self._timer = None
        if self.action == "shutdown":
            abort_shutdown()
        if self.on_suspended:
            self.on_suspended(reason)

    def resume(self):
        """
        Resumes countdown from current remaining seconds.
        """
        if not self._is_active or not self.is_suspended:
            return
        self.is_suspended = False
        self.suspend_reason = ""
        if self.on_resumed:
            self.on_resumed()
        self._schedule_tick()

    def postpone(self, extra_seconds: int = 300):
        """
        Adds extra seconds to countdown or resets countdown and resumes.
        """
        self.remaining_seconds = max(self.remaining_seconds + extra_seconds, extra_seconds)
        if self.is_suspended:
            self.resume()
        elif self._is_active and not self._timer:
            self._schedule_tick()

    def cancel(self):
        self._is_active = False
        self.is_suspended = False
        self.suspend_reason = ""
        if self._timer:
            self._timer.cancel()
            self._timer = None
        if self.action == "shutdown":
            abort_shutdown()
        self.action = "none"
        if self.on_cancelled:
            self.on_cancelled()

    def is_active(self) -> bool:
        return self._is_active

    def get_status_dict(self) -> dict:
        """Returns power management status for API and extensions."""
        return {
            "is_active": self._is_active,
            "action": self.action,
            "remaining_seconds": self.remaining_seconds,
            "is_suspended": self.is_suspended,
            "suspend_reason": self.suspend_reason,
            "idle_duration_seconds": round(get_idle_duration_seconds(), 1)
        }

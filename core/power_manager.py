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

class PowerCountdownManager:
    """
    Manages a countdown before performing a power action (shutdown or sleep),
    allowing UI to display a prompt or dialog where user can cancel it.
    """
    def __init__(self, countdown_seconds: int = 30):
        self.countdown_seconds = countdown_seconds
        self.remaining_seconds = countdown_seconds
        self.action = "none"  # "none", "shutdown", "sleep"
        self._timer: Optional[threading.Timer] = None
        self._is_active = False

        # Callbacks
        self.on_tick: Optional[Callable[[int, str], None]] = None
        self.on_executed: Optional[Callable[[str], None]] = None
        self.on_cancelled: Optional[Callable[[], None]] = None

    def start_countdown(self, action: str, seconds: Optional[int] = None):
        if action not in ("shutdown", "sleep"):
            return
        self.cancel()
        self.action = action
        self.remaining_seconds = seconds if seconds is not None else self.countdown_seconds
        self._is_active = True
        self._schedule_tick()

    def _schedule_tick(self):
        if not self._is_active:
            return
        if self.on_tick:
            self.on_tick(self.remaining_seconds, self.action)

        if self.remaining_seconds <= 0:
            self._execute_action()
            return

        self._timer = threading.Timer(1.0, self._step)
        self._timer.daemon = True
        self._timer.start()

    def _step(self):
        if not self._is_active:
            return
        self.remaining_seconds -= 1
        self._schedule_tick()

    def _execute_action(self):
        self._is_active = False
        act = self.action
        self.action = "none"
        if act == "shutdown":
            execute_shutdown(timeout_seconds=0)
        elif act == "sleep":
            execute_sleep()

        if self.on_executed:
            self.on_executed(act)

    def cancel(self):
        self._is_active = False
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

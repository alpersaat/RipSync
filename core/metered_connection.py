import os
import sys
from typing import Optional
from PyQt6.QtCore import QObject, pyqtSignal, QTimer


# Simulation flag for testing or developer override
_SIMULATED_METERED: Optional[bool] = None


def set_simulated_metered(val: Optional[bool]):
    """Sets a simulated metered state for testing or debugging."""
    global _SIMULATED_METERED
    _SIMULATED_METERED = val


def is_metered_connection() -> bool:
    """
    Detects if the current active network connection is metered (e.g. Hotspot, Cellular/Mobile Data, or user-set Metered Connection in Windows).
    Returns True if metered, False otherwise.
    Safe on all platforms; fails gracefully with False.
    """
    global _SIMULATED_METERED
    if _SIMULATED_METERED is not None:
        return _SIMULATED_METERED

    if sys.platform != "win32":
        return False

    # Strategy 1: Check Windows Network Cost Manager via Registry profile inspection
    try:
        import winreg
        # Check profiles under NetworkList
        profiles_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\NetworkList\Profiles"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, profiles_path) as profiles_key:
            num_subkeys = winreg.QueryInfoKey(profiles_key)[0]
            for i in range(num_subkeys):
                try:
                    sub_name = winreg.EnumKey(profiles_key, i)
                    with winreg.OpenKey(profiles_key, sub_name) as sub_key:
                        # Cost: 1 = Unrestricted, 2 = Fixed (Metered), 4 = Variable (Metered)
                        try:
                            cost_val, _ = winreg.QueryValueEx(sub_key, "Cost")
                            # If Cost has Fixed (2) or Variable (4) flag set
                            if cost_val in (2, 4):
                                return True
                        except FileNotFoundError:
                            pass
                except Exception:
                    continue
    except Exception:
        pass

    # Strategy 2: Check active WLAN profile cost via netsh if available
    try:
        import subprocess
        # Check if connected to a mobile hotspot/metered Wi-Fi
        res = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            text=True,
            timeout=2,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        if res.returncode == 0:
            lines = res.stdout.splitlines()
            for line in lines:
                if "cost" in line.lower() and ("fixed" in line.lower() or "variable" in line.lower() or "metered" in line.lower()):
                    return True
    except Exception:
        pass

    return False


class MeteredConnectionMonitor(QObject):
    """
    Periodically checks if connection is metered and notifies subscribers.
    """
    metered_changed = pyqtSignal(bool)

    def __init__(self, check_interval_ms: int = 20000, parent=None):
        super().__init__(parent)
        self.is_metered: bool = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_status)
        if check_interval_ms > 0:
            self.timer.start(check_interval_ms)
        # Perform initial check
        self.check_status()

    def check_status(self) -> bool:
        current = is_metered_connection()
        if current != self.is_metered:
            self.is_metered = current
            self.metered_changed.emit(self.is_metered)
        return self.is_metered


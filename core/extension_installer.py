"""
RipSync - Browser Extension Helper & Auto-Installer
Detects installed Chromium-based browsers (Chrome, Edge, Brave, Opera, Vivaldi),
handles launching browsers with --load-extension, and assists non-technical users
in installing the unpacked extension effortlessly.
"""

import os
import sys
import subprocess
import webbrowser
from typing import Dict, List, Optional, Tuple
from core.paths import get_extension_dir

# Standard Windows paths for popular Chromium-based browsers
BROWSER_CANDIDATE_PATHS: Dict[str, List[str]] = {
    "chrome": [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ],
    "edge": [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
    ],
    "brave": [
        os.path.expandvars(r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        os.path.expandvars(r"%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe"),
    ],
    "opera": [
        os.path.expandvars(r"%LocalAppData%\Programs\Opera\launcher.exe"),
        os.path.expandvars(r"%ProgramFiles%\Opera\launcher.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Opera\launcher.exe"),
    ],
    "vivaldi": [
        os.path.expandvars(r"%LocalAppData%\Vivaldi\Application\vivaldi.exe"),
        os.path.expandvars(r"%ProgramFiles%\Vivaldi\Application\vivaldi.exe"),
    ]
}

BROWSER_DISPLAY_NAMES = {
    "chrome": "Google Chrome",
    "edge": "Microsoft Edge",
    "brave": "Brave Browser",
    "opera": "Opera",
    "vivaldi": "Vivaldi"
}


def find_browser_executable(browser_key: str) -> Optional[str]:
    """Returns the executable path for the specified browser key, if installed."""
    candidates = BROWSER_CANDIDATE_PATHS.get(browser_key.lower(), [])
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def get_detected_browsers() -> Dict[str, Dict[str, str]]:
    """
    Scans the system for installed Chromium browsers.
    Returns a dict: { "chrome": {"name": "Google Chrome", "exe": "C:\\...", "key": "chrome"}, ... }
    """
    detected = {}
    for key, name in BROWSER_DISPLAY_NAMES.items():
        exe = find_browser_executable(key)
        if exe:
            detected[key] = {
                "key": key,
                "name": name,
                "exe": exe
            }
    return detected


def get_extension_folder_path() -> str:
    """Returns the absolute, normalized path to the extension directory."""
    ext_dir = os.path.abspath(get_extension_dir())
    return ext_dir


def launch_browser_with_extension(browser_key: Optional[str] = None) -> Tuple[bool, str]:
    """
    Launches the specified browser (or first detected Chromium browser)
    with the --load-extension flag pointing to the RipSync unpacked extension directory.
    Returns (success: bool, message: str).
    """
    ext_dir = get_extension_folder_path()
    if not os.path.isdir(ext_dir):
        return False, f"Eklenti klasörü bulunamadı: {ext_dir}"

    exe_path = None
    browser_name = "Tarayıcı"

    if browser_key:
        exe_path = find_browser_executable(browser_key)
        browser_name = BROWSER_DISPLAY_NAMES.get(browser_key, browser_key)
    else:
        # Auto-detect first available browser, prioritizing Chrome then Edge
        detected = get_detected_browsers()
        for preferred in ["chrome", "edge", "brave", "opera", "vivaldi"]:
            if preferred in detected:
                exe_path = detected[preferred]["exe"]
                browser_name = detected[preferred]["name"]
                break

    if not exe_path:
        return False, "Sistemde desteklenen bir Chromium tarayıcısı (Chrome, Edge, Brave) bulunamadı."

    try:
        # Launch browser with --load-extension parameter
        # Note: In Windows, quoting the path in subprocess call
        cmd = [exe_path, f"--load-extension={ext_dir}"]
        subprocess.Popen(cmd)
        return True, f"{browser_name} eklentiyle birlikte başarıyla başlatıldı!"
    except Exception as e:
        return False, f"{browser_name} başlatılırken hata oluştu: {e}"


def open_browser_extension_page(browser_key: Optional[str] = None) -> Tuple[bool, str]:
    """
    Opens the extensions management page (chrome://extensions or edge://extensions).
    Returns (success: bool, message: str).
    """
    page_url = "edge://extensions" if browser_key == "edge" else "chrome://extensions"
    exe_path = find_browser_executable(browser_key) if browser_key else None

    if not exe_path:
        # Fallback to detected browser
        detected = get_detected_browsers()
        for k in ["chrome", "edge", "brave"]:
            if k in detected:
                exe_path = detected[k]["exe"]
                page_url = "edge://extensions" if k == "edge" else "chrome://extensions"
                break

    try:
        if exe_path and os.path.isfile(exe_path):
            subprocess.Popen([exe_path, page_url])
            return True, f"Tarayıcı uzantılar sayfası ({page_url}) açıldı."
        else:
            webbrowser.open(page_url)
            return True, f"Uzantılar sayfası ({page_url}) varsayılan tarayıcıda açıldı."
    except Exception as e:
        return False, f"Uzantılar sayfası açılamadı: {e}"


def copy_extension_path_to_clipboard() -> Tuple[bool, str]:
    """
    Copies the extension directory path to the Windows clipboard.
    Uses PyQt6 clipboard if QApplication is active, otherwise falls back to tkinter or ctypes.
    """
    path = get_extension_folder_path()
    copied = False

    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(path)
                app.processEvents()
                copied = True
    except Exception:
        pass

    if not copied:
        try:
            # Fallback using subprocess clip
            proc = subprocess.Popen(['clip'], stdin=subprocess.PIPE, shell=True)
            proc.communicate(path.encode('utf-16le'))
            copied = True
        except Exception:
            pass

    if copied:
        return True, path
    return False, path

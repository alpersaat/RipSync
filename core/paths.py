import os
import sys
import shutil
from typing import Optional

def is_frozen() -> bool:
    """True if running in a PyInstaller or frozen bundle."""
    return getattr(sys, "frozen", False)

def get_app_dir() -> str:
    """Returns the directory containing the application binaries or entry script."""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_bundle_dir() -> str:
    """Returns the directory where bundled resources (e.g. extracted or onedir assets) live."""
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return getattr(sys, "_MEIPASS")
    return get_app_dir()

def is_portable() -> bool:
    """
    Checks if portable mode is enabled.
    Can be triggered by placing a 'portable.txt' file in the application directory.
    """
    app_dir = get_app_dir()
    return os.path.isfile(os.path.join(app_dir, "portable.txt"))

def get_user_data_dir() -> str:
    """
    Returns the directory where user data (database, settings, logs) must be stored.
    - If portable mode: inside the app directory (./data/)
    - Normal Windows: %APPDATA%/RipSync
    """
    if is_portable():
        data_dir = os.path.join(get_app_dir(), "data")
    else:
        appdata = os.environ.get("APPDATA")
        if not appdata:
            appdata = os.path.expanduser("~")
        data_dir = os.path.join(appdata, "RipSync")

    try:
        os.makedirs(data_dir, exist_ok=True)
    except Exception:
        pass
    return data_dir

def get_database_path() -> str:
    """
    Resolves the SQLite database path and safely migrates existing local database if needed.
    """
    data_dir = get_user_data_dir()
    target_db = os.path.join(data_dir, "downloads.db")

    legacy_db = os.path.join(get_app_dir(), "downloads.db")

    # In dev mode (not frozen), if legacy downloads.db exists in repo root, use it directly
    if not is_frozen() and not is_portable() and os.path.isfile(legacy_db):
        return legacy_db

    # In frozen mode, if legacy db exists and target does not exist yet, copy it over
    if is_frozen() and not is_portable() and os.path.isfile(legacy_db) and not os.path.isfile(target_db):
        try:
            shutil.copy2(legacy_db, target_db)
        except Exception:
            pass

    return target_db

def get_extension_dir() -> str:
    """Returns the absolute path to the unpacked Chrome extension directory."""
    for candidate in [
        os.path.join(get_bundle_dir(), "extension"),
        os.path.join(get_app_dir(), "extension"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "extension")
    ]:
        if os.path.isdir(candidate):
            return candidate
    return os.path.join(get_app_dir(), "extension")

def get_icon_path() -> Optional[str]:
    """Returns the path to the application icon (.ico or .png) if available."""
    candidates = [
        os.path.join(get_bundle_dir(), "resources", "ripsync.ico"),
        os.path.join(get_app_dir(), "resources", "ripsync.ico"),
        os.path.join(get_bundle_dir(), "ripsync.ico"),
        os.path.join(get_app_dir(), "ripsync.ico"),
        os.path.join(get_extension_dir(), "icons", "icon128.png"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


import os
import sys
import shutil
from typing import Optional

MAX_PATH = 260  # Windows Masaüstü API'si için klasik maksimum yol uzunluğu (karakter)


def is_windows() -> bool:
    return os.name == "nt"


def to_long_path(path: str) -> str:
    """
    Windows '\\?\\' önekli uzun yol biçimine dönüştürür; bu sayede MAX_PATH (260)
    sınırını aşan yollar (~32.767 karakter) dosya sistemiyle erişilebilir olur.
    Zaten kısa, zaten önekli veya Windows dışındaysa path aynen döner.
    """
    if not path or not is_windows():
        return path
    if path.startswith("\\\\?\\"):
        return path
    abs_path = os.path.abspath(path)
    if abs_path.startswith("\\\\"):
        # \\server\share\yol -> \\?\UNC\server\share\yol
        unc = abs_path[2:]
        server, _, rest = unc.partition("\\")
        return "\\\\?\\UNC\\" + server + ("\\" + rest if rest else "")
    return "\\\\?\\" + abs_path


def from_long_path(path: str) -> str:
    """Gösterim/Gezgin işlemleri için '\\?\\' (ve \\?\\UNC\\) önekini kaldırır."""
    if not path or not is_windows():
        return path
    if path.startswith("\\\\?\\UNC\\"):
        return "\\\\" + path[len("\\\\?\\UNC\\"):]
    if path.startswith("\\\\?\\"):
        return path[len("\\\\?\\"):]
    return path


def is_path_too_long(path: str, limit: int = MAX_PATH) -> bool:
    """Yol Windows MAX_PATH sınırını (varsayılan 260 karakter) geçiyorsa True döner."""
    if not path or not is_windows():
        return False
    return len(os.path.abspath(path)) > limit


def suggest_short_download_dir() -> str:
    """Kullanıcıya önerilecek kısa bir indirme kök klasörü yolu."""
    if is_windows():
        try:
            drive, _ = os.path.splitdrive(os.path.abspath(os.path.expanduser("~")))
            if drive:
                return f"{drive}\\RipSync"
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "RipSync")


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
    except Exception as e:
        sys.stderr.write(f"[RipSync] Kullanıcı veri dizini oluşturulamadı ({data_dir}): {e}\n")
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
        except Exception as e:
            try:
                from core.logger import get_logger
                get_logger("paths").warning(f"Eski veritabanı kopyalanamadı ({legacy_db} -> {target_db}): {e}")
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

def get_default_download_dir() -> str:
    """Returns the user's default Downloads directory path."""
    return os.path.join(os.path.expanduser("~"), "Downloads")


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

def show_in_explorer(file_or_dir_path: str):
    """
    Opens Windows Explorer highlighting the file, or opening the directory.
    Windows Gezgini '\\?\\' önekini anlamadığı için önek temizlenir.
    """
    import subprocess
    try:
        abs_path = os.path.abspath(file_or_dir_path)
        explorer_path = from_long_path(abs_path) if abs_path.startswith("\\\\?\\") else abs_path
        if os.path.isfile(explorer_path):
            subprocess.Popen(f'explorer /select,"{explorer_path}"')
        elif os.path.isdir(explorer_path):
            subprocess.Popen(f'explorer "{explorer_path}"')
        else:
            parent = os.path.dirname(explorer_path)
            if os.path.exists(parent):
                subprocess.Popen(f'explorer "{parent}"')
    except Exception as e:
        try:
            from core.logger import get_logger
            get_logger("paths").warning(f"Windows Gezgini açılamadı ({file_or_dir_path}): {e}")
        except Exception:
            print(f"[Explorer] Failed to open explorer: {e}")


def get_disk_free_space(path: str) -> int:
    """Returns free disk space in bytes for the volume containing path."""
    try:
        abs_p = os.path.abspath(path or os.path.expanduser("~"))
        while not os.path.exists(abs_p) and os.path.dirname(abs_p) != abs_p:
            abs_p = os.path.dirname(abs_p)
        return shutil.disk_usage(abs_p).free
    except Exception as e:
        try:
            from core.logger import get_logger
            get_logger("paths").warning(f"Disk boş alanı okunamadı ({path}): {e}")
        except Exception:
            pass
        return -1


def get_disk_total_and_free(path: str):
    """Returns (free_bytes, total_bytes, drive_identifier) for the drive."""
    try:
        abs_p = os.path.abspath(path or os.path.expanduser("~"))
        while not os.path.exists(abs_p) and os.path.dirname(abs_p) != abs_p:
            abs_p = os.path.dirname(abs_p)
        usage = shutil.disk_usage(abs_p)
        drive = os.path.splitdrive(abs_p)[0]
        if not drive:
            drive = abs_p[:15]
        return usage.free, usage.total, drive
    except Exception as e:
        try:
            from core.logger import get_logger
            get_logger("paths").warning(f"Disk toplam/boş alan okunamadı ({path}): {e}")
        except Exception:
            pass
        return -1, -1, ""


def sanitize_filename(candidate: str, default_name: str = "download.bin") -> str:
    """
    Sanitizes candidate string into a valid, safe Windows filename.
    - Strips query parameters or hash fragments
    - Replaces invalid Windows characters (< > : " / \\ | ? *) with '_'
    - Trims leading/trailing spaces and dots
    - Avoids reserved Windows device names (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
    - Truncates long filenames to avoid MAX_PATH issues
    """
    import re
    if not candidate:
        return default_name

    # If it is a full URL or has a URL query parameter attached to an extension
    if candidate.startswith("http://") or candidate.startswith("https://"):
        import urllib.parse
        parsed = urllib.parse.urlparse(candidate)
        candidate = os.path.basename(parsed.path) or default_name
    elif "?" in candidate:
        before_q = candidate.split("?")[0]
        if "." in before_q and 1 <= len(before_q.rsplit(".", 1)[-1]) <= 6:
            candidate = before_q

    # Replace invalid Windows chars
    clean = re.sub(r'[\\/*?:"<>|\x00-\x1f]', "_", candidate).strip(" .")

    if not clean:
        return default_name

    # Handle reserved device names in Windows
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
    root, ext = os.path.splitext(clean)
    if root.upper() in reserved:
        clean = f"_{clean}"

    # Truncate if excessively long (e.g. > 200 chars)
    if len(clean) > 200:
        root, ext = os.path.splitext(clean)
        clean = root[:190] + ext

    return clean or default_name


def resolve_file_conflict(target_dir: str, filename: str, action: str = "auto_rename") -> tuple[str, bool]:
    """
    Resolves filename conflicts if a file already exists in target_dir.
    :param target_dir: Directory where the file will be saved.
    :param filename: Desired filename.
    :param action: 'auto_rename' (default), 'overwrite', or 'skip'.
    :return: (resolved_filename, was_conflicted)
    """
    clean_name = sanitize_filename(filename)
    try:
        full_path = os.path.join(target_dir, clean_name)
        if not os.path.exists(to_long_path(full_path)):
            return clean_name, False

        # A conflict exists!
        if action == "overwrite":
            return clean_name, True

        if action == "skip":
            return clean_name, True

        # Default: auto_rename
        # Handle composite extensions like .tar.gz or standard .ext
        lower_name = clean_name.lower()
        if lower_name.endswith(".tar.gz") or lower_name.endswith(".tar.bz2"):
            parts = clean_name.rsplit(".", 2)
            base = parts[0]
            ext = "." + parts[1] + "." + parts[2]
        else:
            base, ext = os.path.splitext(clean_name)

        counter = 1
        max_counter = 10000
        while counter < max_counter:
            candidate = f"{base} ({counter}){ext}"
            candidate_path = os.path.join(target_dir, candidate)
            if not os.path.exists(to_long_path(candidate_path)):
                return candidate, True
            counter += 1

        return clean_name, True
    except Exception as e:
        try:
            from core.logger import get_logger
            get_logger("paths").error(f"Dosya çakışması çözümlenirken hata oluştu ({target_dir}/{clean_name}): {e}", exc_info=True)
        except Exception:
            pass
        return clean_name, False






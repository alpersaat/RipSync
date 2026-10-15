import os
from typing import Optional, Dict, List

# Standard category mapping by extensions
CATEGORY_MAP: Dict[str, List[str]] = {
    "Video": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts"],
    "Music": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".alac"],
    "Compressed": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".dmg"],
    "Programs": [".exe", ".msi", ".iso", ".bat", ".cmd", ".apk", ".appimage", ".deb", ".rpm"],
    "Documents": [".pdf", ".docx", ".doc", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".epub", ".csv", ".rtf", ".srt", ".vtt", ".sub", ".ass"]
}

# Subfolder names inside Windows Downloads directory
CATEGORY_FOLDER_NAMES: Dict[str, str] = {
    "Video": "Videolar",
    "Music": "Müzik",
    "Compressed": "Arşivler",
    "Programs": "Programlar",
    "Documents": "Belgeler",
    "Others": ""
}

def detect_category(filename: str) -> str:
    """
    Detects the file category based on its file extension.
    Returns 'Video', 'Music', 'Compressed', 'Programs', 'Documents', or 'Others'.
    """
    ext = os.path.splitext(filename)[1].lower()
    for cat, extensions in CATEGORY_MAP.items():
        if ext in extensions:
            return cat
    return "Others"

def get_category_folder(category: str, base_dir: Optional[str] = None) -> str:
    """
    Returns the target folder for the given category.
    If base_dir is None, defaults to the user's Windows Downloads directory.
    Subfolders created/used:
      - Video ➔ Videolar
      - Music ➔ Müzik
      - Compressed ➔ Arşivler
      - Programs ➔ Programlar
      - Documents ➔ Belgeler
      - Others ➔ (base_dir directly)
    """
    if not base_dir:
        base_dir = os.path.join(os.path.expanduser("~"), "Downloads")

    subfolder = CATEGORY_FOLDER_NAMES.get(category, "")
    if subfolder:
        target_dir = os.path.join(base_dir, subfolder)
    else:
        target_dir = base_dir

    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception:
        pass

    return target_dir

def get_categorized_save_dir(filename: str, base_dir: Optional[str] = None, category: Optional[str] = None, url: Optional[str] = None, site_rules: Optional[Any] = None) -> str:
    """
    Given a filename or explicit category, resolves and creates the smart categorized target directory.
    If url and site_rules are provided, domain-specific rule takes precedence over extension categorization.
    """
    if url and site_rules:
        custom_folder = site_rules.match_rule(url)
        if custom_folder:
            try:
                os.makedirs(custom_folder, exist_ok=True)
            except Exception:
                pass
            return custom_folder

    cat = category if (category and category != "Otomatik") else detect_category(filename)
    return get_category_folder(cat, base_dir)


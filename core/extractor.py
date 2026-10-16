import os
import shutil
import zipfile
import tarfile
import threading
import subprocess
from typing import Optional, Tuple, Callable

from core.paths import to_long_path

ARCHIVE_EXTENSIONS = (
    ".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz", ".7z", ".rar"
)


def is_archive_file(path_or_name: str) -> bool:
    """Returns True if the path or filename has a supported archive extension."""
    lower = path_or_name.lower().split("?")[0]
    return any(lower.endswith(ext) for ext in ARCHIVE_EXTENSIONS)


def _is_safe_path(base_dir: str, target_path: str) -> bool:
    """Protects against ZipSlip / directory traversal vulnerabilities."""
    abs_base = os.path.abspath(base_dir)
    abs_target = os.path.abspath(target_path)
    return abs_target.startswith(abs_base + os.sep) or abs_target == abs_base


def extract_archive(
    archive_path: str,
    dest_dir: Optional[str] = None,
    create_subfolder: bool = True
) -> Tuple[bool, str]:
    """
    Safely extracts an archive (.zip, .tar*, .7z, .rar) to the destination directory.
    Returns (success: bool, message: str).
    """
    if not os.path.exists(archive_path):
        return False, f"Arşiv dosyası bulunamadı: {archive_path}"

    base_dir = dest_dir or os.path.dirname(archive_path)
    filename = os.path.basename(archive_path)

    # Determine extract target folder
    if create_subfolder:
        name_no_ext = filename
        for ext in sorted(ARCHIVE_EXTENSIONS, key=len, reverse=True):
            if name_no_ext.lower().endswith(ext):
                name_no_ext = name_no_ext[:-len(ext)]
                break
        target_dir = os.path.join(base_dir, name_no_ext.strip(" .") or "extracted")
    else:
        target_dir = base_dir

    os.makedirs(to_long_path(target_dir), exist_ok=True)
    lower_path = archive_path.lower()

    try:
        # 1. ZIP files
        if lower_path.endswith(".zip"):
            with zipfile.ZipFile(archive_path, 'r') as zf:
                for member in zf.infolist():
                    target_member_path = os.path.join(target_dir, member.filename)
                    if not _is_safe_path(target_dir, target_member_path):
                        return False, f"Güvenlik uyarısı: Geçersiz arşiv yolu tespit edildi ({member.filename})"
                zf.extractall(target_dir)
            return True, f"ZIP arşivi başarıyla çıkartıldı: {target_dir}"

        # 2. TAR / TAR.GZ / TAR.BZ2 / TAR.XZ
        elif any(lower_path.endswith(ext) for ext in (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")):
            with tarfile.open(archive_path, 'r:*') as tf:
                for member in tf.getmembers():
                    target_member_path = os.path.join(target_dir, member.name)
                    if not _is_safe_path(target_dir, target_member_path):
                        return False, f"Güvenlik uyarısı: Geçersiz arşiv yolu tespit edildi ({member.name})"
                # Python 3.12+ data_filter support
                if hasattr(tarfile, 'data_filter'):
                    tf.extractall(target_dir, filter='data')
                else:
                    tf.extractall(target_dir)
            return True, f"TAR arşivi başarıyla çıkartıldı: {target_dir}"

        # 3. 7z or RAR
        elif lower_path.endswith(".7z") or lower_path.endswith(".rar"):
            # Try 7-Zip command line if available
            seven_zip = shutil.which("7z") or shutil.which("7za")
            if not seven_zip:
                for candidate in (
                    r"C:\Program Files\7-Zip\7z.exe",
                    r"C:\Program Files (x86)\7-Zip\7z.exe",
                    r"C:\Program Files\WinRAR\WinRAR.exe"
                ):
                    if os.path.exists(candidate):
                        seven_zip = candidate
                        break

            if seven_zip:
                if "winrar" in seven_zip.lower():
                    cmd = [seven_zip, "x", "-ibck", "-o+", archive_path, target_dir]
                else:
                    cmd = [seven_zip, "x", "-y", f"-o{target_dir}", archive_path]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
                if res.returncode == 0:
                    return True, f"Arşiv başarıyla çıkartıldı: {target_dir}"
                return False, f"Arşiv çıkartma hatası (Kod: {res.returncode})"
            else:
                return False, "Sistemde 7z veya WinRAR aracı bulunamadı. Lütfen 7-Zip kurunuz."

        else:
            return False, "Desteklenmeyen arşiv formatı."

    except Exception as e:
        return False, f"Arşiv çıkartılırken hata oluştu: {str(e)}"


def extract_archive_async(
    archive_path: str,
    dest_dir: Optional[str] = None,
    create_subfolder: bool = True,
    callback: Optional[Callable[[bool, str], None]] = None
):
    """Executes extract_archive in a background daemon thread."""
    def _worker():
        success, msg = extract_archive(archive_path, dest_dir=dest_dir, create_subfolder=create_subfolder)
        if callback:
            callback(success, msg)

    t = threading.Thread(target=_worker, daemon=True, name="ArchiveExtractorWorker")
    t.start()


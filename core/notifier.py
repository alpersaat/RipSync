import os
import sys
import subprocess
import pathlib
import threading
from typing import Optional

def notify_download_completed(filename: str, save_path: str, is_video: bool = False):
    """
    Shows Windows Toast notification for completed download:
    'Video başarıyla indirildi - Klasörde Göster' (or file name).
    Clicking the button or notification opens/highlights the file in Windows File Explorer.
    """
    def _worker():
        try:
            from winotify import Notification

            title = "Video başarıyla indirildi" if is_video else "İndirme Tamamlandı"
            msg = filename

            from core.paths import get_icon_path
            icon_path = get_icon_path() or ""

            toast = Notification(
                app_id="RipSync",
                title=title,
                msg=msg,
                icon=icon_path if icon_path else ""
            )

            # Determine folder or file uri
            if save_path and os.path.exists(save_path):
                folder = os.path.dirname(os.path.abspath(save_path))
            elif save_path and os.path.exists(os.path.dirname(save_path)):
                folder = os.path.dirname(os.path.abspath(save_path))
            else:
                folder = os.path.join(os.path.expanduser("~"), "Downloads")

            folder_uri = pathlib.Path(folder).resolve().as_uri()
            toast.add_actions(label="Klasörde Göster", launch=folder_uri)
            toast.show()
        except Exception as e:
            print(f"[Notification] Failed to show Windows toast: {e}")

    threading.Thread(target=_worker, daemon=True).start()

def show_in_explorer(file_or_dir_path: str):
    """
    Opens Windows Explorer highlighting the file, or opening the directory.
    """
    try:
        abs_path = os.path.abspath(file_or_dir_path)
        if os.path.isfile(abs_path):
            subprocess.Popen(f'explorer /select,"{abs_path}"')
        elif os.path.isdir(abs_path):
            subprocess.Popen(f'explorer "{abs_path}"')
        else:
            parent = os.path.dirname(abs_path)
            if os.path.exists(parent):
                subprocess.Popen(f'explorer "{parent}"')
    except Exception as e:
        print(f"[Explorer] Error opening explorer: {e}")

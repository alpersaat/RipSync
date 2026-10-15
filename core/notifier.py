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


def play_completion_sound():
    """Plays subtle IDM-style native notification chime on completion."""
    def _play():
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass
    threading.Thread(target=_play, daemon=True).start()


def play_error_sound():
    """Plays subtle native error chime on download failure."""
    def _play():
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONHAND)
        except Exception:
            pass
    threading.Thread(target=_play, daemon=True).start()


from core.paths import show_in_explorer


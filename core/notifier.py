import os
import sys
import subprocess
import pathlib
import threading
from typing import Optional

from core.logger import get_logger
from core.paths import to_long_path

logger = get_logger("notifier")

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
            if save_path and os.path.exists(to_long_path(save_path)):
                folder = os.path.dirname(os.path.abspath(save_path))
            elif save_path and os.path.exists(to_long_path(os.path.dirname(save_path))):
                folder = os.path.dirname(os.path.abspath(save_path))
            else:
                folder = os.path.join(os.path.expanduser("~"), "Downloads")

            folder_uri = pathlib.Path(folder).resolve().as_uri()
            toast.add_actions(label="Klasörde Göster", launch=folder_uri)
            toast.show()
        except Exception as e:
            logger.warning(f"Windows bildirim balonu gösterilemedi: {e}")

    threading.Thread(target=_worker, daemon=True).start()


def notify_error(title: str, message: str, sound: bool = True):
    """
    Shows Windows Toast notification for critical errors and failures,
    plays error chime, and records the error to the log file.
    """
    logger.error(f"[Kullanıcı Bildirimi - Hata] {title}: {message}")
    if sound:
        play_error_sound()

    def _worker():
        try:
            from winotify import Notification
            from core.paths import get_icon_path
            icon_path = get_icon_path() or ""

            toast = Notification(
                app_id="RipSync",
                title=f"❌ {title}",
                msg=message[:150],  # Toast length limit safety
                icon=icon_path if icon_path else ""
            )
            toast.show()
        except Exception as e:
            logger.warning(f"Windows hata bildirimi gösterilemedi: {e}")

    threading.Thread(target=_worker, daemon=True).start()


def notify_warning(title: str, message: str):
    """
    Shows Windows Toast notification for warnings (e.g. low disk space).
    """
    logger.warning(f"[Kullanıcı Bildirimi - Uyarı] {title}: {message}")

    def _worker():
        try:
            from winotify import Notification
            from core.paths import get_icon_path
            icon_path = get_icon_path() or ""

            toast = Notification(
                app_id="RipSync",
                title=f"⚠️ {title}",
                msg=message[:150],
                icon=icon_path if icon_path else ""
            )
            toast.show()
        except Exception as e:
            logger.warning(f"Windows uyarı bildirimi gösterilemedi: {e}")

    threading.Thread(target=_worker, daemon=True).start()


def play_completion_sound():
    """Plays subtle IDM-style native notification chime on completion."""
    def _play():
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception as e:
            logger.debug(f"Tamamlanma sesi çalınamadı: {e}")
    threading.Thread(target=_play, daemon=True).start()


def play_error_sound():
    """Plays subtle native error chime on download failure."""
    def _play():
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONHAND)
        except Exception as e:
            logger.debug(f"Hata sesi çalınamadı: {e}")
    threading.Thread(target=_play, daemon=True).start()


def play_warning_sound():
    """Plays an alert chime for urgent countdowns and power events."""
    def _play():
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception as e:
            logger.debug(f"Uyarı sesi çalınamadı: {e}")
    threading.Thread(target=_play, daemon=True).start()


def notify_power_countdown(action: str, remaining_seconds: int = 30, sound: bool = True):
    """
    Shows Windows Toast notification when queue is complete and power action is pending:
    '🛑 Bilgisayar Kapatılıyor (30 sn)' or '🌙 Uyku Moduna Geçiliyor (30 sn)'
    """
    action_name = "Kapatılıyor" if action == "shutdown" else "Uyku Moduna Alınıyor"
    icon_symbol = "🛑" if action == "shutdown" else "🌙"
    title = f"{icon_symbol} Bilgisayar {action_name} ({remaining_seconds} sn)"
    message = f"Kuyruk bitti. Bilgisayarınız {remaining_seconds} saniye içinde {action_name.lower()}. İptal etmek veya askıya almak için uygulamayı açın."

    logger.warning(f"[Güç Bildirimi] {title} - {message}")
    if sound:
        play_warning_sound()

    def _worker():
        try:
            from winotify import Notification
            from core.paths import get_icon_path
            icon_path = get_icon_path() or ""

            toast = Notification(
                app_id="RipSync",
                title=title,
                msg=message[:180],
                icon=icon_path if icon_path else ""
            )
            toast.show()
        except Exception as e:
            logger.warning(f"Windows güç bildirimi gösterilemedi: {e}")

    threading.Thread(target=_worker, daemon=True).start()


def notify_power_suspended(action: str, reason: str = "Aktif kullanım algılandı", sound: bool = True):
    """
    Shows Windows Toast notification when shutdown/sleep is suspended because of active user input.
    """
    action_name = "Kapatma" if action == "shutdown" else "Uyku Modu"
    title = f"⚠️ Otomatik {action_name} Askıya Alındı"
    message = f"{reason}. Açık işlerinizin kaybolmaması için sistem eylemi durduruldu."

    logger.info(f"[Güç Bildirimi] {title} - {message}")
    if sound:
        play_warning_sound()

    def _worker():
        try:
            from winotify import Notification
            from core.paths import get_icon_path
            icon_path = get_icon_path() or ""

            toast = Notification(
                app_id="RipSync",
                title=title,
                msg=message[:180],
                icon=icon_path if icon_path else ""
            )
            toast.show()
        except Exception as e:
            logger.warning(f"Windows askıya alma bildirimi gösterilemedi: {e}")

    threading.Thread(target=_worker, daemon=True).start()


def open_browser_power_alert(port: int = 28710, token: str = ""):
    """
    Opens an interactive in-browser alert page in default browser
    so user sees power shutdown countdown even when focused on browser tabs.
    """
    def _open():
        try:
            import webbrowser
            import urllib.parse
            url = f"http://127.0.0.1:{port}/power_alert"
            if token:
                url += f"?token={urllib.parse.quote(token)}"
            webbrowser.open_new_tab(url)
        except Exception as e:
            logger.warning(f"Tarayıcı güç uyarısı açılamadı: {e}")

    threading.Thread(target=_open, daemon=True).start()


from core.paths import show_in_explorer





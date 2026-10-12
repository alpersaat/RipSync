import sys
import os

# Ensure current directory is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from core.database import Database
from core.queue_manager import QueueManager
from server.bridge_server import BridgeServer
from ui.main_window import MainWindow

def main():
    try:
        # Enable high DPI scaling
        app = QApplication(sys.argv)
        app.setApplicationName("RipSync")
        app.setApplicationDisplayName("RipSync - Download Manager")
        app.setQuitOnLastWindowClosed(False)  # Keep running in system tray
        from ui.tray_icon import create_default_icon
        app.setWindowIcon(create_default_icon())

        # 1. Database
        db = Database()

        # 2. Queue Manager
        max_concurrent = int(db.get_setting("max_concurrent", 2))
        speed_enabled = bool(db.get_setting("speed_limit_enabled", False))
        speed_limit = int(db.get_setting("speed_limit_kb", 1024)) * 1024 if speed_enabled else 0

        queue_mgr = QueueManager(db, max_concurrent=max_concurrent, global_speed_limit_bps=speed_limit)

        # 3. Main Window
        window = MainWindow(db, queue_mgr)

        # 4. Bridge Server for Chrome Extension
        port = int(db.get_setting("extension_port", 28710))
        bridge_server = BridgeServer(
            host="127.0.0.1",
            port=port,
            on_download_request=lambda data: window.sig_bridge_download.emit(data),
            on_media_detected=lambda data: None
        )
        bridge_server.start()

        window.show()

        try:
            ret = app.exec()
        finally:
            bridge_server.stop()

        sys.exit(ret)
    except Exception as e:
        import traceback
        try:
            from core.paths import get_user_data_dir
            crash_log = os.path.join(get_user_data_dir(), "crash.log")
            with open(crash_log, "a", encoding="utf-8") as f:
                f.write("\n=== APPLICATION CRASH ===\n")
                traceback.print_exc(file=f)
        except Exception:
            pass
        raise

if __name__ == "__main__":
    main()

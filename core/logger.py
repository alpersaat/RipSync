import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional, Callable

# Central logger instance
_LOGGER_NAME = "RipSync"
_initialized = False
_log_listeners = []


class LogBroadcaster(logging.Handler):
    """Custom logging handler to broadcast error messages to UI/notification listeners."""
    def emit(self, record):
        try:
            if record.levelno >= logging.ERROR:
                msg = self.format(record)
                for listener in list(_log_listeners):
                    try:
                        listener(record.levelname, record.getMessage(), msg)
                    except Exception:
                        pass
        except Exception:
            pass


def init_logging(log_to_console: bool = True, log_level: int = logging.INFO) -> logging.Logger:
    """
    Initializes root application logger with rotating file handler and console handler.
    Log file is stored safely in RipSync user data directory (e.g. %APPDATA%/RipSync/ripsync.log).
    """
    global _initialized
    logger = logging.getLogger(_LOGGER_NAME)
    
    if _initialized:
        return logger

    logger.setLevel(log_level)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. Rotating File Handler
    try:
        from core.paths import get_user_data_dir
        log_dir = get_user_data_dir()
        log_file = os.path.join(log_dir, "ripsync.log")
        
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding="utf-8"
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        sys.stderr.write(f"[RipSync Logging] Failed to setup file handler: {e}\n")

    # 2. Console Handler
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # 3. Broadcaster Handler
    broadcaster = LogBroadcaster()
    broadcaster.setLevel(logging.ERROR)
    logger.addHandler(broadcaster)

    _initialized = True
    logger.info("=== RipSync Logging Started ===")
    return logger


def get_logger(child_name: Optional[str] = None) -> logging.Logger:
    """Returns a logger namespaced under RipSync."""
    if not _initialized:
        init_logging()
    if child_name:
        return logging.getLogger(f"{_LOGGER_NAME}.{child_name}")
    return logging.getLogger(_LOGGER_NAME)


def register_log_listener(callback: Callable[[str, str, str], None]):
    """Registers a callback(level, short_msg, full_msg) for ERROR and CRITICAL events."""
    if callback not in _log_listeners:
        _log_listeners.append(callback)


def unregister_log_listener(callback: Callable[[str, str, str], None]):
    """Unregisters a previously registered log listener."""
    if callback in _log_listeners:
        _log_listeners.remove(callback)

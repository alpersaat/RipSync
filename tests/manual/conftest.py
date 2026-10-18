import os
import sys
import pytest
from PyQt6.QtWidgets import QApplication

# Ensure repository root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture(autouse=True)
def _keep_repo_extension_config_clean(monkeypatch):
    """Test sırasında gerçek eklenti config.json'ının değişmesini engeller.

    Yalnızca depodaki (gerçek) eklenti dizinine yazımı atlar; testler kendi
    tmp dizinlerine geçtiğinde normal davranış korunur.
    """
    try:
        import server.bridge_server as bs
        import core.paths as paths
    except Exception:
        yield
        return
    default_ext = os.path.join(PROJECT_ROOT, "extension")
    real_write = bs.write_extension_config
    real_get_dir = paths.get_extension_dir
    # monkeypatch yerine doğal get_extension_dir çağrısını koru: sadece depo yolu
    # eşleşirse yazıyı atla.
    def _safe_write(token, port=28710):
        try:
            ext_dir = real_get_dir()
        except Exception:
            ext_dir = default_ext
        if os.path.abspath(str(ext_dir)) == os.path.abspath(default_ext):
            return None
        return real_write(token, port)
    monkeypatch.setattr(bs, "write_extension_config", _safe_write, raising=True)
    yield


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


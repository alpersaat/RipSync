"""
Tests for Extension UX improvements, auto-installer helpers,
step-by-step visual guide dialog, and setup onboarding wizard.
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from PyQt6.QtWidgets import QApplication

from core.database import Database
from core.queue_manager import QueueManager
from core.paths import get_extension_dir
import core.extension_installer as ext_inst
from ui.extension_guide_dialog import ExtensionGuideDialog, BrowserMockupCard
from ui.setup_wizard_dialog import SetupWizardDialog
from ui.main_window import MainWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_ext_ux.db")
    db = Database(db_path=db_file)
    return db


def test_extension_folder_path_exists():
    path = ext_inst.get_extension_folder_path()
    assert os.path.isdir(path), f"Extension folder should exist at: {path}"
    manifest_file = os.path.join(path, "manifest.json")
    assert os.path.isfile(manifest_file), "manifest.json must exist in extension directory"


def test_copy_extension_path_to_clipboard(qapp):
    success, path = ext_inst.copy_extension_path_to_clipboard()
    assert success is True
    assert os.path.isdir(path)
    QApplication.processEvents()
    clipboard_text = QApplication.clipboard().text()
    if clipboard_text:
        assert clipboard_text == path




def test_detected_browsers_structure():
    browsers = ext_inst.get_detected_browsers()
    assert isinstance(browsers, dict)
    for k, v in browsers.items():
        assert "key" in v
        assert "name" in v
        assert "exe" in v
        assert os.path.isfile(v["exe"])


def test_launch_browser_with_extension_mock():
    with patch("core.extension_installer.find_browser_executable") as mock_find, \
         patch("subprocess.Popen") as mock_popen:
        mock_find.return_value = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        
        success, msg = ext_inst.launch_browser_with_extension("chrome")
        assert success is True
        assert "Google Chrome" in msg
        mock_popen.assert_called_once()
        cmd = mock_popen.call_args[0][0]
        assert cmd[0] == r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        assert any("--load-extension=" in arg for arg in cmd)


def test_open_browser_extension_page_mock():
    with patch("core.extension_installer.find_browser_executable") as mock_find, \
         patch("subprocess.Popen") as mock_popen:
        mock_find.return_value = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        
        success, msg = ext_inst.open_browser_extension_page("chrome")
        assert success is True
        mock_popen.assert_called_once()
        cmd = mock_popen.call_args[0][0]
        assert cmd[1] == "chrome://extensions"


def test_extension_guide_dialog_steps(qapp, temp_db):
    dlg = ExtensionGuideDialog(bridge_port=28710, bridge_token="test_token_123456")
    try:
        assert dlg.step_stack.count() == 4
        assert dlg.step_stack.currentIndex() == 0
        assert dlg.lbl_step_indicator.text() == "Adım 1 / 4"
        assert dlg.btn_prev_step.isEnabled() is False
        assert dlg.btn_next_step.isEnabled() is True

        # Next step
        dlg._next_step()
        assert dlg.step_stack.currentIndex() == 1
        assert dlg.lbl_step_indicator.text() == "Adım 2 / 4"
        assert dlg.btn_prev_step.isEnabled() is True

        # Next until end
        dlg._next_step()
        dlg._next_step()
        assert dlg.step_stack.currentIndex() == 3
        assert dlg.btn_next_step.isEnabled() is False

        # Prev
        dlg._prev_step()
        assert dlg.step_stack.currentIndex() == 2

        with patch("PyQt6.QtWidgets.QMessageBox.information") as mock_info:
            dlg._copy_extension_path()
            mock_info.assert_called_once()
    finally:
        dlg.close()


def test_setup_wizard_dialog_flow(qapp, temp_db):
    wiz = SetupWizardDialog(db=temp_db)
    try:
        assert wiz.pages.count() == 3
        assert wiz.pages.currentIndex() == 0
        assert wiz.btn_back.isEnabled() is False

        # Advance to extension page
        wiz._go_next()
        assert wiz.pages.currentIndex() == 1
        assert wiz.btn_back.isEnabled() is True
        assert wiz.wizard_card_stack.count() == 4

        # Test inner card navigation
        wiz._next_card()
        assert wiz.wizard_card_stack.currentIndex() == 1
        wiz._prev_card()
        assert wiz.wizard_card_stack.currentIndex() == 0

        # Advance to finish page
        wiz._go_next()
        assert wiz.pages.currentIndex() == 2
        assert wiz.btn_next.text() == "Tamamla & Başla ✔"

        # Complete wizard
        wiz.chk_dont_show.setChecked(True)
        wiz._go_next()

        assert temp_db.get_setting("setup_completed") is True
    finally:
        wiz.close()


def test_main_window_extension_button_menu(qapp, temp_db):
    queue_mgr = QueueManager(temp_db)
    win = MainWindow(temp_db, queue_mgr)
    try:
        assert hasattr(win, "btn_extension"), "MainWindow should have btn_extension"
        menu = win.btn_extension.menu()
        assert menu is not None, "Extension button must have a dropdown menu"

        actions = menu.actions()
        action_texts = [a.text() for a in actions]
        
        # Verify critical user-facing actions exist
        assert any("Eklenti Klasörünü Seç" in t for t in action_texts)
        assert any("Eklenti Klasör Yolunu Kopyala" in t for t in action_texts)
        assert any("Chrome ile Aç" in t for t in action_texts)
        assert any("Görsel Kurulum Rehberi" in t for t in action_texts)
        assert any("Kurulum Sihirbazı" in t for t in action_texts)

        # Test direct folder copy action
        with patch("PyQt6.QtWidgets.QMessageBox.information") as mock_info:
            win._copy_extension_dir_path()
            mock_info.assert_called_once()
    finally:
        win.close()

"""Komut paleti (Ctrl+K): eylem ve ayar arama; tek yerden çalıştırma."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QVBoxLayout, QWidget, QLabel,
)

from ui.styles import T


class CommandPaletteDialog(QDialog):
    """Ctrl+K ile açılan, tüm eylemleri aramadan çalıştıran palet."""

    def __init__(self, window, parent=None):
        super().__init__(parent or window)
        self.window = window
        self._commands = []
        self.setWindowTitle("Komut Paleti")
        self.setModal(True)
        self.resize(540, 380)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText("Komut veya ayar ara...")
        self.edit_search.setStyleSheet(
            f"QLineEdit {{ background-color: {T['bg_card']}; border: 1px solid {T['border']};"
            f" border-radius: 6px; padding: 8px 10px; font-size: 14px; color: {T['text_primary']}; }}"
        )
        self.edit_search.textChanged.connect(self._filter)
        lay.addWidget(self.edit_search)

        self.lst = QListWidget()
        self.lst.setStyleSheet(
            f"QListWidget {{ background-color: {T['bg_panel']}; border: 1px solid {T['border_panel']};"
            f" border-radius: 6px; color: {T['text_primary']}; }}"
            f"QListWidget::item {{ padding: 8px 6px; }}"
            f"QListWidget::item:selected {{ background-color: {T['selection']}; color: {T['text_primary']}; }}"
        )
        self.lst.itemActivated.connect(self._run_item)
        lay.addWidget(self.lst)

        hint = QLabel("↑/↓ seç · Enter çalıştır · Esc kapat")
        hint.setStyleSheet(f"color: {T['text_secondary']}; font-size: 11px;")
        lay.addWidget(hint)

        self.edit_search.installEventFilter(self)

    def open_with(self, commands):
        """commands: list of (label, callback or str-setting-key, group)."""
        self._commands = commands
        self._filter("")
        self.edit_search.setFocus()
        return self.exec()

    def eventFilter(self, obj, ev):
        from PyQt6.QtCore import QEvent
        if obj is self.edit_search and ev.type() == QEvent.Type.KeyPress:
            if ev.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                row = self.lst.currentRow()
                count = self.lst.count()
                if count:
                    step = 1 if ev.key() == Qt.Key.Key_Down else count - 1 if row <= 0 else -1
                    self.lst.setCurrentRow((row + step) % count)
                return True
            if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._run_current()
                return True
            if ev.key() == Qt.Key.Key_Escape:
                self.close()
                return True
        return super().eventFilter(obj, ev)

    def _filter(self, query):
        self.lst.clear()
        q = (query or "").strip().lower()
        for label, target, group in self._commands:
            if q and q not in label.lower():
                continue
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, target)
            if group:
                item.setToolTip(group)
            self.lst.addItem(item)
        if self.lst.count():
            self.lst.setCurrentRow(0)

    def _run_current(self):
        item = self.lst.currentItem()
        if item:
            self._run_item(item)

    def _run_item(self, item):
        target = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
        if callable(target):
            target()


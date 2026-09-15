# ============================================================
# AI FORKLIFT SAFETY SYSTEM — ON-SCREEN KEYBOARD (OSK)
# ============================================================
# Architecture: In-process PyQt5 QWidget overlay & Dialogs.
# Bilingual: Full QWERTY English and Standard Arabic layouts.
# Focus safety: All keys use Qt.NoFocus — the OSK never steals
#               focus from the target QLineEdit.
# Key injection: QLineEdit.insert() / .backspace() — works with
#                both plain text and Password echo mode.
# Layout: Classic PC Keyboard with tactile keycap styling.
# Dialogs: Stationary, cleanly centered, with no dragging or snap buttons.
# ============================================================

import os
import json
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QSizePolicy, QApplication, QLabel,
    QLineEdit, QDialog, QAbstractSpinBox
)
from PyQt5.QtCore import Qt, QEvent, pyqtSignal
from PyQt5.QtGui import QKeyEvent, QColor


# ============================================================
# CLASSIC KEY LAYOUTS & SHIFT MAPS
# ============================================================

ENGLISH_ROWS = [
    # Row 0 — Numbers & Backspace (14 keys)
    [('`', '`', 10), ('1', '1', 10), ('2', '2', 10), ('3', '3', 10), ('4', '4', 10),
     ('5', '5', 10), ('6', '6', 10), ('7', '7', 10), ('8', '8', 10), ('9', '9', 10),
     ('0', '0', 10), ('-', '-', 10), ('=', '=', 10), ('⌫ BACKSPACE', '__BACKSPACE__', 20)],

    # Row 1 — Tab, QWERTY & Backslash (14 keys)
    [('TAB', '__TAB__', 16), ('Q', 'q', 10), ('W', 'w', 10), ('E', 'e', 10), ('R', 'r', 10),
     ('T', 't', 10), ('Y', 'y', 10), ('U', 'u', 10), ('I', 'i', 10), ('O', 'o', 10),
     ('P', 'p', 10), ('[', '[', 10), (']', ']', 10), ('\\', '\\', 14)],

    # Row 2 — Caps Lock, Home row & Enter (13 keys)
    [('⇪ CAPS', '__CAPS__', 18), ('A', 'a', 10), ('S', 's', 10), ('D', 'd', 10), ('F', 'f', 10),
     ('G', 'g', 10), ('H', 'h', 10), ('J', 'j', 10), ('K', 'k', 10), ('L', 'l', 10),
     (';', ';', 10), ("'", "'", 10), ('⏎ ENTER', '__ENTER__', 22)],

    # Row 3 — Shift, ZXCV & Shift (12 keys)
    [('⇧ SHIFT', '__SHIFT__', 24), ('Z', 'z', 10), ('X', 'x', 10), ('C', 'c', 10), ('V', 'v', 10),
     ('B', 'b', 10), ('N', 'n', 10), ('M', 'm', 10), (',', ',', 10), ('.', '.', 10),
     ('/', '/', 10), ('⇧ SHIFT', '__SHIFT__', 26)],

    # Row 4 — Centered Spacebar & Language Toggle
    [('🌐 AR/EN', '__LANG__', 25), ('SPACE', '__SPACE__', 100), ('🌐 AR/EN', '__LANG__', 25)],
]

ENGLISH_SHIFT_MAP = {
    '`': '~', '1': '!', '2': '@', '3': '#', '4': '$', '5': '%',
    '6': '^', '7': '&', '8': '*', '9': '(', '0': ')', '-': '_', '=': '+',
    '[': '{', ']': '}', '\\': '|', ';': ':', "'": '"', ',': '<', '.': '>', '/': '?',
}

ARABIC_ROWS = [
    # Row 0
    [('ذ', 'ذ', 10), ('1', '1', 10), ('2', '2', 10), ('3', '3', 10), ('4', '4', 10),
     ('5', '5', 10), ('6', '6', 10), ('7', '7', 10), ('8', '8', 10), ('9', '9', 10),
     ('0', '0', 10), ('-', '-', 10), ('=', '=', 10), ('⌫ مسح', '__BACKSPACE__', 20)],

    # Row 1
    [('TAB', '__TAB__', 16), ('ض', 'ض', 10), ('ص', 'ص', 10), ('ث', 'ث', 10), ('ق', 'ق', 10),
     ('ف', 'ف', 10), ('غ', 'غ', 10), ('ع', 'ع', 10), ('ه', 'ه', 10), ('خ', 'خ', 10),
     ('ح', 'ح', 10), ('ج', 'ج', 10), ('د', 'د', 10), ('\\', '\\', 14)],

    # Row 2
    [('⇪ CAPS', '__CAPS__', 18), ('ش', 'ش', 10), ('س', 'س', 10), ('ي', 'ي', 10), ('ب', 'ب', 10),
     ('ل', 'ل', 10), ('ا', 'ا', 10), ('ت', 'ت', 10), ('ن', 'ن', 10), ('م', 'م', 10),
     ('ك', 'ك', 10), ('ط', 'ط', 10), ('⏎ دخول', '__ENTER__', 22)],

    # Row 3
    [('⇧ SHIFT', '__SHIFT__', 24), ('ئ', 'ئ', 10), ('ء', 'ء', 10), ('ؤ', 'ؤ', 10), ('ر', 'ر', 10),
     ('لا', 'لا', 10), ('ى', 'ى', 10), ('ة', 'ة', 10), ('و', 'و', 10), ('ز', 'ز', 10),
     ('ظ', 'ظ', 10), ('⇧ SHIFT', '__SHIFT__', 26)],

    # Row 4
    [('🌐 EN/AR', '__LANG__', 25), ('مسافة', '__SPACE__', 100), ('🌐 EN/AR', '__LANG__', 25)],
]

ARABIC_SHIFT_MAP = {
    '1': '!', '2': '@', '3': '#', '4': '$', '5': '%',
    '6': '^', '7': '&', '8': '*', '9': '(', '0': ')', '-': '_',
    '=': '+', 'ض': 'َ', 'ص': 'ً', 'ث': 'ُ', 'ق': 'ٌ',
    'ف': 'لإ', 'غ': 'إ', 'ع': '‘', 'ه': '÷', 'خ': '×',
    'ح': '؛', 'ج': '<', 'د': '>', 'ش': 'ِ', 'س': 'ٍ',
    'ي': ']', 'ب': '[', 'ل': 'لأ', 'ا': 'أ', 'ت': 'ـ',
    'ن': '،', 'ك': ':', 'ط': '"', 'ئ': '~', 'ء': 'ْ',
    'ؤ': '}', 'ر': '{', 'لا': 'لآ', 'ى': 'آ', 'ة': '’',
    'و': ',', 'ز': '.', 'ظ': '؟'
}


# ============================================================
# STYLED OSK KEY CAP
# ============================================================
class OSKKey(QPushButton):
    def __init__(self, label: str, action: str, key_type: str = "normal", parent=None):
        super().__init__(label, parent)
        self.action = action
        self.key_type = key_type
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(44)
        self._apply_style(False)

    def set_active(self, active: bool):
        self._apply_style(active)

    def _apply_style(self, active: bool = False):
        if self.key_type == "action":
            # Enter Key — Industrial Green
            bg = "#15803d" if not active else "#16a34a"
            hover_bg = "#16a34a"
            border = "#22c55e"
            color = "#ffffff"
            font_size = "12px"
            font_weight = "bold"
        elif self.key_type == "modifier":
            # Backspace, Tab, Lang — Slate
            bg = "#1e293b"
            hover_bg = "#334155"
            border = "#475569"
            color = "#94a3b8"
            font_size = "11px"
            font_weight = "bold"
        elif self.key_type in ("caps_off", "shift_off"):
            if active:
                bg = "#1d4ed8"
                hover_bg = "#2563eb"
                border = "#3b82f6"
                color = "#ffffff"
            else:
                bg = "#1e293b"
                hover_bg = "#334155"
                border = "#475569"
                color = "#94a3b8"
            font_size = "11px"
            font_weight = "bold"
        elif self.key_type == "space":
            bg = "#0f172a"
            hover_bg = "#1e293b"
            border = "#334155"
            color = "#94a3b8"
            font_size = "11px"
            font_weight = "normal"
        else:
            # Normal alphanumeric keycap
            bg = "#182234"
            hover_bg = "#24334a"
            border = "#2e415e"
            color = "#e2e8f0"
            font_size = "13px"
            font_weight = "bold"

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {color};
                border: 1px solid {border};
                border-radius: 6px;
                font-family: 'Segoe UI', 'Ubuntu', sans-serif;
                font-size: {font_size};
                font-weight: {font_weight};
                padding: 4px;
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
                border-color: #60a5fa;
            }}
            QPushButton:pressed {{
                background-color: #3b82f6;
                color: #ffffff;
                border-color: #93c5fd;
            }}
        """)


# ============================================================
# MAIN OSK WIDGET (CLASSIC BILINGUAL KEYBOARD)
# ============================================================
class OSKWidget(QWidget):
    enter_pressed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._target_widget = None
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)
        self.setFocusPolicy(Qt.NoFocus)

        self._shift_active = False
        self._caps_active = False
        self._lang = "EN"
        self._all_keys: list[OSKKey] = []

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(6, 6, 6, 6)
        self.main_layout.setSpacing(6)

        self.setStyleSheet("""
            QWidget {
                background-color: #0b0e14;
                border: 1px solid #1e293b;
                border-radius: 10px;
            }
        """)

        self._rebuild_layout()

    def set_target(self, widget):
        self._target_widget = widget

    def get_target(self):
        if self._target_widget is not None:
            try:
                if self._target_widget.isVisible():
                    return self._target_widget
            except RuntimeError:
                self._target_widget = None

        fw = QApplication.focusWidget()
        if fw is not None and fw is not self and not self.isAncestorOf(fw):
            return fw
        return None

    def _rebuild_layout(self):
        # Clear existing keys
        while self.main_layout.count():
            item = self.main_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        self._all_keys.clear()
        current_rows = ARABIC_ROWS if self._lang == "AR" else ENGLISH_ROWS

        for row in current_rows:
            row_widget = QWidget(self)
            row_widget.setFocusPolicy(Qt.NoFocus)
            row_widget.setAttribute(Qt.WA_AcceptTouchEvents, True)
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            for item in row:
                label, action, stretch = item
                if action is None:
                    row_layout.addStretch(stretch)
                    continue

                if action == '__ENTER__':
                    ktype = "action"
                elif action in ('__BACKSPACE__', '__TAB__', '__LANG__'):
                    ktype = "modifier"
                elif action == '__CAPS__':
                    ktype = "caps_off"
                elif action == '__SHIFT__':
                    ktype = "shift_off"
                elif action == '__SPACE__':
                    ktype = "space"
                else:
                    ktype = "normal"

                key = OSKKey(label, action, key_type=ktype, parent=row_widget)
                key.clicked.connect(lambda checked, k=key: self._on_key_pressed(k))
                row_layout.addWidget(key, stretch=stretch)
                self._all_keys.append(key)

            self.main_layout.addWidget(row_widget)

    def _on_key_pressed(self, key: OSKKey):
        action = key.action

        if action == '__BACKSPACE__':
            self._do_backspace()
        elif action == '__SPACE__':
            self._inject(' ')
        elif action == '__ENTER__':
            self._do_enter()
        elif action == '__TAB__':
            self._inject('    ')
        elif action == '__LANG__':
            self._lang = "AR" if self._lang == "EN" else "EN"
            self._rebuild_layout()
        elif action == '__CAPS__':
            self._caps_active = not self._caps_active
            self._update_display()
        elif action == '__SHIFT__':
            self._shift_active = not self._shift_active
            self._update_display()
        else:
            char = action
            uppercase = self._caps_active ^ self._shift_active
            shift_map = ARABIC_SHIFT_MAP if self._lang == "AR" else ENGLISH_SHIFT_MAP

            if self._shift_active and char in shift_map:
                char = shift_map[char]
            elif uppercase and self._lang == "EN":
                char = char.upper()
            elif not uppercase and self._lang == "EN":
                char = char.lower()

            self._inject(char)

            if self._shift_active:
                self._shift_active = False
                self._update_display()

    def _update_display(self):
        uppercase = self._caps_active ^ self._shift_active
        shift_map = ARABIC_SHIFT_MAP if self._lang == "AR" else ENGLISH_SHIFT_MAP

        for key in self._all_keys:
            if key.action == '__SHIFT__':
                key.set_active(self._shift_active)
            elif key.action == '__CAPS__':
                key.set_active(self._caps_active)
            elif len(key.action) == 1 and key.action.isalpha() and self._lang == "EN":
                key.setText(key.action.upper() if uppercase else key.action.lower())
            elif key.action in shift_map:
                if self._shift_active:
                    key.setText(shift_map[key.action])
                else:
                    key.setText(key.action)

    def _inject(self, char: str):
        target = self.get_target()
        if isinstance(target, QLineEdit):
            target.insert(char)
            target.setFocus()
        elif isinstance(target, QAbstractSpinBox):
            le = target.findChild(QLineEdit)
            if le:
                le.insert(char)
                le.setFocus()

    def _do_backspace(self):
        target = self.get_target()
        if isinstance(target, QLineEdit):
            target.backspace()
            target.setFocus()
        elif isinstance(target, QAbstractSpinBox):
            le = target.findChild(QLineEdit)
            if le:
                le.backspace()
                le.setFocus()

    def _do_enter(self):
        target = self.get_target()
        if target is not None:
            press = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier, "\r")
            release = QKeyEvent(QEvent.KeyRelease, Qt.Key_Return, Qt.NoModifier, "\r")
            QApplication.sendEvent(target, press)
            QApplication.sendEvent(target, release)
        self.enter_pressed.emit()


# Alias for explicit embedded keyboard usage
TouchKeyboardWidget = OSKWidget


# ============================================================
# STATIONARY FRAMELESS DIALOG (NO DRAGGING, LOCKED IN PLACE)
# ============================================================
class StationaryFramelessDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setModal(True)

    def mousePressEvent(self, event):
        event.accept()

    def mouseMoveEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()


# ============================================================
# TOUCHSCREEN PASSWORD AUTHENTICATION DIALOG
# ============================================================
class TouchPasswordDialog(StationaryFramelessDialog):
    def __init__(self, parent=None, title="Access Authorization", prompt="Enter Password:", role=""):
        super().__init__(parent)
        self.role = role
        self.setWindowTitle(title)
        self.setStyleSheet("""
            QDialog {
                background-color: #0b0f19;
                border: 2px solid #2b3d54;
                border-radius: 14px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 18)
        layout.setSpacing(12)

        header_bar = QWidget(self)
        header_layout = QHBoxLayout(header_bar)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)

        icon_label = QLabel("🔒", header_bar)
        icon_label.setStyleSheet("font-size: 18px; color: #3b82f6; background: transparent;")
        header_layout.addWidget(icon_label)

        title_label = QLabel(title, header_bar)
        title_label.setStyleSheet("font-family: 'Segoe UI Semibold'; font-size: 14px; font-weight: bold; color: #f1f5f9; background: transparent;")
        header_layout.addWidget(title_label)

        if role:
            role_badge = QLabel(f"[{role.upper()}]", header_bar)
            role_badge.setStyleSheet("font-family: 'Segoe UI Semibold'; font-size: 11px; font-weight: bold; color: #38bdf8; background: #0c4a6e; border-radius: 4px; padding: 2px 8px;")
            header_layout.addWidget(role_badge)

        header_layout.addStretch()

        btn_close = QPushButton("✕", header_bar)
        btn_close.setFocusPolicy(Qt.NoFocus)
        btn_close.setFixedSize(30, 30)
        btn_close.setStyleSheet("""
            QPushButton {
                background: #1e293b; color: #94a3b8; border: 1px solid #334155;
                border-radius: 6px; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background: #dc2626; color: #ffffff; border-color: #ef4444; }
        """)
        btn_close.clicked.connect(self.reject)
        header_layout.addWidget(btn_close)
        layout.addWidget(header_bar)

        sep = QWidget(self)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #1e293b;")
        layout.addWidget(sep)

        input_container = QWidget(self)
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(0, 4, 0, 4)
        input_layout.setSpacing(6)

        prompt_label = QLabel(prompt, input_container)
        prompt_label.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px; color: #94a3b8;")
        input_layout.addWidget(prompt_label)

        entry_row = QHBoxLayout()
        entry_row.setSpacing(8)

        self.password_edit = QLineEdit(input_container)
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("Type password using on-screen keyboard below...")
        self.password_edit.setMinimumHeight(44)
        self.password_edit.setStyleSheet("""
            QLineEdit {
                background-color: #111827; color: #38bdf8; border: 2px solid #1e3a5f;
                border-radius: 8px; font-size: 16px; font-weight: bold; padding: 0 12px; letter-spacing: 2px;
            }
            QLineEdit:focus { border: 2px solid #3b82f6; background-color: #0f172a; }
        """)
        entry_row.addWidget(self.password_edit, stretch=1)

        self.btn_toggle_echo = QPushButton("👁", input_container)
        self.btn_toggle_echo.setFocusPolicy(Qt.NoFocus)
        self.btn_toggle_echo.setFixedSize(44, 44)
        self.btn_toggle_echo.setToolTip("Toggle Password Visibility")
        self.btn_toggle_echo.setStyleSheet("""
            QPushButton {
                background: #1e293b; color: #94a3b8; border: 1px solid #334155;
                border-radius: 8px; font-size: 16px;
            }
            QPushButton:hover { background: #334155; color: #ffffff; }
        """)
        self.btn_toggle_echo.clicked.connect(self._toggle_echo)
        entry_row.addWidget(self.btn_toggle_echo)
        input_layout.addLayout(entry_row)
        layout.addWidget(input_container)

        self.keyboard = OSKWidget(self)
        self.keyboard.set_target(self.password_edit)
        self.keyboard.enter_pressed.connect(self._on_enter_pressed)
        layout.addWidget(self.keyboard)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        btn_cancel = QPushButton("CANCEL", self)
        btn_cancel.setFocusPolicy(Qt.NoFocus)
        btn_cancel.setMinimumHeight(40)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background: #1e293b; color: #94a3b8; border: 1px solid #334155;
                border-radius: 8px; font-size: 12px; font-weight: bold; padding: 0 20px;
            }
            QPushButton:hover { background: #334155; color: #f1f5f9; }
        """)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_row.addStretch()

        self.btn_ok = QPushButton("AUTHENTICATE  →", self)
        self.btn_ok.setFocusPolicy(Qt.NoFocus)
        self.btn_ok.setMinimumHeight(40)
        self.btn_ok.setStyleSheet("""
            QPushButton {
                background: #1d4ed8; color: #ffffff; border: 1px solid #3b82f6;
                border-radius: 8px; font-size: 12px; font-weight: bold; padding: 0 28px;
            }
            QPushButton:hover { background: #2563eb; }
            QPushButton:pressed { background: #1e40af; }
        """)
        self.btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_ok)
        layout.addLayout(btn_row)

        self.password_edit.returnPressed.connect(self.accept)
        self.adjustSize()

    def showEvent(self, event):
        super().showEvent(event)
        if self.parent():
            parent_geo = self.parent().geometry()
            x = parent_geo.x() + (parent_geo.width() - self.width()) // 2
            y = parent_geo.y() + (parent_geo.height() - self.height()) // 2
            self.move(max(0, x), max(0, y))
        self.password_edit.setFocus()
        self.keyboard.set_target(self.password_edit)

    def _toggle_echo(self):
        if self.password_edit.echoMode() == QLineEdit.Password:
            self.password_edit.setEchoMode(QLineEdit.Normal)
            self.btn_toggle_echo.setText("🔒")
        else:
            self.password_edit.setEchoMode(QLineEdit.Password)
            self.btn_toggle_echo.setText("👁")

    def _on_enter_pressed(self):
        self.accept()

    def text(self) -> str:
        return self.password_edit.text()

    @staticmethod
    def get_password(parent=None, title="Authentication Required", prompt="Enter Password:", role=""):
        dlg = TouchPasswordDialog(parent=parent, title=title, prompt=prompt, role=role)
        result = dlg.exec_()
        return dlg.text(), (result == QDialog.Accepted)

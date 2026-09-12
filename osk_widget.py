# ============================================================
# AI FORKLIFT SAFETY SYSTEM — ON-SCREEN KEYBOARD (OSK)
# ============================================================
# Architecture: In-process PyQt5 QWidget overlay.
# Focus safety: All keys use Qt.NoFocus — the OSK never steals
#               focus from the target QLineEdit.
# Key injection: QLineEdit.insert() / .backspace() — works with
#                both plain text and Password echo mode.
# Layout: Classic PC QWERTY Keyboard with physical keycap styling.
# Dialog: Stationary, cleanly centered, with no dragging or snap buttons.
# ============================================================

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QSizePolicy, QApplication, QLabel,
    QLineEdit, QDialog, QAbstractSpinBox
)
from PyQt5.QtCore import Qt, QEvent, pyqtSignal
from PyQt5.QtGui import QKeyEvent


# ============================================================
# CLASSIC KEY LAYOUT & SHIFT MAP
# ============================================================

# Classic QWERTY 5-Row Layout
# Each tuple: (label, action, stretch_factor)
CLASSIC_ROWS = [
    # Row 0 — Numbers & Backspace (14 keys, total weight 150)
    [('`', '`', 10), ('1', '1', 10), ('2', '2', 10), ('3', '3', 10), ('4', '4', 10),
     ('5', '5', 10), ('6', '6', 10), ('7', '7', 10), ('8', '8', 10), ('9', '9', 10),
     ('0', '0', 10), ('-', '-', 10), ('=', '=', 10), ('⌫ BACKSPACE', '__BACKSPACE__', 20)],

    # Row 1 — Tab, QWERTY & Backslash (14 keys, total weight 150)
    [('TAB', '__TAB__', 16), ('Q', 'q', 10), ('W', 'w', 10), ('E', 'e', 10), ('R', 'r', 10),
     ('T', 't', 10), ('Y', 'y', 10), ('U', 'u', 10), ('I', 'i', 10), ('O', 'o', 10),
     ('P', 'p', 10), ('[', '[', 10), (']', ']', 10), ('\\', '\\', 14)],

    # Row 2 — Caps Lock, Home row & Enter (13 keys, total weight 150)
    [('⇪ CAPS', '__CAPS__', 18), ('A', 'a', 10), ('S', 's', 10), ('D', 'd', 10), ('F', 'f', 10),
     ('G', 'g', 10), ('H', 'h', 10), ('J', 'j', 10), ('K', 'k', 10), ('L', 'l', 10),
     (';', ';', 10), ("'", "'", 10), ('⏎ ENTER', '__ENTER__', 22)],

    # Row 3 — Shift, ZXCV & Shift (12 keys, total weight 150)
    [('⇧ SHIFT', '__SHIFT__', 24), ('Z', 'z', 10), ('X', 'x', 10), ('C', 'c', 10), ('V', 'v', 10),
     ('B', 'b', 10), ('N', 'n', 10), ('M', 'm', 10), (',', ',', 10), ('.', '.', 10),
     ('/', '/', 10), ('⇧ SHIFT', '__SHIFT__', 26)],

    # Row 4 — Classic Centered Spacebar (total weight 150)
    [('__SPACER__', None, 25), ('SPACE', '__SPACE__', 100), ('__SPACER__', None, 25)],
]

CLASSIC_SHIFT_MAP = {
    '`': '~', '1': '!', '2': '@', '3': '#', '4': '$', '5': '%',
    '6': '^', '7': '&', '8': '*', '9': '(', '0': ')', '-': '_', '=': '+',
    '[': '{', ']': '}', '\\': '|', ';': ':', "'": '"', ',': '<', '.': '>', '/': '?',
}


# ============================================================
# INDIVIDUAL KEY BUTTON (REALISTIC CLASSIC KEYCAP)
# ============================================================
class OSKKey(QPushButton):
    """
    A single key on the classic on-screen keyboard.
    Always uses Qt.NoFocus to prevent stealing input focus.
    Styled with 3D beveled keycap edges for a classic physical feel.
    """
    def __init__(self, label: str, action: str, key_type: str = "normal", parent=None):
        super().__init__(label, parent)
        self.action = action
        self.key_type = key_type
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(64)
        self._apply_style(key_type)

    def _apply_style(self, ktype: str):
        self.key_type = ktype
        if ktype == "action":  # ENTER key (Classic blue accent)
            self.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563eb, stop:1 #1d4ed8);
                    border-top: 1px solid #60a5fa;
                    border-left: 1px solid #1d4ed8;
                    border-right: 1px solid #1d4ed8;
                    border-bottom: 3px solid #172554;
                    border-radius: 7px;
                    color: #ffffff;
                    font-family: 'Segoe UI', 'Arial', sans-serif;
                    font-size: 18px;
                    font-weight: bold;
                    padding: 4px;
                }
                QPushButton:pressed {
                    background: #1e40af;
                    border-top: 2px solid #172554;
                    border-bottom: 1px solid #60a5fa;
                    color: #bfdbfe;
                }
            """)
        elif ktype in ("modifier", "caps_off", "shift_off"):  # Tab, Caps, Shift, Backspace
            self.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #242c3b, stop:1 #181e29);
                    border-top: 1px solid #3b4658;
                    border-left: 1px solid #232a36;
                    border-right: 1px solid #232a36;
                    border-bottom: 3px solid #0f141c;
                    border-radius: 7px;
                    color: #94a3b8;
                    font-family: 'Segoe UI', 'Arial', sans-serif;
                    font-size: 16px;
                    font-weight: bold;
                    padding: 4px;
                }
                QPushButton:pressed {
                    background: #131822;
                    border-top: 2px solid #0f141c;
                    border-bottom: 1px solid #3b4658;
                    color: #e2e8f0;
                }
            """)
        elif ktype in ("caps_on", "shift_on"):  # Active Caps / Shift (Illuminated)
            self.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1d4ed8, stop:1 #1e3a8a);
                    border-top: 1px solid #93c5fd;
                    border-left: 1px solid #3b82f6;
                    border-right: 1px solid #3b82f6;
                    border-bottom: 3px solid #0f172a;
                    border-radius: 7px;
                    color: #ffffff;
                    font-family: 'Segoe UI', 'Arial', sans-serif;
                    font-size: 16px;
                    font-weight: bold;
                    padding: 4px;
                }
                QPushButton:pressed {
                    background: #172554;
                }
            """)
        elif ktype == "space":  # Wide Spacebar
            self.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2a3344, stop:1 #1c2330);
                    border-top: 1px solid #44536d;
                    border-left: 1px solid #2b3547;
                    border-right: 1px solid #2b3547;
                    border-bottom: 3px solid #111622;
                    border-radius: 7px;
                    color: #94a3b8;
                    font-family: 'Segoe UI', 'Arial', sans-serif;
                    font-size: 16px;
                    font-weight: bold;
                    padding: 4px;
                    letter-spacing: 2px;
                }
                QPushButton:pressed {
                    background: #141923;
                    border-top: 2px solid #111622;
                    border-bottom: 1px solid #44536d;
                    color: #60a5fa;
                }
            """)
        else:  # Normal Alphanumeric Key
            self.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2a3344, stop:1 #1c2330);
                    border-top: 1px solid #44536d;
                    border-left: 1px solid #2b3547;
                    border-right: 1px solid #2b3547;
                    border-bottom: 3px solid #111622;
                    border-radius: 7px;
                    color: #f8fafc;
                    font-family: 'Segoe UI', 'Arial', sans-serif;
                    font-size: 22px;
                    font-weight: bold;
                    padding: 4px;
                }
                QPushButton:pressed {
                    background: #141923;
                    border-top: 2px solid #111622;
                    border-bottom: 1px solid #44536d;
                    color: #60a5fa;
                }
            """)

    def set_active(self, active: bool):
        if self.action == '__SHIFT__':
            self._apply_style("shift_on" if active else "shift_off")
        elif self.action == '__CAPS__':
            self._apply_style("caps_on" if active else "caps_off")

    def set_shift_active(self, active: bool):
        self.set_active(active)

    def set_type(self, key_type: str):
        self._apply_style(key_type)


# ============================================================
# MAIN OSK WIDGET (CLASSIC KEYBOARD)
# ============================================================
class OSKWidget(QWidget):
    """
    Classic QWERTY On-Screen Keyboard overlay for industrial HMI.
    Embedded directly into authentication & input dialogs.
    """
    enter_pressed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._target_widget = None
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)
        self.setFocusPolicy(Qt.NoFocus)

        self._shift_active = False
        self._caps_active = False
        self._all_keys: list[OSKKey] = []

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(6)

        self.setStyleSheet("""
            QWidget {
                background-color: #0b0e14;
                border-radius: 10px;
            }
        """)

        self._build_classic_layout(main_layout)

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

    def _build_classic_layout(self, layout: QVBoxLayout):
        self._all_keys.clear()

        for row in CLASSIC_ROWS:
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
                elif action in ('__BACKSPACE__', '__TAB__'):
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

            layout.addWidget(row_widget)

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
        elif action == '__CAPS__':
            self._caps_active = not self._caps_active
            self._update_display()
        elif action == '__SHIFT__':
            self._shift_active = not self._shift_active
            self._update_display()
        else:
            char = action
            uppercase = self._caps_active ^ self._shift_active
            if self._shift_active and char in CLASSIC_SHIFT_MAP:
                char = CLASSIC_SHIFT_MAP[char]
            elif uppercase:
                char = char.upper()
            else:
                char = char.lower()

            self._inject(char)

            # Auto-release one-shot Shift after character press
            if self._shift_active:
                self._shift_active = False
                self._update_display()

    def _update_display(self):
        uppercase = self._caps_active ^ self._shift_active
        for key in self._all_keys:
            if key.action == '__SHIFT__':
                key.set_active(self._shift_active)
            elif key.action == '__CAPS__':
                key.set_active(self._caps_active)
            elif len(key.action) == 1 and key.action.isalpha():
                key.setText(key.action.upper() if uppercase else key.action.lower())
            elif key.action in CLASSIC_SHIFT_MAP:
                if self._shift_active:
                    key.setText(CLASSIC_SHIFT_MAP[key.action])
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
    """
    Clean, non-draggable modal dialog for industrial touchscreens.
    Locked in place — cannot be moved with mouse or touch gestures.
    Centered automatically on the primary display or parent window.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)

    def center_on_screen(self):
        if self.parentWidget():
            geo = self.parentWidget().geometry()
            x = max(10, geo.x() + (geo.width() - self.width()) // 2)
            y = max(10, geo.y() + (geo.height() - self.height()) // 2)
            self.move(x, y)
        else:
            screen = QApplication.primaryScreen().geometry() if QApplication.primaryScreen() else None
            if screen:
                x = max(10, (screen.width() - self.width()) // 2)
                y = max(10, (screen.height() - self.height()) // 2)
                self.move(x, y)

    def showEvent(self, event):
        super().showEvent(event)
        self.center_on_screen()


# For backward compatibility
DraggableFramelessDialog = StationaryFramelessDialog
DraggableHeaderBar = QWidget


# ============================================================
# INDUSTRIAL TOUCH TEXT INPUT DIALOG (CLASSIC DESIGN)
# ============================================================
class TouchInputDialog(StationaryFramelessDialog):
    """
    Touchscreen-native text input dialog with classic keyboard.
    Non-draggable, stationary, and cleanly centered.
    """
    def __init__(self, parent=None, title="Text Input", prompt="Enter Value:", default_text=""):
        super().__init__(parent)
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

        # Header bar — clean, classic, NO drag handle, NO snap buttons
        header_bar = QWidget(self)
        header_layout = QHBoxLayout(header_bar)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)

        header_icon = QLabel("⌨")
        header_icon.setStyleSheet("font-size: 24px;")
        header_layout.addWidget(header_icon)

        title_lbl = QLabel(title.upper())
        title_lbl.setStyleSheet("color: #f1f5f9; font-family: 'Segoe UI', 'Arial'; font-size: 18px; font-weight: bold; letter-spacing: 1px;")
        header_layout.addWidget(title_lbl)

        header_layout.addStretch()

        # Clean Close Button
        btn_close = QPushButton("✕ CLOSE")
        btn_close.setFixedSize(95, 38)
        btn_close.setFocusPolicy(Qt.NoFocus)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #3b1111;
                color: #fca5a5;
                border: 1px solid #991b1b;
                border-radius: 7px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:pressed {
                background-color: #b91c1c;
                color: white;
            }
        """)
        btn_close.clicked.connect(self.reject)
        header_layout.addWidget(btn_close)
        layout.addWidget(header_bar)

        # Prompt
        prompt_lbl = QLabel(prompt)
        prompt_lbl.setStyleSheet("color: #94a3b8; font-size: 15px; font-family: 'Segoe UI', sans-serif;")
        layout.addWidget(prompt_lbl)

        # Input container
        input_container = QWidget()
        input_container.setFixedHeight(60)
        input_container.setStyleSheet("""
            QWidget {
                background-color: #131b2e;
                border: 2px solid #3b82f6;
                border-radius: 10px;
            }
        """)
        input_row = QHBoxLayout(input_container)
        input_row.setContentsMargins(14, 4, 10, 4)
        input_row.setSpacing(10)

        self.text_edit = QLineEdit()
        self.text_edit.setText(default_text)
        self.text_edit.setPlaceholderText("Enter text and press ENTER...")
        self.text_edit.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: #ffffff;
                font-size: 24px;
                font-family: 'Segoe UI', 'Arial', sans-serif;
            }
        """)
        self.text_edit.returnPressed.connect(self.accept)
        input_row.addWidget(self.text_edit, stretch=1)

        # Clear button
        self.btn_clear = QPushButton("✖")
        self.btn_clear.setFixedSize(50, 50)
        self.btn_clear.setFocusPolicy(Qt.NoFocus)
        self.btn_clear.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #94a3b8;
                border: none;
                border-radius: 8px;
                font-size: 18px;
            }
            QPushButton:pressed {
                background-color: #334155;
                color: #ffffff;
            }
        """)
        self.btn_clear.clicked.connect(self.text_edit.clear)
        input_row.addWidget(self.btn_clear)

        layout.addWidget(input_container)

        # Embedded Classic OSK
        self.embedded_osk = OSKWidget(parent=self)
        self.embedded_osk.set_target(self.text_edit)
        self.embedded_osk.enter_pressed.connect(self.accept)
        layout.addWidget(self.embedded_osk)

        self.resize(1360, 580)
        self.setMinimumSize(1200, 540)
        self.text_edit.setFocus()

    @classmethod
    def get_text(cls, parent=None, title="Text Input", prompt="Enter Value:", default_text="") -> tuple[str, bool]:
        dlg = cls(parent=parent, title=title, prompt=prompt, default_text=default_text)
        dlg.center_on_screen()
        res = dlg.exec_()
        return dlg.text_edit.text(), (res == QDialog.Accepted)


# ============================================================
# INDUSTRIAL TOUCH PASSWORD DIALOG (CLASSIC DESIGN)
# ============================================================
class TouchPasswordDialog(StationaryFramelessDialog):
    """
    Touchscreen-native authentication dialog with classic keyboard.
    Non-draggable, stationary, and cleanly centered.
    """
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

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 18)
        layout.setSpacing(12)

        # Header bar — clean, classic, NO drag handle, NO snap buttons
        header_bar = QWidget(self)
        header_layout = QHBoxLayout(header_bar)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)

        header_icon = QLabel("🔒")
        header_icon.setStyleSheet("font-size: 24px;")
        header_layout.addWidget(header_icon)

        title_lbl = QLabel(title.upper())
        title_lbl.setStyleSheet("color: #f1f5f9; font-family: 'Segoe UI', 'Arial'; font-size: 18px; font-weight: bold; letter-spacing: 1px;")
        header_layout.addWidget(title_lbl)

        if role:
            role_badge = QLabel(f"  ROLE: {role.upper()}  ")
            role_badge.setStyleSheet("""
                background-color: #1e3a8a;
                color: #93c5fd;
                font-family: 'Segoe UI', 'Arial';
                font-size: 13px;
                font-weight: bold;
                border-radius: 5px;
                padding: 4px 12px;
                border: 1px solid #2563eb;
            """)
            header_layout.addWidget(role_badge)

        header_layout.addStretch()

        # Clean Close Button
        btn_close = QPushButton("✕ CLOSE")
        btn_close.setFixedSize(95, 38)
        btn_close.setFocusPolicy(Qt.NoFocus)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #3b1111;
                color: #fca5a5;
                border: 1px solid #991b1b;
                border-radius: 7px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:pressed {
                background-color: #b91c1c;
                color: white;
            }
        """)
        btn_close.clicked.connect(self.reject)
        header_layout.addWidget(btn_close)
        layout.addWidget(header_bar)

        # Prompt
        prompt_lbl = QLabel(prompt)
        prompt_lbl.setStyleSheet("color: #94a3b8; font-size: 15px; font-family: 'Segoe UI', sans-serif;")
        layout.addWidget(prompt_lbl)

        # Input container
        input_container = QWidget()
        input_container.setFixedHeight(60)
        input_container.setStyleSheet("""
            QWidget {
                background-color: #131b2e;
                border: 2px solid #3b82f6;
                border-radius: 10px;
            }
        """)
        input_row = QHBoxLayout(input_container)
        input_row.setContentsMargins(14, 4, 10, 4)
        input_row.setSpacing(10)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("Enter password and press ENTER...")
        self.password_edit.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: #ffffff;
                font-size: 28px;
                font-family: 'Segoe UI', 'Arial', monospace;
                letter-spacing: 4px;
            }
        """)
        self.password_edit.returnPressed.connect(self.accept)
        input_row.addWidget(self.password_edit, stretch=1)

        # Clear button
        self.btn_clear = QPushButton("✖")
        self.btn_clear.setFixedSize(50, 50)
        self.btn_clear.setFocusPolicy(Qt.NoFocus)
        self.btn_clear.setToolTip("Clear text")
        self.btn_clear.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #94a3b8;
                border: none;
                border-radius: 8px;
                font-size: 18px;
            }
            QPushButton:pressed {
                background-color: #334155;
                color: #ffffff;
            }
        """)
        self.btn_clear.clicked.connect(self.password_edit.clear)
        input_row.addWidget(self.btn_clear)

        # Eye button (Show/Hide password)
        self.btn_eye = QPushButton("👁")
        self.btn_eye.setFixedSize(50, 50)
        self.btn_eye.setFocusPolicy(Qt.NoFocus)
        self.btn_eye.setToolTip("Show / Hide password")
        self.btn_eye.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #60a5fa;
                border: 1px solid #2563eb;
                border-radius: 8px;
                font-size: 22px;
            }
            QPushButton:pressed {
                background-color: #2563eb;
                color: #ffffff;
            }
        """)
        self.btn_eye.clicked.connect(self._toggle_echo_mode)
        input_row.addWidget(self.btn_eye)

        layout.addWidget(input_container)

        # Embedded Classic OSK
        self.embedded_osk = OSKWidget(parent=self)
        self.embedded_osk.set_target(self.password_edit)
        self.embedded_osk.enter_pressed.connect(self.accept)
        layout.addWidget(self.embedded_osk)

        self.resize(1360, 580)
        self.setMinimumSize(1200, 540)
        self.password_edit.setFocus()

    def _toggle_echo_mode(self):
        if self.password_edit.echoMode() == QLineEdit.Password:
            self.password_edit.setEchoMode(QLineEdit.Normal)
            self.btn_eye.setText("🙈")
        else:
            self.password_edit.setEchoMode(QLineEdit.Password)
            self.btn_eye.setText("👁")

    @classmethod
    def get_password(cls, parent=None, title="Access Authorization", prompt="Enter Password:", role="") -> tuple[str, bool]:
        dlg = cls(parent=parent, title=title, prompt=prompt, role=role)
        dlg.center_on_screen()
        res = dlg.exec_()
        return dlg.password_edit.text(), (res == QDialog.Accepted)

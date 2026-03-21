import time
from pynput import keyboard
from PyQt6.QtCore import QObject, pyqtSignal
from config import DOUBLE_TAP_INTERVAL


class HotkeyListener(QObject):
    """Global hotkey listener with two modes:

    1. Hold Ctrl+Shift: press-and-hold recording
    2. Double-tap Ctrl: hands-free mode (double-tap Ctrl again to stop)
    """

    pressed = pyqtSignal()
    released = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._ctrl_held = False
        self._shift_held = False
        self._recording = False
        self._hands_free = False
        self._listener: keyboard.Listener | None = None

        # Double-tap detection
        self._last_ctrl_release = 0.0
        self._last_ctrl_press = 0.0
        self._ctrl_tap_count = 0
        self._last_shift_press = 0.0
        self._shift_tap_count = 0

    def start(self):
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _on_press(self, key):
        is_ctrl = key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r)
        is_shift = key in (keyboard.Key.shift, keyboard.Key.shift_r)

        # 1. Track Shift and detect double-tap (Hands-free TOGGLE: START/STOP)
        if is_shift:
            self._shift_held = True
            now = time.time()
            if now - self._last_shift_press < DOUBLE_TAP_INTERVAL:
                self._shift_tap_count += 1
            else:
                self._shift_tap_count = 1
            self._last_shift_press = now

            # Toggle hands-free mode: double-tap Shift starts OR stops
            if self._shift_tap_count >= 2:
                self._shift_tap_count = 0
                if not self._recording:
                    self._hands_free = True
                    self._recording = True
                    self.pressed.emit()
                else:
                    self._hands_free = False
                    self._recording = False
                    self.released.emit()
                return

        # 3. Track Ctrl (used for Hold mode together with Shift)
        elif is_ctrl:
            self._ctrl_held = True
            # Also reset shift tapping on other key down
            self._shift_tap_count = 0

        # 4. Hold mode (Ctrl+Shift): start on press
        if self._ctrl_held and self._shift_held and not self._recording:
            self._recording = True
            self._hands_free = False
            self.pressed.emit()

    def _on_release(self, key):
        is_ctrl = key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r)
        is_shift = key in (keyboard.Key.shift, keyboard.Key.shift_r)

        if is_ctrl:
            self._ctrl_held = False
            self._last_ctrl_release = time.time()
        elif is_shift:
            self._shift_held = False

        # Hold mode: stop when any key released (but not in hands-free mode)
        if self._recording and not self._hands_free:
            if not (self._ctrl_held and self._shift_held):
                self._recording = False
                self.released.emit()

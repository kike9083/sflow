import subprocess
import platform
import time
import ctypes

_is_windows = platform.system() == "Windows"

_saved_hwnd: int | None = None


def save_frontmost_app():
    """Save the currently focused window before recording starts."""
    global _saved_hwnd
    if _is_windows:
        try:
            user32 = ctypes.windll.user32
            _saved_hwnd = user32.GetForegroundWindow()
        except Exception:
            _saved_hwnd = None
    else:
        try:
            result = subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to get name of first process whose frontmost is true'],
                capture_output=True, text=True, timeout=2,
            )
            name = result.stdout.strip()
            if name and name != "SFlow":
                _saved_hwnd = name
        except Exception:
            pass


def paste_text(text: str):
    """Copy text to clipboard and paste into the previously active window."""
    if _is_windows:
        _paste_text_windows(text)
    else:
        _paste_text_macos(text)


def _paste_text_windows(text: str):
    global _saved_hwnd

    import pyperclip
    pyperclip.copy(text)

    # user32 constants
    VK_CONTROL = 0x11
    VK_V = 0x56
    KEYEVENTF_KEYUP = 0x0002

    def keybd_event(vk, scan, flags, extra):
        ctypes.windll.user32.keybd_event(vk, scan, flags, extra)

    if _saved_hwnd:
        try:
            user32 = ctypes.windll.user32
            # Set focus and ensure it's on top
            user32.SetForegroundWindow(_saved_hwnd)
        except Exception:
            pass
        time.sleep(0.1)

    # Perform Ctrl+V using native key events (very reliable)
    keybd_event(VK_CONTROL, 0, 0, 0)      # Ctrl down
    keybd_event(VK_V, 0, 0, 0)            # V down
    time.sleep(0.02)
    keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)       # V up
    keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0) # Ctrl up

    _saved_hwnd = None


def _paste_text_macos(text: str):
    import pyperclip
    pyperclip.copy(text)

    subprocess.run(["osascript", "-e", 'tell application "System Events" to keystroke "v" using command down'])

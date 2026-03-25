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
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            
            # Get window title to verify we aren't saving SFlow itself
            length = user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value
            
            if title == "SFlow" or not title:
                # If we accidentally caught SFlow or an empty title, don't overwrite a potentially good saved handle
                return

            print(f"Objetivo de pegado detectado: {title}")
            _saved_hwnd = hwnd
        except Exception as e:
            print(f"Error al guardar ventana: {e}")
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
    from pynput.keyboard import Controller, Key
    
    # Copy to clipboard
    pyperclip.copy(text)
    time.sleep(0.1)

    if _saved_hwnd:
        try:
            import ctypes
            # Restore the previously active window
            print(f"Restaurando foco a ventana con handle: {_saved_hwnd}")
            ctypes.windll.user32.SetForegroundWindow(_saved_hwnd)
            time.sleep(0.3)  # Give Windows more time to switch back
        except Exception as e:
            print(f"Error al restaurar foco: {e}")
            pass

    # Perform Ctrl+V using pynput Controller
    print(f"Simulando Ctrl+V para pegar: {text[:20]}...")
    keyboard_controller = Controller()
    
    # Safety: ensure everything is released before paste
    keyboard_controller.release(Key.shift)
    keyboard_controller.release(Key.ctrl)
    
    # Robust paste: Ctrl down, V tap, Ctrl up
    with keyboard_controller.pressed(Key.ctrl):
        keyboard_controller.tap('v')

    _saved_hwnd = None


def _paste_text_macos(text: str):
    import pyperclip
    pyperclip.copy(text)

    subprocess.run(["osascript", "-e", 'tell application "System Events" to keystroke "v" using command down'])

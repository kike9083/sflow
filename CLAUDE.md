# CLAUDE.md — SFlow Development Instructions

## What is SFlow?

SFlow is a macOS voice-to-text desktop tool that replaces Wispr Flow ($15/month). It captures audio via global hotkeys, transcribes using Groq Whisper API (~$0.02/hour), and auto-pastes text wherever the cursor is. It includes a floating pill UI overlay, real-time audio visualization, SQLite history, and a web dashboard.

## Quick Start (Dev Mode)

```bash
# 1. Install system dependency
brew install portaudio

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Set up environment
cp .env.example .env
# Edit .env and add your GROQ_API_KEY (get one at https://console.groq.com/keys)

# 5. Run
python3 main.py
```

## Build Desktop App (.app bundle)

```bash
# Build SFlow.app (generates icns, builds with PyInstaller, signs ad-hoc)
bash build.sh

# Install to Applications (MUST use ditto, not cp -r)
ditto dist/SFlow.app /Applications/SFlow.app

# Remove quarantine if needed
xattr -cr /Applications/SFlow.app
```

The .app bundle is self-contained (~107MB). No Python, no venv, no terminal needed.
On first launch, if no API key exists in `~/Library/Application Support/SFlow/.env`,
a dialog asks for it. The app lives in the menu bar (no Dock icon).

### Build Requirements
- Python 3.12+ with venv
- PyInstaller (installed automatically by build.sh)
- portaudio (`brew install portaudio`)

## macOS Permissions Required

- **Accessibility**: System Settings → Privacy & Security → Accessibility → add your Terminal/IDE
- **Microphone**: Automatically requested on first use
- **Input Monitoring**: May be required for pynput — add your Terminal/IDE

## Project Structure

```
sflow/
├── main.py                 # Entry point — tray icon, first-run dialog, launch-at-login, app controller
├── config.py               # All configuration constants (UI, audio, paths, bundle detection)
├── sflow.spec              # PyInstaller spec for building .app bundle
├── build.sh                # One-shot build script (icns → PyInstaller → sign)
├── ui/
│   ├── pill_widget.py      # Floating pill overlay (native macOS via PyObjC)
│   └── audio_visualizer.py # Real-time audio bars
├── core/
│   ├── recorder.py         # sounddevice audio capture
│   ├── transcriber.py      # Groq Whisper API client (lazy init, 10s timeout)
│   ├── hotkey.py           # Global hotkeys (Ctrl+Shift hold + double-tap Ctrl)
│   └── clipboard.py        # Focus save/restore + native paste via AppleScript
├── db/
│   └── database.py         # SQLite CRUD
├── web/
│   └── server.py           # Flask dashboard at localhost:5678 (auto-finds free port)
├── logo.png                # Brand logo (full size, used for .icns generation)
├── logo_small.png          # Brand logo (22x22 for menu bar + pill)
├── SFlow.icns              # macOS app icon (generated from logo.png)
├── requirements.txt
├── .env                    # GROQ_API_KEY (never committed)
└── .env.example
```

## Architecture & Data Flow

```
Hotkey Press (pynput thread)
  → [QueuedConnection] → save_frontmost_app() + recorder.start()
  → pill.set_state(RECORDING)
  → sounddevice callback → queue.Queue → QTimer → audio_visualizer paints bars

Hotkey Release (pynput thread)
  → [QueuedConnection] → recorder.stop()
  → pill.set_state(PROCESSING)
  → background Thread: transcriber.transcribe(wav_buffer)
    → Groq Whisper API returns text
    → [QueuedConnection] → paste_text() + db.insert() + pill.set_state(DONE)
```

## Critical Implementation Details

### 1. Qt Signal Threading (MUST use QueuedConnection)
pynput emits signals from its own thread. Both QObjects live in the main thread, so Qt's `AutoConnection` incorrectly chooses `DirectConnection`. But since `emit()` comes from pynput's thread, UI modifications happen on the wrong thread — undefined behavior on macOS. **Always use explicit `Qt.ConnectionType.QueuedConnection`.**

### 2. macOS Floating Window (MUST use PyObjC)
Qt's `WindowDoesNotAcceptFocus` flag doesn't work properly on macOS. The pill must use native Cocoa APIs via PyObjC to float without stealing focus:
```python
import AppKit, objc
from ctypes import c_void_p

ns_view = objc.objc_object(c_void_p=c_void_p(widget.winId().__int__()))
ns_window = ns_view.window()
ns_window.setLevel_(AppKit.NSFloatingWindowLevel)
ns_window.setStyleMask_(ns_window.styleMask() | AppKit.NSWindowStyleMaskNonactivatingPanel)
ns_window.setHidesOnDeactivate_(False)
ns_window.setCollectionBehavior_(
    AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
    | AppKit.NSWindowCollectionBehaviorStationary
    | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
)
```
This is the same approach used by Spotlight and Wispr Flow itself.

### 3. Auto-Paste (MUST use native AppleScript, not pyautogui)
pyautogui is unreliable on macOS when modifier keys were recently released. Use:
- `save_frontmost_app()` before recording (via AppleScript)
- `pbcopy` to copy text to clipboard
- AppleScript to restore focus to saved app
- AppleScript `keystroke "v" using command down` to paste

### 4. Audio Pipeline (thread-safe)
sounddevice callback runs in audio thread — NEVER touch Qt widgets from it. Use `queue.Queue` as bridge:
- Callback → puts audio chunks in queue
- QTimer on main thread → polls queue → updates visualizer

### 5. Short Recording Filter
Recordings under 0.3 seconds are accidental taps — skip transcription and return to idle.

### 6. Bundle vs Dev Mode (config.py)
`config.py` detects `sys.frozen` to switch between dev and .app bundle:
- **Dev mode**: assets and data live in the project root directory
- **Bundle mode**: read-only assets (logo) come from `sys._MEIPASS`, writable data (DB, .env) goes to `~/Library/Application Support/SFlow/`

### 7. Desktop App Features (main.py)
- **System Tray**: QSystemTrayIcon in menu bar with dashboard link, "Start with macOS" toggle, quit
- **First-Run Dialog**: If GROQ_API_KEY is empty, shows a QDialog to enter it (saves to Application Support)
- **Launch at Login**: Creates/removes a LaunchAgent plist in `~/Library/LaunchAgents/`
- **Hide from Dock**: `NSApplicationActivationPolicyAccessory` via PyObjC (MUST be set AFTER first-run dialog)

### 8. Port Selection (web/server.py)
Default port is 5678 (not 5000 which conflicts with AirPlay on macOS 12+). Auto-scans for free port.

### 9. Building the .app (IMPORTANT)
- Use `ditto` (not `cp -r`) to copy .app to /Applications — `cp -r` corrupts bundle metadata causing segfaults
- The .icns is auto-generated from logo.png by build.sh if missing
- Ad-hoc signing (`codesign --force --deep --sign -`) is sufficient for personal use
- Remove quarantine after install: `xattr -cr /Applications/SFlow.app`

## Customization

### Hotkeys
Edit `core/hotkey.py`:
- **Hold mode**: Currently Ctrl+Shift. Change `is_ctrl`/`is_shift` checks.
- **Hands-free mode**: Currently double-tap Ctrl within 400ms. Change `DOUBLE_TAP_INTERVAL` in config.py.

### UI Dimensions
Edit `config.py`:
- `PILL_WIDTH_IDLE` (34) — width when just showing logo
- `PILL_WIDTH_RECORDING` (120) — width during recording with bars
- `PILL_WIDTH_STATUS` (52) — width for checkmark/spinner/error
- `PILL_HEIGHT` (34) — height of pill
- `PILL_MARGIN_BOTTOM` (14) — distance from bottom of screen

### Audio
Edit `config.py`:
- `SAMPLE_RATE` (16000) — 16kHz is optimal for speech
- `NUM_BARS` (8) — number of visualizer bars
- `BAR_GAIN` (6.0) — sensitivity of bars
- `BAR_DECAY` (0.80) — how quickly bars fall

## Building from Scratch

If you want to rebuild this project from scratch using Claude, copy the `PRP.md` file and give it to Claude with the instruction: "Build this project following the PRP phases. Execute all phases sequentially, validating each one before moving to the next."

The PRP contains all the architectural decisions, gotchas, and anti-patterns discovered during development. It serves as a complete blueprint.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Pill doesn't appear | Check Accessibility permissions for your terminal |
| Pill appears but steals focus | Verify PyObjC is installed: `python3 -c "import AppKit"` |
| Audio not captured | Check Microphone permissions + verify portaudio: `brew list portaudio` |
| Paste doesn't work | Grant Accessibility permission to terminal; check `save_frontmost_app` |
| Ctrl+C doesn't kill the process | This is handled by `signal.signal(signal.SIGINT, signal.SIG_DFL)` in main.py |
| Short taps trigger transcription | Adjust the 0.3s threshold in `main.py` `_on_hotkey_released` |
| Web dashboard not loading | Port auto-selects from 5678. Check: `lsof -i :5678` |
| .app crashes on launch (segfault) | Was copied with `cp -r` instead of `ditto`. Reinstall with `ditto` |
| .app blocked by macOS | Run `xattr -cr /Applications/SFlow.app` to remove quarantine |
| First-run dialog invisible | Bug if NSApplicationActivationPolicyAccessory is set before dialog. Already fixed |
| Transcription hangs forever | API timeout is 10s. Check your GROQ_API_KEY is valid |

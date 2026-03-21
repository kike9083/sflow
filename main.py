#!/usr/bin/env python3
"""SFlow - Voice-to-text desktop tool powered by Groq Whisper."""

import sys
import signal
import threading
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QObject, QTimer, pyqtSignal, pyqtSlot

from ui.pill_widget import PillWidget
from core.recorder import AudioRecorder
from core.transcriber import Transcriber
from core.hotkey import HotkeyListener
from core.clipboard import paste_text, save_frontmost_app
from db.database import TranscriptionDB
from web.server import start_web_server


class SFlowApp(QObject):
    """Main application controller. Wires hotkey -> recorder -> transcriber -> clipboard."""

    # Signal to handle transcription result on the main thread
    transcription_done = pyqtSignal(str, float)
    transcription_error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.recorder = AudioRecorder()
        self.transcriber = Transcriber()
        self.db = TranscriptionDB()
        self.hotkey = HotkeyListener()
        self.pill = PillWidget()

        # Connect visualizer to recorder's audio queue
        self.pill.visualizer.set_audio_queue(self.recorder.audio_queue)

        # Connect hotkey signals - MUST use QueuedConnection because pynput
        # emits from its own thread, but both QObjects live in the main thread
        # so AutoConnection would incorrectly choose DirectConnection
        self.hotkey.pressed.connect(self._on_hotkey_pressed, Qt.ConnectionType.QueuedConnection)
        self.hotkey.released.connect(self._on_hotkey_released, Qt.ConnectionType.QueuedConnection)

        # Connect transcription signals (same reason - emitted from worker thread)
        self.transcription_done.connect(self._on_transcription_done, Qt.ConnectionType.QueuedConnection)
        self.transcription_error.connect(self._on_transcription_error, Qt.ConnectionType.QueuedConnection)

    def start(self):
        self.hotkey.start()
        self.pill.show()
        self.pill.set_state(PillWidget.STATE_IDLE)
        print("SFlow running. Ctrl+Shift (hold) or Shift-Shift (hands-free toggle). Ctrl+C to quit.")

    @pyqtSlot()
    def _on_hotkey_pressed(self):
        save_frontmost_app()
        self.recorder.start()
        self.pill.set_state(PillWidget.STATE_RECORDING)

    @pyqtSlot()
    def _on_hotkey_released(self):
        duration = self.recorder.stop()
        self.pill.set_state(PillWidget.STATE_PROCESSING)

        # Don't transcribe very short recordings (accidental taps)
        if duration < 0.3:
            self.pill.set_state(PillWidget.STATE_IDLE)
            return

        # Transcribe in background thread to avoid blocking UI
        wav_buffer = self.recorder.get_wav_buffer()
        recording_duration = self.recorder.get_duration()
        thread = threading.Thread(
            target=self._transcribe_worker,
            args=(wav_buffer, recording_duration),
            daemon=True,
        )
        thread.start()

    def _transcribe_worker(self, wav_buffer, duration):
        try:
            text = self.transcriber.transcribe(wav_buffer)
            if text:
                self.transcription_done.emit(text, duration)
            else:
                self.transcription_error.emit("No speech detected")
        except Exception as e:
            self.transcription_error.emit(str(e))

    @pyqtSlot(str, float)
    def _on_transcription_done(self, text: str, duration: float):
        # Paste text where cursor is
        paste_text(text)
        # Save to database
        self.db.insert(text=text, duration_seconds=duration)
        # Update UI
        self.pill.set_state(PillWidget.STATE_DONE)
        print(f"Transcribed ({duration:.1f}s): {text[:80]}{'...' if len(text) > 80 else ''}")

    @pyqtSlot(str)
    def _on_transcription_error(self, error: str):
        self.pill.set_state(PillWidget.STATE_ERROR)
        print(f"Transcription error: {error}")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SFlow")
    app.setQuitOnLastWindowClosed(False)

    # Allow Ctrl+C to kill the app
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # Start web dashboard
    port = start_web_server(5000)

    sflow = SFlowApp()
    sflow.start()
    print(f"Dashboard: http://localhost:{port}")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

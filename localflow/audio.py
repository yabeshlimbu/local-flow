"""Microphone capture at 16 kHz mono, with live level metering and quiet-speech gain."""
from __future__ import annotations

import subprocess
import threading
import time

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000


class Recorder:
    def __init__(self, device=None) -> None:
        self.device = device
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._stream: sd.InputStream | None = None
        self.level = 0.0  # 0..1 smoothed RMS for the overlay
        self.started_at = 0.0

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def _callback(self, indata, frames, time_info, status) -> None:
        mono = indata[:, 0].copy()
        with self._lock:
            self._chunks.append(mono)
        rms = float(np.sqrt(np.mean(mono ** 2)) + 1e-9)
        # map roughly -60 dB..-10 dB to 0..1
        db = 20 * np.log10(rms)
        target = min(1.0, max(0.0, (db + 60) / 50))
        self.level = self.level * 0.6 + target * 0.4

    def start(self) -> None:
        if self._stream:
            return
        with self._lock:
            self._chunks = []
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32",
            device=self.device, blocksize=1024, callback=self._callback,
        )
        self._stream.start()
        self.started_at = time.time()

    def elapsed(self) -> float:
        return time.time() - self.started_at if self._stream else 0.0

    def snapshot(self) -> np.ndarray:
        with self._lock:
            return np.concatenate(self._chunks) if self._chunks else np.zeros(0, np.float32)

    def drain(self) -> np.ndarray:
        """Return audio captured so far and clear the buffer (used by Notetaker)."""
        with self._lock:
            audio = np.concatenate(self._chunks) if self._chunks else np.zeros(0, np.float32)
            self._chunks = []
        return audio

    def stop(self) -> np.ndarray:
        if not self._stream:
            return np.zeros(0, np.float32)
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None
            self.level = 0.0
        return self.snapshot()


def is_silent(audio: np.ndarray, threshold_db: float = -55.0) -> bool:
    if audio.size < SAMPLE_RATE * 0.25:
        return True
    rms = float(np.sqrt(np.mean(audio ** 2)) + 1e-12)
    return 20 * np.log10(rms) < threshold_db


def enhance_quiet_speech(audio: np.ndarray) -> np.ndarray:
    """'Whisper mode': remove DC, gate the noise floor and normalise peaks so that
    very quietly spoken / whispered words reach a level the model handles well."""
    if audio.size == 0:
        return audio
    audio = audio - np.mean(audio)
    peak = float(np.max(np.abs(audio)) + 1e-9)
    target_peak = 0.9
    gain = min(target_peak / peak, 30.0)  # cap at ~ +30 dB
    if gain > 1.0:
        audio = audio * gain
    return np.clip(audio, -1.0, 1.0).astype(np.float32)


def play_sound(name: str) -> None:
    """Short system sound cue (non-blocking)."""
    path = f"/System/Library/Sounds/{name}.aiff"
    try:
        subprocess.Popen(["afplay", "-v", "0.35", path],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

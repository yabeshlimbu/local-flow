"""Local speech-to-text with Whisper on Apple Silicon (MLX)."""
from __future__ import annotations

import threading

import numpy as np

from .config import settings


class Transcriber:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded_model: str | None = None

    def warm_up(self) -> None:
        """Load model weights once so the first dictation is fast."""
        self.transcribe(np.zeros(16000, dtype=np.float32))

    def transcribe(self, audio: np.ndarray, language: str | None = None,
                   vocabulary: list[str] | None = None) -> dict:
        import mlx_whisper

        model = settings["whisper_model"]
        lang = language or settings["language"]
        kwargs: dict = {
            "path_or_hf_repo": model,
            "temperature": (0.0, 0.2, 0.4),
            "condition_on_previous_text": False,
            "no_speech_threshold": 0.6,
            "compression_ratio_threshold": 2.4,
            "fp16": True,
        }
        if lang and lang != "auto":
            kwargs["language"] = lang
        if vocabulary:
            # Whisper's prompt biases spelling toward these words (personal dictionary).
            kwargs["initial_prompt"] = "Vocabulary: " + ", ".join(vocabulary[:80]) + "."
        with self._lock:
            result = mlx_whisper.transcribe(audio.astype(np.float32), **kwargs)
            self._loaded_model = model
        text = (result.get("text") or "").strip()
        # Drop hallucinated segments that Whisper is known for on silence.
        segments = result.get("segments") or []
        if segments and all(s.get("no_speech_prob", 0) > 0.8 for s in segments):
            text = ""
        if vocabulary and text.startswith("Vocabulary:"):
            text = ""
        return {"text": text, "language": result.get("language", lang)}


transcriber = Transcriber()

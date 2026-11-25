"""Notetaker: record a meeting / voice memo from the microphone, transcribe it in
rolling chunks, then produce an AI summary (topics, decisions, next steps).
Also 'Ask AI' across all saved meetings and 'What did I miss?' catch-up."""
from __future__ import annotations

import json
import math
import threading
import time
import wave

import numpy as np

from . import llm, storage
from .audio import SAMPLE_RATE, Recorder, enhance_quiet_speech, is_silent
from .config import RECORDINGS_DIR, settings
from .stt import transcriber

CHUNK_SECONDS = 30

SUMMARY_PROMPT = """You turn meeting transcripts into concise notes. Use Markdown with these sections:
## Summary
(2-4 sentences)
## Key topics
(bullets)
## Decisions
(bullets, or "None recorded")
## Action items / next steps
(bullets with owner if mentioned, or "None recorded")
Only use information present in the transcript. Do not invent names or facts."""

TITLE_PROMPT = "Give a short title (max 7 words) for this meeting. Output the title only, no quotes."

CATCHUP_PROMPT = ("The user stepped away from a meeting. Summarise what was said in this recent "
                  "part of the transcript in 3-5 short bullets. Only use the transcript.")

ASK_PROMPT = """Answer the user's question using ONLY the meeting notes and transcripts provided. Cite the meeting title and date in brackets for each fact, e.g. [Weekly sync, 2026-11-20]. If the answer isn't in the notes, say so."""


class Notetaker:
    def __init__(self) -> None:
        self.recorder: Recorder | None = None
        self.segments: list[tuple[float, str]] = []  # (offset seconds, text)
        self.all_audio: list[np.ndarray] = []
        self.started = 0.0
        self.notes = ""
        self._worker: threading.Thread | None = None
        self._running = False
        self.status = "idle"

    @property
    def active(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self.recorder = Recorder(settings["input_device"])
        self.recorder.start()
        self.segments, self.all_audio, self.notes = [], [], ""
        self.started = time.time()
        self._running = True
        self.status = "recording"
        self._worker = threading.Thread(target=self._loop, daemon=True, name="notetaker")
        self._worker.start()

    def _transcribe_chunk(self, audio: np.ndarray, offset: float) -> None:
        if audio.size == 0:
            return
        self.all_audio.append(audio)
        if is_silent(audio, -58):
            return
        if settings["whisper_mode"]:
            audio = enhance_quiet_speech(audio)
        text = transcriber.transcribe(audio, vocabulary=settings["dictionary"])["text"]
        if text:
            self.segments.append((offset, text))

    def _loop(self) -> None:
        offset = 0.0
        while self._running:
            time.sleep(1)
            if self.recorder and self.recorder.elapsed() - offset >= CHUNK_SECONDS:
                chunk = self.recorder.drain()
                self._transcribe_chunk(chunk, offset)
                offset += chunk.size / SAMPLE_RATE

    def transcript(self) -> str:
        return "\n".join(f"[{int(o // 60):02d}:{int(o % 60):02d}] {t}" for o, t in self.segments)

    def catch_up(self, minutes: float = 3) -> str:
        cutoff = (time.time() - self.started) - minutes * 60
        recent = "\n".join(t for o, t in self.segments if o >= cutoff) or "(nothing transcribed yet)"
        return llm.chat(CATCHUP_PROMPT, recent, max_tokens=400)

    def stop(self) -> int | None:
        """Stop recording, finish transcription & summary.  Returns meeting id."""
        if not self._running:
            return None
        self._running = False
        if self._worker:
            self._worker.join(timeout=120)
        duration = time.time() - self.started
        offset = sum(a.size for a in self.all_audio) / SAMPLE_RATE
        tail = self.recorder.stop() if self.recorder else np.zeros(0, np.float32)
        self.status = "transcribing"
        self._transcribe_chunk(tail, offset)
        transcript = self.transcript()
        audio_path = self._save_wav()
        mid = storage.add_meeting(title="Untitled meeting", duration=duration,
                                  transcript=transcript, summary="", notes=self.notes,
                                  audio_path=str(audio_path))
        self.status = "summarizing"
        self._summarize(mid, transcript)
        self.status = "idle"
        return mid

    def _summarize(self, mid: int, transcript: str) -> None:
        if not transcript.strip():
            storage.update_meeting(mid, title="Empty recording", summary="No speech detected.")
            return
        try:
            body = transcript[-24000:]
            summary = llm.chat(SUMMARY_PROMPT, body, max_tokens=900, timeout=240)
            title = llm.chat(TITLE_PROMPT, summary or body[:3000], max_tokens=20).strip('"')
            fields = {"summary": summary, "title": title or "Meeting"}
            try:
                fields["embedding"] = llm.embed(title + "\n" + summary + "\n" + transcript[:6000])
            except llm.LLMError:
                pass
            storage.update_meeting(mid, **fields)
        except llm.LLMError as exc:
            storage.update_meeting(mid, summary=f"(Summary failed: {exc})")

    def _save_wav(self):
        path = RECORDINGS_DIR / time.strftime("meeting-%Y%m%d-%H%M%S.wav")
        audio = np.concatenate(self.all_audio) if self.all_audio else np.zeros(0, np.float32)
        pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(pcm.tobytes())
        return path


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb + 1e-9)


def ask_meetings(question: str, top_k: int = 3) -> dict:
    meetings = storage.all_meetings_full()
    if not meetings:
        return {"answer": "You have no saved meetings yet.", "sources": []}
    try:
        q = llm.embed(question)
        scored = []
        for m in meetings:
            emb = json.loads(m["embedding"]) if m.get("embedding") else None
            scored.append((_cos(q, emb) if emb else 0.0, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        chosen = [m for _, m in scored[:top_k]]
    except llm.LLMError:
        chosen = meetings[:top_k]
    ctx = []
    for m in chosen:
        date = time.strftime("%Y-%m-%d", time.localtime(m["created"]))
        ctx.append(f"### {m['title']} ({date})\nNotes:\n{m['summary']}\n"
                   f"User notes: {m.get('notes') or ''}\nTranscript:\n{(m['transcript'] or '')[:7000]}")
    answer = llm.chat(ASK_PROMPT, "\n\n".join(ctx) + f"\n\nQuestion: {question}",
                      max_tokens=700, timeout=180)
    return {"answer": answer, "sources": [{"id": m["id"], "title": m["title"]} for m in chosen]}


notetaker = Notetaker()

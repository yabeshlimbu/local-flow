"""LocalFlow — menu-bar app that ties hotkeys, recording, Whisper, AI edits and paste together."""
from __future__ import annotations

import threading
import time
import traceback
import webbrowser

import rumps
from PyObjCTools import AppHelper

from . import editor, llm, macos, storage
from .audio import Recorder, enhance_quiet_speech, is_silent, play_sound
from .config import settings
from .hotkey import HotkeyListener
from .notetaker import notetaker
from .overlay import Overlay
from .stt import transcriber

LANGUAGES = [("Auto-detect", "auto"), ("English", "en"), ("Nepali", "ne"), ("Hindi", "hi"),
             ("Spanish", "es"), ("French", "fr"), ("German", "de"), ("Portuguese", "pt"),
             ("Italian", "it"), ("Japanese", "ja"), ("Korean", "ko"), ("Chinese", "zh"),
             ("Arabic", "ar"), ("Russian", "ru")]
ICON_IDLE, ICON_REC, ICON_BUSY, ICON_MEET = "◉", "●", "◌", "◎"


def on_main(fn, *args):
    AppHelper.callAfter(fn, *args)


class Engine:
    """Dictation state machine (independent from the UI so it can be tested)."""

    def __init__(self, ui: "LocalFlowApp") -> None:
        self.ui = ui
        self.recorder = Recorder(settings["input_device"])
        self.mode = "dictation"
        self.bundle_id = ""
        self.app_name = ""
        self.selection = ""
        self.ready = False
        self._busy = threading.Lock()

    # ---- hotkey callbacks (run on the hotkey worker thread) ------------------
    def start(self, mode: str) -> None:
        if notetaker.active or not self.ready:
            if not self.ready:
                on_main(self.ui.overlay.showMessage_, "Loading models…")
            return
        self.mode = mode
        self.bundle_id, self.app_name = macos.frontmost_app()
        self.selection = macos.get_selected_text() if mode == "command" else ""
        try:
            self.recorder.device = settings["input_device"]
            self.recorder.start()
        except Exception as exc:
            on_main(self.ui.overlay.showMessage_, "Mic error")
            print(f"[engine] microphone error: {exc}")
            return
        if settings["sounds"]:
            play_sound("Tink")
        on_main(self.ui.overlay.setState_, "command" if mode == "command" else "recording")
        on_main(self.ui.set_icon, ICON_REC)
        threading.Thread(target=self._watchdog, daemon=True).start()

    def lock_changed(self, locked: bool) -> None:
        if locked and self.recorder.recording and self.mode == "dictation":
            on_main(self.ui.overlay.setState_, "locked")

    def _watchdog(self) -> None:
        limit = settings["max_recording_seconds"]
        while self.recorder.recording:
            if self.ui.hotkeys and self.ui.hotkeys._locked:
                self.lock_changed(True)
            if self.recorder.elapsed() > limit:
                self.ui.hotkeys._locked = False
                self.ui.hotkeys._active = False
                self.stop()
                return
            time.sleep(0.1)

    def cancel(self, silent: bool = False) -> None:
        if not self.recorder.recording:
            return
        self.recorder.stop()
        on_main(self.ui.overlay.setState_, "hidden")
        on_main(self.ui.set_icon, ICON_IDLE)
        if not silent and settings["sounds"]:
            play_sound("Bottle")

    def stop(self) -> None:
        if not self.recorder.recording:
            return
        duration = self.recorder.elapsed()
        audio = self.recorder.stop()
        if settings["sounds"]:
            play_sound("Pop")
        on_main(self.ui.overlay.setState_, "processing")
        on_main(self.ui.set_icon, ICON_BUSY)
        threading.Thread(target=self._process, args=(audio, duration), daemon=True).start()

    # ---- processing -------------------------------------------------------------
    def _process(self, audio, duration: float) -> None:
        t0 = time.time()
        with self._busy:
            try:
                if is_silent(audio):
                    on_main(self.ui.overlay.showMessage_, "No speech heard")
                    return
                if settings["whisper_mode"]:
                    audio = enhance_quiet_speech(audio)
                stt = transcriber.transcribe(audio, vocabulary=settings["dictionary"])
                raw = stt["text"]
                if not raw:
                    on_main(self.ui.overlay.showMessage_, "No speech heard")
                    return
                if self.mode == "command":
                    try:
                        final = editor.command(raw, self.selection, self.bundle_id)
                    except llm.LLMError:
                        on_main(self.ui.overlay.showMessage_, "Ollama not running")
                        return
                    style = ""
                else:
                    result = editor.polish(raw, self.bundle_id)
                    final, style = result["text"], result["style"]
                if final and self.mode == "dictation" and not final.endswith(("\n", " ")):
                    final_to_paste = final + " "  # so consecutive dictations don't stick together
                else:
                    final_to_paste = final
                macos.paste_text(final_to_paste, restore=settings["restore_clipboard"])
                storage.add_dictation(
                    mode=self.mode, app=self.bundle_id, app_name=self.app_name, raw=raw,
                    final=final, instruction=raw if self.mode == "command" else None,
                    language=stt.get("language"), duration=duration,
                    latency=time.time() - t0)
                on_main(self.ui.overlay.setState_, "hidden")
                print(f"[{self.mode} → {self.app_name} {style} {time.time()-t0:.2f}s] {final!r}")
            except Exception:
                traceback.print_exc()
                on_main(self.ui.overlay.showMessage_, "Error — see log")
            finally:
                on_main(self.ui.set_icon, ICON_IDLE)

    def paste_last(self) -> None:
        last = storage.last_dictation()
        if last:
            macos.paste_text(last["final"], restore=settings["restore_clipboard"])


class LocalFlowApp(rumps.App):
    def __init__(self) -> None:
        super().__init__("LocalFlow", title=ICON_BUSY, quit_button=None)
        storage.init()
        self.overlay = Overlay.alloc().init()
        self.engine = Engine(self)
        self.overlay.level_source = lambda: self.engine.recorder.level
        self.hotkeys: HotkeyListener | None = None

        self.status_item = rumps.MenuItem("Loading models…")
        self.meeting_item = rumps.MenuItem("Start Notetaker", callback=self.toggle_meeting)
        self.catchup_item = rumps.MenuItem("What did I miss?", callback=self.catch_up)
        lang_menu = rumps.MenuItem("Language")
        for name, code in LANGUAGES:
            item = rumps.MenuItem(name, callback=self.set_language)
            item.lang_code = code
            item.state = settings["language"] == code
            lang_menu.add(item)
        self.lang_menu = lang_menu
        self.toggles = {}
        for key, label in [("ai_edits", "AI auto-edits"), ("whisper_mode", "Whisper mode (quiet speech)"),
                           ("command_mode", "Command Mode"), ("sounds", "Sound effects")]:
            it = rumps.MenuItem(label, callback=self.toggle_setting)
            it.setting_key = key
            it.state = bool(settings[key])
            self.toggles[key] = it
        key_name = settings["dictation_key"].replace("_", " ")
        self.menu = [
            self.status_item,
            rumps.MenuItem(f"Hold {key_name} to dictate · {key_name}+{settings['command_modifier']} for Command"),
            None,
            rumps.MenuItem("Paste last transcript", callback=lambda _: threading.Thread(
                target=self.engine.paste_last, daemon=True).start()),
            rumps.MenuItem("Open Dashboard…", callback=self.open_dashboard),
            None,
            self.meeting_item, self.catchup_item,
            None,
            lang_menu, *self.toggles.values(),
            None,
            rumps.MenuItem("Quit LocalFlow", callback=self.quit),
        ]
        self.catchup_item.set_callback(None)
        threading.Thread(target=self._boot, daemon=True).start()

    # ---- startup ----------------------------------------------------------------
    def _boot(self) -> None:
        from .dashboard import serve
        threading.Thread(target=serve, args=(self,), daemon=True).start()
        macos.request_input_permissions()
        if not macos.accessibility_trusted(prompt=True):
            print("[boot] Accessibility permission not granted yet — paste/hotkeys need it.")
        try:
            self.hotkeys = HotkeyListener(settings.all, self.engine.start, self.engine.stop,
                                          self.engine.cancel)
            self.hotkeys.start()
        except PermissionError as exc:
            print(exc)
        print("[boot] loading Whisper model (first run downloads ~1.5 GB)…")
        t = time.time()
        transcriber.warm_up()
        print(f"[boot] Whisper ready in {time.time()-t:.1f}s; warming up {settings['llm_model']}…")
        if settings["ai_edits"] and not llm.available_models():
            print("[boot] Ollama not reachable — falling back to rule-based edits.")
        llm.warm_up()
        self.engine.ready = True
        on_main(self._set_ready)
        print("[boot] LocalFlow ready.")

    def _set_ready(self) -> None:
        self.status_item.title = "Ready — 100% local"
        rumps.Timer(self._check_permissions, 2).start()

    def _check_permissions(self, _timer) -> None:
        if self.hotkeys and self.hotkeys.permission_missing:
            self.status_item.title = "⚠︎ Grant Accessibility & Input Monitoring"
        elif self.engine.ready:
            self.status_item.title = "Ready — 100% local"
        self.set_icon(ICON_IDLE)

    def set_icon(self, icon: str) -> None:
        self.title = ICON_MEET if notetaker.active and icon == ICON_IDLE else icon

    # ---- menu actions ---------------------------------------------------------
    def set_language(self, sender) -> None:
        settings.update({"language": sender.lang_code})
        for item in self.lang_menu.values():
            item.state = item.lang_code == sender.lang_code

    def toggle_setting(self, sender) -> None:
        sender.state = not sender.state
        settings.update({sender.setting_key: bool(sender.state)})

    def sync_toggles(self) -> None:
        for key, item in self.toggles.items():
            item.state = bool(settings[key])
        for item in self.lang_menu.values():
            item.state = item.lang_code == settings["language"]

    def open_dashboard(self, _=None) -> None:
        webbrowser.open(f"http://127.0.0.1:{settings['dashboard_port']}")

    def toggle_meeting(self, _=None) -> None:
        if not notetaker.active:
            if not self.engine.ready:
                rumps.notification("LocalFlow", "", "Models are still loading.")
                return
            notetaker.start()
            self.meeting_item.title = "Stop Notetaker & summarize"
            self.catchup_item.set_callback(self.catch_up)
            self.set_icon(ICON_IDLE)
            rumps.notification("LocalFlow Notetaker", "Recording started",
                               "Dictation is paused while the Notetaker records.")
        else:
            self.meeting_item.title = "Finishing notes…"
            self.meeting_item.set_callback(None)
            self.catchup_item.set_callback(None)

            def finish():
                mid = notetaker.stop()
                def done():
                    self.meeting_item.title = "Start Notetaker"
                    self.meeting_item.set_callback(self.toggle_meeting)
                    self.set_icon(ICON_IDLE)
                    rumps.notification("LocalFlow Notetaker", "Notes ready",
                                       "Open the dashboard to view the summary.")
                    webbrowser.open(f"http://127.0.0.1:{settings['dashboard_port']}/#meeting-{mid}")
                on_main(done)
            threading.Thread(target=finish, daemon=True).start()

    def catch_up(self, _=None) -> None:
        def run():
            try:
                text = notetaker.catch_up()
            except llm.LLMError as exc:
                text = f"Could not summarize: {exc}"
            on_main(lambda: rumps.alert("What did I miss?", text))
        threading.Thread(target=run, daemon=True).start()

    def quit(self, _=None) -> None:
        if notetaker.active:
            notetaker.stop()
        rumps.quit_application()


def main() -> None:
    LocalFlowApp().run()


if __name__ == "__main__":
    main()

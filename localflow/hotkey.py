"""Global push-to-talk via a Quartz event tap.

Supports the fn/globe key (which pynput cannot see), right-side modifiers,
hold-to-talk, double-tap hands-free lock, a Command-Mode modifier, and Esc to cancel.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Callable

import Quartz

# virtual key codes for modifier keys (flagsChanged events)
KEYCODES = {
    "fn": 63,
    "right_option": 61,
    "right_command": 54,
    "right_control": 62,
    "right_shift": 60,
}
FLAG_FOR_KEY = {
    "fn": Quartz.kCGEventFlagMaskSecondaryFn,
    "right_option": Quartz.kCGEventFlagMaskAlternate,
    "right_command": Quartz.kCGEventFlagMaskCommand,
    "right_control": Quartz.kCGEventFlagMaskControl,
    "right_shift": Quartz.kCGEventFlagMaskShift,
}
MODIFIER_FLAGS = {
    "control": Quartz.kCGEventFlagMaskControl,
    "command": Quartz.kCGEventFlagMaskCommand,
    "option": Quartz.kCGEventFlagMaskAlternate,
    "shift": Quartz.kCGEventFlagMaskShift,
}
ESC = 53
DOUBLE_TAP_WINDOW = 0.35
MIN_HOLD = 0.18


class HotkeyListener:
    """Callbacks: on_start(mode), on_stop(), on_cancel().  mode = 'dictation' | 'command'."""

    def __init__(self, get_settings: Callable[[], dict], on_start, on_stop, on_cancel) -> None:
        self.get_settings = get_settings
        self.on_start, self.on_stop, self.on_cancel = on_start, on_stop, on_cancel
        self._down = False
        self._down_at = 0.0
        self._last_tap_up = 0.0
        self._locked = False  # hands-free
        self._active = False
        self._tap = None
        self.permission_missing = False
        self._swallow_release = False
        self._pressed = False  # physical key state, updated in the tap callback
        self._q: queue.Queue = queue.Queue()
        threading.Thread(target=self._worker, daemon=True, name="hotkey-worker").start()

    def _worker(self) -> None:
        while True:
            fn, args = self._q.get()
            try:
                fn(*args)
            except Exception as exc:  # never let the worker die
                print(f"[hotkey] {exc!r}")

    # -- state machine -------------------------------------------------------
    def _press(self, flags: int) -> None:
        s = self.get_settings()
        cmd_flag = MODIFIER_FLAGS.get(s.get("command_modifier", "control"), 0)
        now = time.time()
        if self._locked:  # tap again ends hands-free mode
            self._locked = False
            self._active = False
            self.on_stop()
            self._down = True
            self._swallow_release = True
            return
        self._swallow_release = False
        self._down = True
        self._down_at = now
        double = (s.get("hands_free_double_tap", True)
                  and now - self._last_tap_up < DOUBLE_TAP_WINDOW)
        mode = "command" if (s.get("command_mode", True) and flags & cmd_flag) else "dictation"
        if double:
            self._locked = True
        if not self._active:
            self._active = True
            self.on_start(mode)

    def _release(self) -> None:
        self._down = False
        if self._swallow_release:
            self._swallow_release = False
            return
        held = time.time() - self._down_at
        if self._locked:
            return  # keep recording hands-free
        if held < MIN_HOLD:
            # a quick tap: maybe the first half of a double-tap.  Cancel silently.
            self._last_tap_up = time.time()
            if self._active:
                self._active = False
                self.on_cancel(silent=True)
            return
        if self._active:
            self._active = False
            self.on_stop()

    def cancel(self) -> None:
        if self._active:
            self._active = False
            self._locked = False
            self.on_cancel(silent=False)

    # -- event tap -----------------------------------------------------------
    def _callback(self, proxy, etype, event, refcon):
        if etype in (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput):
            Quartz.CGEventTapEnable(self._tap, True)
            return event
        s = self.get_settings()
        key = s.get("dictation_key", "fn")
        code = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
        if etype == Quartz.kCGEventFlagsChanged and code == KEYCODES.get(key):
            flags = Quartz.CGEventGetFlags(event)
            pressed = bool(flags & FLAG_FOR_KEY[key])
            if pressed and not self._pressed:
                self._pressed = True
                self._q.put((self._press, (flags,)))
            elif not pressed and self._pressed:
                self._pressed = False
                self._q.put((self._release, ()))
        elif etype == Quartz.kCGEventKeyDown and code == ESC and self._active:
            self._q.put((self.cancel, ()))
            return None  # swallow Esc while recording
        return event

    def run(self) -> None:
        """Blocking: run on its own thread with its own CFRunLoop."""
        mask = (Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged)
                | Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown))
        warned = False
        while True:
            self._tap = Quartz.CGEventTapCreate(
                Quartz.kCGSessionEventTap, Quartz.kCGHeadInsertEventTap,
                Quartz.kCGEventTapOptionDefault, mask, self._callback, None)
            if self._tap is not None:
                break
            if not warned:
                warned = True
                self.permission_missing = True
                print("[hotkey] Waiting for Accessibility + Input Monitoring permission "
                      "(System Settings → Privacy & Security). Will start automatically.")
            time.sleep(2)
        self.permission_missing = False
        print("[hotkey] keyboard listener active")
        source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        Quartz.CFRunLoopAddSource(Quartz.CFRunLoopGetCurrent(), source, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(self._tap, True)
        Quartz.CFRunLoopRun()

    def start(self) -> threading.Thread:
        t = threading.Thread(target=self.run, daemon=True, name="hotkey")
        t.start()
        return t

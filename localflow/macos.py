"""macOS integration: frontmost app, clipboard, synthetic paste/copy, permission checks."""
from __future__ import annotations

import time

import Quartz
from AppKit import NSPasteboard, NSPasteboardTypeString, NSWorkspace

KEY_V = 9
KEY_C = 8


def frontmost_app() -> tuple[str, str]:
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return "", ""
    return (str(app.bundleIdentifier() or ""), str(app.localizedName() or ""))


# --- clipboard -----------------------------------------------------------------

def get_clipboard() -> str | None:
    pb = NSPasteboard.generalPasteboard()
    s = pb.stringForType_(NSPasteboardTypeString)
    return str(s) if s is not None else None


def set_clipboard(text: str) -> None:
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)


def _change_count() -> int:
    return int(NSPasteboard.generalPasteboard().changeCount())


def _key_combo(keycode: int, flags=Quartz.kCGEventFlagMaskCommand) -> None:
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    down = Quartz.CGEventCreateKeyboardEvent(src, keycode, True)
    up = Quartz.CGEventCreateKeyboardEvent(src, keycode, False)
    Quartz.CGEventSetFlags(down, flags)
    Quartz.CGEventSetFlags(up, flags)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def paste_text(text: str, restore: bool = True) -> None:
    """Insert text at the cursor in whatever app is focused (clipboard + Cmd-V)."""
    if not text:
        return
    previous = get_clipboard() if restore else None
    set_clipboard(text)
    time.sleep(0.03)
    _key_combo(KEY_V)
    if restore and previous is not None:
        time.sleep(0.35)  # give the target app time to read the pasteboard
        set_clipboard(previous)


def get_selected_text() -> str:
    """Copy the current selection (Cmd-C) and return it, restoring the clipboard."""
    previous = get_clipboard()
    before = _change_count()
    _key_combo(KEY_C)
    selected = ""
    for _ in range(20):
        time.sleep(0.02)
        if _change_count() != before:
            selected = get_clipboard() or ""
            break
    if previous is not None:
        set_clipboard(previous)
    return selected


def accessibility_trusted(prompt: bool = True) -> bool:
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
        return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: prompt}))
    except Exception:
        return True


def request_input_permissions() -> None:
    """Ask macOS for Input Monitoring (listen) and keystroke-posting access.
    This registers LocalFlow in System Settings and shows the system prompts."""
    try:
        if not Quartz.CGPreflightListenEventAccess():
            Quartz.CGRequestListenEventAccess()
        if not Quartz.CGPreflightPostEventAccess():
            Quartz.CGRequestPostEventAccess()
    except Exception as exc:
        print(f"[permissions] {exc}")

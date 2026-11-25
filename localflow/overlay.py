"""The floating 'Flow bar' pill at the bottom of the screen (live waveform / processing)."""
from __future__ import annotations

import math
import time

import objc
from AppKit import (
    NSBackingStoreBuffered, NSBezierPath, NSColor, NSFont, NSFontAttributeName,
    NSForegroundColorAttributeName, NSMakeRect, NSPanel, NSScreen, NSString, NSView,
    NSWindowCollectionBehaviorCanJoinAllSpaces, NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless, NSWindowStyleMaskNonactivatingPanel, NSStatusWindowLevel,
)
from Foundation import NSObject, NSTimer

W, H = 210, 40
BARS = 24


def draw_text(s, x, y, size, color):
    attrs = {NSFontAttributeName: NSFont.boldSystemFontOfSize_(size),
             NSForegroundColorAttributeName: color}
    NSString.stringWithString_(s).drawAtPoint_withAttributes_((x, y), attrs)


class PillView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(PillView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.state = "hidden"  # recording | command | locked | processing | message
        self.levels = [0.0] * BARS
        self.message = ""
        return self

    def isFlipped(self):
        return False

    def drawRect_(self, rect):
        b = self.bounds()
        bg = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(b, H / 2, H / 2)
        NSColor.colorWithCalibratedWhite_alpha_(0.08, 0.92).setFill()
        bg.fill()
        NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.12).setStroke()
        bg.setLineWidth_(1.0)
        bg.stroke()

        accent = {
            "recording": NSColor.colorWithCalibratedRed_green_blue_alpha_(1, 1, 1, 0.95),
            "locked": NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.45, 0.4, 0.95),
            "command": NSColor.colorWithCalibratedRed_green_blue_alpha_(0.55, 0.7, 1.0, 0.95),
        }.get(self.state, NSColor.whiteColor())

        if self.state in ("recording", "locked", "command"):
            # status dot
            accent.setFill()
            dot = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(14, H / 2 - 4, 8, 8))
            dot.fill()
            bar_w, gap = 3.0, 3.0
            x0 = 32
            for i, lv in enumerate(self.levels):
                h = max(3.0, lv * (H - 14))
                r = NSMakeRect(x0 + i * (bar_w + gap), (H - h) / 2, bar_w, h)
                NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(r, 1.5, 1.5).fill()
            label = {"command": "CMD", "locked": "LOCK"}.get(self.state)
            if label:
                draw_text(label, W - 44, 13, 10, accent)
        elif self.state == "processing":
            t = time.time()
            NSColor.whiteColor().setFill()
            for i in range(3):
                a = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(t * 6 - i * 0.9))
                NSColor.colorWithCalibratedWhite_alpha_(1, a).setFill()
                NSBezierPath.bezierPathWithOvalInRect_(
                    NSMakeRect(W / 2 - 18 + i * 14, H / 2 - 4, 8, 8)).fill()
        elif self.state == "message":
            draw_text(self.message[:30], 16, 12, 12, NSColor.whiteColor())



class Overlay(NSObject):
    """All methods must be called on the main thread (use performSelectorOnMainThread)."""

    def init(self):
        self = objc.super(Overlay, self).init()
        if self is None:
            return None
        screen = NSScreen.mainScreen().visibleFrame()
        x = screen.origin.x + (screen.size.width - W) / 2
        y = screen.origin.y + 28
        self.panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, W, H),
            NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered, False)
        self.panel.setLevel_(NSStatusWindowLevel)
        self.panel.setOpaque_(False)
        self.panel.setBackgroundColor_(NSColor.clearColor())
        self.panel.setHasShadow_(True)
        self.panel.setIgnoresMouseEvents_(True)
        self.panel.setHidesOnDeactivate_(False)
        self.panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorStationary)
        self.view = PillView.alloc().initWithFrame_(NSMakeRect(0, 0, W, H))
        self.panel.setContentView_(self.view)
        self.level_source = None  # callable -> float
        self.hide_at = 0.0
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1 / 30, self, "tick:", None, True)
        return self

    def tick_(self, _):
        v = self.view
        if v.state == "hidden":
            return
        if v.state in ("recording", "locked", "command") and self.level_source:
            lv = float(self.level_source())
            v.levels = v.levels[1:] + [lv * (0.75 + 0.25 * math.sin(time.time() * 20))]
        if v.state == "message" and time.time() > self.hide_at:
            self.setState_("hidden")
            return
        v.setNeedsDisplay_(True)

    def setState_(self, state):
        v = self.view
        v.state = state
        if state == "hidden":
            self.panel.orderOut_(None)
            return
        if state in ("recording", "command"):
            v.levels = [0.0] * BARS
        self.panel.orderFrontRegardless()
        v.setNeedsDisplay_(True)

    def showMessage_(self, text):
        self.view.message = str(text)
        self.hide_at = time.time() + 2.2
        self.setState_("message")

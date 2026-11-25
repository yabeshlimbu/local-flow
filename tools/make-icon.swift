// Draws LocalFlow's app icon.  Run:  swift tools/make-icon.swift <out.png>
// Idea: the recording pill (red dot + live waveform) above lines of freshly typed text,
// i.e. your voice turning into text. Colours match the project art on the website.
import AppKit

let size: CGFloat = 1024
let out = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "icon.png"
let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(size), pixelsHigh: Int(size),
                           bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                           colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
let ctx = NSGraphicsContext.current!.cgContext
let space = CGColorSpaceCreateDeviceRGB()
func rgb(_ r: CGFloat, _ g: CGFloat, _ b: CGFloat, _ a: CGFloat = 1) -> CGColor { CGColor(red: r, green: g, blue: b, alpha: a) }
func hex(_ h: UInt32, _ a: CGFloat = 1) -> CGColor {
    rgb(CGFloat((h >> 16) & 0xff) / 255, CGFloat((h >> 8) & 0xff) / 255, CGFloat(h & 0xff) / 255, a)
}
func round(_ r: CGRect, _ radius: CGFloat) -> CGPath { CGPath(roundedRect: r, cornerWidth: radius, cornerHeight: radius, transform: nil) }

// macOS icon grid: 824pt rounded square centred in 1024 with a soft drop shadow.
let tile = CGRect(x: 100, y: 100, width: 824, height: 824)
let tilePath = round(tile, 185)
ctx.saveGState()
ctx.setShadow(offset: CGSize(width: 0, height: -12), blur: 28, color: rgb(0, 0, 0, 0.35))
ctx.addPath(tilePath); ctx.setFillColor(hex(0x0a0e15)); ctx.fillPath()
ctx.restoreGState()

// Background: deep night blue with a cool glow top-left and a teal glow bottom-right.
ctx.saveGState()
ctx.addPath(tilePath); ctx.clip()
let base = CGGradient(colorsSpace: space, colors: [hex(0x1b3252), hex(0x0d1522), hex(0x0a0e15)] as CFArray, locations: [0, 0.55, 1])!
ctx.drawLinearGradient(base, start: CGPoint(x: 512, y: 924), end: CGPoint(x: 512, y: 100), options: [])
let glow1 = CGGradient(colorsSpace: space, colors: [hex(0x3d6fb0, 0.55), hex(0x3d6fb0, 0)] as CFArray, locations: [0, 1])!
ctx.drawRadialGradient(glow1, startCenter: CGPoint(x: 260, y: 900), startRadius: 0, endCenter: CGPoint(x: 260, y: 900), endRadius: 560, options: [])
let glow2 = CGGradient(colorsSpace: space, colors: [hex(0x2a6d7c, 0.5), hex(0x2a6d7c, 0)] as CFArray, locations: [0, 1])!
ctx.drawRadialGradient(glow2, startCenter: CGPoint(x: 900, y: 110), startRadius: 0, endCenter: CGPoint(x: 900, y: 110), endRadius: 520, options: [])
ctx.restoreGState()

// The recording pill.
let pill = CGRect(x: 192, y: 548, width: 640, height: 176)
ctx.saveGState()
ctx.setShadow(offset: CGSize(width: 0, height: -16), blur: 44, color: rgb(0, 0, 0, 0.55))
ctx.addPath(round(pill, 88)); ctx.setFillColor(hex(0x0b0d11)); ctx.fillPath()
ctx.restoreGState()
ctx.addPath(round(pill.insetBy(dx: 1.5, dy: 1.5), 86.5)); ctx.setStrokeColor(rgb(1, 1, 1, 0.14)); ctx.setLineWidth(3); ctx.strokePath()

// Red "listening" dot with a soft halo.
let dotC = CGPoint(x: pill.minX + 96, y: pill.midY)
let halo = CGGradient(colorsSpace: space, colors: [hex(0xff5f57, 0.55), hex(0xff5f57, 0)] as CFArray, locations: [0, 1])!
ctx.drawRadialGradient(halo, startCenter: dotC, startRadius: 0, endCenter: dotC, endRadius: 64, options: [])
ctx.addEllipse(in: CGRect(x: dotC.x - 25, y: dotC.y - 25, width: 50, height: 50)); ctx.setFillColor(hex(0xff5f57)); ctx.fillPath()

// Waveform: symmetric bars, tallest in the middle like a voice peak.
let heights: [CGFloat] = [34, 62, 96, 58, 120, 84, 132, 70, 104, 52, 80, 40]
let barW: CGFloat = 18, gap: CGFloat = 16
let waveStart = dotC.x + 72
for (i, h) in heights.enumerated() {
    let x = waveStart + CGFloat(i) * (barW + gap)
    ctx.addPath(round(CGRect(x: x, y: pill.midY - h / 2, width: barW, height: h), barW / 2))
}
ctx.setFillColor(hex(0xeef2f8)); ctx.fillPath()

// Typed text below: two lines of "words" and a blue cursor at the end.
func words(_ y: CGFloat, _ widths: [CGFloat], _ alpha: CGFloat) -> CGFloat {
    var x: CGFloat = 212
    for w in widths {
        ctx.addPath(round(CGRect(x: x, y: y, width: w, height: 40), 20))
        x += w + 26
    }
    ctx.setFillColor(rgb(1, 1, 1, alpha)); ctx.fillPath()
    return x
}
_ = words(392, [140, 200, 110, 72], 0.92)
let end = words(304, [180, 120, 130], 0.62)
ctx.addPath(round(CGRect(x: end - 6, y: 290, width: 16, height: 68), 8)); ctx.setFillColor(hex(0x8fb8ff)); ctx.fillPath()

NSGraphicsContext.current = nil
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: out))
print("wrote \(out)")

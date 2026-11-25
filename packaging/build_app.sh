#!/bin/zsh
# Builds LocalFlow.app (a launcher for this project folder) and installs it to ~/Applications.
set -e
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
APP="$ROOT/LocalFlow.app"
rm -rf "$APP"; mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
clang -O2 -DPROJECT_ROOT="\"$ROOT\"" packaging/launcher.c -o "$APP/Contents/MacOS/LocalFlow"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>LocalFlow</string>
  <key>CFBundleDisplayName</key><string>LocalFlow</string>
  <key>CFBundleIdentifier</key><string>local.localflow.app</string>
  <key>CFBundleExecutable</key><string>LocalFlow</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>LSUIElement</key><true/>
  <key>NSMicrophoneUsageDescription</key><string>LocalFlow listens while you hold the dictation key and transcribes on this Mac.</string>
  <key>NSAppleEventsUsageDescription</key><string>LocalFlow pastes dictated text into the focused app.</string>
</dict></plist>
PLIST
codesign --force --deep --sign - "$APP"
echo "Built $APP"

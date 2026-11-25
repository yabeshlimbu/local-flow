#!/bin/zsh
# Builds LocalFlow.app (a launcher for this project folder) and installs it to ~/Applications.
set -e
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
APP="$ROOT/LocalFlow.app"
rm -rf "$APP"; mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp Resources/AppIcon.icns "$APP/Contents/Resources/AppIcon.icns"
clang -O2 -DPROJECT_ROOT="\"$ROOT\"" packaging/launcher.c -o "$APP/Contents/MacOS/LocalFlow"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>LocalFlow</string>
  <key>CFBundleDisplayName</key><string>LocalFlow</string>
  <key>CFBundleIdentifier</key><string>local.localflow.app</string>
  <key>CFBundleExecutable</key><string>LocalFlow</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>LSUIElement</key><true/>
  <key>NSMicrophoneUsageDescription</key><string>LocalFlow listens while you hold the dictation key and transcribes on this Mac.</string>
  <key>NSAppleEventsUsageDescription</key><string>LocalFlow pastes dictated text into the focused app.</string>
</dict></plist>
PLIST
# Sign with the stable local certificate when it exists (see make_signing_cert.sh) so
# macOS keeps LocalFlow's permissions across rebuilds; otherwise fall back to ad hoc.
IDENTITY="$(security find-identity -p codesigning "$HOME/Library/Keychains/login.keychain-db" 2>/dev/null \
  | awk '/"LocalFlow Code Signing"/ {print $2; exit}')"
if [ -n "$IDENTITY" ]; then
  codesign --force --deep --sign "$IDENTITY" "$APP"
  echo "Signed with \"LocalFlow Code Signing\" (permissions survive rebuilds)"
else
  codesign --force --deep --sign - "$APP"
  echo "Signed ad hoc. Run packaging/make_signing_cert.sh once so rebuilds keep permissions."
fi
echo "Built $APP"

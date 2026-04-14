#!/bin/bash
set -e

echo "=== MirrorMind Setup ==="
echo ""

# Check for Homebrew
if ! command -v brew &> /dev/null; then
    echo "Error: Homebrew not found."
    echo "Install it first: https://brew.sh"
    exit 1
fi

# Install XcodeGen if needed
if ! command -v xcodegen &> /dev/null; then
    echo "Installing XcodeGen..."
    brew install xcodegen
else
    echo "XcodeGen already installed."
fi

# Generate the Xcode project
echo "Generating MirrorMind.xcodeproj..."
xcodegen generate

echo ""
echo "Done! Next steps:"
echo "  1. Open MirrorMind.xcodeproj in Xcode"
echo "  2. Select your iPhone as the run destination"
echo "  3. Set your Apple ID in Signing & Capabilities"
echo "  4. Hit Run"

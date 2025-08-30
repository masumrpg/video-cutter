#!/bin/bash

# VideoCutter One-Click Build Script for macOS
# This script will build the application with all dependencies included

echo "🎬 VideoCutter macOS One-Click Build"
echo "====================================="

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 not found. Please install Python 3.8 or later."
    exit 1
fi

# Check if we're in the right directory
if [ ! -f "main.py" ]; then
    echo "❌ main.py not found. Please run this script from the project directory."
    exit 1
fi

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source .venv/bin/activate

# Install/upgrade dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install PyQt6 pyinstaller

# Check if assets folder exists and copy FFmpeg binaries if needed
if [ ! -d "assets" ]; then
    echo "📁 Creating assets folder..."
    mkdir -p assets
fi

if [ ! -f "assets/ffmpeg" ] || [ ! -f "assets/ffprobe" ]; then
    echo "🔍 Checking for FFmpeg installation..."
    if ! command -v ffmpeg &> /dev/null; then
        echo "❌ FFmpeg not found in system PATH."
        echo "Please install FFmpeg using one of these methods:"
        echo "  • Homebrew: brew install ffmpeg"
        echo "  • MacPorts: sudo port install ffmpeg"
        echo "  • Download from: https://ffmpeg.org/download.html"
        exit 1
    fi
    
    echo "📋 Copying FFmpeg binaries to assets folder..."
    cp $(which ffmpeg) assets/
    cp $(which ffprobe) assets/
    echo "✅ FFmpeg binaries copied to assets/"
else
    echo "✅ FFmpeg binaries found in assets folder"
fi

# Run the build script
echo "🚀 Starting build process..."
python3 build.py

# Check if build was successful
if [ $? -eq 0 ]; then
    echo ""
    echo "🎉 Build completed successfully!"
    echo ""
    echo "📱 Your application is ready at: ./dist/VideoCutter/"
    echo "🚀 To run: ./run_videocutter.sh"
    echo ""
    
    # Ask if user wants to test the app
    read -p "❓ Do you want to test the application now? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🧪 Testing application..."
        ./run_videocutter.sh &
        echo "✅ Application started in background"
    fi
else
    echo "❌ Build failed. Please check the error messages above."
    exit 1
fi

echo "👋 Build script completed!"
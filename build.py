#!/usr/bin/env python3
"""
Build script for Video Cutter macOS Application
This script compiles the PyQt6 application into a standalone macOS app bundle
with FFmpeg included from the system.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def find_ffmpeg_path():
    """Find FFmpeg and FFprobe binaries from project assets folder"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    assets_dir = os.path.join(script_dir, 'assets')
    
    ffmpeg_path = os.path.join(assets_dir, 'ffmpeg')
    ffprobe_path = os.path.join(assets_dir, 'ffprobe')
    
    if not os.path.exists(ffmpeg_path) or not os.path.exists(ffprobe_path):
        print("❌ Error: FFmpeg or FFprobe not found in assets folder")
        print("Please ensure FFmpeg binaries are copied to assets/ folder")
        return None, None
    
    print(f"✅ Found FFmpeg at: {ffmpeg_path}")
    print(f"✅ Found FFprobe at: {ffprobe_path}")
    return ffmpeg_path, ffprobe_path

def check_dependencies():
    """Check if all required dependencies are installed"""
    print("🔍 Checking dependencies...")
    
    # Check PyInstaller
    try:
        import PyInstaller
        print(f"✅ PyInstaller found: {PyInstaller.__version__}")
    except ImportError:
        print("❌ PyInstaller not found. Installing...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'pyinstaller'], check=True)
        print("✅ PyInstaller installed")
    
    # Check PyQt6
    try:
        import PyQt6
        print("✅ PyQt6 found")
    except ImportError:
        print("❌ PyQt6 not found. Please install with: pip install PyQt6")
        return False
    
    return True

def build_app():
    """Build the macOS application using PyInstaller"""
    print("🚀 Starting build process...")
    
    # Find FFmpeg binaries
    ffmpeg_path, ffprobe_path = find_ffmpeg_path()
    if not ffmpeg_path or not ffprobe_path:
        return False
    
    # Check dependencies
    if not check_dependencies():
        return False
    
    # Clean previous builds
    print("🧹 Cleaning previous builds...")
    if os.path.exists('dist'):
        shutil.rmtree('dist')
    if os.path.exists('build'):
        shutil.rmtree('build')
    if os.path.exists('main.spec'):
        os.remove('main.spec')
    
    # PyInstaller command
    cmd = [
        'pyinstaller',
        '--onedir',  # Create a one-folder bundle
        '--windowed',  # Don't show console window
        '--name=VideoCutter',
        '--icon=app_icon.icns',  # Optional: add icon if available
        '--add-binary', f'{ffmpeg_path}:.',  # Include FFmpeg
        '--add-binary', f'{ffprobe_path}:.',  # Include FFprobe
        '--add-data', 'assets:assets',  # Include assets folder
        '--hidden-import', 'PyQt6.QtCore',
        '--hidden-import', 'PyQt6.QtGui',
        '--hidden-import', 'PyQt6.QtWidgets',
        '--clean',
        'main.py'
    ]
    
    # Remove icon parameter if icon file doesn't exist
    if not os.path.exists('app_icon.icns'):
        cmd = [arg for arg in cmd if not arg.startswith('--icon')]
    
    print(f"📦 Running PyInstaller...")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("✅ Build completed successfully!")
        
        # Show build results
        app_path = Path('dist/VideoCutter')
        if app_path.exists():
            print(f"📱 Application built at: {app_path.absolute()}")
            print(f"📊 Application size: {get_folder_size(app_path):.1f} MB")
            
            # Create a simple launcher script
            create_launcher()
            
            return True
        else:
            print("❌ Build failed: Application not found in dist folder")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Build failed with error: {e}")
        print(f"Error output: {e.stderr}")
        return False

def get_folder_size(folder_path):
    """Calculate folder size in MB"""
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(folder_path):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if os.path.exists(filepath):
                total_size += os.path.getsize(filepath)
    return total_size / (1024 * 1024)  # Convert to MB

def create_launcher():
    """Create a simple launcher script"""
    launcher_content = '''#!/bin/bash
# VideoCutter Launcher
echo "🚀 Starting VideoCutter..."
cd "$(dirname "$0")"
./dist/VideoCutter/VideoCutter
'''
    
    with open('run_videocutter.sh', 'w') as f:
        f.write(launcher_content)
    
    # Make it executable
    os.chmod('run_videocutter.sh', 0o755)
    print("✅ Created launcher script: run_videocutter.sh")

def create_dmg():
    """Create a DMG file for distribution (optional)"""
    print("📦 Creating DMG file...")
    
    dmg_name = "VideoCutter-macOS.dmg"
    
    # Remove existing DMG
    if os.path.exists(dmg_name):
        os.remove(dmg_name)
    
    cmd = [
        'hdiutil', 'create',
        '-volname', 'VideoCutter',
        '-srcfolder', 'dist/VideoCutter',
        '-ov', '-format', 'UDZO',
        dmg_name
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print(f"✅ DMG created: {dmg_name}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"⚠️  DMG creation failed: {e}")
        return False

def main():
    """Main build function"""
    print("🎬 VideoCutter macOS Build Script")
    print("=" * 40)
    
    # Check if main.py exists
    if not os.path.exists('main.py'):
        print("❌ Error: main.py not found in current directory")
        return False
    
    # Build the application
    if build_app():
        print("\n🎉 Build completed successfully!")
        print("\n📋 Next steps:")
        print("1. Test the app: ./run_videocutter.sh")
        print("2. Or run directly: ./dist/VideoCutter/VideoCutter")
        
        # Ask if user wants to create DMG
        try:
            create_dmg_choice = input("\n❓ Create DMG file for distribution? (y/n): ").lower().strip()
            if create_dmg_choice == 'y':
                create_dmg()
        except KeyboardInterrupt:
            print("\n👋 Build completed without DMG creation")
        
        return True
    else:
        print("\n❌ Build failed!")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
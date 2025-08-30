# VideoCutter - macOS Video Processing Application

A PyQt6-based video cutting application with FFmpeg integration for macOS.

## Features

- ✂️ Cut video segments with precise timing
- 🎬 Support for various video formats (MP4, MKV, AVI, etc.)
- ⚡ Hardware acceleration support (VideoToolbox, NVENC, Quick Sync)
- ⏸️ Pause/Resume processing
- 🚫 Cancel processing with cleanup
- 📊 Real-time progress tracking
- 🖥️ Native macOS interface

## Requirements

- macOS 10.14 or later
- Python 3.8 or later
- FFmpeg binaries (will be copied to project)

## Setup

### 1. Copy FFmpeg Binaries

First, copy FFmpeg binaries to the project's assets folder:

```bash
# Create assets folder
mkdir -p assets

# Copy FFmpeg binaries (requires FFmpeg to be installed)
cp $(which ffmpeg) assets/
cp $(which ffprobe) assets/
```

**Note**: If you don't have FFmpeg installed, install it first:
```bash
brew install ffmpeg
```

## Quick Start

### Option 1: One-Click Build (Recommended)

```bash
# Make sure FFmpeg binaries are in assets/ folder first
./build.sh
```

This script will:
- Create a virtual environment
- Install all dependencies
- Use FFmpeg from assets folder
- Build the application
- Create a launcher script

### Option 2: Manual Build

1. **Ensure FFmpeg binaries are in assets folder** (see Setup section above)

2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Build the application**:
   ```bash
   python3 build.py
   ```

## Running the Application

After building, you can run the application in several ways:

### Using the launcher script:
```bash
./run_videocutter.sh
```

### Direct execution:
```bash
./dist/VideoCutter/VideoCutter
```

### From Python (development):
```bash
python3 main.py
```

## Build Output

The build process creates:
- `dist/VideoCutter/` - The complete application bundle
- `run_videocutter.sh` - Launcher script
- `VideoCutter-macOS.dmg` - Distribution package (optional)

## Hardware Acceleration

The application automatically detects and uses the best available hardware encoder:

- **macOS**: VideoToolbox (h264_videotoolbox)
- **Windows**: NVENC or Quick Sync
- **Linux**: VAAPI or NVENC
- **Fallback**: Software encoding (libx264)

## Troubleshooting

### FFmpeg not found
```bash
# Install via Homebrew
brew install ffmpeg

# Or check if it's in PATH
which ffmpeg
```

### PyQt6 installation issues
```bash
# Try upgrading pip first
pip install --upgrade pip
pip install PyQt6
```

### Build fails
```bash
# Clean previous builds
rm -rf dist build *.spec

# Try building again
python3 build.py
```

## Development

### Project Structure
```
python-cutter/
├── main.py              # Main application file
├── build.py             # Build script
├── build.sh             # One-click build script
├── requirements.txt     # Python dependencies
├── README.md           # This file
└── dist/               # Built application (after build)
```

### Key Components
- `VideoProcessor`: Handles FFmpeg processing with hardware acceleration
- `MainWindow`: PyQt6 GUI interface
- Hardware encoder detection for optimal performance
- Progress tracking and process control

## License

This project is open source. Feel free to modify and distribute.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test the build process
5. Submit a pull request

---

**Note**: This application includes FFmpeg binaries from your system installation. Make sure FFmpeg is properly licensed for your use case.
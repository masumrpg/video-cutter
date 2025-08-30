import sys
import os
import json
import subprocess
import tempfile
import threading
import re
import platform
import signal
from pathlib import Path
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *

def get_ffmpeg_path():
    """Get the correct path for ffmpeg binary"""
    if getattr(sys, 'frozen', False):
        # Running in a PyInstaller bundle
        bundle_dir = sys._MEIPASS
        # Try assets folder in bundle first
        assets_ffmpeg = os.path.join(bundle_dir, 'assets', 'ffmpeg')
        if os.path.exists(assets_ffmpeg):
            return assets_ffmpeg
        # Fallback to root of bundle
        ffmpeg_path = os.path.join(bundle_dir, 'ffmpeg')
        if os.path.exists(ffmpeg_path):
            return ffmpeg_path
    
    # Try to use ffmpeg from project assets folder first
    script_dir = os.path.dirname(os.path.abspath(__file__))
    assets_ffmpeg = os.path.join(script_dir, 'assets', 'ffmpeg')
    if os.path.exists(assets_ffmpeg):
        return assets_ffmpeg
    
    # Fallback to system ffmpeg
    return 'ffmpeg'

def get_ffprobe_path():
    """Get the correct path for ffprobe binary"""
    if getattr(sys, 'frozen', False):
        # Running in a PyInstaller bundle
        bundle_dir = sys._MEIPASS
        # Try assets folder in bundle first
        assets_ffprobe = os.path.join(bundle_dir, 'assets', 'ffprobe')
        if os.path.exists(assets_ffprobe):
            return assets_ffprobe
        # Fallback to root of bundle
        ffprobe_path = os.path.join(bundle_dir, 'ffprobe')
        if os.path.exists(ffprobe_path):
            return ffprobe_path
    
    # Try to use ffprobe from project assets folder first
    script_dir = os.path.dirname(os.path.abspath(__file__))
    assets_ffprobe = os.path.join(script_dir, 'assets', 'ffprobe')
    if os.path.exists(assets_ffprobe):
        return assets_ffprobe
    
    # Fallback to system ffprobe
    return 'ffprobe'

class VideoProcessor(QThread):
    progress_updated = pyqtSignal(int)
    status_updated = pyqtSignal(str)
    finished = pyqtSignal(bool, str)
    time_info_updated = pyqtSignal(str)
    paused = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(self, input_path, output_path, take_duration, skip_duration):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.take_duration = take_duration
        self.skip_duration = skip_duration
        self.total_duration = 0
        self.is_paused = False
        self.is_cancelled = False
        self.process = None

    def get_video_duration(self):
        """Get total duration of input video"""
        try:
            cmd = [
                get_ffprobe_path(), '-v', 'quiet', '-print_format', 'json',
                '-show_format', self.input_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            return float(data['format']['duration'])
        except:
            return 0
    
    def get_optimal_encoder(self):
        """Detect the best available hardware encoder for the current platform"""
        try:
            # Check available encoders
            result = subprocess.run([get_ffmpeg_path(), '-encoders'], capture_output=True, text=True)
            encoders = result.stdout
            
            # macOS - VideoToolbox hardware acceleration
            if platform.system() == 'Darwin':
                if 'h264_videotoolbox' in encoders:
                    return 'h264_videotoolbox', 'videotoolbox'
            
            # Windows - NVENC or Quick Sync
            elif platform.system() == 'Windows':
                if 'h264_nvenc' in encoders:
                    return 'h264_nvenc', 'cuda'
                elif 'h264_qsv' in encoders:
                    return 'h264_qsv', 'qsv'
            
            # Linux - VAAPI or NVENC
            elif platform.system() == 'Linux':
                if 'h264_nvenc' in encoders:
                    return 'h264_nvenc', 'cuda'
                elif 'h264_vaapi' in encoders:
                    return 'h264_vaapi', 'vaapi'
            
            # Fallback to software encoder
            return 'libx264', 'auto'
            
        except Exception:
            # If detection fails, use software encoder
            return 'libx264', 'auto'

    def parse_ffmpeg_progress(self, line):
        """Parse FFmpeg output for real-time progress"""
        # Look for time=XX:XX:XX.XX pattern
        time_match = re.search(r'time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})', line)
        if time_match:
            hours = int(time_match.group(1))
            minutes = int(time_match.group(2))
            seconds = int(time_match.group(3))
            milliseconds = int(time_match.group(4))

            current_time = hours * 3600 + minutes * 60 + seconds + milliseconds / 100
            return current_time
        return None

    def pause_processing(self):
        """Pause the processing"""
        self.is_paused = True
        if self.process:
            self.process.send_signal(signal.SIGSTOP)
        self.status_updated.emit("⏸️ Processing paused")
        self.paused.emit()

    def resume_processing(self):
        """Resume the processing"""
        self.is_paused = False
        if self.process:
            self.process.send_signal(signal.SIGCONT)
        self.status_updated.emit("▶️ Processing resumed")

    def cancel_processing(self):
        """Cancel the processing and cleanup"""
        self.is_cancelled = True
        if self.process:
            self.process.terminate()
            self.process.wait()
        
        # Remove incomplete output file
        try:
            if os.path.exists(self.output_path):
                os.remove(self.output_path)
        except Exception as e:
            print(f"Error removing incomplete file: {e}")
        
        self.status_updated.emit("❌ Processing cancelled")
        self.cancelled.emit()
        self.finished.emit(False, "Processing was cancelled by user")

    def run(self):
        try:
            # Check if cancelled before starting
            if self.is_cancelled:
                return

            # Get video duration first
            self.status_updated.emit("📊 Analyzing video...")
            self.total_duration = self.get_video_duration()

            if self.total_duration == 0:
                self.finished.emit(False, "Could not determine video duration")
                return

            if self.is_cancelled:
                return

            cycle_duration = self.take_duration + self.skip_duration
            
            # Get optimal encoder for current platform
            video_encoder, hwaccel = self.get_optimal_encoder()
            
            cmd = [get_ffmpeg_path()]
            
            # Add hardware acceleration only if not 'auto' - MUST be before input
            if hwaccel != 'auto':
                cmd.extend(['-hwaccel', hwaccel])
            
            # Add input file
            cmd.extend(['-i', self.input_path])
            
            # Thread optimization - use all available CPU cores
            cmd.extend(['-threads', '0'])
            
            # Video filters
            cmd.extend(['-vf', f"select='between(mod(t,{cycle_duration}),0,{self.take_duration})', setpts=N/FRAME_RATE/TB"])
            
            # Audio filters
            cmd.extend(['-af', f"aselect='between(mod(t,{cycle_duration}),0,{self.take_duration})', asetpts=N/SR/TB"])
            
            # Video codec optimization - use optimal encoder
            cmd.extend(['-c:v', video_encoder])
            
            # Add encoder-specific options
            if video_encoder == 'libx264':
                cmd.extend([
                    '-preset', 'fast',  # Balance between speed and compression
                    '-crf', '23',  # Constant Rate Factor for good quality
                ])
            elif video_encoder == 'h264_videotoolbox':
                cmd.extend([
                    '-b:v', '5000k',  # Bitrate for VideoToolbox
                    '-allow_sw', '1',  # Allow software fallback
                ])
            elif 'nvenc' in video_encoder:
                cmd.extend([
                    '-preset', 'fast',
                    '-cq', '23',  # Constant quality for NVENC
                ])
            elif 'qsv' in video_encoder:
                cmd.extend([
                    '-preset', 'fast',
                    '-global_quality', '23',
                ])
            
            # Add common options
            cmd.extend([
                # Audio codec optimization
                '-c:a', 'aac',
                '-b:a', '128k',
                # Timing and buffer optimizations
                '-avoid_negative_ts', 'make_zero',
                '-max_muxing_queue_size', '9999',
                '-fflags', '+genpts',  # Generate presentation timestamps
                '-movflags', '+faststart',  # Optimize for streaming
                # Progress output
                '-progress', 'pipe:1',
                '-y', self.output_path
            ])
            
            self.status_updated.emit(f"🚀 Using {video_encoder} encoder with {hwaccel} acceleration...")

            self.status_updated.emit("🔄 Starting FFmpeg process...")

            # Debug: Print the FFmpeg command
            print(f"FFmpeg command: {' '.join(cmd)}")
            
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1
            )

            current_progress = 0

            # Read FFmpeg output line by line
            for line in iter(self.process.stdout.readline, ''):
                # Check for cancellation
                if self.is_cancelled:
                    break
                
                # Handle pause
                while self.is_paused and not self.is_cancelled:
                    self.msleep(100)  # Sleep for 100ms
                
                if self.is_cancelled:
                    break

                if line.strip():
                    # Parse progress from FFmpeg output
                    current_time = self.parse_ffmpeg_progress(line)

                    if current_time is not None:
                        # Calculate progress percentage
                        progress = min(int((current_time / self.total_duration) * 100), 100)

                        if progress > current_progress:
                            current_progress = progress
                            self.progress_updated.emit(progress)

                            # Format time info
                            elapsed_formatted = self.format_time(current_time)
                            total_formatted = self.format_time(self.total_duration)
                            time_info = f"{elapsed_formatted} / {total_formatted}"

                            if not self.is_paused:
                                self.status_updated.emit(f"🔄 Processing... {progress}%")
                            self.time_info_updated.emit(time_info)

                    # Check for specific FFmpeg messages
                    if "frame=" in line and not self.is_paused:
                        # Extract frame information if available
                        frame_match = re.search(r'frame=\s*(\d+)', line)
                        if frame_match:
                            frame_num = frame_match.group(1)
                            self.status_updated.emit(f"🎞️ Processing frame {frame_num}...")

            # Wait for process to complete if not cancelled
            if not self.is_cancelled:
                stdout, stderr = self.process.communicate()

                if self.process.returncode == 0:
                    self.progress_updated.emit(100)
                    self.status_updated.emit("✅ Processing completed!")
                    self.time_info_updated.emit("Complete!")
                    self.finished.emit(True, "Video processed successfully!")
                else:
                    error_msg = f"FFmpeg failed with return code {self.process.returncode}"
                    if stderr:
                        error_msg += f"\nError: {stderr}"
                    print(f"FFmpeg error: {error_msg}")
                    self.finished.emit(False, error_msg)
            else:
                # Ensure cleanup if cancelled
                self.cancel_processing()

        except Exception as e:
            self.finished.emit(False, str(e))

    def format_time(self, seconds):
        """Format seconds to HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

class VideoInfoWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Title
        title = QLabel("📊 Video Information")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50; margin-bottom: 10px;")
        layout.addWidget(title)

        # Info display
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMaximumHeight(150)
        self.info_text.setStyleSheet("""
            QTextEdit {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                padding: 10px;
                font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
                font-size: 12px;
            }
        """)
        layout.addWidget(self.info_text)

        self.setLayout(layout)

    def update_info(self, video_path):
        try:
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)

            duration = float(data['format']['duration'])
            file_size = os.path.getsize(video_path) / (1024*1024)

            video_stream = next((s for s in data['streams'] if s['codec_type'] == 'video'), None)
            if video_stream:
                width = video_stream.get('width', 'Unknown')
                height = video_stream.get('height', 'Unknown')
                fps = eval(video_stream.get('r_frame_rate', '25/1'))
                codec = video_stream.get('codec_name', 'Unknown')

                info_text = f"""📹 Duration: {self.format_time(duration)}
📐 Resolution: {width}x{height}
🎞️  Frame Rate: {fps:.2f} fps
💾 File Size: {file_size:.1f} MB
🔧 Video Codec: {codec.upper()}
📁 Filename: {os.path.basename(video_path)}"""

                self.info_text.setPlainText(info_text)
                return duration, f"{width}x{height}", fps

        except Exception as e:
            self.info_text.setPlainText(f"❌ Error reading video info: {str(e)}")
            return None, None, None

    def format_time(self, seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

class DropZone(QLabel):
    files_dropped = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(120)
        self.setStyleSheet("""
            QLabel {
                border: 3px dashed #3498db;
                border-radius: 15px;
                background-color: #ecf0f1;
                color: #2c3e50;
                font-size: 14px;
                padding: 20px;
            }
            QLabel:hover {
                background-color: #d5dbdb;
                border-color: #2980b9;
            }
        """)
        self.setText("🎬 Drag & Drop Video Files Here\n\nOr click 'Browse Files' button below")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet("""
                QLabel {
                    border: 3px dashed #27ae60;
                    border-radius: 15px;
                    background-color: #d5f4e6;
                    color: #2c3e50;
                    font-size: 14px;
                    padding: 20px;
                }
            """)

    def dragLeaveEvent(self, event):
        self.setStyleSheet("""
            QLabel {
                border: 3px dashed #3498db;
                border-radius: 15px;
                background-color: #ecf0f1;
                color: #2c3e50;
                font-size: 14px;
                padding: 20px;
            }
        """)

    def dropEvent(self, event):
        files = []
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv')):
                files.append(file_path)

        if files:
            self.files_dropped.emit(files)
            self.setText(f"✅ {len(files)} file(s) selected")

        self.setStyleSheet("""
            QLabel {
                border: 3px dashed #3498db;
                border-radius: 15px;
                background-color: #ecf0f1;
                color: #2c3e50;
                font-size: 14px;
                padding: 20px;
            }
        """)

class VideoIntervalCutter(QMainWindow):
    def __init__(self):
        super().__init__()
        self.selected_files = []
        self.current_processing = 0
        self.dark_mode = False
        self.output_directory = ""
        self.processor = None
        self.is_processing = False
        self.is_paused = False
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("🎬 FFmpeg Video Interval Cutter Pro")
        self.setGeometry(100, 100, 1000, 750)
        self.setWindowIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Header
        header = QLabel("🎬 FFmpeg Video Interval Cutter Pro")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: white;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                padding: 20px;
                border-radius: 10px;
                margin: 10px;
            }
        """)
        main_layout.addWidget(header)

        # Main content area
        content_layout = QHBoxLayout()

        # Left panel - File selection and settings
        left_panel = QWidget()
        left_panel.setMaximumWidth(400)
        left_layout = QVBoxLayout(left_panel)

        # File selection
        file_group = QGroupBox("📁 File Selection")
        file_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #bdc3c7;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        file_layout = QVBoxLayout(file_group)

        # Drop zone
        self.drop_zone = DropZone()
        self.drop_zone.files_dropped.connect(self.handle_dropped_files)
        file_layout.addWidget(self.drop_zone)

        # Browse button
        browse_btn = QPushButton("📂 Browse Files")
        browse_btn.clicked.connect(self.browse_files)
        browse_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        file_layout.addWidget(browse_btn)

        # File list
        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(100)
        self.file_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #bdc3c7;
                border-radius: 5px;
                background-color: #ffffff;
            }
        """)
        file_layout.addWidget(self.file_list)

        left_layout.addWidget(file_group)

        # Settings
        settings_group = QGroupBox("⚙️ Interval Settings")
        settings_group.setStyleSheet(file_group.styleSheet())
        settings_layout = QFormLayout(settings_group)

        self.take_spin = QSpinBox()
        self.take_spin.setRange(1, 300)
        self.take_spin.setValue(5)
        self.take_spin.setSuffix(" seconds")
        self.take_spin.valueChanged.connect(self.update_preview)

        self.skip_spin = QSpinBox()
        self.skip_spin.setRange(1, 300)
        self.skip_spin.setValue(10)
        self.skip_spin.setSuffix(" seconds")
        self.skip_spin.valueChanged.connect(self.update_preview)

        settings_layout.addRow("🎯 Take Duration:", self.take_spin)
        settings_layout.addRow("⏭️ Skip Duration:", self.skip_spin)

        # Cycle info
        self.cycle_info = QLabel("🔄 Cycle: 15 seconds")
        self.cycle_info.setStyleSheet("color: #7f8c8d; font-style: italic;")
        settings_layout.addRow(self.cycle_info)

        left_layout.addWidget(settings_group)

        # Quality settings
        quality_group = QGroupBox("🎨 Quality Settings")
        quality_group.setStyleSheet(file_group.styleSheet())
        quality_layout = QFormLayout(quality_group)

        self.quality_combo = QComboBox()
        self.quality_combo.addItems([
            "High Quality (CRF 18)",
            "Balanced (CRF 23)",
            "Compressed (CRF 28)",
            "Copy Original (Fastest)"
        ])
        self.quality_combo.setCurrentIndex(1)

        quality_layout.addRow("Quality:", self.quality_combo)
        left_layout.addWidget(quality_group)

        # Process controls
        control_group = QGroupBox("🚀 Processing")
        control_group.setStyleSheet(file_group.styleSheet())
        control_layout = QVBoxLayout(control_group)

        # Button container for horizontal layout
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)

        self.process_btn = QPushButton("▶️ Start Processing")
        self.process_btn.clicked.connect(self.start_processing)
        self.process_btn.setMinimumHeight(50)
        self.process_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                padding: 15px;
                border-radius: 10px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        button_layout.addWidget(self.process_btn)

        # Pause button
        self.pause_btn = QPushButton("⏸️ Pause")
        self.pause_btn.clicked.connect(self.pause_processing)
        self.pause_btn.setMinimumHeight(50)
        self.pause_btn.setVisible(False)  # Hidden initially
        self.pause_btn.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                border: none;
                padding: 15px;
                border-radius: 10px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #e67e22;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        button_layout.addWidget(self.pause_btn)

        # Cancel button
        self.cancel_btn = QPushButton("❌ Cancel")
        self.cancel_btn.clicked.connect(self.cancel_processing)
        self.cancel_btn.setMinimumHeight(50)
        self.cancel_btn.setVisible(False)  # Hidden initially
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                padding: 15px;
                border-radius: 10px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        button_layout.addWidget(self.cancel_btn)

        control_layout.addWidget(button_container)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #bdc3c7;
                border-radius: 8px;
                text-align: center;
                font-weight: bold;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                border-radius: 6px;
            }
        """)
        control_layout.addWidget(self.progress_bar)

        # Time info label
        self.time_info_label = QLabel("⏱️ Time: --:--:-- / --:--:--")
        self.time_info_label.setStyleSheet("color: #7f8c8d; font-family: Monaco, monospace; font-size: 12px;")
        control_layout.addWidget(self.time_info_label)

        # Status
        self.status_label = QLabel("📝 Ready to process")
        self.status_label.setStyleSheet("color: #7f8c8d; font-style: italic;")
        control_layout.addWidget(self.status_label)

        # Current file info
        self.current_file_label = QLabel("📂 No file selected")
        self.current_file_label.setStyleSheet("color: #34495e; font-size: 12px; font-weight: bold;")
        control_layout.addWidget(self.current_file_label)

        left_layout.addWidget(control_group)
        left_layout.addStretch()

        # Right panel - Video info and preview
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        # Video info widget
        self.video_info = VideoInfoWidget()
        right_layout.addWidget(self.video_info)

        # Command preview
        preview_group = QGroupBox("🔍 FFmpeg Command Preview")
        preview_group.setStyleSheet(file_group.styleSheet())
        preview_layout = QVBoxLayout(preview_group)

        self.command_text = QTextEdit()
        self.command_text.setReadOnly(True)
        self.command_text.setMaximumHeight(120)
        self.command_text.setFont(QFont("Monaco", 10))
        self.command_text.setStyleSheet("""
            QTextEdit {
                background-color: #2c3e50;
                color: #ecf0f1;
                border: 1px solid #34495e;
                border-radius: 5px;
                padding: 10px;
                font-size: 11px;
            }
        """)
        preview_layout.addWidget(self.command_text)
        right_layout.addWidget(preview_group)

        # Output log
        log_group = QGroupBox("📋 Processing Log")
        log_group.setStyleSheet(file_group.styleSheet())
        log_layout = QVBoxLayout(log_group)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Monaco", 10))
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #000000;
                color: #00ff00;
                border: 1px solid #333333;
                border-radius: 5px;
                padding: 10px;
                font-size: 11px;
            }
        """)
        log_layout.addWidget(self.log_text)
        right_layout.addWidget(log_group)

        # Add panels to main layout
        content_layout.addWidget(left_panel)
        content_layout.addWidget(right_panel)
        main_layout.addLayout(content_layout)

        # Menu bar
        self.create_menu_bar()

        # Update preview
        self.update_preview()

    def create_menu_bar(self):
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu('📁 File')

        open_action = QAction('📂 Open Video', self)
        open_action.triggered.connect(self.browse_files)
        open_action.setShortcut('Ctrl+O')
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        exit_action = QAction('❌ Exit', self)
        exit_action.triggered.connect(self.close)
        exit_action.setShortcut('Ctrl+Q')
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu('👀 View')

        toggle_theme = QAction('🌙 Toggle Dark Mode', self)
        toggle_theme.triggered.connect(self.toggle_dark_mode)
        view_menu.addAction(toggle_theme)

        # Help menu
        help_menu = menubar.addMenu('❓ Help')

        about_action = QAction('ℹ️ About', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def browse_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Video Files",
            "",
            "Video Files (*.mp4 *.avi *.mov *.mkv *.webm *.flv *.wmv *.m4v);;All Files (*)"
        )
        if files:
            self.handle_dropped_files(files)

    def handle_dropped_files(self, files):
        self.selected_files = files
        self.file_list.clear()

        for file_path in files:
            item = QListWidgetItem(f"📹 {os.path.basename(file_path)}")
            item.setToolTip(file_path)
            self.file_list.addItem(item)

        if files:
            # Update video info for first file
            self.video_info.update_info(files[0])
            self.log_text.append(f"✅ Selected {len(files)} file(s)")

    def update_preview(self):
        take = self.take_spin.value()
        skip = self.skip_spin.value()
        cycle = take + skip

        self.cycle_info.setText(f"🔄 Cycle: {cycle} seconds (Take {take}s → Skip {skip}s)")

        cmd = f"""ffmpeg -i input.mp4 \\
  -vf "select='between(mod(t,{cycle}),0,{take})', setpts=N/FRAME_RATE/TB" \\
  -af "aselect='between(mod(t,{cycle}),0,{take})', asetpts=N/SR/TB" \\
  -avoid_negative_ts make_zero \\
  -max_muxing_queue_size 9999 \\
  -progress pipe:1 \\
  output.mp4"""

        self.command_text.setPlainText(cmd)

    def start_processing(self):
        if not self.selected_files:
            QMessageBox.warning(self, "Warning", "Please select video files first!")
            return

        output_dir = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if not output_dir:
            return

        self.output_directory = output_dir
        self.process_btn.setEnabled(False)
        self.current_processing = 0
        self.is_processing = True
        self.is_paused = False
        self.update_button_states()
        self.process_next_file()

    def pause_processing(self):
        if self.processor and self.is_processing:
            if not self.is_paused:
                self.processor.pause_processing()
                self.is_paused = True
                self.pause_btn.setText("▶️ Resume")
                self.status_label.setText("Status: Paused")
            else:
                self.processor.resume_processing()
                self.is_paused = False
                self.pause_btn.setText("⏸️ Pause")
                self.status_label.setText("Status: Processing...")

    def cancel_processing(self):
        if self.processor and self.is_processing:
            reply = QMessageBox.question(self, "Cancel Processing", 
                                       "Are you sure you want to cancel processing? Any incomplete files will be deleted.",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.processor.cancel_processing()
                self.is_processing = False
                self.is_paused = False
                self.update_button_states()
                self.status_label.setText("Status: Cancelled")

    def update_button_states(self):
        if self.is_processing:
            self.process_btn.setVisible(False)
            self.pause_btn.setVisible(True)
            self.cancel_btn.setVisible(True)
        else:
            self.process_btn.setVisible(True)
            self.pause_btn.setVisible(False)
            self.cancel_btn.setVisible(False)
            self.pause_btn.setText("⏸️ Pause")

    def process_next_file(self):
        if self.current_processing >= len(self.selected_files):
            # All files processed
            self.is_processing = False
            self.process_btn.setEnabled(True)
            self.update_button_states()
            self.current_file_label.setText("📂 Processing complete!")
            self.time_info_label.setText("⏱️ All files completed")
            self.log_text.append("🎉 All files processed successfully!")
            QMessageBox.information(self, "Complete", "All videos have been processed!")
            return

        current_file = self.selected_files[self.current_processing]
        filename = os.path.basename(current_file)

        # Update current file display
        self.current_file_label.setText(f"📂 Processing: {filename} ({self.current_processing + 1}/{len(self.selected_files)})")

        # Create output filename
        name_without_ext = os.path.splitext(filename)[0]
        output_filename = f"cut_{name_without_ext}_take{self.take_spin.value()}s_skip{self.skip_spin.value()}s.mp4"
        output_path = os.path.join(self.output_directory, output_filename)

        self.log_text.append(f"\n🔄 Processing: {filename}")
        self.log_text.append(f"📤 Output: {output_filename}")

        # Reset progress
        self.progress_bar.setValue(0)
        self.time_info_label.setText("⏱️ Time: --:--:-- / --:--:--")

        # Start processing thread
        self.processor = VideoProcessor(
            current_file,
            output_path,
            self.take_spin.value(),
            self.skip_spin.value()
        )
        self.processor.progress_updated.connect(self.progress_bar.setValue)
        self.processor.status_updated.connect(self.status_label.setText)
        self.processor.time_info_updated.connect(self.update_time_info)
        self.processor.finished.connect(self.on_processing_finished)
        self.processor.start()

    def update_time_info(self, time_info):
        """Update time information display"""
        self.time_info_label.setText(f"⏱️ Time: {time_info}")

    def on_processing_finished(self, success, message):
        if success:
            self.log_text.append(f"✅ {message}")
            # Show file size of output
            try:
                output_file = os.path.join(self.output_directory,
                    f"cut_{os.path.splitext(os.path.basename(self.selected_files[self.current_processing]))[0]}_take{self.take_spin.value()}s_skip{self.skip_spin.value()}s.mp4")
                if os.path.exists(output_file):
                    size_mb = os.path.getsize(output_file) / (1024 * 1024)
                    self.log_text.append(f"📊 Output file size: {size_mb:.1f} MB")
            except:
                pass
        else:
            self.log_text.append(f"❌ Error: {message}")

        self.current_processing += 1

        # Check if processing was cancelled
        if not self.is_processing:
            self.process_btn.setEnabled(True)
            self.update_button_states()
            return

        # Check if all files are processed
        if self.current_processing >= len(self.selected_files):
            self.is_processing = False
            self.is_paused = False
            self.process_btn.setEnabled(True)
            self.update_button_states()
            return

        # Process next file after a short delay
        QTimer.singleShot(2000, self.process_next_file)

    def toggle_dark_mode(self):
        self.dark_mode = not self.dark_mode
        if self.dark_mode:
            self.setStyleSheet("""
                QMainWindow {
                    background-color: #2c3e50;
                    color: #ecf0f1;
                }
                QWidget {
                    background-color: #2c3e50;
                    color: #ecf0f1;
                }
                QGroupBox {
                    border: 2px solid #7f8c8d;
                    color: #ecf0f1;
                }
            """)
        else:
            self.setStyleSheet("")

    def show_about(self):
        QMessageBox.about(self, "About", """
🎬 FFmpeg Video Interval Cutter Pro

Professional video processing tool for cutting videos with custom intervals.

Features:
• Drag & drop file support
• Batch processing
• Real-time progress tracking
• Accurate time display
• High quality output
• No file size limit

Version: 2.0 (Real-time Progress)
Built with PyQt6 & FFmpeg

Improvements in this version:
✅ Real-time progress parsing
✅ Accurate time tracking
✅ Better status updates
✅ Enhanced UI feedback
        """)

    def closeEvent(self, event):
        """Handle application closing"""
        if hasattr(self, 'processor') and self.processor is not None and self.processor.isRunning():
            reply = QMessageBox.question(
                self, 'Confirm Exit',
                'Video processing is still running. Are you sure you want to exit?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                # Terminate the processor thread
                self.processor.terminate()
                self.processor.wait(3000)  # Wait max 3 seconds
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    # Set application icon
    app.setWindowIcon(app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))

    window = VideoIntervalCutter()
    window.show()

    sys.exit(app.exec())

if __name__ == '__main__':
    main()
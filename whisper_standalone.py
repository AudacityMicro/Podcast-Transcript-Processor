#!/usr/bin/env python
"""
Audio Transcription Tool - All-in-one launcher and application.
Handles virtual environment setup, dependencies, and GUI application.

Usage: python main.py
"""

import os
import sys
import subprocess
import venv
import platform
from pathlib import Path


def main():
    """Main entry point that decides whether to run setup or launch the app."""
    # Check if we're already in the venv
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix) or 'venv' in sys.executable:
        # We're in a venv, run the app directly
        run_app()
    else:
        # We're not in a venv, run the launcher
        launcher = TranscriptionLauncher()
        launcher.run()


class TranscriptionLauncher:
    """Handles environment setup and dependency installation."""

    def __init__(self):
        self.project_dir = Path(__file__).parent
        self.venv_dir = self.project_dir / "venv"
        self.is_windows = platform.system() == "Windows"
        self.python_exe = self.get_venv_python()
        self.pip_exe = self.get_venv_pip()

    def get_venv_python(self):
        """Get the path to the Python executable in the venv."""
        if self.is_windows:
            return str(self.venv_dir / "Scripts" / "python.exe")
        else:
            return str(self.venv_dir / "bin" / "python")

    def get_venv_pip(self):
        """Get the path to pip in the venv."""
        if self.is_windows:
            return str(self.venv_dir / "Scripts" / "pip.exe")
        else:
            return str(self.venv_dir / "bin" / "pip")

    def create_venv(self):
        """Create virtual environment if it doesn't exist."""
        if not self.venv_dir.exists():
            print("Creating virtual environment...")
            venv.create(self.venv_dir, with_pip=True)
            print("✓ Virtual environment created")

            # Upgrade pip
            print("Upgrading pip...")
            subprocess.run([self.python_exe, "-m", "pip", "install", "--upgrade", "pip"],
                         capture_output=True)
        else:
            print("✓ Virtual environment already exists")

    def check_ffmpeg(self):
        """Check if FFmpeg is installed."""
        try:
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
            if result.returncode == 0:
                print("✓ FFmpeg is installed")
                return True
        except FileNotFoundError:
            pass

        print("⚠ FFmpeg not found. Please install it:")
        if self.is_windows:
            print("  Download from: https://ffmpeg.org/download.html")
            print("  Or use: winget install ffmpeg")
        elif platform.system() == "Darwin":
            print("  Use: brew install ffmpeg")
        else:
            print("  Use: sudo apt install ffmpeg")
        return False

    def check_dependencies(self):
        """Check if required packages are installed."""
        try:
            result = subprocess.run(
                [self.python_exe, "-c", "import whisper; import torch; import numpy"],
                capture_output=True, text=True
            )
            return result.returncode == 0
        except:
            return False

    def install_dependencies(self):
        """Install required Python packages."""
        print("\nInstalling dependencies...")

        requirements = [
            "numpy",
            ("torch", ["torch", "torchvision", "torchaudio", "--index-url", "https://download.pytorch.org/whl/cpu"]),
            "openai-whisper",
            "ffmpeg-python",
            "tqdm",
        ]

        for package in requirements:
            if isinstance(package, tuple):
                package_name, install_cmd = package
                print(f"Installing {package_name}...")
                cmd = [self.pip_exe, "install"] + install_cmd
            else:
                print(f"Installing {package}...")
                cmd = [self.pip_exe, "install", package]

            try:
                subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"  ✓ {package_name if isinstance(package, tuple) else package}")
            except subprocess.CalledProcessError:
                if package == "openai-whisper":
                    print("  Trying alternative installation...")
                    try:
                        subprocess.check_call([
                            self.pip_exe, "install", "git+https://github.com/openai/whisper.git"
                        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        print(f"  ✓ {package} (from GitHub)")
                    except:
                        print(f"  ✗ Could not install {package}")
                else:
                    print(f"  ✗ Failed to install {package}")

        print("\n✓ Dependencies installed")

    def launch_app_in_venv(self):
        """Launch the application using the venv Python."""
        print("\n" + "="*50)
        print("Launching Audio Transcription Tool...")
        print("="*50 + "\n")

        # Run this same script but with the venv Python
        subprocess.run([self.python_exe, __file__])

    def run(self):
        """Main execution flow."""
        print("="*50)
        print("Audio Transcription Tool - Setup")
        print("="*50)
        print(f"Python: {sys.version.split()[0]}")
        print(f"Platform: {platform.system()}")
        print()

        # Check FFmpeg first
        ffmpeg_ok = self.check_ffmpeg()
        if not ffmpeg_ok:
            print("\n⚠ FFmpeg is required. Please install it and run this script again.")
            input("\nPress Enter to exit...")
            return

        # Create venv
        self.create_venv()

        # Check if dependencies are already installed
        if not self.check_dependencies():
            # Install dependencies
            self.install_dependencies()
        else:
            print("✓ Dependencies already installed")

        # Launch the app in venv
        self.launch_app_in_venv()


def run_app():
    """Run the actual transcription application."""
    import tkinter as tk
    from tkinter import ttk, filedialog, scrolledtext, messagebox
    import threading
    import queue
    import subprocess
    import tempfile
    from pathlib import Path
    from typing import List
    import warnings

    # Try to import whisper
    try:
        import whisper
        WHISPER_AVAILABLE = True
    except ImportError:
        WHISPER_AVAILABLE = False
        print("Whisper not installed. The installer should have installed it.")
        print("Try running: pip install openai-whisper")

    warnings.filterwarnings("ignore")


    class TranscriptSegment:
        """Represents a transcript segment."""
        def __init__(self, start, end, text, speaker):
            self.start = start
            self.end = end
            self.text = text
            self.speaker = speaker


    class SimpleTranscriber:
        """Simple transcriber using Whisper without pydub."""

        def __init__(self, model_size="base"):
            if not WHISPER_AVAILABLE:
                raise ImportError("Whisper is not installed")
            self.model = whisper.load_model(model_size)

        def convert_to_wav(self, input_file):
            """Convert audio file to WAV using ffmpeg directly."""
            if input_file.lower().endswith('.wav'):
                return input_file

            temp_wav = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            temp_wav.close()

            try:
                cmd = [
                    "ffmpeg", "-i", input_file,
                    "-ar", "16000",  # 16kHz sample rate
                    "-ac", "1",      # Mono
                    "-y",            # Overwrite
                    temp_wav.name
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    return temp_wav.name
                else:
                    print(f"FFmpeg error: {result.stderr}")
                    return None
            except Exception as e:
                print(f"Error converting: {e}")
                return None

        def transcribe_file(self, audio_path, speaker_name, progress_callback=None):
            """Transcribe a single audio file."""
            if progress_callback:
                progress_callback(f"Converting {Path(audio_path).name}...")

            wav_path = self.convert_to_wav(audio_path)
            if not wav_path:
                return []

            try:
                if progress_callback:
                    progress_callback(f"Transcribing {speaker_name}...")

                result = self.model.transcribe(wav_path, language='en', fp16=False)

                segments = []
                for seg in result['segments']:
                    segments.append(TranscriptSegment(
                        start=seg['start'],
                        end=seg['end'],
                        text=seg['text'].strip(),
                        speaker=speaker_name
                    ))

                if progress_callback:
                    progress_callback(f"Completed {speaker_name}: {len(segments)} segments")

                return segments

            finally:
                if wav_path != audio_path and os.path.exists(wav_path):
                    try:
                        os.unlink(wav_path)
                    except:
                        pass


    class TranscriptionApp:
        """Main GUI application."""

        def __init__(self, root):
            self.root = root
            self.root.title("Audio Transcription Tool")
            self.root.geometry("900x700")

            # State
            self.audio_files = []
            self.speaker_entries = {}
            self.is_transcribing = False
            self.message_queue = queue.Queue()
            self.model_size = tk.StringVar(value="base")
            self.output_directory = None  # None means use input file directory

            self.setup_ui()
            self.process_queue()

        def setup_ui(self):
            """Setup the user interface."""
            main_frame = ttk.Frame(self.root, padding="10")
            main_frame.pack(fill="both", expand=True)

            # Top section - Settings
            top_frame = ttk.LabelFrame(main_frame, text="Settings", padding="10")
            top_frame.pack(fill="x", pady=(0, 10))

            # Model selection row
            settings_row = ttk.Frame(top_frame)
            settings_row.pack(fill="x")

            ttk.Label(settings_row, text="Model:").pack(side="left", padx=(0, 5))
            model_combo = ttk.Combobox(
                settings_row,
                textvariable=self.model_size,
                values=["tiny", "base", "small", "medium", "large"],
                state="readonly",
                width=10
            )
            model_combo.pack(side="left", padx=(0, 20))

            ttk.Button(settings_row, text="Select Files", command=self.select_files).pack(side="left", padx=2)
            self.transcribe_btn = ttk.Button(
                settings_row,
                text="Start Transcription",
                command=self.start_transcription,
                state="disabled"
            )
            self.transcribe_btn.pack(side="left", padx=2)
            ttk.Button(settings_row, text="Clear Files", command=self.clear_files).pack(side="left", padx=2)

            # Output directory row
            output_row = ttk.Frame(top_frame)
            output_row.pack(fill="x", pady=(10, 0))

            ttk.Label(output_row, text="Output:").pack(side="left", padx=(0, 5))
            self.output_label = ttk.Label(output_row, text="Same as input files", foreground="blue")
            self.output_label.pack(side="left", padx=(0, 10))
            ttk.Button(output_row, text="Change Output Directory", command=self.select_output_dir).pack(side="left")
            ttk.Button(output_row, text="Reset to Input Dir", command=self.reset_output_dir).pack(side="left", padx=(5, 0))

            # File list section
            list_frame = ttk.LabelFrame(main_frame, text="Audio Files", padding="10")
            list_frame.pack(fill="both", expand=True, pady=(0, 10))

            # Create scrollable area for file list
            canvas = tk.Canvas(list_frame, height=150)
            scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
            self.file_frame = ttk.Frame(canvas)

            self.file_frame.bind(
                "<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
            )

            canvas.create_window((0, 0), window=self.file_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)

            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")

            # Log section
            log_frame = ttk.LabelFrame(main_frame, text="Progress Log", padding="10")
            log_frame.pack(fill="both", expand=True)

            self.log_text = scrolledtext.ScrolledText(
                log_frame,
                height=10,
                wrap=tk.WORD,
                bg="white",
                fg="black"
            )
            self.log_text.pack(fill="both", expand=True)

            # Progress bar
            self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
            self.progress.pack(fill="x", pady=(10, 0))

            # Status label
            self.status_label = ttk.Label(main_frame, text="Ready")
            self.status_label.pack(pady=(5, 0))

        def select_files(self):
            """Select audio files."""
            files = filedialog.askopenfilenames(
                title="Select Audio Files",
                filetypes=[
                    ("Audio Files", "*.wav *.mp3 *.flac *.m4a *.ogg"),
                    ("All Files", "*.*")
                ]
            )
            if files:
                self.audio_files = list(files)
                self.update_file_list()
                self.transcribe_btn.config(state="normal")
                self.log(f"Selected {len(files)} file(s)")

        def update_file_list(self):
            """Update file list display."""
            for widget in self.file_frame.winfo_children():
                widget.destroy()

            self.speaker_entries = {}

            for i, file_path in enumerate(self.audio_files):
                name = Path(file_path).stem

                row_frame = ttk.Frame(self.file_frame)
                row_frame.pack(fill="x", pady=2)

                ttk.Label(row_frame, text=f"{i+1}.").pack(side="left", padx=(0, 5))
                ttk.Label(row_frame, text=Path(file_path).name, width=40).pack(side="left", padx=(0, 10))

                ttk.Label(row_frame, text="Speaker:").pack(side="left", padx=(0, 5))
                var = tk.StringVar(value=name)
                entry = ttk.Entry(row_frame, textvariable=var, width=30)
                entry.pack(side="left")

                self.speaker_entries[file_path] = var

        def clear_files(self):
            """Clear selected files."""
            self.audio_files = []
            self.update_file_list()
            self.transcribe_btn.config(state="disabled")
            self.log("Cleared file selection")

        def select_output_dir(self):
            """Select a custom output directory."""
            directory = filedialog.askdirectory(
                title="Select Output Directory",
                initialdir=self.output_directory or os.getcwd()
            )
            if directory:
                self.output_directory = directory
                # Shorten path for display if too long
                display_path = directory
                if len(display_path) > 50:
                    display_path = "..." + display_path[-47:]
                self.output_label.config(text=display_path, foreground="green")
                self.log(f"Output directory set to: {directory}")

        def reset_output_dir(self):
            """Reset output directory to use input file directory."""
            self.output_directory = None
            self.output_label.config(text="Same as input files", foreground="blue")
            self.log("Output will be saved in input file directory")

        def start_transcription(self):
            """Start transcription in background thread."""
            if self.is_transcribing or not self.audio_files:
                return

            if not WHISPER_AVAILABLE:
                messagebox.showerror(
                    "Whisper Not Installed",
                    "Please restart the application to install dependencies."
                )
                return

            self.is_transcribing = True
            self.transcribe_btn.config(state="disabled")
            self.status_label.config(text="Transcribing...")
            self.progress.start(10)

            thread = threading.Thread(target=self.run_transcription)
            thread.daemon = True
            thread.start()

        def run_transcription(self):
            """Run the transcription process."""
            try:
                self.log(f"Loading {self.model_size.get()} model...")

                transcriber = SimpleTranscriber(self.model_size.get())

                all_segments = []

                for i, file_path in enumerate(self.audio_files):
                    speaker = self.speaker_entries[file_path].get()
                    self.log(f"Processing file {i+1}/{len(self.audio_files)}: {speaker}")

                    segments = transcriber.transcribe_file(
                        file_path,
                        speaker,
                        progress_callback=lambda msg: self.log(f"  {msg}")
                    )

                    all_segments.extend(segments)

                # Sort by timestamp
                all_segments.sort(key=lambda s: s.start)

                # Save results
                self.save_transcripts(all_segments)

                self.message_queue.put(("complete", "Transcription completed successfully!"))

            except Exception as e:
                self.message_queue.put(("error", str(e)))

            finally:
                self.message_queue.put(("finished", None))

        def save_transcripts(self, segments):
            """Save transcript files."""
            # Determine output directory
            if self.output_directory:
                # Use custom output directory
                output_dir = self.output_directory
            else:
                # Use the directory of the first input file
                output_dir = str(Path(self.audio_files[0]).parent)

            # Create full paths for output files
            text_path = os.path.join(output_dir, "merged_transcript.txt")
            srt_path = os.path.join(output_dir, "merged_transcript.srt")

            # Text format
            with open(text_path, "w", encoding="utf-8") as f:
                for seg in segments:
                    time = self.format_time(seg.start)
                    f.write(f"{time} {seg.speaker}: {seg.text}\n")

            # SRT format
            with open(srt_path, "w", encoding="utf-8") as f:
                for i, seg in enumerate(segments, 1):
                    f.write(f"{i}\n")
                    f.write(f"{self.format_srt_time(seg.start)} --> {self.format_srt_time(seg.end)}\n")
                    f.write(f"{seg.speaker}: {seg.text}\n\n")

            self.log(f"Saved files to: {output_dir}")
            self.log("  - merged_transcript.txt")
            self.log("  - merged_transcript.srt")

        def format_time(self, seconds):
            """Format time as [HH:MM:SS]."""
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            return f"[{h:02d}:{m:02d}:{s:02d}]"

        def format_srt_time(self, seconds):
            """Format time for SRT."""
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            ms = int((seconds % 1) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        def log(self, message):
            """Add message to log."""
            self.message_queue.put(("log", message))

        def process_queue(self):
            """Process messages from queue."""
            try:
                while True:
                    msg_type, msg_data = self.message_queue.get_nowait()

                    if msg_type == "log":
                        self.log_text.insert(tk.END, msg_data + "\n")
                        self.log_text.see(tk.END)
                    elif msg_type == "complete":
                        self.log_text.insert(tk.END, msg_data + "\n")
                        self.log_text.see(tk.END)
                        messagebox.showinfo("Success", msg_data)
                    elif msg_type == "error":
                        self.log_text.insert(tk.END, f"ERROR: {msg_data}\n")
                        self.log_text.see(tk.END)
                        messagebox.showerror("Error", msg_data)
                    elif msg_type == "finished":
                        self.is_transcribing = False
                        self.transcribe_btn.config(state="normal")
                        self.status_label.config(text="Ready")
                        self.progress.stop()

            except queue.Empty:
                pass

            self.root.after(100, self.process_queue)


    # Run the GUI application
    if not WHISPER_AVAILABLE:
        print("\n" + "="*50)
        print("Whisper is not installed!")
        print("Please restart the application.")
        print("="*50)
        input("\nPress Enter to exit...")
        return

    root = tk.Tk()
    app = TranscriptionApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
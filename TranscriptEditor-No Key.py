import re
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import os
from openai import OpenAI
import json
from tkinter import ttk
import threading
import queue
import subprocess
import tempfile
from pathlib import Path
import warnings
import sys
import platform

# Try to import whisper (may not be installed)
try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

warnings.filterwarnings("ignore")


def get_pip_executable():
    """Get the path to pip in the current environment."""
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        # We're in a venv
        if platform.system() == "Windows":
            return os.path.join(sys.prefix, "Scripts", "pip.exe")
        else:
            return os.path.join(sys.prefix, "bin", "pip")
    else:
        # Not in venv, use system pip
        return "pip"


def check_ffmpeg():
    """Check if FFmpeg is installed."""
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def install_whisper_dependencies(progress_callback=None):
    """Install whisper and its dependencies."""
    pip_exe = get_pip_executable()

    def run_pip_install(args, package_name):
        """Run pip install and return success status."""
        try:
            result = subprocess.run(args, capture_output=True, text=True)
            if result.returncode == 0:
                return True, None
            else:
                return False, result.stderr
        except Exception as e:
            return False, str(e)

    # Install numpy first
    if progress_callback:
        progress_callback("Installing numpy...")
    success, error = run_pip_install([pip_exe, "install", "numpy"], "numpy")
    if success:
        if progress_callback:
            progress_callback("  Installed numpy")
    else:
        if progress_callback:
            progress_callback(f"  Failed to install numpy: {error}")
        return False

    # Install torch - try simple install first, then CPU-specific if needed
    if progress_callback:
        progress_callback("Installing torch (this may take a while)...")

    # First try simple torch install
    success, error = run_pip_install([pip_exe, "install", "torch"], "torch")
    if not success:
        if progress_callback:
            progress_callback("  Simple install failed, trying CPU-only version...")
        # Try CPU-only version for Windows
        success, error = run_pip_install(
            [pip_exe, "install", "torch", "--index-url", "https://download.pytorch.org/whl/cpu"],
            "torch"
        )

    if success:
        if progress_callback:
            progress_callback("  Installed torch")
    else:
        if progress_callback:
            progress_callback(f"  Failed to install torch")
            progress_callback(f"  Error: {error[:500] if error else 'Unknown error'}")
        return False

    # Install openai-whisper
    if progress_callback:
        progress_callback("Installing openai-whisper...")
    success, error = run_pip_install([pip_exe, "install", "openai-whisper"], "openai-whisper")
    if not success:
        if progress_callback:
            progress_callback("  Trying alternative installation from GitHub...")
        success, error = run_pip_install(
            [pip_exe, "install", "git+https://github.com/openai/whisper.git"],
            "openai-whisper"
        )

    if success:
        if progress_callback:
            progress_callback("  Installed openai-whisper")
    else:
        if progress_callback:
            progress_callback(f"  Failed to install openai-whisper")
            progress_callback(f"  Error: {error[:500] if error else 'Unknown error'}")
        return False

    # Install ffmpeg-python
    if progress_callback:
        progress_callback("Installing ffmpeg-python...")
    success, error = run_pip_install([pip_exe, "install", "ffmpeg-python"], "ffmpeg-python")
    if success:
        if progress_callback:
            progress_callback("  Installed ffmpeg-python")
    else:
        if progress_callback:
            progress_callback(f"  Failed to install ffmpeg-python: {error}")
        return False

    return True

# Configurable Hosts List
hosts = []  # No hard-coded hosts, more can be added through the GUI

# Path to the JSON file for storing settings
settings_file = 'settings.json'

# Tooltip class
class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event=None):
        x = self.widget.winfo_rootx() + self.widget.winfo_width() + 10
        y = self.widget.winfo_rooty() + 10
        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.geometry(f"+{x}+{y}")
        label = tk.Label(self.tooltip, text=self.text, background="#ffffe0", relief="solid", borderwidth=1, padx=5, pady=3)
        label.pack()

    def hide_tooltip(self, event=None):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None


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


def generate_summary(text, summary_type="short", api_key=None):
    if not api_key:
        raise ValueError("API key is required")

    client = OpenAI(api_key=api_key)

    prompt = "Summarize the following transcript."
    if summary_type == "detailed":
        prompt = "Provide a detailed five-paragraph summary of the following transcript."
    elif summary_type == "short":
        prompt = "Summarize the following transcript in three sentences."

    # Flip the max tokens for detailed and standard summaries
    max_tokens = 10000 if summary_type == "detailed" else 16384

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": text}
        ],
        max_tokens=max_tokens
    )
    summary = response.choices[0].message.content.strip()
    return summary

def process_transcript(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        transcript = file.read()

    # Step 1: Remove timecodes
    transcript = re.sub(r'\d{2}:\d{2}:\d{2}\.\d{2}|\d{2}:\d{2}\.\d{2}', '', transcript)

    # Step 2: Find and replace words based on user input
    for find_entry, replace_entry, _ in find_replace_entries:
        find_word = find_entry.get().strip()
        replace_word = replace_entry.get().strip()
        if find_word:
            transcript = transcript.replace(find_word, replace_word)

    # Step 3: Replace host names with formatted versions
    for host in hosts:
        formatted_host = f"'''{host}''':   "
        transcript = re.sub(rf"\b{host}\b", formatted_host, transcript)

    # Step 4: Ensure the host names are followed by their dialogue on the same line
    transcript = re.sub(rf"(?<={formatted_host})\s*\n+", " ", transcript)

    # Step 5: Add <br> at the beginning of each line that starts with a host's name
    for host in hosts:
        formatted_host = f"'''{host}''':   "
        transcript = re.sub(rf"(?<!<br>)({re.escape(formatted_host)})", r"<br>\1", transcript)

    # Step 6: Remove any extra newlines between host sections
    transcript = re.sub(r"\n{2,}", "\n", transcript)

    # Step 7: Generate summaries using ChatGPT API
    api_key = api_key_entry.get().strip()
    short_summary = generate_summary(transcript, summary_type="short", api_key=api_key)
    detailed_summary = generate_summary(transcript, summary_type="detailed", api_key=api_key)
    
    # Step 8: Wikimedia Page Preparation with summaries
    transcript = (f"=TLDR=\n\n{short_summary}\n\n"
                  f"=Links=\n\n"
                  f"=Summary=\n\n{detailed_summary}\n\n"
                  f"=Transcript=\n\n" + transcript)

    # Output the processed transcript
    output_file_path = file_path.replace('.txt', '_processed.txt')
    with open(output_file_path, 'w', encoding='utf-8') as file:
        file.write(transcript)

    return output_file_path


def select_files():
    file_paths = filedialog.askopenfilenames(filetypes=[("Text Files", "*.txt")])
    if file_paths:
        file_label.config(text=f"{len(file_paths)} files loaded")
        start_button.config(state=tk.NORMAL)
        start_button.file_paths = file_paths

def process_transcripts():
    status_label.config(text="Processing... Please wait.", fg="red")
    start_button.config(state=tk.DISABLED)  # Disable the start button
    window.update_idletasks()

    processed_files = []
    for file_path in start_button.file_paths:
        processed_file = process_transcript(file_path)
        processed_files.append(processed_file)

    status_label.config(text="Processing complete. Files saved.", fg="green")
    window.update_idletasks()

    messagebox.showinfo("Success", f"Processed transcripts saved. Files: {', '.join(processed_files)}")
    start_button.config(state=tk.NORMAL)  # Re-enable the start button

    # Open each processed file in the default text editor
    for file in processed_files:
        if os.name == 'nt':  # Windows
            os.startfile(file)
        elif os.name == 'posix':  # macOS and Linux
            os.system(f'open "{file}"')

def add_host():
    new_host = host_entry.get().strip()
    if new_host and new_host not in hosts:
        hosts.append(new_host)
        host_list_label.config(text="Hosts: " + ", ".join(hosts))
        update_remove_host_dropdown()
        host_entry.delete(0, tk.END)

def remove_host():
    selected_host = remove_host_var.get()
    if selected_host in hosts:
        hosts.remove(selected_host)
        host_list_label.config(text="Hosts: " + ", ".join(hosts))
        update_remove_host_dropdown()

def update_remove_host_dropdown():
    remove_host_menu['menu'].delete(0, 'end')
    for host in hosts:
        remove_host_menu['menu'].add_command(label=host, command=tk._setit(remove_host_var, host))

def set_api_key(api_key):
    # Validate API key by attempting to use it
    if api_key:
        display_key = api_key[:5] + '*' * (len(api_key) - 5)
        api_key_status_label.config(text=f"API Key Set: {display_key}", fg="green")
        window.update_idletasks()

def add_find_replace():
    find_replace_frame = tk.Frame(find_replace_container)
    find_replace_frame.grid(sticky="ew", padx=5, pady=5)

    find_label = tk.Label(find_replace_frame, text="Find:")
    find_label.grid(row=0, column=0, sticky="w", padx=5)
    find_entry = tk.Entry(find_replace_frame)
    find_entry.grid(row=0, column=1, sticky="ew", padx=5)

    replace_label = tk.Label(find_replace_frame, text="Replace with:")
    replace_label.grid(row=0, column=2, sticky="w", padx=5)
    replace_entry = tk.Entry(find_replace_frame)
    replace_entry.grid(row=0, column=3, sticky="ew", padx=5)

    remove_button = tk.Button(find_replace_frame, text="Remove", command=lambda: remove_find_replace(find_replace_frame))
    remove_button.grid(row=0, column=4, sticky="e", padx=5)

    find_replace_frame.grid_columnconfigure(1, weight=1)
    find_replace_frame.grid_columnconfigure(3, weight=1)

    find_replace_entries.append((find_entry, replace_entry, find_replace_frame))

def remove_find_replace(frame):
    frame.destroy()
    find_replace_entries[:] = [entry for entry in find_replace_entries if entry[2] != frame]

def clear_find_replace_entries():
    for _, _, frame in find_replace_entries:
        frame.destroy()
    find_replace_entries.clear()

def load_settings():
    if os.path.exists(settings_file):
        with open(settings_file, 'r') as f:
            settings = json.load(f)
            # Load hosts
            global hosts
            hosts = settings.get("hosts", hosts)
            host_list_label.config(text="Hosts: " + ", ".join(hosts))
            update_remove_host_dropdown()

            # Load API key
            api_key = settings.get("api_key", "")
            api_key_entry.delete(0, tk.END)
            api_key_entry.insert(0, api_key)
            if api_key:
                set_api_key(api_key)

            # Clear existing find/replace entries
            clear_find_replace_entries()

            # Load find/replace pairs
            for pair in settings.get("find_replace", []):
                add_find_replace()
                find_replace_entries[-1][0].insert(0, pair["find"])
                find_replace_entries[-1][1].insert(0, pair["replace"])

def save_settings():
    settings = {
        "hosts": hosts,
        "api_key": api_key_entry.get().strip(),
        "find_replace": [
            {"find": find_entry.get().strip(), "replace": replace_entry.get().strip()}
            for find_entry, replace_entry, _ in find_replace_entries
        ]
    }
    with open(settings_file, 'w') as f:
        json.dump(settings, f)
    messagebox.showinfo("Settings Saved", "Settings have been saved to the JSON file.")

def reload_settings():
    load_settings()
    messagebox.showinfo("Settings Loaded", "Settings have been reloaded from the JSON file.")

def clear_window():
    """Clear all widgets from the window."""
    for widget in window.winfo_children():
        widget.destroy()

def show_main_menu():
    """Display the main menu screen."""
    clear_window()

    window.title("Transcript Tools")

    menu_frame = tk.Frame(window)
    menu_frame.grid(sticky="nsew", padx=40, pady=40)

    window.grid_rowconfigure(0, weight=1)
    window.grid_columnconfigure(0, weight=1)
    menu_frame.grid_rowconfigure(1, weight=1)
    menu_frame.grid_columnconfigure(0, weight=1)

    # Title
    title_label = tk.Label(menu_frame, text="Transcript Tools", font=("Arial", 24, "bold"))
    title_label.grid(row=0, column=0, pady=(0, 30))

    # Buttons frame
    buttons_frame = tk.Frame(menu_frame)
    buttons_frame.grid(row=1, column=0)

    # Post-process Podcast Transcript button
    transcript_btn = tk.Button(
        buttons_frame,
        text="Post-process Podcast Transcript",
        command=create_transcript_processor_gui,
        font=("Arial", 14),
        width=30,
        height=2
    )
    transcript_btn.grid(row=0, column=0, pady=10)
    ToolTip(transcript_btn, "Process transcript files: remove timecodes, format hosts, generate summaries.")

    # Transcribe Audio button
    transcribe_btn = tk.Button(
        buttons_frame,
        text="Transcribe Audio (Whisper)",
        command=create_transcription_gui,
        font=("Arial", 14),
        width=30,
        height=2
    )
    transcribe_btn.grid(row=1, column=0, pady=10)
    ToolTip(transcribe_btn, "Transcribe audio files using OpenAI Whisper. Requires FFmpeg.")

    # Generate Minutes button
    minutes_btn = tk.Button(
        buttons_frame,
        text="Generate Minutes from Transcript",
        command=create_minutes_generator_gui,
        font=("Arial", 14),
        width=30,
        height=2
    )
    minutes_btn.grid(row=2, column=0, pady=10)
    ToolTip(minutes_btn, "Generate meeting minutes from a transcript using ChatGPT.")


def create_minutes_generator_gui():
    """Create the minutes generator interface."""
    clear_window()

    window.title("Generate Minutes from Transcript")

    # Default prompt
    default_prompt = """You are an expert at creating meeting minutes. Given the following transcript, create well-organized meeting minutes that include:

1. **Meeting Overview**: Brief summary of the meeting's purpose
2. **Key Discussion Points**: Main topics discussed
3. **Decisions Made**: Any decisions or conclusions reached
4. **Action Items**: Tasks assigned with responsible parties (if mentioned)
5. **Notable Quotes**: Any important statements worth preserving

Format the output in clean markdown. Be concise but comprehensive."""

    def load_minutes_settings():
        """Load settings, pulling API key from shared settings file."""
        settings = {
            'api_key': '',
            'model': 'gpt-4o-mini',
            'prompt': default_prompt,
            'output_directory': ''
        }
        # Load from shared settings file (includes API key from transcript processor)
        if os.path.exists(settings_file):
            try:
                with open(settings_file, 'r') as f:
                    shared_settings = json.load(f)
                    # Pull API key from shared settings
                    if 'api_key' in shared_settings:
                        settings['api_key'] = shared_settings['api_key']
                    # Load minutes-specific settings if they exist
                    if 'minutes_model' in shared_settings:
                        settings['model'] = shared_settings['minutes_model']
                    if 'minutes_prompt' in shared_settings:
                        settings['prompt'] = shared_settings['minutes_prompt']
                    if 'minutes_output_directory' in shared_settings:
                        settings['output_directory'] = shared_settings['minutes_output_directory']
            except:
                pass
        return settings

    def save_minutes_settings():
        """Save minutes settings to shared settings file."""
        # Load existing settings first to preserve other data
        existing = {}
        if os.path.exists(settings_file):
            try:
                with open(settings_file, 'r') as f:
                    existing = json.load(f)
            except:
                pass

        # Update with current values
        existing['api_key'] = api_key_var.get()
        existing['minutes_model'] = model_var.get()
        existing['minutes_prompt'] = prompt_text.get("1.0", tk.END).strip()
        existing['minutes_output_directory'] = output_dir_var.get()

        with open(settings_file, 'w') as f:
            json.dump(existing, f, indent=2)
        log_message("Settings saved.")

    # Load existing settings
    saved_settings = load_minutes_settings()

    # State
    state = {
        'input_file': None,
        'is_processing': False
    }

    # Variables
    api_key_var = tk.StringVar(value=saved_settings.get('api_key', ''))
    model_var = tk.StringVar(value=saved_settings.get('model', 'gpt-4o-mini'))
    output_dir_var = tk.StringVar(value=saved_settings.get('output_directory', ''))

    def select_input_file():
        file_path = filedialog.askopenfilename(
            title="Select Transcript File",
            filetypes=[
                ("Text Files", "*.txt"),
                ("All Files", "*.*")
            ]
        )
        if file_path:
            state['input_file'] = file_path
            input_file_label.config(text=Path(file_path).name)
            # Set default output directory to input file's directory if not set
            if not output_dir_var.get():
                output_dir_var.set(str(Path(file_path).parent))
                output_label.config(text=str(Path(file_path).parent))
            generate_btn.config(state=tk.NORMAL)
            log_message(f"Selected: {file_path}")

    def select_output_dir():
        directory = filedialog.askdirectory(
            title="Select Output Directory",
            initialdir=output_dir_var.get() or os.getcwd()
        )
        if directory:
            output_dir_var.set(directory)
            output_label.config(text=directory)
            log_message(f"Output directory: {directory}")

    def log_message(msg):
        log_text.insert(tk.END, msg + "\n")
        log_text.see(tk.END)
        window.update_idletasks()

    def generate_minutes():
        if state['is_processing'] or not state['input_file']:
            return

        api_key = api_key_var.get().strip()
        if not api_key:
            messagebox.showerror("Error", "Please enter your OpenAI API key.")
            return

        state['is_processing'] = True
        generate_btn.config(state=tk.DISABLED)
        progress.start(10)
        log_message("Starting minutes generation...")

        def process_thread():
            try:
                # Read the transcript
                log_message("Reading transcript...")
                with open(state['input_file'], 'r', encoding='utf-8') as f:
                    transcript = f.read()

                log_message(f"Transcript length: {len(transcript)} characters")

                # Get the prompt
                prompt = prompt_text.get("1.0", tk.END).strip()

                # Call OpenAI API
                log_message(f"Calling {model_var.get()}...")
                client = OpenAI(api_key=api_key)

                response = client.chat.completions.create(
                    model=model_var.get(),
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": transcript}
                    ],
                    max_tokens=16384
                )

                minutes = response.choices[0].message.content.strip()
                log_message("Minutes generated successfully.")

                # Determine output path
                input_path = Path(state['input_file'])
                output_dir = output_dir_var.get() or str(input_path.parent)
                output_filename = f"{input_path.stem}-minutes{input_path.suffix}"
                output_path = Path(output_dir) / output_filename

                # Write output
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(minutes)

                log_message(f"Saved to: {output_path}")

                window.after(0, lambda: messagebox.showinfo(
                    "Success",
                    f"Minutes generated successfully!\n\nSaved to:\n{output_path}"
                ))

                # Open the file
                if os.name == 'nt':
                    os.startfile(str(output_path))
                elif os.name == 'posix':
                    os.system(f'open "{output_path}"')

            except Exception as e:
                error_msg = str(e)
                log_message(f"Error: {error_msg}")
                window.after(0, lambda msg=error_msg: messagebox.showerror("Error", msg))

            finally:
                window.after(0, lambda: progress.stop())
                window.after(0, lambda: generate_btn.config(state=tk.NORMAL if state['input_file'] else tk.DISABLED))
                state['is_processing'] = False

        thread = threading.Thread(target=process_thread)
        thread.daemon = True
        thread.start()

    def load_config():
        """Reload settings from file."""
        nonlocal saved_settings
        saved_settings = load_minutes_settings()
        api_key_var.set(saved_settings.get('api_key', ''))
        model_var.set(saved_settings.get('model', 'gpt-4o-mini'))
        output_dir_var.set(saved_settings.get('output_directory', ''))
        prompt_text.delete("1.0", tk.END)
        prompt_text.insert("1.0", saved_settings.get('prompt', default_prompt))
        if saved_settings.get('output_directory'):
            output_label.config(text=saved_settings.get('output_directory'))
        log_message("Configuration loaded from settings.json")

    # Build the UI
    main_frame = ttk.Frame(window, padding="10")
    main_frame.pack(fill="both", expand=True)

    # Header row with back button on left, config buttons on right
    header_frame = ttk.Frame(main_frame)
    header_frame.pack(fill="x", pady=(0, 10))

    back_btn = ttk.Button(header_frame, text="< Back to Menu", command=show_main_menu)
    back_btn.pack(side="left")

    save_config_btn = ttk.Button(header_frame, text="Save Config", command=save_minutes_settings)
    save_config_btn.pack(side="right", padx=(5, 0))

    load_config_btn = ttk.Button(header_frame, text="Load Config", command=load_config)
    load_config_btn.pack(side="right")

    # API Key section
    api_frame = ttk.LabelFrame(main_frame, text="OpenAI API Key", padding="10")
    api_frame.pack(fill="x", pady=(0, 10))

    api_key_entry = ttk.Entry(api_frame, textvariable=api_key_var, show="*", width=50)
    api_key_entry.pack(side="left", fill="x", expand=True)

    # Model selection
    model_frame = ttk.LabelFrame(main_frame, text="Model", padding="10")
    model_frame.pack(fill="x", pady=(0, 10))

    model_combo = ttk.Combobox(
        model_frame,
        textvariable=model_var,
        values=["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo", "o1-mini", "o1-preview"],
        state="readonly",
        width=20
    )
    model_combo.pack(side="left")

    ttk.Label(model_frame, text="  (gpt-4o-mini is fast and cheap, gpt-4o is more capable)").pack(side="left")

    # File selection section
    file_frame = ttk.LabelFrame(main_frame, text="Input / Output", padding="10")
    file_frame.pack(fill="x", pady=(0, 10))

    # Input file row
    input_row = ttk.Frame(file_frame)
    input_row.pack(fill="x", pady=(0, 5))

    ttk.Label(input_row, text="Input:").pack(side="left", padx=(0, 5))
    input_file_label = ttk.Label(input_row, text="No file selected", foreground="gray")
    input_file_label.pack(side="left", padx=(0, 10))
    ttk.Button(input_row, text="Select Transcript File", command=select_input_file).pack(side="left")

    # Output directory row
    output_row = ttk.Frame(file_frame)
    output_row.pack(fill="x")

    ttk.Label(output_row, text="Output:").pack(side="left", padx=(0, 5))
    output_label = ttk.Label(output_row, text=output_dir_var.get() or "Same as input file", foreground="blue")
    output_label.pack(side="left", padx=(0, 10))
    ttk.Button(output_row, text="Change Output Directory", command=select_output_dir).pack(side="left")

    # Prompt section
    prompt_frame = ttk.LabelFrame(main_frame, text="Prompt (customize how minutes are generated)", padding="10")
    prompt_frame.pack(fill="both", expand=True, pady=(0, 10))

    prompt_text = scrolledtext.ScrolledText(prompt_frame, height=8, wrap=tk.WORD)
    prompt_text.pack(fill="both", expand=True)
    prompt_text.insert("1.0", saved_settings.get('prompt', default_prompt))

    # Reset prompt button
    ttk.Button(prompt_frame, text="Reset Prompt to Default", command=lambda: (prompt_text.delete("1.0", tk.END), prompt_text.insert("1.0", default_prompt))).pack(anchor="w", pady=(10, 0))

    # Log section
    log_frame = ttk.LabelFrame(main_frame, text="Log", padding="10")
    log_frame.pack(fill="both", expand=True, pady=(0, 10))

    log_text = scrolledtext.ScrolledText(log_frame, height=6, wrap=tk.WORD, bg="white", fg="black")
    log_text.pack(fill="both", expand=True)

    # Progress bar
    progress = ttk.Progressbar(main_frame, mode='indeterminate')
    progress.pack(fill="x", pady=(0, 10))

    # Generate button
    generate_btn = tk.Button(
        main_frame,
        text="Generate Minutes",
        command=generate_minutes,
        state=tk.DISABLED,
        font=("Arial", 16),
        height=2,
        width=20
    )
    generate_btn.pack(pady=10)


def show_whisper_setup_screen():
    """Show a setup screen to install Whisper dependencies."""
    main_frame = ttk.Frame(window, padding="20")
    main_frame.pack(fill="both", expand=True)

    # Back button
    back_btn = ttk.Button(main_frame, text="< Back to Menu", command=show_main_menu)
    back_btn.pack(anchor="w", pady=(0, 20))

    # Title
    title_label = tk.Label(main_frame, text="Whisper Setup Required", font=("Arial", 18, "bold"))
    title_label.pack(pady=(0, 20))

    # Check FFmpeg status
    ffmpeg_ok = check_ffmpeg()

    # Status frame
    status_frame = ttk.LabelFrame(main_frame, text="Requirements", padding="15")
    status_frame.pack(fill="x", pady=(0, 20))

    # FFmpeg status
    ffmpeg_status = "Installed" if ffmpeg_ok else "NOT FOUND"
    ffmpeg_color = "green" if ffmpeg_ok else "red"
    ffmpeg_label = tk.Label(status_frame, text=f"FFmpeg: {ffmpeg_status}", fg=ffmpeg_color, font=("Arial", 11))
    ffmpeg_label.pack(anchor="w")

    if not ffmpeg_ok:
        if platform.system() == "Windows":
            ffmpeg_help = "Download from: https://ffmpeg.org/download.html\nOr use: winget install ffmpeg"
        elif platform.system() == "Darwin":
            ffmpeg_help = "Install with: brew install ffmpeg"
        else:
            ffmpeg_help = "Install with: sudo apt install ffmpeg"
        ffmpeg_help_label = tk.Label(status_frame, text=ffmpeg_help, fg="gray", justify="left")
        ffmpeg_help_label.pack(anchor="w", padx=(20, 0))

    # Whisper status
    whisper_label = tk.Label(status_frame, text="Whisper: NOT INSTALLED", fg="red", font=("Arial", 11))
    whisper_label.pack(anchor="w", pady=(10, 0))

    # Info text
    info_text = tk.Label(
        main_frame,
        text="Click the button below to automatically install Whisper and its dependencies.\nThis will download PyTorch and OpenAI Whisper (may take a few minutes).",
        justify="center"
    )
    info_text.pack(pady=(0, 20))

    # Log area
    log_frame = ttk.LabelFrame(main_frame, text="Installation Log", padding="10")
    log_frame.pack(fill="both", expand=True, pady=(0, 20))

    log_text = scrolledtext.ScrolledText(log_frame, height=10, wrap=tk.WORD, bg="white", fg="black")
    log_text.pack(fill="both", expand=True)

    # Progress bar
    progress = ttk.Progressbar(main_frame, mode='indeterminate')
    progress.pack(fill="x", pady=(0, 10))

    def log_message(msg):
        log_text.insert(tk.END, msg + "\n")
        log_text.see(tk.END)
        window.update_idletasks()

    def run_installation():
        install_btn.config(state=tk.DISABLED)
        progress.start(10)
        log_message("Starting installation...")

        def install_thread():
            global WHISPER_AVAILABLE
            success = install_whisper_dependencies(progress_callback=log_message)

            if success:
                log_message("\nInstallation complete!")
                log_message("Please restart the application to use Whisper transcription.")

                # Try to import whisper now
                try:
                    import importlib
                    import whisper as whisper_module
                    importlib.reload(whisper_module)
                    WHISPER_AVAILABLE = True
                    window.after(0, lambda: messagebox.showinfo(
                        "Installation Complete",
                        "Whisper has been installed successfully!\n\nPlease restart the application to use the transcription feature."
                    ))
                except:
                    window.after(0, lambda: messagebox.showinfo(
                        "Installation Complete",
                        "Dependencies installed!\n\nPlease restart the application to use the transcription feature."
                    ))
            else:
                log_message("\nInstallation failed. Please check the log for errors.")
                window.after(0, lambda: messagebox.showerror(
                    "Installation Failed",
                    "Failed to install some dependencies.\nPlease check the log for details."
                ))

            window.after(0, lambda: progress.stop())
            window.after(0, lambda: install_btn.config(state=tk.NORMAL))

        thread = threading.Thread(target=install_thread)
        thread.daemon = True
        thread.start()

    # Install button
    install_btn = tk.Button(
        main_frame,
        text="Install Whisper Dependencies",
        command=run_installation,
        font=("Arial", 14),
        height=2,
        width=25,
        state=tk.NORMAL if ffmpeg_ok else tk.DISABLED
    )
    install_btn.pack(pady=10)

    if not ffmpeg_ok:
        warning_label = tk.Label(
            main_frame,
            text="Please install FFmpeg first before installing Whisper.",
            fg="red"
        )
        warning_label.pack()


def create_transcription_gui():
    """Create the audio transcription interface."""
    global WHISPER_AVAILABLE

    clear_window()
    window.title("Transcribe Audio (Whisper)")

    # Check if whisper needs to be installed
    if not WHISPER_AVAILABLE:
        show_whisper_setup_screen()
        return

    # State variables for this screen
    transcription_state = {
        'audio_files': [],
        'speaker_entries': {},
        'is_transcribing': False,
        'message_queue': queue.Queue(),
        'output_directory': None
    }

    model_size = tk.StringVar(value="base")

    def select_audio_files():
        files = filedialog.askopenfilenames(
            title="Select Audio Files",
            filetypes=[
                ("Audio Files", "*.wav *.mp3 *.flac *.m4a *.ogg"),
                ("All Files", "*.*")
            ]
        )
        if files:
            transcription_state['audio_files'] = list(files)
            update_file_list()
            transcribe_btn.config(state=tk.NORMAL)
            log_message(f"Selected {len(files)} file(s)")

    def update_file_list():
        for widget in file_frame_inner.winfo_children():
            widget.destroy()

        transcription_state['speaker_entries'] = {}

        for i, file_path in enumerate(transcription_state['audio_files']):
            name = Path(file_path).stem

            row_frame = ttk.Frame(file_frame_inner)
            row_frame.pack(fill="x", pady=2)

            ttk.Label(row_frame, text=f"{i+1}.").pack(side="left", padx=(0, 5))
            ttk.Label(row_frame, text=Path(file_path).name, width=40).pack(side="left", padx=(0, 10))

            ttk.Label(row_frame, text="Speaker:").pack(side="left", padx=(0, 5))
            var = tk.StringVar(value=name)
            entry = ttk.Entry(row_frame, textvariable=var, width=30)
            entry.pack(side="left")

            transcription_state['speaker_entries'][file_path] = var

    def clear_files():
        transcription_state['audio_files'] = []
        update_file_list()
        transcribe_btn.config(state=tk.DISABLED)
        log_message("Cleared file selection")

    def select_output_dir():
        directory = filedialog.askdirectory(
            title="Select Output Directory",
            initialdir=transcription_state['output_directory'] or os.getcwd()
        )
        if directory:
            transcription_state['output_directory'] = directory
            display_path = directory
            if len(display_path) > 50:
                display_path = "..." + display_path[-47:]
            output_label.config(text=display_path, foreground="green")
            log_message(f"Output directory set to: {directory}")

    def reset_output_dir():
        transcription_state['output_directory'] = None
        output_label.config(text="Same as input files", foreground="blue")
        log_message("Output will be saved in input file directory")

    def log_message(message):
        log_text.insert(tk.END, message + "\n")
        log_text.see(tk.END)

    def format_time(seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"[{h:02d}:{m:02d}:{s:02d}]"

    def format_srt_time(seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    def save_transcripts(segments):
        if transcription_state['output_directory']:
            output_dir = transcription_state['output_directory']
        else:
            output_dir = str(Path(transcription_state['audio_files'][0]).parent)

        text_path = os.path.join(output_dir, "merged_transcript.txt")
        srt_path = os.path.join(output_dir, "merged_transcript.srt")

        with open(text_path, "w", encoding="utf-8") as f:
            for seg in segments:
                time = format_time(seg.start)
                f.write(f"{time} {seg.speaker}: {seg.text}\n")

        with open(srt_path, "w", encoding="utf-8") as f:
            for i, seg in enumerate(segments, 1):
                f.write(f"{i}\n")
                f.write(f"{format_srt_time(seg.start)} --> {format_srt_time(seg.end)}\n")
                f.write(f"{seg.speaker}: {seg.text}\n\n")

        return output_dir, text_path, srt_path

    def run_transcription():
        try:
            transcription_state['message_queue'].put(("log", f"Loading {model_size.get()} model..."))

            transcriber = SimpleTranscriber(model_size.get())

            all_segments = []

            for i, file_path in enumerate(transcription_state['audio_files']):
                speaker = transcription_state['speaker_entries'][file_path].get()
                transcription_state['message_queue'].put(("log", f"Processing file {i+1}/{len(transcription_state['audio_files'])}: {speaker}"))

                segments = transcriber.transcribe_file(
                    file_path,
                    speaker,
                    progress_callback=lambda msg: transcription_state['message_queue'].put(("log", f"  {msg}"))
                )

                all_segments.extend(segments)

            all_segments.sort(key=lambda s: s.start)

            output_dir, text_path, srt_path = save_transcripts(all_segments)

            transcription_state['message_queue'].put(("log", f"Saved files to: {output_dir}"))
            transcription_state['message_queue'].put(("log", "  - merged_transcript.txt"))
            transcription_state['message_queue'].put(("log", "  - merged_transcript.srt"))
            transcription_state['message_queue'].put(("complete", "Transcription completed successfully!"))

        except Exception as e:
            transcription_state['message_queue'].put(("error", str(e)))

        finally:
            transcription_state['message_queue'].put(("finished", None))

    def start_transcription():
        if transcription_state['is_transcribing'] or not transcription_state['audio_files']:
            return

        transcription_state['is_transcribing'] = True
        transcribe_btn.config(state=tk.DISABLED)
        status_label.config(text="Transcribing...")
        progress.start(10)

        thread = threading.Thread(target=run_transcription)
        thread.daemon = True
        thread.start()

    def process_queue():
        try:
            while True:
                msg_type, msg_data = transcription_state['message_queue'].get_nowait()

                if msg_type == "log":
                    log_message(msg_data)
                elif msg_type == "complete":
                    log_message(msg_data)
                    messagebox.showinfo("Success", msg_data)
                elif msg_type == "error":
                    log_message(f"ERROR: {msg_data}")
                    messagebox.showerror("Error", msg_data)
                elif msg_type == "finished":
                    transcription_state['is_transcribing'] = False
                    transcribe_btn.config(state=tk.NORMAL if transcription_state['audio_files'] else tk.DISABLED)
                    status_label.config(text="Ready")
                    progress.stop()

        except queue.Empty:
            pass

        window.after(100, process_queue)

    # Build the UI
    main_frame = ttk.Frame(window, padding="10")
    main_frame.pack(fill="both", expand=True)

    # Back button
    back_btn = ttk.Button(main_frame, text="< Back to Menu", command=show_main_menu)
    back_btn.pack(anchor="w", pady=(0, 10))

    # Top section - Settings
    top_frame = ttk.LabelFrame(main_frame, text="Settings", padding="10")
    top_frame.pack(fill="x", pady=(0, 10))

    settings_row = ttk.Frame(top_frame)
    settings_row.pack(fill="x")

    ttk.Label(settings_row, text="Model:").pack(side="left", padx=(0, 5))
    model_combo = ttk.Combobox(
        settings_row,
        textvariable=model_size,
        values=["tiny", "base", "small", "medium", "large"],
        state="readonly",
        width=10
    )
    model_combo.pack(side="left", padx=(0, 20))

    ttk.Button(settings_row, text="Select Files", command=select_audio_files).pack(side="left", padx=2)
    ttk.Button(settings_row, text="Clear Files", command=clear_files).pack(side="left", padx=2)

    # Output directory row
    output_row = ttk.Frame(top_frame)
    output_row.pack(fill="x", pady=(10, 0))

    ttk.Label(output_row, text="Output:").pack(side="left", padx=(0, 5))
    output_label = ttk.Label(output_row, text="Same as input files", foreground="blue")
    output_label.pack(side="left", padx=(0, 10))
    ttk.Button(output_row, text="Change Output Directory", command=select_output_dir).pack(side="left")
    ttk.Button(output_row, text="Reset to Input Dir", command=reset_output_dir).pack(side="left", padx=(5, 0))

    # File list section
    list_frame = ttk.LabelFrame(main_frame, text="Audio Files", padding="10")
    list_frame.pack(fill="both", expand=True, pady=(0, 10))

    canvas = tk.Canvas(list_frame, height=150)
    scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
    file_frame_inner = ttk.Frame(canvas)

    file_frame_inner.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.create_window((0, 0), window=file_frame_inner, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # Log section
    log_frame = ttk.LabelFrame(main_frame, text="Progress Log", padding="10")
    log_frame.pack(fill="both", expand=True)

    log_text = scrolledtext.ScrolledText(
        log_frame,
        height=10,
        wrap=tk.WORD,
        bg="white",
        fg="black"
    )
    log_text.pack(fill="both", expand=True)

    # Progress bar
    progress = ttk.Progressbar(main_frame, mode='indeterminate')
    progress.pack(fill="x", pady=(10, 0))

    # Status label
    status_label = ttk.Label(main_frame, text="")
    status_label.pack(pady=(5, 0))

    # Start Transcription button at bottom
    transcribe_btn = tk.Button(
        main_frame,
        text="Start Transcription",
        command=start_transcription,
        state=tk.DISABLED,
        font=("Arial", 16),
        height=2,
        width=20
    )
    transcribe_btn.pack(pady=20)

    # Start processing queue
    process_queue()


def create_transcript_processor_gui():
    """Create the transcript processor interface."""
    clear_window()

    global find_replace_container, find_replace_entries, api_key_entry, host_list_label, remove_host_var, remove_host_menu, api_key_status_label

    window.title("Post-process Podcast Transcript")

    window.grid_rowconfigure(0, weight=1)
    window.grid_columnconfigure(0, weight=1)

    content_frame = tk.Frame(window)
    content_frame.grid(sticky="nsew", padx=10, pady=10)

    content_frame.grid_columnconfigure(0, weight=1)

    find_replace_entries = []

    # Back button
    back_button = tk.Button(content_frame, text="< Back to Menu", command=show_main_menu)
    back_button.grid(row=0, column=0, sticky="w", pady=(0, 10))

    # Group: File Selection
    file_frame = tk.LabelFrame(content_frame, text="File Selection", padx=10, pady=10)
    file_frame.grid(row=1, column=0, sticky="ew")

    file_frame.grid_columnconfigure(0, weight=1)

    label = tk.Label(file_frame, text="Select text files to process:")
    label.grid(row=0, column=0, sticky="w")

    select_button = tk.Button(file_frame, text="Select Files", command=select_files)
    select_button.grid(row=1, column=0, pady=5)

    global file_label
    file_label = tk.Label(file_frame, text="No files loaded")
    file_label.grid(row=2, column=0, sticky="w")

    ToolTip(file_frame, "Use this section to load the transcript files you want to process in bulk.")

    # Group: API Key
    api_key_frame = tk.LabelFrame(content_frame, text="API Key", padx=10, pady=10)
    api_key_frame.grid(row=2, column=0, sticky="ew")

    api_key_frame.grid_columnconfigure(0, weight=1)

    api_key_label = tk.Label(api_key_frame, text="Enter your OpenAI API Key:")
    api_key_label.grid(row=0, column=0, sticky="w")

    global api_key_entry
    api_key_entry = tk.Entry(api_key_frame, show="*")
    api_key_entry.grid(row=1, column=0, sticky="ew", pady=5)

    set_api_key_button = tk.Button(api_key_frame, text="Set API Key", command=lambda: set_api_key(api_key_entry.get().strip()))
    set_api_key_button.grid(row=2, column=0, pady=5)

    api_key_status_label = tk.Label(api_key_frame, text="")
    api_key_status_label.grid(row=3, column=0, sticky="w")

    ToolTip(api_key_frame, "Enter and set your OpenAI API key to enable processing with the GPT-4o-mini model.")

    # Group: Hosts
    host_frame = tk.LabelFrame(content_frame, text="Hosts", padx=10, pady=10)
    host_frame.grid(row=3, column=0, sticky="ew")

    host_frame.grid_columnconfigure(0, weight=1)

    host_list_label = tk.Label(host_frame, text="Hosts: " + ", ".join(hosts))
    host_list_label.grid(row=0, column=0, sticky="w")

    host_entry_frame = tk.Frame(host_frame)
    host_entry_frame.grid(row=1, column=0, sticky="ew", pady=5)

    global host_entry
    host_entry = tk.Entry(host_entry_frame)
    host_entry.grid(row=0, column=0, sticky="ew")

    host_entry_frame.grid_columnconfigure(0, weight=1)

    add_host_button = tk.Button(host_entry_frame, text="Add Host", command=add_host)
    add_host_button.grid(row=0, column=1, padx=5)

    remove_host_frame = tk.Frame(host_frame)
    remove_host_frame.grid(row=2, column=0, sticky="ew", pady=5)

    remove_host_frame.grid_columnconfigure(0, weight=1)

    remove_host_var = tk.StringVar(host_frame)
    remove_host_var.set(hosts[0] if hosts else '')  # Set the first host as default or empty if no hosts
    remove_host_menu = tk.OptionMenu(remove_host_frame, remove_host_var, *(hosts if hosts else [""]))
    remove_host_menu.grid(row=0, column=0, sticky="ew")

    remove_host_button = tk.Button(remove_host_frame, text="Remove Host", command=remove_host)
    remove_host_button.grid(row=0, column=1, padx=5)

    ToolTip(host_frame, "Manage the list of hosts in the transcript, adding or removing as needed.")

    # Group: Find/Replace
    find_replace_container = tk.LabelFrame(content_frame, text="Find and Replace", padx=10, pady=10)
    find_replace_container.grid(row=4, column=0, sticky="ew")

    find_replace_container.grid_columnconfigure(0, weight=1)

    add_find_replace_button = tk.Button(find_replace_container, text="Add Find/Replace", command=add_find_replace)
    add_find_replace_button.grid(row=0, column=0, pady=5)

    ToolTip(find_replace_container, "Add find/replace pairs to process specific words or phrases in the transcript.")

    # Group: Actions
    actions_frame = tk.Frame(content_frame, padx=10, pady=10)
    actions_frame.grid(row=5, column=0, sticky="ew")

    actions_frame.grid_columnconfigure(0, weight=1)

    save_settings_button = tk.Button(actions_frame, text="Save Settings", command=save_settings)
    save_settings_button.grid(row=0, column=0, padx=5, sticky="w")

    load_json_button = tk.Button(actions_frame, text="Load from JSON", command=reload_settings)
    load_json_button.grid(row=0, column=1, padx=5, sticky="w")

    global status_label
    status_label = tk.Label(actions_frame, text="")
    status_label.grid(row=1, column=0, padx=5, sticky="w", columnspan=2)

    global start_button
    start_button = tk.Button(content_frame, text="Start", command=process_transcripts, state=tk.DISABLED, font=("Arial", 16), height=2, width=20)
    start_button.grid(row=6, column=0, pady=20)

    ToolTip(actions_frame, "Save your settings or reload them from a JSON file. Start processing when ready.")

    # Load settings after defining necessary widgets
    load_settings()

def create_main_window():
    """Create the main application window and show the menu."""
    global window
    window = tk.Tk()
    window.minsize(400, 300)  # Set minimum window size
    show_main_menu()
    window.mainloop()

# Start the application
create_main_window()

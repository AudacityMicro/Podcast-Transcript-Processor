import re
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import openai
import threading
import json
from tkinter import ttk

# Configurable Hosts List
hosts = ['AJ', 'Harrison']  # Default hosts, more can be added through the GUI

# Path to the JSON file for storing settings
settings_file = 'transcript_processor_settings.json'

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

def generate_summary(text, summary_type="short"):
    prompt = "Summarize the following transcript."
    if summary_type == "detailed":
        prompt = "Provide a detailed five-paragraph summary of the following transcript."
    elif summary_type == "short":
        prompt = "Summarize the following transcript in three sentences."

    # Flip the max tokens for detailed and standard summaries
    max_tokens = 10000 if summary_type == "detailed" else 16384

    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": text}
        ],
        max_tokens=max_tokens
    )
    summary = response.choices[0].message['content'].strip()
    return summary

def process_transcript(file_path):
    status_label.config(text="Processing... Please wait.", fg="red")
    start_button.config(state=tk.DISABLED)  # Disable the start button
    window.update_idletasks()

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
        transcript = transcript.replace(host, formatted_host)

    # Step 4: Move <br> before each instance of the formatted host names
    for host in hosts:
        formatted_host = f"'''{host}''':   "
        transcript = re.sub(rf"\n<br>{re.escape(formatted_host)}", f"<br>\n{formatted_host}", transcript)

    # Step 5: Speaker Formatting
    speaker_pattern = re.compile(r"(" + "|".join(re.escape(host) for host in hosts) + r"):\n\s*(.+)", re.DOTALL)

    def format_speaker(match):
        speaker = match.group(1)
        dialogue = match.group(2).replace('\n', ' ').strip()
        return f"'''{speaker}''':   {dialogue}"

    transcript = re.sub(speaker_pattern, format_speaker, transcript)

    # Add <br> at the beginning of every line
    lines = transcript.split('\n')
    formatted_lines = []
    for line in lines:
        if line.strip():  # Ignore lines that only contain whitespace
            formatted_lines.append(f"<br>{line}")

    transcript = '\n'.join(formatted_lines)

    # Step 6: Remove any lingering <br> after host names
    for host in hosts:
        formatted_host = f"'''{host}''':   "
        transcript = re.sub(rf"({re.escape(formatted_host)})\n<br>", r"\1", transcript)

    # Step 7: Generate summaries using ChatGPT API
    short_summary = generate_summary(transcript, summary_type="short")
    detailed_summary = generate_summary(transcript, summary_type="detailed")
    
    # Step 8: Wikimedia Page Preparation with summaries
    transcript = (f"=TLDR=\n\n{short_summary}\n\n"
                  f"=Links=\n\n"
                  f"=Summary=\n\n{detailed_summary}\n\n"
                  f"=Transcript=\n\n" + transcript)

    # Output the processed transcript
    output_file_path = file_path.replace('.txt', '_processed.txt')
    with open(output_file_path, 'w', encoding='utf-8') as file:
        file.write(transcript)

    status_label.config(text="Processing complete. File saved.", fg="green")
    window.update_idletasks()

    messagebox.showinfo("Success", f"Processed transcript saved to {output_file_path}")
    start_button.config(state=tk.NORMAL)  # Re-enable the start button

    # Step 9: Open the processed file in the default text editor
    os.startfile(output_file_path)

def select_file():
    file_path = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
    if file_path:
        file_label.config(text=f"File loaded: {file_path}")
        start_button.config(state=tk.NORMAL)
        start_button.file_path = file_path

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

def set_api_key():
    api_key = api_key_entry.get().strip()
    if api_key:
        openai.api_key = api_key
        api_key_status_label.config(text="API Key Set", fg="green")
        window.update_idletasks()
        messagebox.showinfo("API Key Set", "Your OpenAI API key has been set.")

def add_find_replace():
    find_replace_frame = tk.Frame(find_replace_container)
    find_replace_frame.pack(fill="x", pady=5)

    find_label = tk.Label(find_replace_frame, text="Find:")
    find_label.pack(side=tk.LEFT, padx=5)
    find_entry = tk.Entry(find_replace_frame)
    find_entry.pack(side=tk.LEFT, padx=5)

    replace_label = tk.Label(find_replace_frame, text="Replace with:")
    replace_label.pack(side=tk.LEFT, padx=5)
    replace_entry = tk.Entry(find_replace_frame)
    replace_entry.pack(side=tk.LEFT, padx=5)

    remove_button = tk.Button(find_replace_frame, text="Remove", command=lambda: remove_find_replace(find_replace_frame))
    remove_button.pack(side=tk.LEFT, padx=5)

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
            api_key_entry.delete(0, tk.END)
            api_key_entry.insert(0, settings.get("api_key", ""))

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

def start_processing():
    status_label.config(text="Starting processing...", fg="blue")
    window.update_idletasks()
    threading.Thread(target=process_transcript_thread).start()

def process_transcript_thread():
    file_path = start_button.file_path
    if file_path:
        process_transcript(file_path)

def create_gui():
    global window, find_replace_container, find_replace_entries, api_key_entry, host_list_label, remove_host_var, remove_host_menu
    window = tk.Tk()
    window.title("Transcript Processor")
    window.geometry("800x700")  # Set the initial window size

    # Create a scrollbar and canvas for the main content
    main_frame = tk.Frame(window)
    main_frame.pack(fill="both", expand=True)

    canvas = tk.Canvas(main_frame)
    canvas.pack(side="left", fill="both", expand=True)

    scrollbar = tk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
    scrollbar.pack(side="right", fill="y")

    scrollable_frame = tk.Frame(canvas)
    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    find_replace_entries = []

    # Group: File Selection
    file_frame = tk.LabelFrame(scrollable_frame, text="File Selection", padx=10, pady=10)
    file_frame.pack(padx=10, pady=10, fill="x")

    label = tk.Label(file_frame, text="Select a text file to process:")
    label.pack(anchor="w")

    select_button = tk.Button(file_frame, text="Select File", command=select_file)
    select_button.pack(pady=5)

    global file_label
    file_label = tk.Label(file_frame, text="No file loaded")
    file_label.pack(anchor="w")

    ToolTip(file_frame, "Use this section to load the transcript file you want to process.")

    # Group: API Key
    api_key_frame = tk.LabelFrame(scrollable_frame, text="API Key", padx=10, pady=10)
    api_key_frame.pack(padx=10, pady=10, fill="x")

    api_key_label = tk.Label(api_key_frame, text="Enter your OpenAI API Key:")
    api_key_label.pack(anchor="w")

    global api_key_entry
    api_key_entry = tk.Entry(api_key_frame, show="*")
    api_key_entry.pack(fill="x")

    set_api_key_button = tk.Button(api_key_frame, text="Set API Key", command=set_api_key)
    set_api_key_button.pack(pady=5)

    global api_key_status_label
    api_key_status_label = tk.Label(api_key_frame, text="")
    api_key_status_label.pack(anchor="w")

    ToolTip(api_key_frame, "Enter and set your OpenAI API key to enable processing with the GPT-4o-mini model.")

    # Group: Hosts
    host_frame = tk.LabelFrame(scrollable_frame, text="Hosts", padx=10, pady=10)
    host_frame.pack(padx=10, pady=10, fill="x")

    host_list_label = tk.Label(host_frame, text="Hosts: " + ", ".join(hosts))
    host_list_label.pack(anchor="w")

    host_entry_frame = tk.Frame(host_frame)
    host_entry_frame.pack(fill="x", pady=5)

    global host_entry
    host_entry = tk.Entry(host_entry_frame)
    host_entry.pack(side=tk.LEFT, fill="x", expand=True)

    add_host_button = tk.Button(host_entry_frame, text="Add Host", command=add_host)
    add_host_button.pack(side=tk.LEFT, padx=5)

    remove_host_frame = tk.Frame(host_frame)
    remove_host_frame.pack(fill="x", pady=5)

    remove_host_var = tk.StringVar(host_frame)
    remove_host_var.set(hosts[0])  # Default value

    remove_host_menu = tk.OptionMenu(remove_host_frame, remove_host_var, *hosts)
    remove_host_menu.pack(side=tk.LEFT, fill="x", expand=True)

    remove_host_button = tk.Button(remove_host_frame, text="Remove Host", command=remove_host)
    remove_host_button.pack(side=tk.LEFT, padx=5)

    ToolTip(host_frame, "Manage the list of hosts in the transcript, adding or removing as needed.")

    # Group: Find/Replace
    find_replace_container = tk.LabelFrame(scrollable_frame, text="Find and Replace", padx=10, pady=10)
    find_replace_container.pack(padx=10, pady=10, fill="x")

    add_find_replace_button = tk.Button(find_replace_container, text="Add Find/Replace", command=add_find_replace)
    add_find_replace_button.pack(pady=5)

    ToolTip(find_replace_container, "Add find/replace pairs to process specific words or phrases in the transcript.")

    # Group: Actions
    actions_frame = tk.Frame(scrollable_frame, padx=10, pady=10)
    actions_frame.pack(padx=10, pady=10, fill="x")

    save_settings_button = tk.Button(actions_frame, text="Save Settings", command=save_settings)
    save_settings_button.pack(side=tk.LEFT, padx=5)

    load_json_button = tk.Button(actions_frame, text="Load from JSON", command=reload_settings)
    load_json_button.pack(side=tk.LEFT, padx=5)

    global status_label
    status_label = tk.Label(actions_frame, text="")
    status_label.pack(side=tk.LEFT, padx=5)

    global start_button
    start_button = tk.Button(scrollable_frame, text="Start", command=start_processing, state=tk.DISABLED, font=("Arial", 16), height=2, width=20)
    start_button.pack(pady=20)

    ToolTip(actions_frame, "Save your settings or reload them from a JSON file. Start processing when ready.")

    # Load settings after defining necessary widgets
    load_settings()

    # Run the GUI loop
    window.mainloop()

# Start the GUI
create_gui()

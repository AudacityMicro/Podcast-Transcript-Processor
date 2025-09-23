import re
import tkinter as tk
from tkinter import filedialog, messagebox
import os
from openai import OpenAI
import json
from tkinter import ttk

# Configurable Hosts List
hosts = []  # No hard-coded hosts, more can be added through the GUI

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

def create_gui():
    global window, find_replace_container, find_replace_entries, api_key_entry, host_list_label, remove_host_var, remove_host_menu, api_key_status_label
    window = tk.Tk()
    window.title("Transcript Processor")
    window.geometry("800x700")  # Set the initial window size

    window.grid_rowconfigure(0, weight=1)
    window.grid_columnconfigure(0, weight=1)

    content_frame = tk.Frame(window)
    content_frame.grid(sticky="nsew", padx=10, pady=10)
    
    content_frame.grid_columnconfigure(0, weight=1)

    find_replace_entries = []

    # Group: File Selection
    file_frame = tk.LabelFrame(content_frame, text="File Selection", padx=10, pady=10)
    file_frame.grid(row=0, column=0, sticky="ew")

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
    api_key_frame.grid(row=1, column=0, sticky="ew")

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
    host_frame.grid(row=2, column=0, sticky="ew")

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
    find_replace_container.grid(row=3, column=0, sticky="ew")

    find_replace_container.grid_columnconfigure(0, weight=1)

    add_find_replace_button = tk.Button(find_replace_container, text="Add Find/Replace", command=add_find_replace)
    add_find_replace_button.grid(row=0, column=0, pady=5)

    ToolTip(find_replace_container, "Add find/replace pairs to process specific words or phrases in the transcript.")

    # Group: Actions
    actions_frame = tk.Frame(content_frame, padx=10, pady=10)
    actions_frame.grid(row=4, column=0, sticky="ew")

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
    start_button.grid(row=5, column=0, pady=20)

    ToolTip(actions_frame, "Save your settings or reload them from a JSON file. Start processing when ready.")

    # Load settings after defining necessary widgets
    load_settings()

    # Run the GUI loop
    window.mainloop()

# Start the GUI
create_gui()

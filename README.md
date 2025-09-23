# Podcast Transcript Processor

A powerful GUI application for processing and formatting podcast transcripts, with automatic summarization using OpenAI's GPT-4o-mini model. This tool streamlines the workflow of converting raw transcripts into wiki-ready formatted text with AI-generated summaries.

## Features

- **Batch Processing**: Process multiple transcript files simultaneously
- **AI-Powered Summaries**: Automatically generates both short (3-sentence) and detailed (5-paragraph) summaries using OpenAI's GPT-4o-mini
- **Smart Formatting**:
  - Removes timestamps from transcripts
  - Formats host names with wiki-style markup
  - Applies custom find/replace rules
  - Prepares output for wiki platforms
- **Customizable Settings**:
  - Add/remove podcast hosts dynamically
  - Create custom find/replace rules for consistent formatting
  - Save and load settings from JSON configuration files
- **User-Friendly GUI**: Built with Tkinter for easy interaction
- **Cross-Platform**: Works on macOS, Windows, and Linux

## Output Format

The processed transcript includes:

- **TLDR Section**: A concise 3-sentence summary
- **Links Section**: Placeholder for relevant links
- **Summary Section**: A detailed 5-paragraph analysis
- **Transcript Section**: The formatted conversation with host names highlighted

## Requirements

- Python 3.12+ (required for macOS compatibility)
- OpenAI API key for summary generation

## Installation

### Quick Start

1. Clone the repository:

```bash
git clone https://github.com/yourusername/Podcast-Transcript-Processor.git
cd Podcast-Transcript-Processor
```

2. Run the launcher (automatically handles virtual environment):

```bash
python main.py
```

The launcher will automatically:

- Create a virtual environment if it doesn't exist
- Install all required dependencies
- Launch the application

### Manual Installation

If you prefer to set up manually:

1. Create a virtual environment:

```bash
python3.12 -m venv venv
```

2. Activate the virtual environment:

```bash
# On macOS/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Run the application:

```bash
python "TranscriptEditor-No Key.py"
```

## Usage

### Getting Started

1. **Launch the Application**: Run `python main.py` from the project directory

2. **Set Your API Key**:

   - Enter your OpenAI API key in the API Key field
   - Click "Set API Key" to confirm

3. **Configure Hosts**:

   - Add podcast host names that appear in your transcripts
   - These will be formatted with wiki-style markup in the output

4. **Add Find/Replace Rules** (Optional):

   - Click "Add Find/Replace" to create custom text replacements
   - Useful for fixing common transcription errors or standardizing terms

5. **Select Files**:

   - Click "Select Files" to choose one or more transcript files (.txt format)
   - The application supports batch processing

6. **Process Transcripts**:
   - Click "Start" to begin processing
   - Processed files will be saved with "\_processed" suffix
   - Files automatically open in your default text editor when complete

### Settings Management

- **Save Settings**: Save your current configuration (API key, hosts, find/replace rules) to a JSON file
- **Load from JSON**: Restore previously saved settings
- Settings are stored in `transcript_processor_settings.json`

### Input File Format

The application expects plain text transcript files with optional timestamps. Example:

```
00:12:34 John: Welcome to our podcast...
00:12:45 Jane: Thanks for having me...
```

### Output Example

```
=TLDR=

[AI-generated 3-sentence summary]

=Links=

=Summary=

[AI-generated detailed 5-paragraph summary]

=Transcript=

<br>'''John''':   Welcome to our podcast...
<br>'''Jane''':   Thanks for having me...
```

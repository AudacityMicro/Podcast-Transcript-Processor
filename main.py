#!/usr/bin/env python3
"""
Podcast Transcript Processor Launcher

This script automatically manages the virtual environment and launches the main application.
It ensures all dependencies are installed and uses the correct Python version.
"""

import os
import sys
import subprocess
import platform

def check_python_version():
    """Check if Python version is 3.12 or higher."""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 12):
        print(f"Error: Python 3.12 or higher is required. You have Python {version.major}.{version.minor}")
        print("Please install Python 3.12+ and try again.")

        if platform.system() == "Darwin":  # macOS
            print("\nOn macOS, you can install Python 3.12 using Homebrew:")
            print("  brew install python@3.12")

        sys.exit(1)

def find_python_312():
    """Find Python 3.12+ executable on the system."""
    # Try different common Python executable names
    python_commands = [
        "python3.12",
        "python3.13",
        "/opt/homebrew/bin/python3.12",
        "/opt/homebrew/bin/python3.13",
        "/usr/local/bin/python3.12",
        "/usr/local/bin/python3.13",
        "python3",
        "python"
    ]

    for cmd in python_commands:
        try:
            result = subprocess.run(
                [cmd, "--version"],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                # Extract version from output like "Python 3.12.0"
                version_str = result.stdout.strip().split()[1]
                major, minor = map(int, version_str.split('.')[:2])
                if major == 3 and minor >= 12:
                    return cmd
        except (FileNotFoundError, ValueError):
            continue

    return None

def setup_venv():
    """Create virtual environment if it doesn't exist."""
    venv_path = os.path.join(os.path.dirname(__file__), "venv")

    if not os.path.exists(venv_path):
        print("Creating virtual environment...")

        # Find appropriate Python 3.12+ executable
        python_cmd = find_python_312()
        if not python_cmd:
            print("Error: Could not find Python 3.12 or higher on your system.")
            print("\nPlease install Python 3.12+ and try again.")
            if platform.system() == "Darwin":
                print("\nOn macOS, you can install it using Homebrew:")
                print("  brew install python@3.12")
            sys.exit(1)

        subprocess.run([python_cmd, "-m", "venv", "venv"], check=True)
        print("Virtual environment created.")

        # Install dependencies
        print("Installing dependencies...")
        if platform.system() == "Windows":
            pip_path = os.path.join(venv_path, "Scripts", "pip")
        else:
            pip_path = os.path.join(venv_path, "bin", "pip")

        subprocess.run([pip_path, "install", "--upgrade", "pip"], check=True)

        requirements_file = os.path.join(os.path.dirname(__file__), "requirements.txt")
        if os.path.exists(requirements_file):
            subprocess.run([pip_path, "install", "-r", requirements_file], check=True)
            print("Dependencies installed.")
        else:
            # Install openai directly if requirements.txt doesn't exist
            subprocess.run([pip_path, "install", "openai"], check=True)
            print("OpenAI package installed.")

    return venv_path

def run_app():
    """Run the main application using the virtual environment."""
    venv_path = setup_venv()

    # Determine the Python executable path in the venv
    if platform.system() == "Windows":
        python_path = os.path.join(venv_path, "Scripts", "python.exe")
    else:
        python_path = os.path.join(venv_path, "bin", "python")

    # Path to the main script
    script_path = os.path.join(os.path.dirname(__file__), "TranscriptEditor-No Key.py")

    if not os.path.exists(script_path):
        print(f"Error: Main script not found at {script_path}")
        sys.exit(1)

    print("Launching Podcast Transcript Processor...")
    print("-" * 50)

    # Run the main application
    try:
        subprocess.run([python_path, script_path], check=True)
    except subprocess.CalledProcessError as e:
        print(f"\nError running application: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nApplication closed by user.")
        sys.exit(0)

def main():
    """Main entry point."""
    print("Podcast Transcript Processor Launcher")
    print("=" * 50)

    # Change to script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # Check if running with appropriate Python version
    if sys.version_info >= (3, 12):
        # Current Python is good, proceed
        run_app()
    else:
        # Try to find and use Python 3.12+
        python_312 = find_python_312()
        if python_312:
            print(f"Switching to {python_312}...")
            # Re-run this script with the correct Python version
            subprocess.run([python_312, __file__] + sys.argv[1:])
        else:
            check_python_version()  # This will show error and exit

if __name__ == "__main__":
    main()
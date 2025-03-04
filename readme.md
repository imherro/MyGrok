
# Grok3-API

A simple, unofficial Python script to interact with the Grok interface (powered by xAI) via browser automation. This script opens a separate browser window, sends messages and files (e.g., images) to Grok, and retrieves responses using clipboard and UI automation. It was written with a little help from Grok itself!

> **Note**: This is a modest, experimental script with no warranties. All rights to Grok and its underlying technology belong to xAI.

## Features
- Send text messages to Grok.
- Upload files (e.g., images) along with messages.
- Retrieve responses via clipboard automation.
- Works only on Linux due to dependency on `xdotool` and related tools.

## Prerequisites
This script is designed for **Linux** systems only. It relies on the following dependencies:
- Python 3.6+
- `xdotool` - for window and mouse/keyboard automation
- `xclip` - for clipboard management
- `imagemagick` - for image conversion
- Additional Python libraries (see installation steps)
- An active Grok account at [grok.com](https://grok.com) (you’ll need to log in manually).

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/DragonsWho/grok3-api.git
   cd grok3-api
   ```

2. **Set up a virtual environment** (optional but recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   (The `requirements.txt` includes: `pyperclip`, `opencv-python`, `numpy`, `mss`, `mimetypes`.)

4. **Install system dependencies**:
   On a Debian/Ubuntu-based system:
   ```bash
   sudo apt update
   sudo apt install xdotool xclip imagemagick
   ```
  
5. **Log in to Grok**:
   - Open [grok.com](https://grok.com) in your browser and log in to your xAI account. The script will open a separate browser window and interact with this page, so keep your session active.

## Usage
Run the script from the command line:
```bash
python grok_api.py "Your message here" [file1] [file2] ...
```
Example:
```bash
python grok_api.py "What’s on this picture? Where is this mountain?" image.png
```

### Options
- `--reuse-window` or `-rw`: Reuse an existing browser window.
- `--no-close` or `-nc`: Keep the browser window open after execution.

## How It Works
Since Grok doesn’t provide an official API, this script uses browser automation:
- It opens a new browser window to [grok.com](https://grok.com).
- It interacts with the page by simulating clicks and keystrokes using `xdotool`.
- Messages and files are sent via the clipboard and UI elements (e.g., input fields, buttons).
- Responses are retrieved by copying text from the Grok interface.

Tricks like copying cookies, using Selenium, or other advanced automation methods are blocked by cloudflare protections, so this script relies on basic UI manipulation.

## Limitations
- **Linux-only**: Depends on `xdotool`, `xclip`, and `imagemagick`.
- **Manual Setup**: Requires UI templates and an active logged-in session on [grok.com](https://grok.com).
- **Rate Limits**: Heavy use will quickly hit Grok’s request limits, potentially locking you out temporarily. Consider a premium subscription to Grok for better access.
- **No Official API**: This is a workaround due to the lack of a proper API from xAI.
- **Fragile**: May break if Grok’s UI changes significantly. But I don't think so. And you can easily update the item pictures at any time.

## Recommendations
For a smoother experience, consider purchasing a **premium subscription to Grok** on [grok.com](https://grok.com). This may increase your rate limits and reduce interruptions from hitting free-tier caps.

## Disclaimer
This script is an unofficial, community-driven effort and comes with **no guarantees** of functionality, reliability, or compatibility with future Grok updates. All intellectual property rights related to Grok belong to **xAI**. Use at your own risk! If you overuse this script, you’ll likely exhaust your free-tier limits quickly.

## Credits
- Written with assistance from Grok, created by xAI. Seriously, he did most of the work.
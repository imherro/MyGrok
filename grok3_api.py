import time
import pyperclip
import subprocess
import os
import cv2
import numpy as np
import mss
import mimetypes
from functools import wraps

# Constants
TEMPLATES_DIR = "grok_templates"
WINDOW_ID_FILE = "grok_window_id.txt"
XDOTOOL = "xdotool"

def retry_on_failure(func):
    """Decorator to retry a function on failure."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            return kwargs.get('default', None)
    return wrapper

def wait_for_condition(condition_func, timeout=5.0, interval=0.1):
    """Wait for a condition to be met within a timeout."""
    start = time.time()
    while time.time() - start < timeout:
        if result := condition_func():
            return result
        time.sleep(interval)
    return None

class XdotoolWrapper:
    """Wrapper for xdotool commands."""
    @staticmethod
    @retry_on_failure
    def run(command, default=None):
        return subprocess.run([XDOTOOL] + command, check=True, capture_output=True).returncode == 0

    @staticmethod
    @retry_on_failure
    def get_output(command):
        return subprocess.check_output([XDOTOOL] + command).decode('utf-8').strip()

class GrokAPI:
    def __init__(self, url="https://grok.com", reuse_window=False, anonymous_chat=False):
        os.makedirs(TEMPLATES_DIR, exist_ok=True)
        self.url = url
        self.reuse_window = reuse_window
        self.anonymous_chat = anonymous_chat
        self.window_id = None
        self.templates = self._load_templates()
        self.template_cache = self._preload_templates()

    def _preload_templates(self):
        """Preload UI templates into memory."""
        cache = {}
        for key, path in self.templates.items():
            try:
                img = cv2.imread(path)
                if img is not None:
                    cache[key] = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            except Exception:
                pass
        return cache

    def _load_templates(self):
        """Load UI template paths from file."""
        templates_path = os.path.join(TEMPLATES_DIR, "templates_info.txt")
        try:
            with open(templates_path, 'r') as f:
                templates = dict(line.strip().split(":", 1) for line in f if ":" in line)
            valid_keys = ['input_field', 'input_field_alt', 'copy_button', 
                         'copy_button_alt', 'send_button_active']
            return {k: v.strip() for k, v in templates.items() if k in valid_keys and os.path.exists(v.strip())}
        except FileNotFoundError:
            return {}

    def _save_window_id(self, window_id):
        with open(WINDOW_ID_FILE, 'w') as f:
            f.write(str(window_id))

    def _load_window_id(self):
        try:
            with open(WINDOW_ID_FILE, 'r') as f:
                return int(f.read().strip())
        except (FileNotFoundError, ValueError):
            return None

    def _open_browser(self):
        """Open a browser window and return its ID."""
        if self.reuse_window and (wid := self._load_window_id()) and XdotoolWrapper.run(['windowactivate', str(wid)]):
            return wid

        for browser in ["google-chrome", "chromium", "firefox"]:
            try:
                with open(os.devnull, 'w') as devnull:
                    subprocess.Popen([browser, "--new-window", self.url], stdout=devnull, stderr=devnull)
                time.sleep(2)
                self.window_id = int(XdotoolWrapper.get_output(['getactivewindow']))
                self._save_window_id(self.window_id)
                return self.window_id
            except Exception:
                continue
        return None

    def _capture_screenshot(self):
        """Capture a screenshot of the active window."""
        with mss.mss() as sct:
            if not self.window_id:
                return np.array(sct.grab(sct.monitors[1]))
            try:
                window_info = XdotoolWrapper.get_output(['getwindowgeometry', str(self.window_id)]).split('\n')
                x, y = map(int, window_info[1].split('Position: ')[1].split(' ')[0].split(','))
                w, h = map(int, window_info[2].split('Geometry: ')[1].split('x'))
                monitor = {"top": y, "left": x, "width": w, "height": h}
                return np.array(sct.grab(monitor))
            except Exception:
                return np.array(sct.grab(sct.monitors[1]))

    def _find_template(self, template_key, confidence=0.8):
        """Locate a template in the current screenshot."""
        screenshot = self._capture_screenshot()
        screenshot_rgb = cv2.cvtColor(screenshot, cv2.COLOR_BGR2RGB)
        template_rgb = self.template_cache.get(template_key)
        if template_rgb is None:
            return None
        h, w = template_rgb.shape[:-1]
        result = cv2.matchTemplate(screenshot_rgb, template_rgb, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val >= confidence:
            return max_loc[0] + w // 2, max_loc[1] + h // 2
        return None

    def _wait_for_template(self, template_key, alt_key=None, timeout=3.0, interval=0.5, confidence=0.7):
        """Wait for a template to appear."""
        templates = [template_key] + ([alt_key] if alt_key in self.templates else [])
        return wait_for_condition(lambda: next((pos for t in templates if (pos := self._find_template(t, confidence))), None), timeout, interval)

    def _copy_file(self, file_path):
        """Copy a file to the clipboard."""
        if not os.path.exists(file_path):
            return False
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type and mime_type.startswith('image/'):
            try:
                subprocess.run(f'convert "{file_path}" png:- | xclip -selection clipboard -t image/png', shell=True, check=True, timeout=10)
                return True
            except Exception:
                return False
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                pyperclip.copy(f.read())
            return True
        except Exception:
            return False

    def send_message(self, message="", file_paths=None):
        """Send a message with optional files."""
        if not self.templates:
            return False
        input_pos = self._wait_for_template('input_field', 'input_field_alt', timeout=3.0)
        if not input_pos:
            XdotoolWrapper.run(['click', '5'])
            input_pos = self._wait_for_template('input_field', 'input_field_alt', timeout=3.0)
        if not input_pos:
            return False

        XdotoolWrapper.run(['mousemove', str(input_pos[0]), str(input_pos[1]), 'click', '1'])
        time.sleep(0.3)
        XdotoolWrapper.run(['key', 'ctrl+a', 'Delete'])

        # Открываем новый анонимный чат, если включён режим
        if self.anonymous_chat:
            XdotoolWrapper.run(['key', 'ctrl+shift+J'])
            time.sleep(0.3)  # Ждём загрузки интерфейса

        original_clipboard = pyperclip.paste()
        if message:
            pyperclip.copy(message)
            XdotoolWrapper.run(['key', 'ctrl+v'])
            time.sleep(1)

        if file_paths:
            for file_path in file_paths:
                if self._copy_file(file_path):
                    XdotoolWrapper.run(['key', 'ctrl+v'])
                    time.sleep(2.0)

        send_pos = self._wait_for_template('send_button_active', timeout=15.0, interval=0.5, confidence=0.8)
        if send_pos:
            XdotoolWrapper.run(['mousemove', str(send_pos[0]), str(send_pos[1]), 'click', '1'])
            pyperclip.copy(original_clipboard)
            return True
        pyperclip.copy(original_clipboard)
        return False

    def get_response(self, timeout=60):
        """Retrieve the response from the UI."""
        start_time = time.time()
        original_clipboard = pyperclip.paste()
        while time.time() - start_time < timeout:
            for key in ['copy_button', 'copy_button_alt']:
                if key in self.templates and (pos := self._find_template(key, 0.7)):
                    XdotoolWrapper.run(['mousemove', str(pos[0]), str(pos[1]), 'click', '1'])
                    time.sleep(1)
                    response = pyperclip.paste()
                    if response != original_clipboard and response.strip():
                        return response
            time.sleep(1)
        return "Error: Timeout waiting for response"

    def ask(self, message="", file_paths=None, timeout=60, close_after=True):
        """Send a request and get a response."""
        if not self._open_browser():
            return "Error: Failed to open browser"
        if not self.send_message(message, file_paths):
            return "Error: Failed to send message"
        response = self.get_response(timeout)
        # Окно закрывается только если reuse_window=False и close_after=True
        if not self.reuse_window and close_after and (wid := self._load_window_id()):
            XdotoolWrapper.run(['windowactivate', str(wid), 'key', 'ctrl+F4'])
            os.remove(WINDOW_ID_FILE) if os.path.exists(WINDOW_ID_FILE) else None
        return response

def check_dependencies():
    """Verify required dependencies are installed."""
    return all(subprocess.run(['which', cmd], capture_output=True).returncode == 0 for cmd in ['xdotool', 'xclip', 'convert'])

if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    reuse_window = any(x in args for x in ["--reuse-window", "-rw"])
    anonymous_chat = any(x in args for x in ["--anonymous-chat", "-ac"])
    close_after = not any(x in args for x in ["--no-close", "-nc"])

    if not check_dependencies():
        print("Error: Missing dependencies (xdotool, xclip, imagemagick)")
        sys.exit(1)

    message = ""
    file_paths = []
    for arg in args:
        if arg.startswith("-"):
            continue
        elif os.path.exists(arg):
            file_paths.append(os.path.abspath(arg))
        elif not message:
            message = arg

    api = GrokAPI(reuse_window=reuse_window, anonymous_chat=anonymous_chat)
    if message or file_paths:
        response = api.ask(message, file_paths, close_after=close_after)
        print(response)
    else:
        print("Usage: python grok_api.py [options] \"message\" [files...]")
        print("Options: --reuse-window/-rw, --anonymous-chat/-ac, --no-close/-nc")
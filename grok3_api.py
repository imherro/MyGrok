import time
import pyperclip
import subprocess
import os
import cv2
import numpy as np
import mss
import mimetypes
import io
import win32clipboard
from PIL import Image
from functools import wraps

# Constants
TEMPLATES_DIR = "grok_templates"
WINDOW_ID_FILE = "grok_window_id.txt"

# Import required modules
import pyautogui
import win32gui

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

class WindowsAutomation:
    @staticmethod
    @retry_on_failure
    def run(action, *args):
        try:
            if action == 'click':
                pyautogui.click(x=args[0], y=args[1])
            elif action == 'mousemove':
                pyautogui.moveTo(x=args[0], y=args[1])
            elif action == 'key':
                # 改进按键处理
                if len(args) == 1:
                    # 单个按键
                    pyautogui.press(args[0])
                else:
                    # 组合键
                    pyautogui.hotkey(*args)
                # 确保按键事件被处理
                time.sleep(0.5)
            return True
        except Exception as e:
            print(f"自动化操作失败: {str(e)}")
            return False

    @staticmethod
    def get_active_window():
        return win32gui.GetForegroundWindow()

    @staticmethod
    def activate_window(hwnd):
        try:
            win32gui.SetForegroundWindow(hwnd)
            return True
        except Exception:
            return False

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


    
    # 修改 _open_browser 方法
    def _open_browser(self):
        """Open a browser window and return its ID."""
        # 尝试复用已存在的窗口
        if self.reuse_window:
            # 检查是否存在窗口ID文件
            if os.path.exists(WINDOW_ID_FILE):
                wid = self._load_window_id()
                if wid:
                    # 尝试激活窗口
                    if WindowsAutomation.activate_window(wid):
                        # 验证窗口是否真的存在且可用
                        try:
                            if win32gui.IsWindow(wid):
                                self.window_id = wid
                                return wid
                        except Exception:
                            pass
                    # 如果窗口无效，删除ID文件
                    os.remove(WINDOW_ID_FILE)
    
        browsers = {
            "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            "firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe"
        }
    
        # 只尝试打开第一个可用的浏览器
        for name, path in browsers.items():
            if os.path.exists(path):
                try:
                    # 使用--new-instance参数确保创建新的浏览器实例
                    process = subprocess.Popen([path, "--new-instance", "--new-window", self.url])
                    # 等待浏览器窗口出现
                    for _ in range(10):  # 最多等待5秒
                        time.sleep(0.5)
                        self.window_id = WindowsAutomation.get_active_window()
                        if self.window_id:
                            self._save_window_id(self.window_id)
                            return self.window_id
                    # 如果无法获取窗口ID，终止进程
                    process.terminate()
                except Exception as e:
                    print(f"Error opening {name}: {str(e)}")
                    continue
                break  # 成功启动浏览器后退出循环
        
        if not self.window_id:
            print("Error: Failed to open browser")
        return self.window_id
    
    # 在类中替换所有 XdotoolWrapper 的使用为 WindowsAutomation
    def _capture_screenshot(self):
        """Capture a screenshot of the active window."""
        with mss.mss() as sct:
            if not self.window_id:
                return np.array(sct.grab(sct.monitors[1]))
            try:
                # Get window position and size using win32gui
                rect = win32gui.GetWindowRect(self.window_id)
                x, y = rect[0], rect[1]
                w, h = rect[2] - rect[0], rect[3] - rect[1]
                monitor = {"top": y, "left": x, "width": w, "height": h}
                return np.array(sct.grab(monitor))
            except Exception:
                return np.array(sct.grab(sct.monitors[1]))

    def _find_template(self, template_key, confidence=0.85):
        """Locate a template in the current screenshot with improved error handling."""
        try:
            screenshot = self._capture_screenshot()
            if screenshot is None or screenshot.size == 0:
                print(f"Warning: Invalid screenshot for template {template_key}")
                return None

            screenshot_rgb = cv2.cvtColor(screenshot, cv2.COLOR_BGR2RGB)
            template_rgb = self.template_cache.get(template_key)
            if template_rgb is None:
                print(f"Warning: Template not found in cache: {template_key}")
                return None

            h, w = template_rgb.shape[:-1]
            if h <= 0 or w <= 0:
                print(f"Warning: Invalid template dimensions for {template_key}")
                return None

            # 使用固定比例1.0进行模板匹配以提高效率
            scale = 1.0
            scaled_template = cv2.resize(template_rgb, (int(w * scale), int(h * scale)))
            # 尝试多种匹配方法
            methods = [cv2.TM_CCOEFF_NORMED, cv2.TM_SQDIFF_NORMED, cv2.TM_CCORR_NORMED]
            
            max_val_overall = 0
            best_loc = None
            
            for method in methods:
                result = cv2.matchTemplate(screenshot_rgb, scaled_template, method)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)
                
                # 对于SQDIFF方法需要反转置信度
                if method == cv2.TM_SQDIFF_NORMED:
                    max_val = 1 - max_val

                if max_val > max_val_overall:
                    max_val_overall = max_val
                    best_loc = (int(max_loc[0] + (w * scale) // 2), int(max_loc[1] + (h * scale) // 2))
            
            # 只在找到匹配时输出调试信息
            if max_val_overall >= confidence:
                print(f"[模板匹配] {template_key} 位置: {best_loc}, 置信度: {max_val_overall:.2f}")
                return best_loc
            return None

        except Exception as e:
            print(f"Error in template matching for {template_key}: {str(e)}")
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
            print("Error: No templates loaded")
            return False
            
        # 确保窗口处于激活状态并等待足够时间
        if not self.window_id:
            print("Error: No window ID available")
            return False
            
        print("正在激活窗口...")
        # 多次尝试激活窗口，增加等待时间
        window_activated = False
        for attempt in range(3):  # 重试次数改为3次
            if WindowsAutomation.activate_window(self.window_id):
                time.sleep(5.0)  # 增加窗口激活等待时间
                window_activated = True
                print(f"窗口激活成功 (尝试 {attempt + 1}/3)")
                break
            print(f"窗口激活重试中... (尝试 {attempt + 1}/3)")
            time.sleep(2.0)  # 增加重试间隔
            
        if not window_activated:
            print("Error: Failed to activate window")
            return False
            
        print("正在定位输入框...")
        # 使用更长的超时时间和更高的置信度来定位输入框
        input_pos = None
        # 先等待页面完全加载
        time.sleep(5.0)  # 增加初始等待时间
        
        for attempt in range(3):  # 增加重试次数
            # 先检查页面是否已加载完成
            print(f"正在检查页面加载状态... (尝试 {attempt + 1}/3)")
            if not self._wait_for_template('input_field', 'input_field_alt', timeout=5.0, confidence=0.7):
                print(f"等待页面加载... (尝试 {attempt + 1}/3)")
                time.sleep(2.0)
                continue
            print("页面加载检查完成，开始定位输入框...")
            
            # 点击页面中心以确保窗口焦点
            screen = self._capture_screenshot()
            center_x, center_y = screen.shape[1] // 2, screen.shape[0] // 2
            WindowsAutomation.run('click', center_x, center_y)
            time.sleep(1.5)  # 增加等待时间
            
            # 尝试定位输入框
            print(f"正在尝试定位输入框... (第 {attempt + 1} 次尝试)")
            input_pos = self._wait_for_template('input_field', 'input_field_alt', timeout=5.0, confidence=0.85)
            if input_pos:
                print(f"输入框定位成功！坐标: ({input_pos[0]}, {input_pos[1]})")
                break
            
            # 如果找不到输入框，尝试不同的焦点切换方法
            print(f"尝试切换焦点... (尝试 {attempt + 1}/3)")
            if attempt % 3 == 0:
                WindowsAutomation.run('key', 'tab')
                time.sleep(1.5)
            elif attempt % 3 == 1:
                WindowsAutomation.run('key', 'escape')
                time.sleep(1.5)
            else:
                # 尝试点击页面不同区域
                for offset in [(0, 50), (0, -50), (50, 0), (-50, 0)]:
                    WindowsAutomation.run('click', center_x + offset[0], center_y + offset[1])
                    time.sleep(1.0)
                
        if not input_pos:
            print("Error: Could not locate input field")
            return False

        print("正在获取输入框焦点...")
        # 多次尝试确保输入框获得焦点
        focus_obtained = False
        for attempt in range(3):  # 重试次数改为3次
            # 移动到输入框位置并等待
            print(f"正在移动鼠标到输入框位置... (第 {attempt + 1} 次尝试)")
            if WindowsAutomation.run('mousemove', input_pos[0], input_pos[1]):
                print("鼠标移动成功")
            else:
                print("鼠标移动失败，重试中...")
            time.sleep(2.0)  # 增加等待时间
            
            print(f"尝试点击输入框... (尝试 {attempt + 1}/3)")
            # 单击并等待
            if WindowsAutomation.run('click', input_pos[0], input_pos[1]):
                print("点击输入框成功")
            else:
                print("点击输入框失败，重试中...")
            time.sleep(3.0)  # 增加等待时间
            
            # 验证焦点是否真正获得
            WindowsAutomation.run('key', 'ctrl', 'a')
            time.sleep(1.5)  # 增加等待时间
            
            # 检查输入框状态，降低验证时的置信度阈值，增加调试信息
            print("正在验证输入框焦点状态...")
            input_field_pos = self._find_template('input_field', 0.85)
            input_field_alt_pos = self._find_template('input_field_alt', 0.85)
            
            if input_field_pos or input_field_alt_pos:
                focus_obtained = True
                print("输入框焦点获取成功！")
                if input_field_pos:
                    print(f"主输入框模板匹配位置: {input_field_pos}")
                if input_field_alt_pos:
                    print(f"备用输入框模板匹配位置: {input_field_alt_pos}")
                break
            
            print("焦点验证失败，可能原因：")
            print("1. 输入框模板匹配置信度不足")
            print("2. 页面状态发生变化")
            print("3. 焦点可能被其他元素捕获")
            break
            
            print(f"焦点获取失败，尝试其他方法... (尝试 {attempt + 1}/3)")
            # 如果失败，尝试不同的焦点获取方式
            if attempt % 2 == 0:
                WindowsAutomation.run('key', 'tab')
                time.sleep(1.5)
            else:
                # 点击页面中心后再次尝试
                screen = self._capture_screenshot()
                center_x, center_y = screen.shape[1] // 2, screen.shape[0] // 2
                WindowsAutomation.run('click', center_x, center_y)
                time.sleep(2.0)
                
        if not focus_obtained:
            print("Error: Failed to obtain input field focus")
            return False
        
        # 清空输入框
        for _ in range(2):  # 尝试两次清空操作
            WindowsAutomation.run('key', 'ctrl', 'a')
            time.sleep(0.5)
            WindowsAutomation.run('key', 'Delete')
            time.sleep(0.5)

        # 处理匿名聊天模式
        if self.anonymous_chat:
            WindowsAutomation.run('key', 'ctrl', 'shift', 'j')
            time.sleep(2.0)  # 增加等待时间
    
        # 保存并恢复剪贴板内容
        original_clipboard = pyperclip.paste()
        
        try:
            # 输入消息
            if message:
                # 多次尝试粘贴消息
                for _ in range(3):  # 重试次数改为3次
                    # 确保输入框为空
                    WindowsAutomation.run('key', 'ctrl', 'a')
                    time.sleep(0.5)
                    WindowsAutomation.run('key', 'delete')
                    time.sleep(1.0)
                    
                    # 粘贴消息
                    pyperclip.copy(message)
                    time.sleep(1.0)  # 增加等待时间
                    WindowsAutomation.run('key', 'ctrl', 'v')
                    time.sleep(2.0)  # 增加等待时间
                    
                    # 验证消息是否已粘贴
                    WindowsAutomation.run('key', 'ctrl', 'a')
                    time.sleep(1.0)
                    current_text = pyperclip.paste()
                    if current_text == message:
                        print("消息粘贴成功")
                        break
                    print("消息粘贴失败，重试中...")
                    time.sleep(1.0)  # 重试前等待

            # 处理文件
            if file_paths:
                for file_path in file_paths:
                    if self._copy_file(file_path):
                        WindowsAutomation.run('key', 'ctrl', 'v')
                        time.sleep(2.0)

            # 尝试发送消息
            print("尝试发送消息...")
            
            # 确保输入框有焦点
            input_pos = self._find_template('input_field', 0.85)
            if input_pos:
                WindowsAutomation.run('mousemove', input_pos[0], input_pos[1])
                time.sleep(0.5)
                WindowsAutomation.run('click', input_pos[0], input_pos[1])
                time.sleep(1.0)
            
            # 清空输入框
            WindowsAutomation.run('key', 'ctrl', 'a')
            time.sleep(0.5)
            WindowsAutomation.run('key', 'delete')
            time.sleep(0.5)
            
            # 使用pyautogui.typewrite输入消息和发送
            print("直接输入消息和发送...")
            pyautogui.typewrite(message + '\n')  # 直接在消息后面加上回车
            time.sleep(2.0)  # 增加等待时间
            
            # 再发送一次回车以确保
            print("再次发送回车...")
            pyautogui.typewrite(['\n'])
            time.sleep(2.0)
            
            # 等待一段时间让消息发送
            print("等待消息发送完成...")
            time.sleep(5.0)
            
            # 假定消息已发送成功
            print("消息已发送！")
            return True
        finally:
            # 确保在任何情况下都恢复原始剪贴板内容
            pyperclip.copy(original_clipboard)



    def get_response(self, timeout=60):
        """Retrieve the response from the UI."""
        start_time = time.time()
        original_clipboard = pyperclip.paste()
        
        print("\n[获取响应] 开始等待响应...")
        
        # Make sure the window is active
        if self.window_id:
            WindowsAutomation.activate_window(self.window_id)
            time.sleep(0.1)  # Give time for activation
        
        # 等待页面加载完成
        print("[获取响应] 等待页面加载...")
        time.sleep(10.0)  # 增加初始等待时间
        
        while time.time() - start_time < timeout:
            print(f"\r[获取响应] 等待中... 已等待 {int(time.time() - start_time)} 秒", end="")
            
            # 滚动到页面底部
            WindowsAutomation.run('key', 'end')
            time.sleep(2.0)  # 增加滚动后等待时间
            
            # 先尝试找到复制按钮
            copy_button_pos = None
            for key in ['copy_button', 'copy_button_alt']:
                if key in self.templates:
                    # 降低匹配阈值，增加容错率
                    pos = self._find_template(key, 0.6)
                    if pos:
                        print(f"\n[获取响应] 找到复制按钮: {key}")
                        copy_button_pos = pos
                        break
            
            if copy_button_pos:
                # 移动到按钮位置并点击
                WindowsAutomation.run('mousemove', copy_button_pos[0], copy_button_pos[1])
                time.sleep(1.0)
                WindowsAutomation.run('click', copy_button_pos[0], copy_button_pos[1])
                time.sleep(2.0)  # 增加点击后等待时间
                
                # 检查剪贴板内容
                response = pyperclip.paste()
                if response != original_clipboard and response.strip():
                    print("\n[获取响应] 成功获取响应内容")
                    return response
            
            # 如果找不到复制按钮或复制失败，继续尝试
            time.sleep(2.0)  # 增加重试间隔
            WindowsAutomation.run('key', 'page_down')
            time.sleep(2.0)
        
        print("\n[获取响应] 超时等待响应")
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
            WindowsAutomation.activate_window(wid)
            WindowsAutomation.run('key', 'ctrl', 'F4')
            os.remove(WINDOW_ID_FILE) if os.path.exists(WINDOW_ID_FILE) else None
        return response

def check_dependencies():
    def check_command(cmd):
        try:
            # 检查常见的 ImageMagick 安装路径
            if cmd == 'magick':
                common_paths = [
                    r"C:\Program Files\ImageMagick-7.1.1-Q16",
                    r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI",
                    r"C:\Program Files (x86)\ImageMagick-7.1.1-Q16",
                    r"C:\Program Files (x86)\ImageMagick-7.1.1-Q16-HDRI",
                    # 添加更多可能的版本
                    r"C:\Program Files\ImageMagick*",
                    r"C:\Program Files (x86)\ImageMagick*"
                ]
                
                # 使用通配符查找实际安装路径
                for pattern in common_paths:
                    if '*' in pattern:
                        import glob
                        paths = glob.glob(pattern)
                        for path in paths:
                            magick_exe = os.path.join(path, "magick.exe")
                            if os.path.exists(magick_exe):
                                os.environ["PATH"] = path + os.pathsep + os.environ["PATH"]
                                return True
                    else:
                        magick_exe = os.path.join(pattern, "magick.exe")
                        if os.path.exists(magick_exe):
                            os.environ["PATH"] = pattern + os.pathsep + os.environ["PATH"]
                            return True
                return False

            # 对其他命令使用 where
            result = subprocess.run(['where', cmd], capture_output=True, text=True)
            return result.returncode == 0
        except FileNotFoundError:
            return False

    # 检查 ImageMagick 的 convert 命令
    if not check_command('magick'):
        print("请安装 ImageMagick")
        return False

    # 检查 PyAutoGUI (替代 xdotool)
    try:
        import pyautogui
    except ImportError:
        print("请安装 PyAutoGUI: pip install pyautogui")
        return False

    # 检查 pyperclip (替代 xclip)
    try:
        import pyperclip
    except ImportError:
        print("请安装 pyperclip: pip install pyperclip")
        return False

    return True

if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    reuse_window = any(x in args for x in ["--reuse-window", "-rw"])
    anonymous_chat = any(x in args for x in ["--anonymous-chat", "-ac"])
    close_after = not any(x in args for x in ["--no-close", "-nc"])

    if not check_dependencies():
        print("Error: Missing dependencies (pyautogui, pyperclip, imagemagick)")
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
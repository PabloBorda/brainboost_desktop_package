import os
import json
import platform
import sqlite3
import subprocess
import threading
import io
import queue
from datetime import datetime

import cv2
import numpy as np
import pyautogui
import pytesseract
from mss import mss
from PIL import ImageGrab, Image
from screeninfo import get_monitors
from pynput import keyboard, mouse

# Import or define any additional modules that your class depends on
# These might be external or other internal packages:
from brainboost_ocr_package.BBOcr import BBOcr
from brainboost_configuration_package.BBConfig import BBConfig
from brainboost_data_source_logger_package.BBLogger import BBLogger
from brainboost_configuration_package.BBConfig import BBConfig

if platform.system() == "Darwin":
    from Quartz import (
        CGWindowListCopyWindowInfo,
        kCGWindowListOptionOnScreenOnly,
        kCGWindowListOptionOnScreenAbove,
        kCGNullWindowID,
        CGMainDisplayID
    )

if platform.system() == "Windows":
    import pygetwindow as gw

class Desktop:
    _instance = None  # Singleton instance
    _lock = threading.Lock()  # Lock for thread-safe creation

    def __init__(self):
        if Desktop._instance is not None:
            raise RuntimeError("Use get_desktop_singleton() to access the Desktop instance.")
        self.system = platform.system()
        self.base_image = None
        self.init_database()
        self.conn = sqlite3.connect(BBConfig.get('snapshots_database_path'), check_same_thread=False)
        self.lock = threading.Lock()
        self.ocr = BBOcr()
        self.user_input_queue = queue.Queue()
        self.monitoring_user_input = False

        # Start user input monitoring if enabled
        BBConfig.override('monitor_user_input',True)
        if BBConfig.get('monitor_user_input'):
            self.monitoring_user_input = True
            threading.Thread(target=self._monitor_user_input, daemon=True).start()

    def init_database(self):
        if BBConfig.get('snapshots_database_enabled'):
            self.conn = sqlite3.connect(BBConfig.get('snapshots_database_path'))
            cursor = self.conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY,
                    type TEXT,
                    timestamp TEXT,
                    data BLOB,
                    position TEXT,
                    text TEXT,
                    user_input TEXT
                )
            """)
            self.conn.commit()

    def get_thread_safe_connection(self):
        return sqlite3.connect(BBConfig.get('snapshots_database_path'))

    def _monitor_user_input(self):
        def on_key_press(key):
            try:
                input_data = {
                    "type": "keyboard",
                    "value": str(key),
                    "timestamp": datetime.now().isoformat()
                }
                BBLogger.log(f"Captured key press: {input_data}")
                self.user_input_queue.put(input_data)
            except Exception as e:
                BBLogger.log(f"Error in key press handler: {e}")

        def on_mouse_click(x, y, button, pressed):
            input_data = {
                "type": "mouse",
                "value": "click" if pressed else "release",
                "position": {"x": x, "y": y},
                "timestamp": datetime.now().isoformat()
            }
            BBLogger.log(f"Captured mouse event: {input_data}")
            self.user_input_queue.put(input_data)

        try:
            with keyboard.Listener(on_press=on_key_press) as key_listener, \
                 mouse.Listener(on_click=on_mouse_click) as mouse_listener:
                key_listener.join()
                mouse_listener.join()
        except Exception as e:
            BBLogger.log(f"Error starting listeners: {e}")

    def _save_user_input(self):
        user_inputs = []
        while not self.user_input_queue.empty():
            user_inputs.append(self.user_input_queue.get())
        return user_inputs

    def _save_screenshot_diff(self, new_img):
        if self.base_image is None:
            self.base_image = new_img
            return

        diff = cv2.absdiff(self.base_image, new_img)
        gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        _, diff_thresh = cv2.threshold(gray_diff, 30, 255, cv2.THRESH_BINARY)
        x, y, w, h = cv2.boundingRect(diff_thresh)

        ocr_results = self.ocr.extract_text(new_img)
        ocr_text_json = [
            {
                "text": result['text'],
                "rect": {
                    "x": result['rect'][0],
                    "y": result['rect'][1],
                    "width": result['rect'][2] - result['rect'][0],
                    "height": result['rect'][3] - result['rect'][1]
                }
            } for result in ocr_results
        ]

        user_inputs = self._save_user_input()
        user_input_json = json.dumps(user_inputs)

        if w > 0 and h > 0:
            cropped_diff = new_img[y:y + h, x:x + w]
            _, compressed_diff = cv2.imencode(".png", cropped_diff)

            conn = self.get_thread_safe_connection()
            cursor = conn.cursor()
            timestamp = datetime.now().isoformat()
            cursor.execute(
                "INSERT INTO snapshots (timestamp, type, data, position, text, user_input) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    timestamp,
                    "desktop_screenshot",
                    compressed_diff.tobytes(),
                    f'{{"x": {x}, "y": {y}, "width": {w}, "height": {h}}}',
                    json.dumps(ocr_text_json),
                    user_input_json
                )
            )
            conn.commit()
            conn.close()

        self.base_image = new_img

    @classmethod
    def get_desktop_singleton(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    def get_screen_coordinates(self):
        screen_info = []
        for monitor in get_monitors():
            screen_info.append({
                "left": monitor.x,
                "top": monitor.y,
                "width": monitor.width,
                "height": monitor.height
            })
        return screen_info

    def get_open_windows(self):
        def _get_linux_windows():
            try:
                output = subprocess.check_output(["wmctrl", "-l"]).decode("utf-8").strip().split("\n")
                windows = [{"id": line.split()[0], "title": line.split(None, 3)[-1]} for line in output]
                return windows
            except subprocess.CalledProcessError:
                return []

        def _get_window_windows():
            if self.system != "Windows":
                raise EnvironmentError("This method is only available on Windows.")

            windows = []
            for win in gw.getAllWindows():
                windows.append({
                    "title": win.title,
                    "left": win.left,
                    "top": win.top,
                    "width": win.width,
                    "height": win.height,
                })
            return windows

        def _get_darwin_windows():
            if self.system != "Darwin":
                raise EnvironmentError("This method is only available on macOS.")

            window_list = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
            windows = []
            for window in window_list:
                title = window.get("kCGWindowName", "Unknown")
                bounds = window.get("kCGWindowBounds", {})
                x = int(bounds.get("X", 0))
                y = int(bounds.get("Y", 0))
                width = int(bounds.get("Width", 0))
                height = int(bounds.get("Height", 0))
                windows.append({
                    "title": title,
                    "left": x,
                    "top": y,
                    "width": width,
                    "height": height,
                })
            return windows

        if self.system == "Linux":
            return _get_linux_windows()
        elif self.system == "Windows":
            return _get_window_windows()
        elif self.system == "Darwin":
            return _get_darwin_windows()
        else:
            raise NotImplementedError("This method is only implemented for Windows and macOS.")

    def get_focused_window(self):
        def _get_linux_focused_window():
            try:
                window_id = subprocess.check_output(["xprop", "-root", "_NET_ACTIVE_WINDOW"]).decode().strip()
                window_id = window_id.split()[-1]

                window_info = subprocess.check_output(["xwininfo", "-id", window_id]).decode().splitlines()
                window_name = ""
                for line in window_info:
                    if "xwininfo" in line and "-name" in line:
                        window_name = line.split('"', 1)[-1].strip().strip('"')
                        break
                return {"title": window_name, "id": window_id}
            except Exception as e:
                BBLogger.log(f"Error retrieving focused window on Linux: {e}")
                return None

        def _get_windows_focused_window():
            try:
                active_window = gw.getActiveWindow()
                if active_window:
                    return {
                        "title": active_window.title,
                        "left": active_window.left,
                        "top": active_window.top,
                        "width": active_window.width,
                        "height": active_window.height,
                    }
                else:
                    BBLogger.log("No active window found.")
                    return None
            except Exception as e:
                BBLogger.log(f"Error retrieving focused window on Windows: {e}")
                return None

        def _get_darwin_focused_window():
            try:
                window_list = CGWindowListCopyWindowInfo(
                    kCGWindowListOptionOnScreenAbove, CGMainDisplayID()
                )
                for window in window_list:
                    if window.get("kCGWindowIsOnscreen") and window.get("kCGWindowName"):
                        bounds = window["kCGWindowBounds"]
                        return {
                            "title": window.get("kCGWindowName"),
                            "left": int(bounds["X"]),
                            "top": int(bounds["Y"]),
                            "width": int(bounds["Width"]),
                            "height": int(bounds["Height"]),
                        }
                BBLogger.log("No focused window found.")
                return None
            except Exception as e:
                BBLogger.log(f"Error retrieving focused window on macOS: {e}")
                return None

        if self.system == "Linux":
            return _get_linux_focused_window()
        elif self.system == "Windows":
            return _get_windows_focused_window()
        elif self.system == "Darwin":
            return _get_darwin_focused_window()
        else:
            raise NotImplementedError("This method is only implemented for Linux, Windows, and macOS.")

    def take_screenshot_from_window(self, name):
        def _take_screenshot_linux(name):
            try:
                window_id = None
                output = subprocess.check_output(["wmctrl", "-l"]).decode("utf-8").strip().split("\n")
                for line in output:
                    if name in line:
                        window_id = line.split()[0]
                        break

                if not window_id:
                    BBLogger.log(f"Window '{name}' not found.")
                    return None

                output = subprocess.check_output(["xwininfo", "-id", window_id]).decode("utf-8")
                x, y, width, height = None, None, None, None
                for line in output.splitlines():
                    if "Absolute upper-left X" in line:
                        x = int(line.split(":")[1].strip())
                    elif "Absolute upper-left Y" in line:
                        y = int(line.split(":")[1].strip())
                    elif "Width" in line:
                        width = int(line.split(":")[1].strip())
                    elif "Height" in line:
                        height = int(line.split(":")[1].strip())

                if x is None or y is None or width is None or height is None:
                    BBLogger.log("Unable to retrieve window geometry.")
                    return None

                bbox = (x, y, x + width, y + height)
                screenshot = ImageGrab.grab(bbox)
                screenshot.save(f"{name}_screenshot.png")
                BBLogger.log(f"Screenshot saved as {name}_screenshot.png")
                return screenshot
            except Exception as e:
                BBLogger.log(f"Error capturing screenshot on Linux: {e}")
                return None

        def _take_screenshot_windows(name):
            try:
                window = gw.getWindowsWithTitle(name)
                if not window:
                    BBLogger.log(f"Window '{name}' not found.")
                    return None
                window = window[0]
                bbox = (window.left, window.top, window.right, window.bottom)
                screenshot = ImageGrab.grab(bbox)
                screenshot.save(f"{name}_screenshot.png")
                BBLogger.log(f"Screenshot saved as {name}_screenshot.png")
                return screenshot
            except Exception as e:
                BBLogger.log(f"Error capturing screenshot on Windows: {e}")
                return None

        def _take_screenshot_macos(name):
            try:
                window_info_list = CGWindowListCopyWindowInfo(
                    kCGWindowListOptionOnScreenOnly, kCGNullWindowID
                )
                for window in window_info_list:
                    if window.get("kCGWindowName") == name:
                        bounds = window["kCGWindowBounds"]
                        x, y = int(bounds["X"]), int(bounds["Y"])
                        width, height = int(bounds["Width"]), int(bounds["Height"])

                        image = Quartz.CGWindowListCreateImage(
                            (x, y, width, height),
                            Quartz.kCGWindowListOptionOnScreenOnly,
                            Quartz.kCGNullWindowID,
                            Quartz.kCGWindowImageDefault
                        )

                        if image:
                            data = Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(image))
                            pil_image = Image.open(io.BytesIO(data))
                            pil_image.save(f"{name}_screenshot.png")
                            BBLogger.log(f"Screenshot saved as {name}_screenshot.png")
                            return pil_image
                        break
                else:
                    BBLogger.log(f"Window '{name}' not found.")
                    return None
            except Exception as e:
                BBLogger.log(f"Error capturing screenshot on macOS: {e}")
                return None

        if self.system == "Linux":
            return _take_screenshot_linux(name)
        elif self.system == "Windows":
            return _take_screenshot_windows(name)
        elif self.system == "Darwin":
            return _take_screenshot_macos(name)
        else:
            raise NotImplementedError("This method is only implemented for Linux, Windows, and macOS.")

    def take_snapshot(self):
        return self.take_fullscreen_screenshot()

    def take_fullscreen_screenshot(self):
        with mss() as sct:
            screenshots = [np.array(sct.grab(monitor)) for monitor in sct.monitors[1:]]
            combined_screenshot = cv2.vconcat(screenshots) if len(screenshots) > 1 else screenshots[0]

            if combined_screenshot.shape[2] == 4:
                combined_screenshot = cv2.cvtColor(combined_screenshot, cv2.COLOR_BGRA2BGR)

            if self.base_image is None:
                self.base_image = combined_screenshot

            if BBConfig.get('write_screenshots_to_files'):
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                snapshot_dir = BBConfig.get('snapshot_images')
                os.makedirs(snapshot_dir, exist_ok=True)
                snapshot_path = os.path.join(snapshot_dir, f'snapshot_{timestamp}.png')
                cv2.imwrite(snapshot_path, combined_screenshot)

            if BBConfig.get('snapshots_database_enabled'):
                self._save_screenshot_diff(new_img=combined_screenshot)

            return combined_screenshot

    def get_window_coordinates(self):
        def _get_linux_window_coordinates():
            try:
                windows = []
                output = subprocess.check_output(["wmctrl", "-l"]).decode("utf-8").strip().split("\n")
                for line in output:
                    window_id = line.split()[0]
                    window_name = line.split(None, 3)[-1]
                    win_output = subprocess.check_output(["xwininfo", "-id", window_id]).decode("utf-8")
                    x, y, width, height = None, None, None, None
                    for detail in win_output.splitlines():
                        if "Absolute upper-left X" in detail:
                            x = int(detail.split(":")[1].strip())
                        elif "Absolute upper-left Y" in detail:
                            y = int(detail.split(":")[1].strip())
                        elif "Width" in detail:
                            width = int(detail.split(":")[1].strip())
                        elif "Height" in detail:
                            height = int(detail.split(":")[1].strip())
                    windows.append({
                        "title": window_name,
                        "left": x,
                        "top": y,
                        "width": width,
                        "height": height
                    })
                return windows
            except subprocess.CalledProcessError as e:
                BBLogger.log(f"Error retrieving window coordinates on Linux: {e}")
                return []

        def _get_windows_window_coordinates():
            windows = []
            for win in gw.getAllWindows():
                windows.append({
                    "title": win.title,
                    "left": win.left,
                    "top": win.top,
                    "width": win.width,
                    "height": win.height
                })
            return windows

        def _get_darwin_window_coordinates():
            try:
                windows = []
                window_list = CGWindowListCopyWindowInfo(
                    kCGWindowListOptionOnScreenOnly, kCGNullWindowID
                )
                for window in window_list:
                    title = window.get("kCGWindowName", "Unknown")
                    bounds = window.get("kCGWindowBounds", {})
                    x = int(bounds.get("X", 0))
                    y = int(bounds.get("Y", 0))
                    width = int(bounds.get("Width", 0))
                    height = int(bounds.get("Height", 0))
                    windows.append({
                        "title": title,
                        "left": x,
                        "top": y,
                        "width": width,
                        "height": height
                    })
                return windows
            except Exception as e:
                BBLogger.log(f"Error retrieving window coordinates on macOS: {e}")
                return []

        if self.system == "Linux":
            return _get_linux_window_coordinates()
        elif self.system == "Windows":
            return _get_windows_window_coordinates()
        elif self.system == "Darwin":
            return _get_darwin_window_coordinates()
        else:
            raise NotImplementedError("This method is only implemented for Linux, Windows, and macOS.")

    def move_mouse_to(self, coordinate):
        if isinstance(coordinate, tuple) and len(coordinate) == 2:
            x, y = coordinate
            BBLogger.log(f"Moving mouse to: {coordinate}")
            pyautogui.moveTo(x, y)
        else:
            raise ValueError("Coordinate must be a tuple of (x, y)")

    def click(self):
        BBLogger.log("Clicking at current mouse position")
        pyautogui.click()

    def click_button(self, button_text):
        try:
            BBLogger.log(f"Searching for button with text: '{button_text}'")
            screenshot = pyautogui.screenshot()
            ocr_data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)
            for i, text in enumerate(ocr_data['text']):
                if text.strip().lower() == button_text.lower():
                    x = ocr_data['left'][i]
                    y = ocr_data['top'][i]
                    width = ocr_data['width'][i]
                    height = ocr_data['height'][i]
                    center_x = x + width // 2
                    center_y = y + height // 2
                    pyautogui.click(center_x, center_y)
                    BBLogger.log(f"Button '{button_text}' clicked at location: ({center_x}, {center_y})")
                    return True
            BBLogger.log(f"Button '{button_text}' not found on screen.")
            return False
        except Exception as e:
            BBLogger.log(f"Error finding button '{button_text}': {e}")
            return False

# -*- coding: utf-8 -*-
"""
MuMu adventure reward helper.

Run:
    python mumu_adventure_assistant.py

The tool detects running MuMu Nx device windows, attaches a control bar
under the selected emulator window, and only performs the reward flow when the
user presses a button.
"""

from __future__ import annotations

import ctypes
import io
import json
import os
import subprocess
import threading
import time
import traceback
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageGrab

try:
    import psutil
except Exception:  # pragma: no cover - psutil is optional at runtime.
    psutil = None


CONTROL_HEIGHT = 260
REFRESH_MS = 900
TASK_BUFFER_SECONDS = 3
ADB_REF_WIDTH = 720
ADB_REF_HEIGHT = 1280

MUMU_INSTALL_HINT = r"D:\Program Files\Netease\MuMu\nx_main"
MUMU_MAIN_DIR = Path(MUMU_INSTALL_HINT)
MUMU_MANAGER_EXE = MUMU_MAIN_DIR / "MuMuManager.exe"
MUMU_ADB_EXE = MUMU_MAIN_DIR / "adb.exe"
MUMU_PROCESS_NAMES = {"MuMuNxDevice.exe"}
MUMU_WINDOW_CLASS_KEYWORD = "QWindowIcon"
CREATE_NO_WINDOW = 0x08000000

# Relative boxes are based on ADB screenshots. With the fixed MuMu profile
# supplied by the user, these screenshots are 720x1280 at 320 dpi.
# They are intentionally a little loose so they survive small DPI/resolution
# differences while still avoiding unrelated red/green UI elsewhere.
ADB_EXPLORE_TAB_BOX = (0.00, 0.90, 0.19, 0.995)
ADB_ADVENTURE_HEADER_BOX = (0.00, 0.00, 0.36, 0.105)
ADB_SIDE_CLAIM_BUTTON_BOX = (0.72, 0.52, 0.98, 0.74)
ADB_POPUP_CLAIM_BUTTON_BOX = (0.28, 0.65, 0.73, 0.80)
ADB_REWARD_OVERLAY_BOX = (0.10, 0.19, 0.90, 0.31)

# Fallback boxes for ordinary window screenshots if ADB is unavailable.
WIN_EXPLORE_TAB_BOX = (0.00, 0.91, 0.19, 0.995)
WIN_ADVENTURE_HEADER_BOX = (0.00, 0.045, 0.36, 0.13)
WIN_SIDE_CLAIM_BUTTON_BOX = (0.72, 0.55, 0.98, 0.75)
WIN_POPUP_CLAIM_BUTTON_BOX = (0.28, 0.67, 0.73, 0.80)
WIN_REWARD_OVERLAY_BOX = (0.10, 0.23, 0.90, 0.34)

ADB_TAP_POINTS = {
    "explore": (65, 1220),
    "side_claim": (620, 865),
    "popup_claim": (360, 920),
    "reward_blank": (360, 1180),
    "back": (45, 45),
    "queue_expand": (15, 545),
    "screen_center": (360, 640),
    "soldier_building": (335, 705),
    "building_train": (480, 855),
    "soldier_train": (535, 1115),
}

WINDOW_CLICK_POINTS = {
    "explore": (0.09, 0.955),
    "side_claim": (0.86, 0.69),
    "popup_claim": (0.50, 0.735),
    "reward_blank": (0.50, 0.93),
    "back": (0.065, 0.075),
    "queue_expand": (0.02, 0.43),
    "screen_center": (0.50, 0.50),
    "soldier_building": (0.465, 0.55),
    "building_train": (0.67, 0.67),
    "soldier_train": (0.74, 0.88),
}

DEBUG_DIR = Path("debug_captures")

TASK_DEFINITIONS = [
    ("adventure", "探险领取"),
    ("train_soldiers", "训练士兵"),
]

TRAIN_UNITS = [
    ("shield", "盾兵", 555),
    ("spear", "矛兵", 632),
    ("archer", "射手", 710),
]

TRAIN_LEVEL_CANDIDATES = [
    (45, "IV"),
    (175, "V"),
    (305, "VI"),
    (435, "VII"),
    (565, "VIII"),
    (690, "IX"),
]

NAV_BLUE = (82, 118, 175)
ADVENTURE_HEADER_BLUE = (20, 68, 113)
ADVENTURE_BUTTON_BLUE = (80, 160, 235)

EXPLORE_NAV_BLOCKS = [
    (15, 1186, 34, 1214),
    (97, 1186, 116, 1214),
    (18, 1230, 34, 1256),
    (98, 1230, 116, 1256),
]
EXPLORE_SWORD_BLOCKS = [
    (53, 1193, 67, 1213),
    (68, 1198, 82, 1218),
    (80, 1193, 94, 1213),
    (52, 1218, 67, 1238),
    (76, 1218, 92, 1238),
]

ADVENTURE_HEADER_BLOCKS = [
    (180, 15, 690, 75),
    (120, 85, 700, 112),
]
ADVENTURE_BACK_BLOCK = (8, 20, 78, 82)
ADVENTURE_ACTION_BUTTON_BLOCKS = [
    (230, 1150, 490, 1235),
    (255, 1168, 465, 1215),
]
ADVENTURE_STAGE_MARKER_BLOCKS = [
    (0, 1038, 135, 1098),
    (315, 1030, 410, 1110),
    (595, 1030, 670, 1110),
]
ADVENTURE_CHEST_BLOCK = (560, 710, 700, 930)

MAIN_CITY_TOGGLE_ICON_BLOCK = (600, 1145, 715, 1225)
MAIN_CITY_TOGGLE_BLOCK = (575, 1125, 720, 1280)

SIDE_CLAIM_GREEN_BLOCKS = [
    (560, 820, 680, 860),
    (555, 850, 682, 910),
    (590, 870, 670, 895),
]
POPUP_CLAIM_GREEN_BLOCKS = [
    (270, 850, 450, 910),
    (285, 880, 435, 945),
    (310, 900, 410, 960),
]

BUILDING_ACTION_SCAN_BOX = (120, 690, 610, 990)
BUILDING_ACTION_MIN_AREA = 3400
BUILDING_ACTION_MAX_AREA = 7600
BUILDING_ACTION_MIN_WHITE_RATIO = 0.045
BUILDING_ACTION_MIN_BLUE_RATIO = 0.22
BUILDING_GUIDE_HAND_SCAN_BOX = (380, 630, 680, 950)

SOLDIER_PAGE_BACK_BLOCK = (0, 0, 90, 90)
SOLDIER_SELECTED_TAB_BLOCK = (20, 1170, 240, 1278)
SOLDIER_SPEAR_TAB_BLOCK = (250, 1180, 468, 1278)
SOLDIER_ARCHER_TAB_BLOCK = (470, 1180, 695, 1278)
SOLDIER_BOTTOM_BUTTON_BLOCK = (20, 1060, 700, 1165)
SOLDIER_QUEUE_ROW_TAP_X = 250


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

GA_ROOT = 2
GW_OWNER = 4
SW_RESTORE = 9
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
HWND_TOPMOST = wintypes.HWND(-1)
HWND_NOTOPMOST = wintypes.HWND(-2)
SWP_NOACTIVATE = 0x0010
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
DEBUG_TRANSPARENT_COLOR = "#ff00ff"

user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]

try:
    get_window_long = user32.GetWindowLongPtrW
    set_window_long = user32.SetWindowLongPtrW
except AttributeError:  # pragma: no cover - 32 bit Python fallback.
    get_window_long = user32.GetWindowLongW
    set_window_long = user32.SetWindowLongW

get_window_long.argtypes = [wintypes.HWND, ctypes.c_int]
get_window_long.restype = ctypes.c_ssize_t
set_window_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
set_window_long.restype = ctypes.c_ssize_t


_mumu_info_cache: dict[int, dict] = {}
_mumu_info_cache_time = 0.0
_adb_connected: set[str] = set()


def enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


@dataclass(frozen=True)
class TargetWindow:
    hwnd: int
    pid: int
    title: str
    class_name: str
    process_name: str
    exe_path: str
    rect: Rect
    vm_index: str = ""
    adb_serial: str = ""
    adb_port: int | None = None

    @property
    def label(self) -> str:
        title = self.title or "(未命名)"
        adb = self.adb_serial if self.adb_serial else "无ADB"
        index = self.vm_index if self.vm_index else "?"
        return f"{title} | index={index} | adb={adb} | hwnd=0x{self.hwnd:X}"


@dataclass(frozen=True)
class ScreenProfile:
    explore_tab_box: tuple[float, float, float, float]
    adventure_header_box: tuple[float, float, float, float]
    side_claim_button_box: tuple[float, float, float, float]
    popup_claim_button_box: tuple[float, float, float, float]
    reward_overlay_box: tuple[float, float, float, float]


@dataclass(frozen=True)
class Detection:
    explore_tab_visible: bool
    adventure_page_visible: bool
    claim_widget_visible: bool
    side_claim_green: bool
    popup_claim_green: bool
    reward_overlay_visible: bool
    side_green_density: float
    popup_green_density: float
    claim_widget_density: float
    reward_overlay_density: float
    adventure_header_density: float


ADB_PROFILE = ScreenProfile(
    explore_tab_box=ADB_EXPLORE_TAB_BOX,
    adventure_header_box=ADB_ADVENTURE_HEADER_BOX,
    side_claim_button_box=ADB_SIDE_CLAIM_BUTTON_BOX,
    popup_claim_button_box=ADB_POPUP_CLAIM_BUTTON_BOX,
    reward_overlay_box=ADB_REWARD_OVERLAY_BOX,
)
WINDOW_PROFILE = ScreenProfile(
    explore_tab_box=WIN_EXPLORE_TAB_BOX,
    adventure_header_box=WIN_ADVENTURE_HEADER_BOX,
    side_claim_button_box=WIN_SIDE_CLAIM_BUTTON_BOX,
    popup_claim_button_box=WIN_POPUP_CLAIM_BUTTON_BOX,
    reward_overlay_box=WIN_REWARD_OVERLAY_BOX,
)


def get_window_text(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def get_class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def get_window_rect(hwnd: int) -> Rect | None:
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return Rect(rect.left, rect.top, rect.right, rect.bottom)


def get_client_rect_on_screen(hwnd: int) -> Rect | None:
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    top_left = wintypes.POINT(rect.left, rect.top)
    bottom_right = wintypes.POINT(rect.right, rect.bottom)
    if not user32.ClientToScreen(hwnd, ctypes.byref(top_left)):
        return None
    if not user32.ClientToScreen(hwnd, ctypes.byref(bottom_right)):
        return None
    return Rect(top_left.x, top_left.y, bottom_right.x, bottom_right.y)


def get_emulator_content_rect(hwnd: int) -> Rect | None:
    client = get_client_rect_on_screen(hwnd) or get_window_rect(hwnd)
    if client is None or client.width <= 0 or client.height <= 0:
        return client

    scale = min(client.width / ADB_REF_WIDTH, client.height / ADB_REF_HEIGHT)
    content_width = max(1, round(ADB_REF_WIDTH * scale))
    content_height = max(1, round(ADB_REF_HEIGHT * scale))
    left = client.left + round((client.width - content_width) / 2)
    # MuMu's client area includes its top toolbar, while ADB screenshots start at
    # the Android game surface. The game surface is aligned to the bottom.
    top = client.bottom - content_height
    return Rect(left, top, left + content_width, top + content_height)


def get_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def get_process_info(pid: int) -> tuple[str, str]:
    if psutil is None:
        return "", ""
    try:
        proc = psutil.Process(pid)
        return proc.name(), proc.exe()
    except Exception:
        return "", ""


def run_hidden(
    args: list[str],
    timeout: float = 10.0,
    text: bool = True,
) -> subprocess.CompletedProcess:
    kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "timeout": timeout,
        "creationflags": CREATE_NO_WINDOW,
    }
    if text:
        kwargs.update({"encoding": "utf-8", "errors": "ignore"})
    return subprocess.run(args, **kwargs)


def extract_json(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("输出中没有 JSON 对象")
    return json.loads(text[start : end + 1])


def load_mumu_info(force: bool = False) -> dict[int, dict]:
    global _mumu_info_cache, _mumu_info_cache_time

    now = time.monotonic()
    if not force and _mumu_info_cache and now - _mumu_info_cache_time < 4.0:
        return _mumu_info_cache
    if not MUMU_MANAGER_EXE.exists():
        return _mumu_info_cache

    try:
        result = run_hidden(
            [str(MUMU_MANAGER_EXE), "info", "--vmindex", "all"],
            timeout=8.0,
            text=True,
        )
        if result.returncode != 0 and not result.stdout.strip():
            return _mumu_info_cache
        raw = extract_json(result.stdout)
    except Exception:
        return _mumu_info_cache

    by_hwnd: dict[int, dict] = {}
    for index, item in raw.items():
        hwnd_text = str(item.get("main_wnd", "")).strip()
        if not hwnd_text:
            continue
        try:
            hwnd = int(hwnd_text, 16)
        except ValueError:
            continue

        adb_port = item.get("adb_port")
        adb_serial = ""
        if adb_port:
            adb_serial = f"127.0.0.1:{int(adb_port)}"

        by_hwnd[hwnd] = {
            "vm_index": str(item.get("index", index)),
            "adb_port": int(adb_port) if adb_port else None,
            "adb_serial": adb_serial,
            "name": str(item.get("name", "")),
            "player_state": str(item.get("player_state", "")),
        }

    _mumu_info_cache = by_hwnd
    _mumu_info_cache_time = now
    return by_hwnd


def ensure_adb_connected(serial: str, force: bool = False) -> None:
    if not serial:
        raise RuntimeError("目标窗口没有可用的 ADB serial")
    if not force and serial in _adb_connected:
        return
    if not MUMU_ADB_EXE.exists():
        raise RuntimeError(f"找不到 MuMu adb.exe：{MUMU_ADB_EXE}")

    if force:
        _adb_connected.discard(serial)
        run_hidden([str(MUMU_ADB_EXE), "disconnect", serial], timeout=5.0, text=True)

    result = run_hidden([str(MUMU_ADB_EXE), "connect", serial], timeout=10.0, text=True)
    combined = f"{result.stdout}\n{result.stderr}".lower()
    if result.returncode != 0 and "connected" not in combined and "already connected" not in combined:
        raise RuntimeError(f"ADB 连接失败：{combined.strip()}")

    state = run_hidden([str(MUMU_ADB_EXE), "-s", serial, "get-state"], timeout=6.0, text=True)
    if state.stdout.strip() != "device":
        raise RuntimeError(f"ADB 状态异常：{serial} -> {state.stdout.strip() or state.stderr.strip()}")
    _adb_connected.add(serial)


def adb_screencap(serial: str) -> Image.Image:
    last_error = ""
    for attempt in range(2):
        ensure_adb_connected(serial, force=attempt > 0)
        result = run_hidden(
            [str(MUMU_ADB_EXE), "-s", serial, "exec-out", "screencap", "-p"],
            timeout=15.0,
            text=False,
        )
        if result.returncode == 0 and result.stdout:
            return Image.open(io.BytesIO(result.stdout)).convert("RGB")
        last_error = (
            result.stderr.decode("utf-8", "ignore")
            if isinstance(result.stderr, bytes)
            else str(result.stderr)
        ).strip()
        _adb_connected.discard(serial)
        time.sleep(0.2)
    raise RuntimeError(f"ADB 截图失败：{last_error}")


def adb_tap(serial: str, x: int, y: int) -> None:
    last_error = ""
    for attempt in range(2):
        ensure_adb_connected(serial, force=attempt > 0)
        result = run_hidden(
            [str(MUMU_ADB_EXE), "-s", serial, "shell", "input", "tap", str(int(x)), str(int(y))],
            timeout=6.0,
            text=True,
        )
        if result.returncode == 0:
            return
        last_error = (result.stderr.strip() or result.stdout.strip())
        _adb_connected.discard(serial)
        time.sleep(0.2)
    raise RuntimeError(f"ADB 点击失败：{last_error}")


def is_alive_window(hwnd: int) -> bool:
    return bool(hwnd and user32.IsWindow(hwnd))


def enum_mumu_windows() -> list[TargetWindow]:
    windows: list[TargetWindow] = []
    info_by_hwnd = load_mumu_info()

    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetWindow(hwnd, GW_OWNER):
            return True

        rect = get_window_rect(hwnd)
        if rect is None or rect.width < 300 or rect.height < 500:
            return True

        pid = get_pid(hwnd)
        process_name, exe_path = get_process_info(pid)
        class_name = get_class_name(hwnd)
        title = get_window_text(hwnd)
        mumu_info = info_by_hwnd.get(int(hwnd), {})

        if process_name not in MUMU_PROCESS_NAMES:
            return True
        if MUMU_WINDOW_CLASS_KEYWORD not in class_name:
            return True
        if not title or title == "MuMuNxDevice":
            return True

        windows.append(
            TargetWindow(
                hwnd=int(hwnd),
                pid=pid,
                title=title,
                class_name=class_name,
                process_name=process_name,
                exe_path=exe_path,
                rect=rect,
                vm_index=str(mumu_info.get("vm_index", "")),
                adb_serial=str(mumu_info.get("adb_serial", "")),
                adb_port=mumu_info.get("adb_port"),
            )
        )
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return sorted(windows, key=lambda w: (w.rect.left, w.rect.top, w.title))


def foreground_root() -> int:
    hwnd = int(user32.GetForegroundWindow())
    if not hwnd:
        return 0
    root = int(user32.GetAncestor(hwnd, GA_ROOT))
    return root or hwnd


def find_top_window_by_pid_and_title(pid: int, title_text: str) -> int:
    found: list[int] = []

    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        if get_pid(hwnd) == pid and get_window_text(hwnd) == title_text:
            found.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return found[0] if found else 0


def tk_top_hwnd(widget: tk.Misc) -> int:
    widget.update_idletasks()
    hwnd = int(user32.GetAncestor(int(widget.winfo_id()), GA_ROOT))
    return hwnd or int(widget.winfo_id())


def make_click_through(hwnd: int) -> None:
    if not hwnd:
        return
    style = int(get_window_long(hwnd, GWL_EXSTYLE))
    style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
    set_window_long(hwnd, GWL_EXSTYLE, style)


def choose_default_window(windows: list[TargetWindow]) -> TargetWindow | None:
    if not windows:
        return None
    root = foreground_root()
    for window in windows:
        if window.hwnd == root:
            return window
    return windows[0]


def restore_and_focus(hwnd: int) -> None:
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.2)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.25)


def click_screen(x: int, y: int) -> None:
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.06)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
    time.sleep(0.05)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)
    time.sleep(0.18)


def click_relative(hwnd: int, rel_x: float, rel_y: float) -> None:
    rect = get_window_rect(hwnd)
    if rect is None:
        raise RuntimeError("目标窗口已经不存在")
    x = rect.left + round(rect.width * rel_x)
    y = rect.top + round(rect.height * rel_y)
    click_screen(x, y)


def capture_window(hwnd: int) -> Image.Image:
    rect = get_window_rect(hwnd)
    if rect is None:
        raise RuntimeError("目标窗口已经不存在")
    return ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom)).convert("RGB")


def capture_target(window: TargetWindow) -> tuple[Image.Image, ScreenProfile]:
    if window.adb_serial:
        return adb_screencap(window.adb_serial), ADB_PROFILE
    restore_and_focus(window.hwnd)
    return capture_window(window.hwnd), WINDOW_PROFILE


def tap_target(window: TargetWindow, action: str) -> None:
    if window.adb_serial:
        x, y = ADB_TAP_POINTS[action]
        adb_tap(window.adb_serial, x, y)
        time.sleep(0.18)
        return
    rel_x, rel_y = WINDOW_CLICK_POINTS[action]
    restore_and_focus(window.hwnd)
    click_relative(window.hwnd, rel_x, rel_y)


def tap_point(window: TargetWindow, x: int, y: int) -> None:
    if window.adb_serial:
        adb_tap(window.adb_serial, x, y)
        time.sleep(0.18)
        return
    click_relative(window.hwnd, x / 720, y / 1280)


def adb_point_to_image(image: Image.Image, x: int, y: int) -> tuple[int, int]:
    width, height = image.size
    px = max(0, min(width - 1, round(x * width / ADB_REF_WIDTH)))
    py = max(0, min(height - 1, round(y * height / ADB_REF_HEIGHT)))
    return px, py


def adb_box_to_image(image: Image.Image, box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x1, y1 = adb_point_to_image(image, box[0], box[1])
    x2, y2 = adb_point_to_image(image, box[2], box[3])
    left = min(x1, x2)
    top = min(y1, y2)
    right = max(left + 1, max(x1, x2))
    bottom = max(top + 1, max(y1, y2))
    return left, top, right, bottom


def crop_adb_box(image: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    return image.crop(adb_box_to_image(image, box)).convert("RGB")


def rgb_distance(color: tuple[int, int, int], target: tuple[int, int, int]) -> int:
    return max(abs(color[index] - target[index]) for index in range(3))


def color_near(color: tuple[int, int, int], target: tuple[int, int, int], tolerance: int) -> bool:
    return rgb_distance(color, target) <= tolerance


def adb_box_ratio(image: Image.Image, box: tuple[int, int, int, int], predicate) -> float:
    crop = crop_adb_box(image, box)
    return pixel_density(crop, predicate)


def adb_box_average(image: Image.Image, box: tuple[int, int, int, int]) -> tuple[float, float, float]:
    crop = crop_adb_box(image, box)
    total = crop.size[0] * crop.size[1]
    if total <= 0:
        return (0.0, 0.0, 0.0)
    red_total = green_total = blue_total = 0
    for red, green, blue in crop.getdata():
        red_total += red
        green_total += green
        blue_total += blue
    return (red_total / total, green_total / total, blue_total / total)


def adb_box_average_near(
    image: Image.Image,
    box: tuple[int, int, int, int],
    target: tuple[int, int, int],
    tolerance: int,
) -> bool:
    average = adb_box_average(image, box)
    return color_near((round(average[0]), round(average[1]), round(average[2])), target, tolerance)


def adb_color_block_hits(
    image: Image.Image,
    boxes: list[tuple[int, int, int, int]],
    predicate,
    min_ratio: float,
) -> int:
    return sum(1 for box in boxes if adb_box_ratio(image, box, predicate) >= min_ratio)


def crop_relative(image: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    width, height = image.size
    left = max(0, min(width, round(width * box[0])))
    top = max(0, min(height, round(height * box[1])))
    right = max(left + 1, min(width, round(width * box[2])))
    bottom = max(top + 1, min(height, round(height * box[3])))
    return image.crop((left, top, right, bottom)).convert("RGB")


def pixel_density(image: Image.Image, predicate) -> float:
    total = image.size[0] * image.size[1]
    if total <= 0:
        return 0.0
    hits = 0
    for red, green, blue in image.getdata():
        if predicate(red, green, blue):
            hits += 1
    return hits / total


def green_button_density(image: Image.Image, box: tuple[float, float, float, float]) -> float:
    crop = crop_relative(image, box)
    return pixel_density(
        crop,
        lambda r, g, b: g >= 135 and r <= 105 and b <= 145 and g >= r + 45 and g >= b + 25,
    )


def claim_widget_density(image: Image.Image, box: tuple[float, float, float, float]) -> float:
    crop = crop_relative(image, box)
    return pixel_density(
        crop,
        lambda r, g, b: (
            95 <= r <= 185
            and 95 <= g <= 185
            and 95 <= b <= 195
            and abs(r - g) <= 38
            and abs(g - b) <= 48
        )
        or (r >= 175 and g >= 175 and b >= 175),
    )


def reward_overlay_density(image: Image.Image, box: tuple[float, float, float, float]) -> float:
    crop = crop_relative(image, box)
    return pixel_density(
        crop,
        lambda r, g, b: 40 <= r <= 140
        and 165 <= g <= 255
        and 195 <= b <= 255
        and g >= r + 70
        and b >= r + 75,
    )


def adventure_header_density(image: Image.Image, box: tuple[float, float, float, float]) -> float:
    crop = crop_relative(image, box)
    return pixel_density(
        crop,
        lambda r, g, b: 15 <= r <= 70
        and 45 <= g <= 125
        and 85 <= b <= 175
        and b >= r + 45
        and b >= g + 15,
    )


def nav_blue_pixel(red: int, green: int, blue: int) -> bool:
    return (
        color_near((red, green, blue), NAV_BLUE, 30)
        and blue >= red + 45
        and blue >= green + 15
    )


def icon_white_pixel(red: int, green: int, blue: int) -> bool:
    return red >= 210 and green >= 210 and blue >= 215


def button_blue_pixel(red: int, green: int, blue: int) -> bool:
    return (
        color_near((red, green, blue), ADVENTURE_BUTTON_BLUE, 55)
        and 35 <= red <= 135
        and 115 <= green <= 215
        and 165 <= blue <= 255
        and blue >= red + 55
        and blue >= green + 20
    )


def header_blue_pixel(red: int, green: int, blue: int) -> bool:
    return (
        color_near((red, green, blue), ADVENTURE_HEADER_BLUE, 32)
        and red <= 55
        and 45 <= green <= 105
        and 80 <= blue <= 155
        and blue >= red + 45
        and blue >= green + 15
    )


def claim_green_pixel(red: int, green: int, blue: int) -> bool:
    return (
        15 <= red <= 115
        and 130 <= green <= 220
        and 20 <= blue <= 155
        and green >= red + 40
        and green >= blue + 20
    )


def gold_brown_pixel(red: int, green: int, blue: int) -> bool:
    return (
        125 <= red <= 255
        and 70 <= green <= 195
        and 0 <= blue <= 125
        and red >= green + 20
        and green >= blue + 20
    ) or (
        80 <= red <= 180
        and 45 <= green <= 130
        and 0 <= blue <= 90
        and red >= green + 15
        and green >= blue + 10
    )


def adventure_stage_pixel(red: int, green: int, blue: int) -> bool:
    orange = red >= 175 and 85 <= green <= 180 and blue <= 90 and red >= green + 35
    green_marker = 25 <= red <= 115 and 115 <= green <= 230 and 35 <= blue <= 160 and green >= red + 35
    red_marker = red >= 145 and green <= 105 and blue <= 115 and red >= green + 40 and red >= blue + 40
    return orange or green_marker or red_marker


def adventure_chest_pixel(red: int, green: int, blue: int) -> bool:
    return gold_brown_pixel(red, green, blue) or claim_green_pixel(red, green, blue)


def sampled_green_button_visible(
    image: Image.Image,
    boxes: list[tuple[int, int, int, int]],
    min_hits: int,
) -> bool:
    return adb_color_block_hits(image, boxes, claim_green_pixel, 0.22) >= min_hits


def legacy_explore_tab_visible(image: Image.Image, profile: ScreenProfile) -> bool:
    crop = crop_relative(image, profile.explore_tab_box)
    blue_density = pixel_density(
        crop,
        lambda r, g, b: 45 <= r <= 115
        and 75 <= g <= 155
        and 120 <= b <= 215
        and b >= r + 35
        and b >= g + 15,
    )
    white_density = pixel_density(crop, lambda r, g, b: r >= 205 and g >= 210 and b >= 215)
    deep_blue_density = pixel_density(
        crop,
        lambda r, g, b: r <= 45 and 35 <= g <= 105 and 75 <= b <= 170 and b >= r + 45,
    )
    nav_crop = crop_relative(image, (0.0, 0.915, 1.0, 0.995))
    nav_blue_density = pixel_density(
        nav_crop,
        lambda r, g, b: 45 <= r <= 115
        and 75 <= g <= 155
        and 120 <= b <= 215
        and b >= r + 35
        and b >= g + 15,
    )
    nav_deep_blue_density = pixel_density(
        nav_crop,
        lambda r, g, b: r <= 45 and 35 <= g <= 105 and 75 <= b <= 170 and b >= r + 45,
    )
    return (
        blue_density >= 0.58
        and white_density >= 0.035
        and deep_blue_density < 0.05
        and nav_blue_density >= 0.55
        and nav_deep_blue_density < 0.04
    )


def explore_tab_visible(image: Image.Image, profile: ScreenProfile) -> bool:
    if profile is not ADB_PROFILE:
        return legacy_explore_tab_visible(image, profile)

    nav_hits = 0
    for box in EXPLORE_NAV_BLOCKS:
        if adb_box_ratio(image, box, nav_blue_pixel) >= 0.75 or adb_box_average_near(image, box, NAV_BLUE, 24):
            nav_hits += 1

    sword_hits = adb_color_block_hits(image, EXPLORE_SWORD_BLOCKS, icon_white_pixel, 0.25)

    return nav_hits >= 3 and sword_hits >= 3


def adventure_page_visible(image: Image.Image, profile: ScreenProfile) -> bool:
    if profile is not ADB_PROFILE:
        return adventure_header_density(image, profile.adventure_header_box) >= 0.30

    header_hits = adb_color_block_hits(image, ADVENTURE_HEADER_BLOCKS, header_blue_pixel, 0.60)
    back_white_ratio = adb_box_ratio(image, ADVENTURE_BACK_BLOCK, icon_white_pixel)
    button_hits = adb_color_block_hits(image, ADVENTURE_ACTION_BUTTON_BLOCKS, button_blue_pixel, 0.45)
    stage_hits = adb_color_block_hits(image, ADVENTURE_STAGE_MARKER_BLOCKS, adventure_stage_pixel, 0.05)
    chest_ratio = adb_box_ratio(image, ADVENTURE_CHEST_BLOCK, adventure_chest_pixel)

    return header_hits >= 1 and back_white_ratio >= 0.035 and button_hits >= 1 and stage_hits >= 1 and chest_ratio >= 0.06


def analyze_screen(image: Image.Image, profile: ScreenProfile = ADB_PROFILE) -> Detection:
    side_green_density = green_button_density(image, profile.side_claim_button_box)
    popup_green_density = green_button_density(image, profile.popup_claim_button_box)
    claim_density = claim_widget_density(image, profile.side_claim_button_box)
    reward_density = reward_overlay_density(image, profile.reward_overlay_box)
    header_density = adventure_header_density(image, profile.adventure_header_box)
    adventure_visible = adventure_page_visible(image, profile)
    side_green_visible = (
        sampled_green_button_visible(image, SIDE_CLAIM_GREEN_BLOCKS, 2)
        if profile is ADB_PROFILE
        else side_green_density >= 0.020
    )
    popup_green_visible = (
        sampled_green_button_visible(image, POPUP_CLAIM_GREEN_BLOCKS, 2)
        if profile is ADB_PROFILE
        else popup_green_density >= 0.080
    )
    return Detection(
        explore_tab_visible=explore_tab_visible(image, profile),
        adventure_page_visible=adventure_visible,
        claim_widget_visible=adventure_visible and (claim_density >= 0.15 or side_green_density >= 0.02),
        side_claim_green=side_green_visible,
        popup_claim_green=popup_green_visible,
        reward_overlay_visible=reward_density >= 0.080,
        side_green_density=side_green_density,
        popup_green_density=popup_green_density,
        claim_widget_density=claim_density,
        reward_overlay_density=reward_density,
        adventure_header_density=header_density,
    )


def adb_box(x1: int, y1: int, x2: int, y2: int) -> tuple[float, float, float, float]:
    return (x1 / 720, y1 / 1280, x2 / 720, y2 / 1280)


def relative_box_to_adb(box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    return (
        round(box[0] * ADB_REF_WIDTH),
        round(box[1] * ADB_REF_HEIGHT),
        round(box[2] * ADB_REF_WIDTH),
        round(box[3] * ADB_REF_HEIGHT),
    )


DebugRange = tuple[str, str, tuple[int, int, int, int]]


@dataclass(frozen=True)
class BuildingActionCandidate:
    center: tuple[int, int]
    box: tuple[int, int, int, int]
    area: int
    white_ratio: float
    blue_ratio: float


def debug_ranges_for_step(
    step: str,
    unit_label: str = "",
    row_y: int | None = None,
) -> list[DebugRange]:
    ranges: list[tuple[str, str, tuple[int, int, int, int]]] = []

    if step == "home":
        return [
            ("主界面返回", "#a78bfa", (0, 95, 75, 155)),
            ("主城切换图标", "#f59e0b", MAIN_CITY_TOGGLE_ICON_BLOCK),
        ]

    if step == "explore_entry":
        for index, box in enumerate(EXPLORE_NAV_BLOCKS, start=1):
            ranges.append((f"探险底色{index}", "#38bdf8", box))
        for index, box in enumerate(EXPLORE_SWORD_BLOCKS, start=1):
            ranges.append((f"双剑白边{index}", "#facc15", box))
        return ranges

    if step == "adventure_page":
        for index, box in enumerate(ADVENTURE_HEADER_BLOCKS, start=1):
            ranges.append((f"探险页头{index}", "#fde047", box))
        ranges.append(("探险返回", "#fde047", ADVENTURE_BACK_BLOCK))
        for index, box in enumerate(ADVENTURE_ACTION_BUTTON_BLOCKS, start=1):
            ranges.append((f"探险按钮{index}", "#f97316", box))
        for index, box in enumerate(ADVENTURE_STAGE_MARKER_BLOCKS, start=1):
            ranges.append((f"探险节点{index}", "#fb923c", box))
        ranges.append(("探险宝箱", "#fb923c", ADVENTURE_CHEST_BLOCK))
        return ranges

    if step == "side_claim":
        return [(f"侧边领取{index}", "#22c55e", box) for index, box in enumerate(SIDE_CLAIM_GREEN_BLOCKS, start=1)]

    if step == "popup_claim":
        return [(f"弹窗领取{index}", "#16a34a", box) for index, box in enumerate(POPUP_CLAIM_GREEN_BLOCKS, start=1)]

    if step == "reward":
        return [("奖励弹层", "#06b6d4", relative_box_to_adb(ADB_REWARD_OVERLAY_BOX))]

    if step == "queue_panel":
        ranges.append(("队列面板", "#8b5cf6", (0, 220, 445, 885)))
        for _unit_key, label, y in TRAIN_UNITS:
            ranges.append((f"{label}状态", "#c084fc", (375, y - 34, 430, y + 34)))
            ranges.append((f"{label}倒计时", "#c084fc", (75, y - 24, 370, y + 24)))
        return ranges

    if step == "unit_row" and row_y is not None:
        label = unit_label or "士兵"
        return [
            (f"{label}状态", "#c084fc", (375, row_y - 34, 430, row_y + 34)),
            (f"{label}倒计时", "#c084fc", (75, row_y - 24, 370, row_y + 24)),
        ]

    if step == "building_train":
        return [
            ("训练按钮扫描区", "#fb7185", BUILDING_ACTION_SCAN_BOX),
            ("手势扫描区", "#f59e0b", BUILDING_GUIDE_HAND_SCAN_BOX),
        ]

    if step == "soldier_page":
        return [
            ("训练页返回", "#60a5fa", SOLDIER_PAGE_BACK_BLOCK),
            ("盾兵营标签", "#60a5fa", SOLDIER_SELECTED_TAB_BLOCK),
            ("矛兵营标签", "#60a5fa", SOLDIER_SPEAR_TAB_BLOCK),
            ("射手营标签", "#60a5fa", SOLDIER_ARCHER_TAB_BLOCK),
            ("训练页按钮区", "#60a5fa", SOLDIER_BOTTOM_BUTTON_BLOCK),
        ]

    if step == "train_levels":
        for x, label in TRAIN_LEVEL_CANDIDATES:
            ranges.append((f"等级{label}边框", "#e879f9", (max(0, x - 45), 623, min(ADB_REF_WIDTH, x + 45), 715)))
        ranges.append(("训练页按钮区", "#60a5fa", (360, 1060, 705, 1180)))
        return ranges

    return ranges


def box_density(image: Image.Image, box: tuple[float, float, float, float], predicate) -> float:
    return pixel_density(crop_relative(image, box), predicate)


def queue_panel_visible(image: Image.Image) -> bool:
    density = box_density(
        image,
        adb_box(0, 220, 445, 885),
        lambda r, g, b: 15 <= r <= 75
        and 35 <= g <= 95
        and 65 <= b <= 140
        and b >= r + 30,
    )
    known_rows = sum(1 for _unit_key, _unit_label, row_y in TRAIN_UNITS if unit_row_state(image, row_y) != "unknown")
    return density >= 0.35 and known_rows >= 2


def main_return_icon_visible(image: Image.Image) -> bool:
    # Main map/city screens show a small rounded return icon below the avatar.
    # Regular subpages show a large back arrow at the very top-left instead.
    icon_box = adb_box(0, 95, 75, 155)
    white_density = box_density(image, icon_box, lambda r, g, b: r >= 205 and g >= 210 and b >= 215)
    blue_density = box_density(
        image,
        icon_box,
        lambda r, g, b: 65 <= r <= 150
        and 95 <= g <= 185
        and 135 <= b <= 235
        and b >= r + 35,
    )
    return white_density >= 0.06 and blue_density >= 0.08


def main_city_toggle_visible(image: Image.Image) -> bool:
    icon_white_ratio = adb_box_ratio(image, MAIN_CITY_TOGGLE_ICON_BLOCK, icon_white_pixel)
    icon_gold_ratio = adb_box_ratio(image, MAIN_CITY_TOGGLE_ICON_BLOCK, gold_brown_pixel)
    icon_nav_ratio = adb_box_ratio(image, MAIN_CITY_TOGGLE_ICON_BLOCK, nav_blue_pixel)
    block_nav_ratio = adb_box_ratio(image, MAIN_CITY_TOGGLE_BLOCK, nav_blue_pixel)

    return (
        icon_white_ratio >= 0.12
        and icon_gold_ratio >= 0.035
        and (icon_nav_ratio >= 0.10 or block_nav_ratio >= 0.22)
    )


def main_screen_visible(image: Image.Image) -> bool:
    return main_return_icon_visible(image) and main_city_toggle_visible(image)


def unit_upgrade_blocked_pixel(red: int, green: int, blue: int) -> bool:
    return (
        160 <= red <= 255
        and 70 <= green <= 185
        and blue <= 115
        and red >= green + 35
        and green >= blue + 15
    )


def unit_row_state(image: Image.Image, row_y: int) -> str:
    action_box = adb_box(375, row_y - 34, 430, row_y + 34)
    progress_box = adb_box(75, row_y - 24, 370, row_y + 24)
    status_text_box = adb_box(155, row_y - 26, 355, row_y + 28)

    black_density = box_density(image, progress_box, lambda r, g, b: r <= 45 and g <= 50 and b <= 60)
    upgrade_density = box_density(image, status_text_box, unit_upgrade_blocked_pixel)
    green_density = box_density(
        image,
        action_box,
        lambda r, g, b: g >= 145 and r <= 95 and b <= 145 and g >= r + 55 and g >= b + 25,
    )
    blue_density = box_density(
        image,
        action_box,
        lambda r, g, b: 35 <= r <= 130
        and 105 <= g <= 220
        and 145 <= b <= 255
        and b >= r + 55,
    )

    if black_density >= 0.16:
        return "busy"
    if upgrade_density >= 0.025:
        return "blocked"
    if green_density >= 0.12:
        return "ready"
    if blue_density >= 0.12:
        return "idle"
    return "unknown"


def soldier_tab_selected_pixel(red: int, green: int, blue: int) -> bool:
    return (
        red >= 175
        and green >= 195
        and blue >= 205
        and blue >= red - 10
        and blue >= green - 30
    )


def soldier_tab_blue_pixel(red: int, green: int, blue: int) -> bool:
    return (
        65 <= red <= 150
        and 100 <= green <= 195
        and 145 <= blue <= 245
        and blue >= red + 40
        and blue >= green + 5
    )


def soldier_button_pixel(red: int, green: int, blue: int) -> bool:
    yellow_button = red >= 190 and 105 <= green <= 195 and blue <= 95 and red >= green + 25
    blue_button = soldier_tab_blue_pixel(red, green, blue)
    return yellow_button or blue_button


def soldier_page_visible(image: Image.Image) -> bool:
    back_ratio = adb_box_ratio(image, SOLDIER_PAGE_BACK_BLOCK, icon_white_pixel)
    selected_tab_ratio = adb_box_ratio(image, SOLDIER_SELECTED_TAB_BLOCK, soldier_tab_selected_pixel)
    spear_tab_ratio = adb_box_ratio(image, SOLDIER_SPEAR_TAB_BLOCK, soldier_tab_blue_pixel)
    archer_tab_ratio = adb_box_ratio(image, SOLDIER_ARCHER_TAB_BLOCK, soldier_tab_blue_pixel)
    button_ratio = adb_box_ratio(image, SOLDIER_BOTTOM_BUTTON_BLOCK, soldier_button_pixel)

    return (
        back_ratio >= 0.030
        and selected_tab_ratio >= 0.45
        and spear_tab_ratio >= 0.45
        and archer_tab_ratio >= 0.42
        and button_ratio >= 0.22
    )


def soldier_training_started_visible(image: Image.Image) -> bool:
    panel_density = box_density(
        image,
        adb_box(50, 815, 680, 1045),
        lambda r, g, b: 35 <= r <= 95
        and 75 <= g <= 160
        and 120 <= b <= 220
        and b >= r + 55,
    )
    return soldier_page_visible(image) and panel_density >= 0.25


def building_action_blue_pixel(red: int, green: int, blue: int) -> bool:
    return (
        55 <= red <= 140
        and 105 <= green <= 190
        and 165 <= blue <= 245
        and blue >= red + 60
        and blue >= green + 18
        and green >= red + 8
    )


def action_icon_white_pixel(red: int, green: int, blue: int) -> bool:
    return red >= 205 and green >= 205 and blue >= 210 and max(red, green, blue) - min(red, green, blue) <= 65


def guide_hand_pixel(red: int, green: int, blue: int) -> bool:
    return (
        145 <= red <= 245
        and 85 <= green <= 190
        and 45 <= blue <= 155
        and red >= green + 25
        and green >= blue + 5
    )


def image_point_to_adb(image: Image.Image, x: int, y: int) -> tuple[int, int]:
    width, height = image.size
    adb_x = max(0, min(ADB_REF_WIDTH - 1, round(x * ADB_REF_WIDTH / width)))
    adb_y = max(0, min(ADB_REF_HEIGHT - 1, round(y * ADB_REF_HEIGHT / height)))
    return adb_x, adb_y


def find_guided_building_train_action(image: Image.Image) -> tuple[int, int] | None:
    if queue_panel_visible(image) or soldier_page_visible(image) or not main_screen_visible(image):
        return None
    if image.mode != "RGB":
        image = image.convert("RGB")

    left, top, right, bottom = adb_box_to_image(image, BUILDING_GUIDE_HAND_SCAN_BOX)
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        return None

    pixels = image.load()
    mask = bytearray(width * height)
    for y in range(height):
        row_offset = y * width
        for x in range(width):
            if guide_hand_pixel(*pixels[left + x, top + y]):
                mask[row_offset + x] = 1

    seen = bytearray(width * height)
    image_width, image_height = image.size
    area_scale = (ADB_REF_WIDTH * ADB_REF_HEIGHT) / (image_width * image_height)
    best: tuple[int, tuple[int, int, int, int]] | None = None

    for start_y in range(height):
        for start_x in range(width):
            start_index = start_y * width + start_x
            if not mask[start_index] or seen[start_index]:
                continue

            queue = [(start_x, start_y)]
            seen[start_index] = 1
            cursor = 0
            count = 0
            min_x = max_x = start_x
            min_y = max_y = start_y

            while cursor < len(queue):
                current_x, current_y = queue[cursor]
                cursor += 1
                count += 1
                min_x = min(min_x, current_x)
                max_x = max(max_x, current_x)
                min_y = min(min_y, current_y)
                max_y = max(max_y, current_y)

                for next_y in range(current_y - 1, current_y + 2):
                    if next_y < 0 or next_y >= height:
                        continue
                    for next_x in range(current_x - 1, current_x + 2):
                        if next_x < 0 or next_x >= width or (next_x == current_x and next_y == current_y):
                            continue
                        next_index = next_y * width + next_x
                        if mask[next_index] and not seen[next_index]:
                            seen[next_index] = 1
                            queue.append((next_x, next_y))

            adb_area = round(count * area_scale)
            comp_left, comp_top = image_point_to_adb(image, left + min_x, top + min_y)
            comp_right, comp_bottom = image_point_to_adb(image, left + max_x + 1, top + max_y + 1)
            comp_width = comp_right - comp_left
            comp_height = comp_bottom - comp_top

            if not (2500 <= adb_area <= 12000 and 55 <= comp_width <= 150 and 85 <= comp_height <= 210):
                continue
            if best is None or adb_area > best[0]:
                best = (adb_area, (comp_left, comp_top, comp_right, comp_bottom))

    if best is None:
        return None

    _area, (comp_left, _comp_top, comp_right, comp_bottom) = best
    comp_width = comp_right - comp_left
    comp_height = comp_bottom - _comp_top
    target_x = comp_left + round(comp_width * 0.18)
    target_y = min(comp_bottom + round(comp_height * 0.22), 870)
    target_y = max(target_y, _comp_top + round(comp_height * 0.75))
    target_x = max(BUILDING_ACTION_SCAN_BOX[0], min(BUILDING_ACTION_SCAN_BOX[2], target_x))
    target_y = max(BUILDING_ACTION_SCAN_BOX[1], min(BUILDING_ACTION_SCAN_BOX[3], target_y))
    return target_x, target_y


def building_action_candidates(image: Image.Image) -> list[BuildingActionCandidate]:
    if image.mode != "RGB":
        image = image.convert("RGB")

    left, top, right, bottom = adb_box_to_image(image, BUILDING_ACTION_SCAN_BOX)
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        return []

    pixels = image.load()
    mask = bytearray(width * height)
    for y in range(height):
        row_offset = y * width
        for x in range(width):
            if building_action_blue_pixel(*pixels[left + x, top + y]):
                mask[row_offset + x] = 1

    seen = bytearray(width * height)
    candidates: list[BuildingActionCandidate] = []
    image_width, image_height = image.size
    area_scale = (ADB_REF_WIDTH * ADB_REF_HEIGHT) / (image_width * image_height)
    pad_x = max(2, round(14 * image_width / ADB_REF_WIDTH))
    pad_y = max(2, round(14 * image_height / ADB_REF_HEIGHT))

    for start_y in range(height):
        for start_x in range(width):
            start_index = start_y * width + start_x
            if not mask[start_index] or seen[start_index]:
                continue

            queue = [(start_x, start_y)]
            seen[start_index] = 1
            cursor = 0
            count = 0
            min_x = max_x = start_x
            min_y = max_y = start_y

            while cursor < len(queue):
                current_x, current_y = queue[cursor]
                cursor += 1
                count += 1
                min_x = min(min_x, current_x)
                max_x = max(max_x, current_x)
                min_y = min(min_y, current_y)
                max_y = max(max_y, current_y)

                for next_y in range(current_y - 1, current_y + 2):
                    if next_y < 0 or next_y >= height:
                        continue
                    for next_x in range(current_x - 1, current_x + 2):
                        if next_x < 0 or next_x >= width or (next_x == current_x and next_y == current_y):
                            continue
                        next_index = next_y * width + next_x
                        if mask[next_index] and not seen[next_index]:
                            seen[next_index] = 1
                            queue.append((next_x, next_y))

            adb_area = round(count * area_scale)
            comp_left, comp_top = image_point_to_adb(image, left + min_x, top + min_y)
            comp_right, comp_bottom = image_point_to_adb(image, left + max_x + 1, top + max_y + 1)
            comp_width = comp_right - comp_left
            comp_height = comp_bottom - comp_top

            if not (
                BUILDING_ACTION_MIN_AREA <= adb_area <= BUILDING_ACTION_MAX_AREA
                and 78 <= comp_width <= 122
                and 74 <= comp_height <= 112
            ):
                continue

            sample_left = max(0, left + min_x - pad_x)
            sample_top = max(0, top + min_y - pad_y)
            sample_right = min(image_width, left + max_x + 1 + pad_x)
            sample_bottom = min(image_height, top + max_y + 1 + pad_y)
            sample_total = max(1, (sample_right - sample_left) * (sample_bottom - sample_top))
            white_hits = 0
            blue_hits = 0
            for sample_y in range(sample_top, sample_bottom):
                for sample_x in range(sample_left, sample_right):
                    red, green, blue = pixels[sample_x, sample_y]
                    if action_icon_white_pixel(red, green, blue):
                        white_hits += 1
                    if building_action_blue_pixel(red, green, blue):
                        blue_hits += 1

            white_ratio = white_hits / sample_total
            blue_ratio = blue_hits / sample_total
            if white_ratio < BUILDING_ACTION_MIN_WHITE_RATIO or blue_ratio < BUILDING_ACTION_MIN_BLUE_RATIO:
                continue

            center_x, center_y = image_point_to_adb(
                image,
                left + (min_x + max_x + 1) // 2,
                top + (min_y + max_y + 1) // 2,
            )
            candidates.append(
                BuildingActionCandidate(
                    center=(center_x, center_y),
                    box=(comp_left, comp_top, comp_right, comp_bottom),
                    area=adb_area,
                    white_ratio=white_ratio,
                    blue_ratio=blue_ratio,
                )
            )

    return candidates


def find_building_train_action(image: Image.Image) -> tuple[int, int] | None:
    if queue_panel_visible(image) or soldier_page_visible(image) or not main_screen_visible(image):
        return None

    guided_action = find_guided_building_train_action(image)
    if guided_action is not None:
        return guided_action

    candidates = building_action_candidates(image)
    if not candidates:
        return None

    best = max(candidates, key=lambda candidate: (candidate.center[0], candidate.white_ratio, candidate.area))
    return best.center


def building_train_action_visible(image: Image.Image) -> bool:
    if find_building_train_action(image) is None:
        return False
    return True


def train_level_border_boxes(x: int) -> dict[str, tuple[int, int, int, int]]:
    return {
        "top": (x - 35, 623, x + 35, 646),
        "left": (x - 45, 645, x - 27, 715),
        "right": (x + 27, 645, x + 45, 715),
        "upper": (x - 42, 623, x + 42, 690),
    }


def train_level_border_white_pixel(red: int, green: int, blue: int) -> bool:
    return red >= 205 and green >= 205 and blue >= 210


def train_level_border_glow_pixel(red: int, green: int, blue: int) -> bool:
    return (
        120 <= red <= 225
        and 150 <= green <= 245
        and 180 <= blue <= 255
        and blue >= red + 5
        and green >= red - 20
    )


def train_level_border_gray_pixel(red: int, green: int, blue: int) -> bool:
    return 85 <= red <= 185 and 85 <= green <= 185 and 85 <= blue <= 185 and max(red, green, blue) - min(red, green, blue) <= 48


def train_level_available(image: Image.Image, x: int) -> bool:
    boxes = train_level_border_boxes(x)
    top_white = adb_box_ratio(image, boxes["top"], train_level_border_white_pixel)
    top_glow = adb_box_ratio(image, boxes["top"], train_level_border_glow_pixel)
    left_white = adb_box_ratio(image, boxes["left"], train_level_border_white_pixel)
    left_glow = adb_box_ratio(image, boxes["left"], train_level_border_glow_pixel)
    right_white = adb_box_ratio(image, boxes["right"], train_level_border_white_pixel)
    right_glow = adb_box_ratio(image, boxes["right"], train_level_border_glow_pixel)
    upper_gray = adb_box_ratio(image, boxes["upper"], train_level_border_gray_pixel)

    light_score = max(top_white, top_glow, left_white, left_glow, right_white, right_glow)
    return light_score >= 0.09 and upper_gray < 0.36


def highest_available_level_x(image: Image.Image) -> int | None:
    if main_screen_visible(image) or queue_panel_visible(image):
        return None

    best_x: int | None = None
    for x, _label in TRAIN_LEVEL_CANDIDATES:
        if x > 690:
            continue
        if train_level_available(image, x):
            best_x = x
    return best_x


def save_debug_capture(image: Image.Image, prefix: str) -> Path:
    DEBUG_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    path = DEBUG_DIR / f"{prefix}_{stamp}.png"
    image.save(path)
    return path


class App:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("MuMu 探险助手")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", False)
        self.root.configure(bg="#1f2937")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.target_by_label: dict[str, TargetWindow] = {}
        self.current_hwnd: int | None = None
        self.worker: threading.Thread | None = None
        self.debug_saves = tk.BooleanVar(value=False)
        self.target_var = tk.StringVar()
        self.status_var = tk.StringVar(value="正在扫描 MuMu 窗口...")

        self._drag_start: tuple[int, int] | None = None

        self.build_ui()
        self.refresh_targets(attach_default=True)
        self.follow_target()

    def build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        title_bar = tk.Frame(self.root, bg="#111827", height=30)
        title_bar.grid(row=0, column=0, sticky="ew")
        title_bar.grid_columnconfigure(1, weight=1)
        title_bar.bind("<ButtonPress-1>", self.start_drag)
        title_bar.bind("<B1-Motion>", self.drag_panel)

        title = tk.Label(
            title_bar,
            text="MuMu 探险助手",
            bg="#111827",
            fg="#f9fafb",
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        title.grid(row=0, column=0, padx=(10, 8), pady=5, sticky="w")
        title.bind("<ButtonPress-1>", self.start_drag)
        title.bind("<B1-Motion>", self.drag_panel)

        hint = tk.Label(
            title_bar,
            text=f"附加在目标窗口下方，高度约 {CONTROL_HEIGHT}px",
            bg="#111827",
            fg="#9ca3af",
            font=("Microsoft YaHei UI", 9),
        )
        hint.grid(row=0, column=1, pady=5, sticky="w")
        hint.bind("<ButtonPress-1>", self.start_drag)
        hint.bind("<B1-Motion>", self.drag_panel)

        close_btn = tk.Button(
            title_bar,
            text="×",
            command=self.close,
            bd=0,
            bg="#111827",
            fg="#f9fafb",
            activebackground="#991b1b",
            activeforeground="#ffffff",
            font=("Microsoft YaHei UI", 13, "bold"),
            width=3,
        )
        close_btn.grid(row=0, column=2, sticky="e")

        controls = tk.Frame(self.root, bg="#1f2937")
        controls.grid(row=1, column=0, sticky="ew", padx=10, pady=(9, 5))
        controls.columnconfigure(1, weight=1)

        tk.Label(
            controls,
            text="目标",
            bg="#1f2937",
            fg="#d1d5db",
            font=("Microsoft YaHei UI", 9),
        ).grid(row=0, column=0, padx=(0, 6), sticky="w")

        self.target_combo = ttk.Combobox(
            controls,
            textvariable=self.target_var,
            state="readonly",
            height=6,
        )
        self.target_combo.grid(row=0, column=1, sticky="ew")
        self.target_combo.bind("<<ComboboxSelected>>", self.on_target_selected)

        refresh_btn = tk.Button(
            controls,
            text="刷新",
            command=lambda: self.refresh_targets(attach_default=True),
            bg="#374151",
            fg="#f9fafb",
            activebackground="#4b5563",
            activeforeground="#ffffff",
            bd=0,
            padx=12,
            pady=4,
        )
        refresh_btn.grid(row=0, column=2, padx=(8, 0))

        actions = tk.Frame(self.root, bg="#1f2937")
        actions.grid(row=2, column=0, sticky="ew", padx=10)
        for idx in range(4):
            actions.columnconfigure(idx, weight=1)

        self.run_btn = tk.Button(
            actions,
            text="一键领取当前窗口",
            command=self.run_current,
            bg="#16a34a",
            fg="#ffffff",
            activebackground="#15803d",
            activeforeground="#ffffff",
            bd=0,
            padx=8,
            pady=8,
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        self.run_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.run_all_btn = tk.Button(
            actions,
            text="扫描全部窗口",
            command=self.run_all,
            bg="#2563eb",
            fg="#ffffff",
            activebackground="#1d4ed8",
            activeforeground="#ffffff",
            bd=0,
            padx=8,
            pady=8,
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        self.run_all_btn.grid(row=0, column=1, sticky="ew", padx=6)

        attach_btn = tk.Button(
            actions,
            text="重新附加",
            command=self.attach_selected,
            bg="#4b5563",
            fg="#ffffff",
            activebackground="#6b7280",
            activeforeground="#ffffff",
            bd=0,
            padx=8,
            pady=8,
        )
        attach_btn.grid(row=0, column=2, sticky="ew", padx=6)

        status = tk.Label(
            self.root,
            textvariable=self.status_var,
            bg="#111827",
            fg="#d1d5db",
            justify="left",
            anchor="nw",
            wraplength=600,
            font=("Microsoft YaHei UI", 9),
        )
        status.grid(row=3, column=0, sticky="nsew", padx=10, pady=(8, 10))

    def start_drag(self, event) -> None:
        self._drag_start = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def drag_panel(self, event) -> None:
        if self._drag_start is None:
            return
        dx, dy = self._drag_start
        self.root.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")

    def close(self) -> None:
        self.root.destroy()

    def log(self, text: str) -> None:
        now = datetime.now().strftime("%H:%M:%S")
        self.status_var.set(f"[{now}] {text}")

    def thread_log(self, text: str) -> None:
        self.root.after(0, lambda: self.log(text))

    def set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.run_btn.configure(state=state)
        self.run_all_btn.configure(state=state)

    def refresh_targets(self, attach_default: bool = False) -> list[TargetWindow]:
        windows = enum_mumu_windows()
        old_hwnd = self.current_hwnd
        self.target_by_label = {window.label: window for window in windows}
        labels = list(self.target_by_label)
        self.target_combo["values"] = labels

        selected_label = self.target_var.get()
        selected_still_exists = selected_label in self.target_by_label

        if attach_default or not selected_still_exists:
            default = None
            if old_hwnd is not None:
                default = next((w for w in windows if w.hwnd == old_hwnd), None)
            if default is None:
                default = choose_default_window(windows)
            if default is not None:
                self.current_hwnd = default.hwnd
                self.target_var.set(default.label)
                self.attach_to(default)
            elif not windows:
                self.current_hwnd = None
                self.target_var.set("")
                self.set_panel_geometry(520, CONTROL_HEIGHT, 200, 200)
                self.log(f"未发现 MuMu 目标窗口。默认安装路径提示：{MUMU_INSTALL_HINT}")

        if windows and not selected_still_exists and not attach_default:
            self.log(f"发现 {len(windows)} 个 MuMu 窗口，已附加到第一个。")
        return windows

    def on_target_selected(self, _event=None) -> None:
        self.attach_selected()

    def attach_selected(self) -> None:
        window = self.selected_window()
        if window is None:
            self.log("没有可附加的 MuMu 窗口。")
            return
        self.current_hwnd = window.hwnd
        self.attach_to(window)
        self.log(f"已附加：{window.title}")

    def attach_to(self, window: TargetWindow) -> None:
        rect = get_window_rect(window.hwnd) or window.rect
        screen_h = self.root.winfo_screenheight()
        left = rect.left
        top = rect.bottom
        if top + CONTROL_HEIGHT > screen_h:
            top = max(0, rect.top - CONTROL_HEIGHT)
        width = max(360, rect.width)
        self.set_panel_geometry(width, CONTROL_HEIGHT, left, top)

    def set_panel_geometry(self, width: int, height: int, left: int, top: int) -> None:
        self.root.geometry(f"{width}x{height}+{left}+{top}")
        self.root.update_idletasks()

        hwnd = find_top_window_by_pid_and_title(os.getpid(), self.root.title())
        if not hwnd:
            hwnd = int(user32.GetAncestor(int(self.root.winfo_id()), GA_ROOT))
        if not hwnd:
            hwnd = int(self.root.winfo_id())
        user32.SetWindowPos(hwnd, HWND_NOTOPMOST, left, top, width, height, SWP_NOACTIVATE)

    def selected_window(self) -> TargetWindow | None:
        label = self.target_var.get()
        window = self.target_by_label.get(label)
        if window is not None and is_alive_window(window.hwnd):
            fresh_rect = get_window_rect(window.hwnd)
            if fresh_rect is not None:
                return TargetWindow(
                    hwnd=window.hwnd,
                    pid=window.pid,
                    title=window.title,
                    class_name=window.class_name,
                process_name=window.process_name,
                exe_path=window.exe_path,
                rect=fresh_rect,
                vm_index=window.vm_index,
                adb_serial=window.adb_serial,
                adb_port=window.adb_port,
            )
        return None

    def follow_target(self) -> None:
        try:
            self.refresh_targets(attach_default=False)
            window = self.selected_window()
            if window is not None:
                self.attach_to(window)
        finally:
            self.root.after(REFRESH_MS, self.follow_target)

    def run_current(self) -> None:
        window = self.selected_window()
        if window is None:
            self.log("未选择有效目标窗口。")
            return
        self.start_worker([window])

    def run_all(self) -> None:
        windows = self.refresh_targets(attach_default=False)
        if not windows:
            self.log("没有可扫描的 MuMu 窗口。")
            return
        self.start_worker(windows)

    def start_worker(self, windows: list[TargetWindow]) -> None:
        if self.worker and self.worker.is_alive():
            self.log("任务正在执行中，请稍等。")
            return
        self.set_busy(True)
        self.worker = threading.Thread(target=self.worker_main, args=(windows,), daemon=True)
        self.worker.start()

    def worker_main(self, windows: list[TargetWindow]) -> None:
        try:
            for index, window in enumerate(windows, start=1):
                self.thread_log(f"开始处理 {index}/{len(windows)}：{window.title}")
                self.claim_one_window(window)
                time.sleep(0.4)
        except Exception as exc:
            traceback.print_exc()
            self.thread_log(f"执行失败：{exc}")
        finally:
            self.root.after(0, lambda: self.set_busy(False))

    def maybe_debug(self, image: Image.Image, prefix: str) -> None:
        if not self.debug_saves.get():
            return
        path = save_debug_capture(image, prefix)
        self.thread_log(f"已保存调试截图：{path}")

    def claim_one_window(self, window: TargetWindow) -> None:
        if not is_alive_window(window.hwnd):
            self.thread_log(f"{window.title} 已关闭，跳过。")
            return

        backend = f"ADB {window.adb_serial}" if window.adb_serial else "窗口截图"
        self.thread_log(f"{window.title}：使用 {backend} 检测。")
        image, profile = capture_target(window)
        self.maybe_debug(image, f"{window.hwnd:X}_home")
        detection = analyze_screen(image, profile)

        if not detection.explore_tab_visible:
            self.thread_log(f"{window.title}：左下角未识别到“探险”入口，跳过。")
            return

        self.thread_log(f"{window.title}：识别到探险/双剑入口，点击进入。")
        tap_target(window, "explore")

        side_detection = None
        for _ in range(12):
            time.sleep(0.35)
            image, profile = capture_target(window)
            side_detection = analyze_screen(image, profile)
            if side_detection.side_claim_green:
                break

        self.maybe_debug(image, f"{window.hwnd:X}_adventure")
        if side_detection is None or not side_detection.side_claim_green:
            self.thread_log(f"{window.title}：进入后领取按钮绿色图块未命中，跳过。")
            return

        self.thread_log(f"{window.title}：领取按钮为绿色，点击第一次领取。")
        tap_target(window, "side_claim")

        popup_detection = None
        for _ in range(12):
            time.sleep(0.35)
            image, profile = capture_target(window)
            popup_detection = analyze_screen(image, profile)
            if popup_detection.popup_claim_green:
                break

        self.maybe_debug(image, f"{window.hwnd:X}_popup")
        if popup_detection is None or not popup_detection.popup_claim_green:
            self.thread_log(f"{window.title}：未发现弹窗绿色领取按钮图块。")
            return

        self.thread_log(f"{window.title}：点击弹窗第二次领取。")
        tap_target(window, "popup_claim")
        time.sleep(0.4)
        self.thread_log(f"{window.title}：流程完成。")

    def run(self) -> None:
        self.root.mainloop()


class DebugRangeOverlay:
    def __init__(self, root: tk.Tk, window: TargetWindow) -> None:
        self.window = window
        self.ranges: list[DebugRange] = debug_ranges_for_step("home")
        self.top = tk.Toplevel(root)
        self.top.withdraw()
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.configure(bg=DEBUG_TRANSPARENT_COLOR)
        try:
            self.top.attributes("-transparentcolor", DEBUG_TRANSPARENT_COLOR)
        except tk.TclError:
            pass

        self.canvas = tk.Canvas(
            self.top,
            bg=DEBUG_TRANSPARENT_COLOR,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(fill="both", expand=True)

    def update_window(self, window: TargetWindow) -> None:
        self.window = window
        self.refresh()

    def set_ranges(self, ranges: list[DebugRange]) -> None:
        self.ranges = ranges
        self.refresh()

    def refresh(self) -> None:
        if not is_alive_window(self.window.hwnd):
            self.top.withdraw()
            return

        rect = get_emulator_content_rect(self.window.hwnd)
        if rect is None or rect.width <= 0 or rect.height <= 0:
            self.top.withdraw()
            return

        self.top.geometry(f"{rect.width}x{rect.height}+{rect.left}+{rect.top}")
        self.top.deiconify()
        self.top.lift()
        self.top.update_idletasks()
        hwnd = tk_top_hwnd(self.top)
        make_click_through(hwnd)
        user32.SetWindowPos(hwnd, HWND_TOPMOST, rect.left, rect.top, rect.width, rect.height, SWP_NOACTIVATE)

        self.canvas.configure(width=rect.width, height=rect.height)
        self.canvas.delete("all")
        for label, color, box in self.ranges:
            x1 = round(box[0] * rect.width / ADB_REF_WIDTH)
            y1 = round(box[1] * rect.height / ADB_REF_HEIGHT)
            x2 = round(box[2] * rect.width / ADB_REF_WIDTH)
            y2 = round(box[3] * rect.height / ADB_REF_HEIGHT)
            if x2 <= x1 or y2 <= y1:
                continue
            width = 2 if (x2 - x1) >= 12 and (y2 - y1) >= 12 else 1
            self.canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=width)
            if x2 - x1 >= 34 and y2 - y1 >= 16:
                label_y = y1 - 15 if y1 >= 18 else y2 + 3
                self.canvas.create_text(
                    x1 + 3,
                    label_y,
                    text=label,
                    fill=color,
                    anchor="nw",
                    font=("Microsoft YaHei UI", 8, "bold"),
                )

    def destroy(self) -> None:
        self.top.destroy()


class TargetPanel:
    def __init__(self, app: "MultiPanelApp", root: tk.Tk, window: TargetWindow) -> None:
        self.app = app
        self.window = window
        self.status_var = tk.StringVar(master=root, value="已附加，等待操作。")
        self.task_vars: dict[str, tk.BooleanVar] = {}
        self.task_checks: dict[str, tk.Checkbutton] = {}
        self.start_btn: tk.Button | None = None
        self.stop_btn: tk.Button | None = None
        self.debug_ranges_var = tk.BooleanVar(master=root, value=False)
        self.debug_check: tk.Checkbutton | None = None
        self.debug_overlay: DebugRangeOverlay | None = None
        self.debug_ranges: list[DebugRange] = debug_ranges_for_step("home")

        self.top = tk.Toplevel(root)
        self.top.title(f"MuMu 探险助手 {window.hwnd:X}")
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", False)
        self.top.configure(bg="#1f2937")
        self.top.protocol("WM_DELETE_WINDOW", app.close)

        self._drag_start: tuple[int, int] | None = None
        self.build_ui()
        self.attach()

    def build_ui(self) -> None:
        self.top.columnconfigure(0, weight=1)

        title_bar = tk.Frame(self.top, bg="#111827", height=30)
        title_bar.grid(row=0, column=0, sticky="ew")
        title_bar.grid_columnconfigure(1, weight=1)
        title_bar.bind("<ButtonPress-1>", self.start_drag)
        title_bar.bind("<B1-Motion>", self.drag_panel)

        self.title_label = tk.Label(
            title_bar,
            text=self.short_title(),
            bg="#111827",
            fg="#f9fafb",
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        self.title_label.grid(row=0, column=0, padx=(10, 8), pady=5, sticky="w")
        self.title_label.bind("<ButtonPress-1>", self.start_drag)
        self.title_label.bind("<B1-Motion>", self.drag_panel)

        hint = tk.Label(
            title_bar,
            text="附加在模拟器上方",
            bg="#111827",
            fg="#9ca3af",
            font=("Microsoft YaHei UI", 9),
        )
        hint.grid(row=0, column=1, pady=5, sticky="w")
        hint.bind("<ButtonPress-1>", self.start_drag)
        hint.bind("<B1-Motion>", self.drag_panel)

        close_btn = tk.Button(
            title_bar,
            text="×",
            command=self.app.close,
            bd=0,
            bg="#111827",
            fg="#f9fafb",
            activebackground="#991b1b",
            activeforeground="#ffffff",
            font=("Microsoft YaHei UI", 13, "bold"),
            width=3,
        )
        close_btn.grid(row=0, column=2, sticky="e")

        meta = tk.Label(
            self.top,
            text=self.window.label,
            bg="#1f2937",
            fg="#d1d5db",
            anchor="w",
            font=("Microsoft YaHei UI", 9),
        )
        meta.grid(row=1, column=0, sticky="ew", padx=10, pady=(8, 4))
        self.meta_label = meta

        tasks = tk.Frame(self.top, bg="#1f2937")
        tasks.grid(row=2, column=0, sticky="ew", padx=10, pady=(2, 6))
        tasks.columnconfigure(0, weight=1)
        tasks.columnconfigure(1, weight=1)

        for index, (task_key, task_label) in enumerate(TASK_DEFINITIONS):
            var = tk.BooleanVar(master=self.top, value=True)
            check = tk.Checkbutton(
                tasks,
                text=task_label,
                variable=var,
                indicatoron=True,
                bg="#1f2937",
                fg="#d1d5db",
                selectcolor="#111827",
                activebackground="#1f2937",
                activeforeground="#ffffff",
                font=("Microsoft YaHei UI", 10, "bold"),
                anchor="w",
            )
            check.grid(row=index, column=0, sticky="ew", padx=(0, 8), pady=3)
            self.task_vars[task_key] = var
            self.task_checks[task_key] = check

        self.debug_check = tk.Checkbutton(
            tasks,
            text="显示取色范围",
            variable=self.debug_ranges_var,
            command=self.toggle_debug_ranges,
            indicatoron=True,
            bg="#1f2937",
            fg="#d1d5db",
            selectcolor="#111827",
            activebackground="#1f2937",
            activeforeground="#ffffff",
            font=("Microsoft YaHei UI", 9),
            anchor="w",
        )
        self.debug_check.grid(row=len(TASK_DEFINITIONS), column=0, sticky="ew", padx=(0, 8), pady=3)

        self.start_btn = tk.Button(
            tasks,
            text="开始任务",
            command=lambda: self.app.start_panel_tasks(self),
            bg="#16a34a",
            fg="#ffffff",
            activebackground="#15803d",
            activeforeground="#ffffff",
            bd=0,
            padx=8,
            pady=8,
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        self.start_btn.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=3)

        self.stop_btn = tk.Button(
            tasks,
            text="停止",
            command=self.app.stop_all_tasks,
            bg="#dc2626",
            fg="#ffffff",
            activebackground="#b91c1c",
            activeforeground="#ffffff",
            bd=0,
            padx=8,
            pady=8,
        )
        self.stop_btn.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=3)

        status = tk.Label(
            self.top,
            textvariable=self.status_var,
            bg="#111827",
            fg="#d1d5db",
            justify="left",
            anchor="nw",
            wraplength=600,
            font=("Microsoft YaHei UI", 9),
        )
        status.grid(row=3, column=0, sticky="nsew", padx=10, pady=(2, 10))

    def short_title(self) -> str:
        index = self.window.vm_index or "?"
        return f"{self.window.title} · index={index}"

    def update_window(self, window: TargetWindow) -> None:
        self.window = window
        self.title_label.configure(text=self.short_title())
        self.meta_label.configure(text=window.label)
        self.attach()
        self.refresh_debug_overlay()

    def start_drag(self, event) -> None:
        self._drag_start = (event.x_root - self.top.winfo_x(), event.y_root - self.top.winfo_y())

    def drag_panel(self, event) -> None:
        if self._drag_start is None:
            return
        dx, dy = self._drag_start
        self.top.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")

    def attach(self) -> None:
        rect = get_window_rect(self.window.hwnd) or self.window.rect
        left = rect.left
        top = max(0, rect.top - CONTROL_HEIGHT)
        width = max(360, rect.width)
        self.set_geometry(width, CONTROL_HEIGHT, left, top)
        self.refresh_debug_overlay()

    def set_geometry(self, width: int, height: int, left: int, top: int) -> None:
        self.top.geometry(f"{width}x{height}+{left}+{top}")
        self.top.update_idletasks()
        hwnd = find_top_window_by_pid_and_title(os.getpid(), self.top.title())
        if not hwnd:
            hwnd = int(user32.GetAncestor(int(self.top.winfo_id()), GA_ROOT))
        if not hwnd:
            hwnd = int(self.top.winfo_id())
        user32.SetWindowPos(hwnd, HWND_NOTOPMOST, left, top, width, height, SWP_NOACTIVATE)

    def log(self, text: str) -> None:
        now = datetime.now().strftime("%H:%M:%S")
        self.status_var.set(f"[{now}] {text}")

    def set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        if self.start_btn is not None:
            self.start_btn.configure(state=state)
        for check in self.task_checks.values():
            check.configure(state=state)

    def toggle_debug_ranges(self) -> None:
        if self.debug_ranges_var.get():
            if self.debug_overlay is None:
                self.debug_overlay = DebugRangeOverlay(self.top, self.window)
            self.debug_overlay.set_ranges(self.debug_ranges)
            self.debug_overlay.refresh()
            self.log("已显示取色范围。")
            return
        self.hide_debug_overlay()
        self.log("已隐藏取色范围。")

    def show_debug_ranges(self, ranges: list[DebugRange]) -> None:
        self.debug_ranges = ranges
        if self.debug_overlay is not None and self.debug_ranges_var.get():
            self.debug_overlay.set_ranges(ranges)

    def refresh_debug_overlay(self) -> None:
        if self.debug_overlay is not None and self.debug_ranges_var.get():
            self.debug_overlay.update_window(self.window)

    def hide_debug_overlay(self) -> None:
        if self.debug_overlay is not None:
            self.debug_overlay.destroy()
            self.debug_overlay = None

    def selected_tasks(self) -> list[str]:
        return [key for key, _label in TASK_DEFINITIONS if self.task_vars[key].get()]

    def reset_task_states(self) -> None:
        for check in self.task_checks.values():
            check.configure(fg="#d1d5db", activeforeground="#ffffff")

    def mark_task_done(self, task_key: str) -> None:
        check = self.task_checks.get(task_key)
        if check is not None:
            check.configure(fg="#22c55e", activeforeground="#22c55e")

    def destroy(self) -> None:
        self.hide_debug_overlay()
        self.top.destroy()


class MultiPanelApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.panels: dict[int, TargetPanel] = {}
        self.workers: dict[int, threading.Thread] = {}
        self.stop_events: dict[int, threading.Event] = {}

        self.refresh_targets(force=True)
        self.follow_targets()

    def close(self) -> None:
        self.stop_all_tasks()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()

    def refresh_targets(self, force: bool = False) -> list[TargetWindow]:
        if force:
            load_mumu_info(force=True)
        windows = enum_mumu_windows()
        live_hwnds = {window.hwnd for window in windows}

        for window in windows:
            panel = self.panels.get(window.hwnd)
            if panel is None:
                self.panels[window.hwnd] = TargetPanel(self, self.root, window)
            else:
                panel.update_window(window)

        for hwnd in list(self.panels):
            if hwnd not in live_hwnds or not is_alive_window(hwnd):
                self.panels[hwnd].destroy()
                del self.panels[hwnd]

        if not windows:
            self.root.after(0, lambda: None)
        return windows

    def follow_targets(self) -> None:
        try:
            self.refresh_targets(force=False)
        finally:
            self.root.after(REFRESH_MS, self.follow_targets)

    def start_panel_tasks(self, panel: TargetPanel) -> None:
        task_keys = panel.selected_tasks()
        if not task_keys:
            panel.log("未勾选任务。")
            return
        panel.reset_task_states()
        self.start_worker(panel, task_keys)

    def start_worker(self, panel: TargetPanel, task_keys: list[str]) -> None:
        hwnd = panel.window.hwnd
        existing_worker = self.workers.get(hwnd)
        if existing_worker and existing_worker.is_alive():
            panel.log("任务正在执行中，请稍等。")
            return
        panel.set_busy(True)
        stop_event = threading.Event()
        self.stop_events[hwnd] = stop_event
        worker = threading.Thread(target=self.worker_main, args=(panel.window, task_keys, stop_event), daemon=True)
        self.workers[hwnd] = worker
        worker.start()

    def stop_all_tasks(self) -> None:
        running = 0
        for hwnd, worker in list(self.workers.items()):
            if worker.is_alive():
                running += 1
                event = self.stop_events.get(hwnd)
                if event is not None:
                    event.set()
        for panel in list(self.panels.values()):
            panel.log("已发送停止指令。" if running else "当前没有正在执行的任务。")

    def set_busy(self, busy: bool) -> None:
        for panel in list(self.panels.values()):
            panel.set_busy(busy)

    def thread_log(self, window: TargetWindow, text: str) -> None:
        def _log() -> None:
            panel = self.panels.get(window.hwnd)
            if panel:
                panel.log(text)

        self.root.after(0, _log)

    def show_debug_step(
        self,
        window: TargetWindow,
        step: str,
        unit_label: str = "",
        row_y: int | None = None,
    ) -> None:
        ranges = debug_ranges_for_step(step, unit_label=unit_label, row_y=row_y)

        def _show() -> None:
            panel = self.panels.get(window.hwnd)
            if panel:
                panel.show_debug_ranges(ranges)

        self.root.after(0, _show)

    def should_stop(self, window: TargetWindow) -> bool:
        event = self.stop_events.get(window.hwnd)
        return bool(event and event.is_set())

    def sleep_with_stop(self, window: TargetWindow, seconds: float) -> bool:
        end_time = time.monotonic() + seconds
        while time.monotonic() < end_time:
            if self.should_stop(window):
                return False
            remaining = end_time - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(0.1, remaining))
        return not self.should_stop(window)

    def worker_main(self, window: TargetWindow, task_keys: list[str], stop_event: threading.Event) -> None:
        task_labels = dict(TASK_DEFINITIONS)
        handlers = {
            "adventure": self.task_adventure,
            "train_soldiers": self.task_train_soldiers,
        }
        try:
            for index, task_key in enumerate(task_keys, start=1):
                if stop_event.is_set():
                    self.thread_log(window, "任务已停止。")
                    break

                task_label = task_labels.get(task_key, task_key)
                handler = handlers.get(task_key)
                if handler is None:
                    self.thread_log(window, f"任务未实现：{task_label}")
                    continue

                self.thread_log(window, f"开始任务 {index}/{len(task_keys)}：{task_label}")
                ok = handler(window)
                if not ok:
                    self.thread_log(window, f"任务未完成：{task_label}")
                    break

                self.root.after(0, lambda key=task_key, hwnd=window.hwnd: self.mark_task_done(hwnd, key))
                if index < len(task_keys):
                    self.thread_log(window, f"{task_label} 已完成，等待 {TASK_BUFFER_SECONDS} 秒后继续。")
                    if not self.sleep_with_stop(window, TASK_BUFFER_SECONDS):
                        self.thread_log(window, "任务已停止。")
                        break
        except Exception as exc:
            traceback.print_exc()
            self.thread_log(window, f"执行失败：{exc}")
        finally:
            self.workers.pop(window.hwnd, None)
            self.stop_events.pop(window.hwnd, None)
            self.show_debug_step(window, "home")
            self.root.after(0, lambda hwnd=window.hwnd: self.set_panel_busy(hwnd, False))

    def set_panel_busy(self, hwnd: int, busy: bool) -> None:
        panel = self.panels.get(hwnd)
        if panel:
            panel.set_busy(busy)

    def mark_task_done(self, hwnd: int, task_key: str) -> None:
        panel = self.panels.get(hwnd)
        if panel:
            panel.mark_task_done(task_key)

    def capture_detection(self, window: TargetWindow) -> tuple[Image.Image, ScreenProfile, Detection]:
        image, profile = capture_target(window)
        return image, profile, analyze_screen(image, profile)

    def wait_for(
        self,
        window: TargetWindow,
        predicate,
        ok_message: str,
        fail_message: str,
        attempts: int = 14,
        interval: float = 0.35,
    ) -> tuple[bool, Image.Image, ScreenProfile, Detection]:
        last_image, last_profile, last_detection = self.capture_detection(window)
        for _ in range(attempts):
            if self.should_stop(window):
                self.thread_log(window, "收到停止指令，结束等待。")
                return False, last_image, last_profile, last_detection
            if predicate(last_detection):
                self.thread_log(window, ok_message)
                return True, last_image, last_profile, last_detection
            if not self.sleep_with_stop(window, interval):
                self.thread_log(window, "收到停止指令，结束等待。")
                return False, last_image, last_profile, last_detection
            last_image, last_profile, last_detection = self.capture_detection(window)
        self.thread_log(window, fail_message)
        return False, last_image, last_profile, last_detection

    def wait_for_image(
        self,
        window: TargetWindow,
        predicate,
        ok_message: str,
        fail_message: str,
        attempts: int = 12,
        interval: float = 0.35,
    ) -> tuple[bool, Image.Image]:
        last_image, _profile = capture_target(window)
        for _ in range(attempts):
            if self.should_stop(window):
                self.thread_log(window, "收到停止指令，结束等待。")
                return False, last_image
            if predicate(last_image):
                self.thread_log(window, ok_message)
                return True, last_image
            if not self.sleep_with_stop(window, interval):
                self.thread_log(window, "收到停止指令，结束等待。")
                return False, last_image
            last_image, _profile = capture_target(window)
        self.thread_log(window, fail_message)
        return False, last_image

    def ensure_home_screen(self, window: TargetWindow) -> bool:
        if self.should_stop(window):
            self.thread_log(window, "任务已停止。")
            return False

        self.show_debug_step(window, "home")
        image, profile, detection = self.capture_detection(window)
        if detection.reward_overlay_visible:
            self.show_debug_step(window, "reward")
            self.thread_log(window, "当前在奖励页，先点空白处退出。")
            tap_target(window, "reward_blank")
            ok, _image = self.wait_for_image(
                window,
                lambda img: not analyze_screen(img, ADB_PROFILE).reward_overlay_visible,
                "奖励页已关闭。",
                "奖励页未关闭，停止当前任务。",
            )
            if not ok:
                return False

        for attempt in range(6):
            if self.should_stop(window):
                self.thread_log(window, "任务已停止。")
                return False

            self.show_debug_step(window, "home")
            image, profile, detection = self.capture_detection(window)
            if main_screen_visible(image) and not detection.adventure_page_visible and not detection.reward_overlay_visible:
                if attempt > 0:
                    self.thread_log(window, "已回到主界面。")
                return True

            self.thread_log(window, "当前不在主界面，点击左上角返回。")
            tap_target(window, "back")
            if not self.sleep_with_stop(window, 0.45):
                self.thread_log(window, "任务已停止。")
                return False

        image, profile, detection = self.capture_detection(window)
        if main_screen_visible(image) and not detection.adventure_page_visible and not detection.reward_overlay_visible:
            self.thread_log(window, "已回到主界面。")
            return True
        self.thread_log(window, "多次返回后仍未识别到主界面图标，停止当前任务。")
        return False

    def ensure_home_for_training(self, window: TargetWindow) -> bool:
        return self.ensure_home_screen(window)

    def ensure_queue_panel(self, window: TargetWindow) -> bool:
        if self.should_stop(window):
            self.thread_log(window, "任务已停止。")
            return False

        self.show_debug_step(window, "queue_panel")
        image, _profile = capture_target(window)
        if queue_panel_visible(image):
            return True

        self.thread_log(window, "展开左侧队列面板。")
        tap_target(window, "queue_expand")
        ok, _image = self.wait_for_image(
            window,
            queue_panel_visible,
            "队列面板已展开。",
            "未验证到队列面板展开，停止训练任务。",
            attempts=10,
        )
        return ok

    def task_train_soldiers(self, window: TargetWindow) -> bool:
        if not is_alive_window(window.hwnd):
            self.thread_log(window, "目标窗口已关闭，跳过。")
            return False
        if not self.ensure_home_for_training(window):
            return False

        for unit_key, unit_label, row_y in TRAIN_UNITS:
            if self.should_stop(window):
                self.thread_log(window, "任务已停止。")
                return False
            if not self.train_one_unit(window, unit_label, row_y):
                return False
            if not self.sleep_with_stop(window, 0.45):
                self.thread_log(window, "任务已停止。")
                return False
        self.thread_log(window, "士兵训练任务完成。")
        return True

    def train_one_unit(self, window: TargetWindow, unit_label: str, row_y: int) -> bool:
        if self.should_stop(window):
            self.thread_log(window, "任务已停止。")
            return False
        if not self.ensure_queue_panel(window):
            return False

        self.show_debug_step(window, "unit_row", unit_label=unit_label, row_y=row_y)
        image, _profile = capture_target(window)
        state = unit_row_state(image, row_y)
        state_text = {
            "ready": "已完成",
            "idle": "空闲中",
            "busy": "训练中",
            "blocked": "建筑升级中",
            "unknown": "未知",
        }.get(state, state)
        self.thread_log(window, f"{unit_label} 当前状态：{state_text}。")

        if state == "busy":
            self.thread_log(window, f"{unit_label} 正在训练，跳过。")
            return True
        if state == "blocked":
            self.thread_log(window, f"{unit_label} 建筑升级中，跳过。")
            return True
        if state not in {"ready", "idle"}:
            self.thread_log(window, f"{unit_label} 状态无法确认，跳过。")
            return True

        self.thread_log(window, f"点击 {unit_label} 行。")
        tap_point(window, SOLDIER_QUEUE_ROW_TAP_X, row_y)

        def training_entry_context_visible(candidate_image: Image.Image) -> bool:
            if queue_panel_visible(candidate_image):
                return False
            return soldier_page_visible(candidate_image) or main_screen_visible(candidate_image)

        ok, image = self.wait_for_image(
            window,
            training_entry_context_visible,
            f"{unit_label} 已进入训练入口场景。",
            f"{unit_label} 点击后未验证到训练入口场景，停止训练任务。",
            attempts=10,
        )
        if not ok:
            return False

        if not soldier_page_visible(image):
            train_action_center: tuple[int, int] | None = None
            for attempt in range(6):
                if self.should_stop(window):
                    self.thread_log(window, "任务已停止。")
                    return False
                self.show_debug_step(window, "building_train")
                image, _profile = capture_target(window)

                if soldier_page_visible(image):
                    self.thread_log(window, f"已在 {unit_label} 训练页。")
                    break

                if not main_screen_visible(image):
                    self.thread_log(window, "未停留在主城训练入口场景，停止训练任务。")
                    return False

                train_action_center = find_building_train_action(image)
                if train_action_center is not None:
                    self.thread_log(
                        window,
                        f"已验证到建筑训练图标，坐标=({train_action_center[0]}, {train_action_center[1]})。",
                    )
                    break

                if attempt >= 5:
                    break

                self.thread_log(window, f"未识别到训练图标，第 {attempt + 1}/5 次点击兵营建筑。")
                tap_target(window, "soldier_building")
                if not self.sleep_with_stop(window, 0.45):
                    self.thread_log(window, "任务已停止。")
                    return False

            if soldier_page_visible(image):
                pass
            elif train_action_center is None:
                self.thread_log(window, "多次点击兵营建筑后仍未出现训练图标，停止训练任务。")
                return False
            else:
                self.thread_log(window, "点击已识别到的建筑训练图标。")
                tap_point(window, train_action_center[0], train_action_center[1])
                self.show_debug_step(window, "soldier_page")
                ok, image = self.wait_for_image(
                    window,
                    soldier_page_visible,
                    f"已进入 {unit_label} 训练页。",
                    f"未进入 {unit_label} 训练页，停止训练任务。",
                    attempts=14,
                )
                if not ok:
                    return False
        else:
            self.thread_log(window, f"已在 {unit_label} 训练页。")

        self.show_debug_step(window, "train_levels")
        level_x = highest_available_level_x(image)
        if level_x is None:
            self.thread_log(window, "未识别到白色边框的可训练等级，停止训练任务。")
            return False
        self.thread_log(window, f"选择最高可用等级，x={level_x}。")
        tap_point(window, level_x, 675)
        if not self.sleep_with_stop(window, 0.25):
            self.thread_log(window, "任务已停止。")
            return False

        self.thread_log(window, "点击训练按钮。")
        tap_target(window, "soldier_train")
        ok, image = self.wait_for_image(
            window,
            soldier_training_started_visible,
            f"{unit_label} 已开始训练。",
            f"{unit_label} 点击训练后未验证到训练中状态，停止训练任务。",
            attempts=16,
        )
        if not ok:
            return False

        self.thread_log(window, "点击左上角返回。")
        tap_target(window, "back")
        ok, _image = self.wait_for_image(
            window,
            lambda img: not soldier_page_visible(img),
            f"{unit_label} 已返回主界面。",
            f"{unit_label} 返回后仍在训练页，请手动确认。",
            attempts=10,
        )
        return ok

    def task_adventure(self, window: TargetWindow) -> bool:
        if not is_alive_window(window.hwnd):
            self.thread_log(window, "目标窗口已关闭，跳过。")
            return False

        if not self.ensure_home_screen(window):
            return False
        if self.should_stop(window):
            self.thread_log(window, "任务已停止。")
            return False

        backend = f"ADB {window.adb_serial}" if window.adb_serial else "窗口截图"
        self.thread_log(window, f"使用 {backend} 检测。")
        self.show_debug_step(window, "explore_entry")
        image, profile, detection = self.capture_detection(window)

        if not detection.adventure_page_visible:
            if not detection.explore_tab_visible:
                self.thread_log(window, "未识别到探险/双剑入口，跳过。")
                return False

            self.thread_log(window, "识别到探险/双剑入口，点击进入。")
            tap_target(window, "explore")
            self.show_debug_step(window, "adventure_page")
            ok, image, profile, detection = self.wait_for(
                window,
                lambda d: d.adventure_page_visible,
                "已进入探险页。",
                "点击探险后未验证到探险页，停止本窗口。",
            )
            if not ok:
                return False
        else:
            self.thread_log(window, "当前已在探险页。")

        self.show_debug_step(window, "side_claim")
        if not detection.side_claim_green:
            self.thread_log(
                window,
                "领取按钮绿色图块未命中，跳过领取并返回上一层。",
            )
            tap_target(window, "back")
            ok, image, profile, detection = self.wait_for(
                window,
                lambda d: d.explore_tab_visible and not d.adventure_page_visible and not d.reward_overlay_visible,
                "已返回上一层。",
                "返回后未验证到上一层，请手动确认。",
            )
            return ok

        self.thread_log(window, "领取按钮为绿色，点击第一次领取。")
        tap_target(window, "side_claim")
        self.show_debug_step(window, "popup_claim")
        ok, image, profile, detection = self.wait_for(
            window,
            lambda d: d.popup_claim_green,
            "已弹出挂机收益领取窗口。",
            "第一次领取后未验证到弹窗领取按钮，停止本窗口。",
        )
        if not ok:
            return False

        self.thread_log(window, "点击弹窗第二次领取。")
        tap_target(window, "popup_claim")
        self.show_debug_step(window, "reward")
        ok, image, profile, detection = self.wait_for(
            window,
            lambda d: d.reward_overlay_visible,
            "已验证获得奖励页。",
            "第二次领取后未验证到获得奖励页，停止本窗口。",
            attempts=18,
        )
        if not ok:
            return False

        self.thread_log(window, "点击空白处退出奖励页。")
        tap_target(window, "reward_blank")
        ok, image, profile, detection = self.wait_for(
            window,
            lambda d: not d.reward_overlay_visible and d.adventure_page_visible,
            "奖励页已关闭，已回到探险页。",
            "点击空白处后未验证到探险页，请手动确认。",
            attempts=12,
        )
        if not ok:
            return False

        self.thread_log(window, "点击左上角返回上一层。")
        tap_target(window, "back")
        ok, image, profile, detection = self.wait_for(
            window,
            lambda d: d.explore_tab_visible and not d.adventure_page_visible and not d.reward_overlay_visible,
            "流程完成，已返回上一层。",
            "点击返回后未验证到上一层，请手动确认。",
            attempts=14,
        )
        return ok


def main() -> None:
    enable_dpi_awareness()
    os.chdir(Path(__file__).resolve().parent)
    MultiPanelApp().run()


if __name__ == "__main__":
    main()

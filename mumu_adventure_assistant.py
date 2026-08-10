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
import sys
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


CONTROL_HEIGHT = 280
COLLAPSED_CONTROL_HEIGHT = 40
REFRESH_MS = 900
TASK_BUFFER_SECONDS = 3
TASK_STEP_TIMEOUT_SECONDS = 60
ADVENTURE_LOOP_INTERVAL_SECONDS = 4 * 60 * 60
SOLDIER_LOOP_FALLBACK_SECONDS = 5 * 60
SOLDIER_LOOP_COMPLETE_DELAY_SECONDS = 5
DEFAULT_PANEL_OPACITY = 92
MIN_PANEL_OPACITY = 55
MAX_PANEL_OPACITY = 100
AUTO_ASSIST_DEFAULT_INTERVAL_SECONDS = 60
AUTO_ASSIST_MIN_INTERVAL_SECONDS = 5
AUTO_ASSIST_MAX_INTERVAL_SECONDS = 60
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
    "queue_collapse": (470, 550),
    "screen_center": (360, 640),
    "soldier_building": (335, 705),
    "building_train": (480, 855),
    "soldier_train": (535, 1115),
    "auto_assist": (535, 1138),
}

WINDOW_CLICK_POINTS = {
    "explore": (0.09, 0.955),
    "side_claim": (0.86, 0.69),
    "popup_claim": (0.50, 0.735),
    "reward_blank": (0.50, 0.93),
    "back": (0.065, 0.075),
    "queue_expand": (0.02, 0.43),
    "queue_collapse": (0.653, 0.43),
    "screen_center": (0.50, 0.50),
    "soldier_building": (0.465, 0.55),
    "building_train": (0.67, 0.67),
    "soldier_train": (0.74, 0.88),
    "auto_assist": (0.743, 0.889),
}

DEBUG_DIR = Path("debug_captures")
ASSET_DIR = Path(__file__).resolve().parent / "assets"
BUILDING_TRAIN_ACTION_TEMPLATE = ASSET_DIR / "building_train_action_template.png"
CONFIG_PATH = Path(__file__).resolve().with_name("mumu_assistant_settings.json")

TASK_DEFINITIONS = [
    ("adventure", "探险领取"),
    ("train_soldiers", "训练士兵"),
    ("auto_assist", "自动协助"),
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
MAIN_AVATAR_FIXED_POINTS = [
    ("头像左白", 4, 60, (255, 255, 255)),
    ("头像右蓝", 97, 90, (86, 123, 176)),
]
MAIN_TOP_FIXED_POINTS = [
    ("顶栏蓝", 112, 58, (172, 200, 223)),
    ("顶栏黄", 441, 76, (250, 203, 72)),
]
MAIN_TOP_BAR_BLOCKS = [
    (200, 16, 245, 48),
    (320, 16, 390, 48),
    (455, 16, 535, 48),
    (610, 16, 690, 48),
]
MAIN_TOGGLE_FIXED_POINTS = [
    ("切换金", 630, 1180, (249, 162, 26)),
    ("底栏蓝", 600, 1230, NAV_BLUE),
]

ALLIANCE_NAV_BLOCKS = [
    (475, 1186, 493, 1214),
    (550, 1186, 568, 1214),
    (476, 1230, 493, 1256),
    (550, 1230, 568, 1256),
]
ALLIANCE_ICON_BLOCKS = [
    (505, 1168, 550, 1208),
    (515, 1190, 550, 1220),
]
AUTO_ASSIST_BUBBLE_BLOCK = (492, 1035, 608, 1145)
AUTO_ASSIST_GREEN_BLOCK = (510, 1075, 570, 1130)
AUTO_ASSIST_HAND_BLOCK = (522, 1082, 572, 1118)

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

BUILDING_ACTION_SCAN_BOX = (90, 650, 650, 1040)
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
SOLDIER_QUANTITY_BAR_BLOCK = (95, 955, 440, 1000)
SOLDIER_TRAIN_BUTTON_BLOCK = (360, 1060, 705, 1180)
SOLDIER_TRAIN_GUIDE_HAND_SCAN_BOX = (360, 850, 700, 1165)
SOLDIER_QUEUE_ROW_TAP_X = 250
QUEUE_TOP_BUILDING_ICON_BLOCK = (15, 300, 45, 335)
QUEUE_TOP_TROOP_ICON_BLOCK = (15, 488, 45, 520)
QUEUE_TOP_RESEARCH_ICON_BLOCK = (15, 748, 45, 782)
QUEUE_COLLAPSE_ARROW_BLOCK = (450, 500, 490, 600)
QUEUE_SCROLL_X = 230
QUEUE_SCROLL_TOP_START_Y = 430
QUEUE_SCROLL_TOP_END_Y = 835
QUEUE_TIME_TEMPLATE_WIDTH = 8
QUEUE_TIME_TEMPLATE_HEIGHT = 12
QUEUE_TIME_DIGIT_TEMPLATES = {
    "0": [
        "001111001111111011111111110001111100001111000011110000111100001111000011110001111111111111111110",
        "001111110111111111100011110000011100000111000001110000011100000111000001111000110111111100111110",
        "011111101111111111000011110000111100000111000001100000011100000111000011111001110111111100111110",
        "001111100111111111100011110000011100000111000001110000011100000111000001111000110111111100111110",
        "001111100111111001100111111000111100001111000011110000111100001111000011011001110111111100111110",
        "000111000011111001100111011000111100001111000011110000011100001101100011011000110111111100111110",
    ],
    "1": [
        "111111111111111111111111001111110011111100111111001111110011111100111111001111110011111100111111",
        "111111111111111100111111000011110000111100001111000011110000111100001111000011110000111100001111",
        "000001101111111111111111000011110000111100001111000011110000111100001111000011110000111100001111",
        "001111111111111100111111000011110000111100001111000011110000111100001111000011110000111100001111",
        "000011111111111100111111000011110000111100001111000011110000111100001111000011110000111100001111",
    ],
    "2": [
        "001111100111111101100111000000110000001100000111000001110000111000011100001110000111111111111111",
    ],
    "3": [
        "011111001111111000000110000001100000011000111110001111100000011100000011000001111100111111111110",
        "011111001111111010000111000000110000001000111110001111110000011100000011000000111110011111111110",
    ],
    "4": [
        "000011100000111000011110001111100011011000100110011001100110011011111111111111110000011100000110",
        "000011100001111000011110001111100011011000100110011001100110011011111111111111110000011000000110",
    ],
    "5": [
        "111111101111111011000000110000001110000011111110000001110000001100000011100001111111111011111100",
        "111111101111111011000000110000001110000011111110000011100000011100000111000001111111111011111100",
        "111111101111111011100000110000001110000011111110000011110000001100000011000001111111111011111110",
    ],
    "6": [
        "001111100011111101110111111000001110000011111111111111111110001111100011111000110111111101111111",
    ],
    "7": [
        "111111111111111100000111000000110000011100000111000011100000110000011100000111000001100000111000",
        "111111111111111100000110000001100000010000001100000011000001100000011000001110000011000000110000",
    ],
    "8": [
        "000111100111111101100011011000010110000101111111011111110110001111000001111000010111001101111111",
        "011111100111111111100011111000110110001101111111011001111100001111000001111000111111111101111110",
        "011111100111111111100011111000110110001101111111011111111100001111000001110000011111111101111111",
    ],
    "9": [
        "001111000111111101100111111000111110001111111111001111110000001100000011000001110111011101111110",
    ],
}


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

GA_ROOT = 2
GW_OWNER = 4
SW_RESTORE = 9
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
HWND_TOP = wintypes.HWND(0)
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


def default_panel_settings() -> dict:
    return {
        "tasks": {task_key: True for task_key, _task_label in TASK_DEFINITIONS},
        "assist_interval": AUTO_ASSIST_DEFAULT_INTERVAL_SECONDS,
        "debug_ranges": False,
        "expanded": False,
        "opacity": DEFAULT_PANEL_OPACITY,
    }


def load_app_settings() -> dict:
    if not CONFIG_PATH.exists():
        return {"windows": {}}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"windows": {}}
    if not isinstance(data, dict):
        return {"windows": {}}
    windows = data.get("windows")
    if not isinstance(windows, dict):
        data["windows"] = {}
    return data


def save_app_settings(settings: dict) -> None:
    try:
        CONFIG_PATH.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    except Exception:
        pass


def window_settings_keys(window: TargetWindow) -> list[str]:
    keys: list[str] = []
    if window.vm_index:
        keys.append(f"index:{window.vm_index}")
    if window.adb_serial:
        keys.append(f"adb:{window.adb_serial}")
    if window.title:
        keys.append(f"title:{window.title}")
    return keys or [f"hwnd:{window.hwnd}"]


def primary_window_settings_key(window: TargetWindow) -> str:
    return window_settings_keys(window)[0]


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


def adb_swipe(serial: str, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 420) -> None:
    last_error = ""
    for attempt in range(2):
        ensure_adb_connected(serial, force=attempt > 0)
        result = run_hidden(
            [
                str(MUMU_ADB_EXE),
                "-s",
                serial,
                "shell",
                "input",
                "swipe",
                str(int(x1)),
                str(int(y1)),
                str(int(x2)),
                str(int(y2)),
                str(int(duration_ms)),
            ],
            timeout=8.0,
            text=True,
        )
        if result.returncode == 0:
            return
        last_error = (result.stderr.strip() or result.stdout.strip())
        _adb_connected.discard(serial)
        time.sleep(0.2)
    raise RuntimeError(f"ADB 滑动失败：{last_error}")


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


def swipe_point(window: TargetWindow, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 420) -> None:
    if window.adb_serial:
        adb_swipe(window.adb_serial, x1, y1, x2, y2, duration_ms)
        time.sleep(0.25)
        return

    rect = get_window_rect(window.hwnd)
    if rect is None:
        raise RuntimeError("目标窗口已经不存在")
    start_x = rect.left + round(rect.width * x1 / ADB_REF_WIDTH)
    start_y = rect.top + round(rect.height * y1 / ADB_REF_HEIGHT)
    end_x = rect.left + round(rect.width * x2 / ADB_REF_WIDTH)
    end_y = rect.top + round(rect.height * y2 / ADB_REF_HEIGHT)
    restore_and_focus(window.hwnd)
    user32.SetCursorPos(start_x, start_y)
    time.sleep(0.05)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
    time.sleep(duration_ms / 1000)
    user32.SetCursorPos(end_x, end_y)
    time.sleep(0.05)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)
    time.sleep(0.25)


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


def adb_point_matches(
    image: Image.Image,
    x: int,
    y: int,
    predicate,
) -> bool:
    rgb_image = image if image.mode == "RGB" else image.convert("RGB")
    px, py = adb_point_to_image(rgb_image, x, y)
    return predicate(*rgb_image.getpixel((px, py)))


def adb_multi_point_hits(
    image: Image.Image,
    points: list[tuple[int, int]],
    predicate,
) -> int:
    return sum(1 for x, y in points if adb_point_matches(image, x, y, predicate))


def adb_multi_point_visible(
    image: Image.Image,
    points: list[tuple[int, int]],
    predicate,
    min_hits: int,
) -> bool:
    return adb_multi_point_hits(image, points, predicate) >= min_hits


def template_sample_kind(red: int, green: int, blue: int) -> str | None:
    if action_icon_white_pixel(red, green, blue):
        return "white"
    if building_action_blue_pixel(red, green, blue) or soldier_tab_blue_pixel(red, green, blue):
        return "blue"
    return None


def target_sample_matches(red: int, green: int, blue: int, kind: str) -> bool:
    if kind == "white":
        return action_icon_white_pixel(red, green, blue) or icon_white_pixel(red, green, blue)
    if kind == "blue":
        return building_action_blue_pixel(red, green, blue) or soldier_tab_blue_pixel(red, green, blue)
    return False


def load_image_template(path: Path, sample_step: int = 8) -> ImageTemplate | None:
    cache_key = (str(path.resolve()), sample_step)
    cached = _image_template_cache.get(cache_key)
    if cached is not None:
        return cached
    if not path.exists():
        return None

    image = Image.open(path).convert("RGB")
    samples: list[tuple[int, int, str]] = []
    for y in range(0, image.height, sample_step):
        for x in range(0, image.width, sample_step):
            kind = template_sample_kind(*image.getpixel((x, y)))
            if kind is not None:
                samples.append((x, y, kind))

    if not samples:
        return None
    template = ImageTemplate(path=path, width=image.width, height=image.height, samples=tuple(samples))
    _image_template_cache[cache_key] = template
    return template


def find_template_matches(
    image: Image.Image,
    template: ImageTemplate,
    scan_box: tuple[int, int, int, int],
    min_score: float = 0.74,
    search_step: int = 4,
    max_results: int = 3,
) -> list[TemplateMatchCandidate]:
    rgb_image = image if image.mode == "RGB" else image.convert("RGB")
    left, top, right, bottom = adb_box_to_image(rgb_image, scan_box)
    image_width, image_height = rgb_image.size
    template_width = max(1, round(template.width * image_width / ADB_REF_WIDTH))
    template_height = max(1, round(template.height * image_height / ADB_REF_HEIGHT))
    if right - left < template_width or bottom - top < template_height:
        return []

    scaled_samples = [
        (
            max(0, min(template_width - 1, round(x * image_width / ADB_REF_WIDTH))),
            max(0, min(template_height - 1, round(y * image_height / ADB_REF_HEIGHT))),
            kind,
        )
        for x, y, kind in template.samples
    ]
    if not scaled_samples:
        return []

    raw_matches: list[TemplateMatchCandidate] = []
    for candidate_y in range(top, bottom - template_height + 1, search_step):
        for candidate_x in range(left, right - template_width + 1, search_step):
            hits = 0
            weighted_total = 0
            for sample_x, sample_y, kind in scaled_samples:
                weight = 2 if kind == "white" else 1
                weighted_total += weight
                if target_sample_matches(*rgb_image.getpixel((candidate_x + sample_x, candidate_y + sample_y)), kind):
                    hits += weight
            score = hits / max(1, weighted_total)
            if score < min_score:
                continue

            box_left, box_top = image_point_to_adb(rgb_image, candidate_x, candidate_y)
            box_right, box_bottom = image_point_to_adb(
                rgb_image,
                candidate_x + template_width,
                candidate_y + template_height,
            )
            center = ((box_left + box_right) // 2, (box_top + box_bottom) // 2)
            raw_matches.append(TemplateMatchCandidate(center=center, box=(box_left, box_top, box_right, box_bottom), score=score))

    min_gap = max(22, min(template_width, template_height) // 2)
    filtered_matches: list[TemplateMatchCandidate] = []
    for match in sorted(raw_matches, key=lambda candidate: candidate.score, reverse=True):
        if any(
            abs(match.center[0] - existing.center[0]) < min_gap
            and abs(match.center[1] - existing.center[1]) < min_gap
            for existing in filtered_matches
        ):
            continue
        filtered_matches.append(match)
        if len(filtered_matches) >= max_results:
            break
    return filtered_matches


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


def auto_assist_green_pixel(red: int, green: int, blue: int) -> bool:
    return (
        20 <= red <= 125
        and 120 <= green <= 230
        and 25 <= blue <= 150
        and green >= red + 45
        and green >= blue + 35
    )


def auto_assist_hand_pixel(red: int, green: int, blue: int) -> bool:
    return (
        150 <= red <= 245
        and 80 <= green <= 185
        and 45 <= blue <= 150
        and red >= green + 25
        and green >= blue + 15
    )


def alliance_tab_visible(image: Image.Image, profile: ScreenProfile = ADB_PROFILE) -> bool:
    if profile is not ADB_PROFILE:
        profile = ADB_PROFILE

    nav_hits = 0
    for box in ALLIANCE_NAV_BLOCKS:
        if adb_box_ratio(image, box, nav_blue_pixel) >= 0.68 or adb_box_average_near(image, box, NAV_BLUE, 28):
            nav_hits += 1

    icon_hits = adb_color_block_hits(image, ALLIANCE_ICON_BLOCKS, icon_white_pixel, 0.22)
    return nav_hits >= 3 and icon_hits >= 1


def auto_assist_handshake_visible(image: Image.Image, profile: ScreenProfile = ADB_PROFILE) -> bool:
    if not alliance_tab_visible(image, profile):
        return False

    green_ratio = adb_box_ratio(image, AUTO_ASSIST_GREEN_BLOCK, auto_assist_green_pixel)
    hand_ratio = adb_box_ratio(image, AUTO_ASSIST_HAND_BLOCK, auto_assist_hand_pixel)
    bubble_white_ratio = adb_box_ratio(image, AUTO_ASSIST_BUBBLE_BLOCK, icon_white_pixel)
    return green_ratio >= 0.055 and hand_ratio >= 0.045 and bubble_white_ratio >= 0.10


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


def debug_point_box(x: int, y: int, radius: int = 4) -> tuple[int, int, int, int]:
    return (
        max(0, x - radius),
        max(0, y - radius),
        min(ADB_REF_WIDTH, x + radius + 1),
        min(ADB_REF_HEIGHT, y + radius + 1),
    )


@dataclass(frozen=True)
class BuildingActionCandidate:
    center: tuple[int, int]
    box: tuple[int, int, int, int]
    area: int
    white_ratio: float
    blue_ratio: float


@dataclass(frozen=True)
class ImageTemplate:
    path: Path
    width: int
    height: int
    samples: tuple[tuple[int, int, str], ...]


@dataclass(frozen=True)
class TemplateMatchCandidate:
    center: tuple[int, int]
    box: tuple[int, int, int, int]
    score: float


_image_template_cache: dict[tuple[str, int], ImageTemplate] = {}


def debug_ranges_for_step(
    step: str,
    unit_label: str = "",
    row_y: int | None = None,
) -> list[DebugRange]:
    ranges: list[tuple[str, str, tuple[int, int, int, int]]] = []

    if step == "home":
        for label, x, y, _target in MAIN_AVATAR_FIXED_POINTS:
            ranges.append((label, "#a78bfa", debug_point_box(x, y)))
        for label, x, y, _target in MAIN_TOP_FIXED_POINTS:
            ranges.append((label, "#38bdf8", debug_point_box(x, y)))
        for index, box in enumerate(MAIN_TOP_BAR_BLOCKS, start=1):
            ranges.append((f"顶栏底色{index}", "#38bdf8", box))
        for label, x, y, _target in MAIN_TOGGLE_FIXED_POINTS:
            ranges.append((label, "#f59e0b", debug_point_box(x, y)))
        ranges.append(("右下图形兜底", "#f59e0b", MAIN_CITY_TOGGLE_ICON_BLOCK))
        return ranges

    if step == "explore_entry":
        for index, box in enumerate(EXPLORE_NAV_BLOCKS, start=1):
            ranges.append((f"探险底色{index}", "#38bdf8", box))
        for index, box in enumerate(EXPLORE_SWORD_BLOCKS, start=1):
            ranges.append((f"双剑白边{index}", "#facc15", box))
        return ranges

    if step == "auto_assist":
        for index, box in enumerate(ALLIANCE_NAV_BLOCKS, start=1):
            ranges.append((f"联盟底色{index}", "#38bdf8", box))
        for index, box in enumerate(ALLIANCE_ICON_BLOCKS, start=1):
            ranges.append((f"联盟图形{index}", "#facc15", box))
        ranges.append(("协助白框", "#e879f9", AUTO_ASSIST_BUBBLE_BLOCK))
        ranges.append(("协助绿底", "#22c55e", AUTO_ASSIST_GREEN_BLOCK))
        ranges.append(("握手图形", "#fb923c", AUTO_ASSIST_HAND_BLOCK))
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
        ranges.append(("顶部建筑锚点", "#facc15", QUEUE_TOP_BUILDING_ICON_BLOCK))
        ranges.append(("顶部部队锚点", "#facc15", QUEUE_TOP_TROOP_ICON_BLOCK))
        ranges.append(("顶部科研锚点", "#facc15", QUEUE_TOP_RESEARCH_ICON_BLOCK))
        ranges.append(("队列收起箭头", "#60a5fa", QUEUE_COLLAPSE_ARROW_BLOCK))
        for _unit_key, label, y in TRAIN_UNITS:
            ranges.append((f"{label}状态", "#c084fc", (375, y - 34, 430, y + 34)))
            ranges.append((f"{label}倒计时", "#c084fc", (75, y - 24, 370, y + 24)))
            ranges.append((f"{label}进度条", "#22c55e", (75, y + 6, 370, y + 28)))
        return ranges

    if step == "unit_row" and row_y is not None:
        label = unit_label or "士兵"
        return [
            (f"{label}状态", "#c084fc", (375, row_y - 34, 430, row_y + 34)),
            (f"{label}倒计时", "#c084fc", (75, row_y - 24, 370, row_y + 24)),
            (f"{label}进度条", "#22c55e", (75, row_y + 6, 370, row_y + 28)),
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
            ("数量条", "#22c55e", SOLDIER_QUANTITY_BAR_BLOCK),
            ("训练按钮手势", "#f59e0b", SOLDIER_TRAIN_GUIDE_HAND_SCAN_BOX),
            ("训练按钮区", "#60a5fa", SOLDIER_TRAIN_BUTTON_BLOCK),
        ]

    if step == "train_levels":
        for x, label in TRAIN_LEVEL_CANDIDATES:
            ranges.append((f"等级{label}边框", "#e879f9", (max(0, x - 45), 623, min(ADB_REF_WIDTH, x + 45), 715)))
        ranges.append(("数量条", "#22c55e", SOLDIER_QUANTITY_BAR_BLOCK))
        ranges.append(("训练按钮手势", "#f59e0b", SOLDIER_TRAIN_GUIDE_HAND_SCAN_BOX))
        ranges.append(("训练按钮区", "#60a5fa", SOLDIER_TRAIN_BUTTON_BLOCK))
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


def queue_anchor_light_pixel(red: int, green: int, blue: int) -> bool:
    return red >= 180 and green >= 180 and blue >= 180


def queue_panel_at_top_visible(image: Image.Image) -> bool:
    if not queue_panel_visible(image):
        return False

    building_ratio = adb_box_ratio(image, QUEUE_TOP_BUILDING_ICON_BLOCK, queue_anchor_light_pixel)
    troop_ratio = adb_box_ratio(image, QUEUE_TOP_TROOP_ICON_BLOCK, queue_anchor_light_pixel)
    research_ratio = adb_box_ratio(image, QUEUE_TOP_RESEARCH_ICON_BLOCK, queue_anchor_light_pixel)
    collapse_white_ratio = adb_box_ratio(image, QUEUE_COLLAPSE_ARROW_BLOCK, icon_white_pixel)
    collapse_blue_ratio = adb_box_ratio(image, QUEUE_COLLAPSE_ARROW_BLOCK, nav_blue_pixel)
    known_rows = sum(1 for _unit_key, _unit_label, row_y in TRAIN_UNITS if unit_row_state(image, row_y) != "unknown")

    return (
        building_ratio >= 0.18
        and troop_ratio >= 0.15
        and research_ratio >= 0.08
        and collapse_white_ratio >= 0.12
        and collapse_blue_ratio >= 0.20
        and known_rows >= 2
    )


def queue_progress_green_pixel(red: int, green: int, blue: int) -> bool:
    return (
        10 <= red <= 90
        and 110 <= green <= 230
        and blue <= 130
        and green >= red + 60
        and green >= blue + 35
    )


def queue_progress_bar_visible(image: Image.Image, row_y: int) -> bool:
    progress_box = adb_box(75, row_y + 6, 370, row_y + 28)
    green_density = box_density(image, progress_box, queue_progress_green_pixel)
    time_box = adb_box(150, row_y + 2, 365, row_y + 31)
    time_density = box_density(image, time_box, queue_time_foreground_pixel)
    return green_density >= 0.055 and time_density >= 0.010


def queue_time_foreground_pixel(red: int, green: int, blue: int) -> bool:
    white_digit = red >= 205 and green >= 205 and blue >= 205
    orange_digit = red >= 185 and 80 <= green <= 185 and blue <= 105 and red >= green + 35
    return white_digit or orange_digit


def queue_time_digit_runs(crop: Image.Image) -> list[tuple[int, int, int, int, int]]:
    crop = crop.convert("RGB")
    columns = [
        sum(1 for y in range(crop.height) if queue_time_foreground_pixel(*crop.getpixel((x, y))))
        for x in range(crop.width)
    ]
    runs: list[tuple[int, int, int, int, int]] = []
    in_run = False
    start = 0
    for index, count in enumerate(columns):
        if count > 0 and not in_run:
            start = index
            in_run = True
        if in_run and (count == 0 or index == len(columns) - 1):
            end = index if count == 0 else index + 1
            ys = [
                y
                for y in range(crop.height)
                for x in range(start, end)
                if queue_time_foreground_pixel(*crop.getpixel((x, y)))
            ]
            if ys:
                runs.append((start, end, min(ys), max(ys) + 1, len(ys)))
            in_run = False
    return [run for run in runs if run[4] >= 20]


def queue_time_digit_signature(crop: Image.Image, run: tuple[int, int, int, int, int]) -> str:
    x1, x2, y1, y2, _area = run
    glyph = crop.crop((x1, y1, x2, y2)).convert("RGB")
    bits: list[str] = []
    for yy in range(QUEUE_TIME_TEMPLATE_HEIGHT):
        for xx in range(QUEUE_TIME_TEMPLATE_WIDTH):
            sx1 = int(xx * glyph.width / QUEUE_TIME_TEMPLATE_WIDTH)
            sx2 = max(sx1 + 1, int((xx + 1) * glyph.width / QUEUE_TIME_TEMPLATE_WIDTH))
            sy1 = int(yy * glyph.height / QUEUE_TIME_TEMPLATE_HEIGHT)
            sy2 = max(sy1 + 1, int((yy + 1) * glyph.height / QUEUE_TIME_TEMPLATE_HEIGHT))
            hits = total = 0
            for sy in range(sy1, min(glyph.height, sy2)):
                for sx in range(sx1, min(glyph.width, sx2)):
                    total += 1
                    if queue_time_foreground_pixel(*glyph.getpixel((sx, sy))):
                        hits += 1
            bits.append("1" if total and hits / total >= 0.20 else "0")
    return "".join(bits)


def hamming_distance(left: str, right: str) -> int:
    return sum(1 for a, b in zip(left, right) if a != b) + abs(len(left) - len(right))


def classify_queue_time_digit(signature: str) -> str | None:
    best_digit: str | None = None
    best_distance = 10**9
    for digit, templates in QUEUE_TIME_DIGIT_TEMPLATES.items():
        for template in templates:
            distance = hamming_distance(signature, template)
            if distance < best_distance:
                best_distance = distance
                best_digit = digit
    return best_digit if best_distance <= 28 else None


def unit_row_remaining_seconds(image: Image.Image, row_y: int) -> int | None:
    crop = crop_adb_box(image, (145, row_y + 2, 370, row_y + 32))
    runs = queue_time_digit_runs(crop)
    if len(runs) < 6:
        return None
    digit_runs = runs[-6:]
    digits: list[str] = []
    for run in digit_runs:
        digit = classify_queue_time_digit(queue_time_digit_signature(crop, run))
        if digit is None:
            return None
        digits.append(digit)
    hours = int("".join(digits[0:2]))
    minutes = int("".join(digits[2:4]))
    seconds = int("".join(digits[4:6]))
    if minutes >= 60 or seconds >= 60:
        return None
    return hours * 3600 + minutes * 60 + seconds


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def unit_row_status_text(image: Image.Image, row_y: int) -> str:
    state, remaining = unit_row_status_data(image, row_y)
    return unit_status_display_text(state, remaining)


def unit_row_status_data(image: Image.Image, row_y: int) -> tuple[str, int | None]:
    state = unit_row_state(image, row_y)
    remaining = unit_row_remaining_seconds(image, row_y) if state == "busy" else None
    return state, remaining


def unit_status_display_text(state: str, remaining: int | None = None) -> str:
    if state == "busy":
        return f"训练中 {format_duration(remaining)}" if remaining is not None else "训练中"
    if state == "ready":
        return "已完成"
    if state == "idle":
        return "空闲中"
    if state == "blocked":
        return "建筑升级中"
    return "未知"


def adb_fixed_point_visible(image: Image.Image, x: int, y: int, target: tuple[int, int, int]) -> bool:
    rgb_image = image if image.mode == "RGB" else image.convert("RGB")
    px, py = adb_point_to_image(image, x, y)
    return rgb_image.getpixel((px, py)) == target


def adb_fixed_point_hits(image: Image.Image, points: list[tuple[str, int, int, tuple[int, int, int]]]) -> int:
    rgb_image = image if image.mode == "RGB" else image.convert("RGB")
    hits = 0
    for _label, x, y, target in points:
        px, py = adb_point_to_image(rgb_image, x, y)
        if rgb_image.getpixel((px, py)) == target:
            hits += 1
    return hits


def legacy_main_return_icon_visible(image: Image.Image) -> bool:
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


def main_avatar_frame_visible(image: Image.Image) -> bool:
    if image.size != (ADB_REF_WIDTH, ADB_REF_HEIGHT):
        return legacy_main_return_icon_visible(image)
    return adb_fixed_point_hits(image, MAIN_AVATAR_FIXED_POINTS) == len(MAIN_AVATAR_FIXED_POINTS)


def main_top_bar_pixel(red: int, green: int, blue: int) -> bool:
    return (
        20 <= red <= 80
        and 40 <= green <= 95
        and 65 <= blue <= 125
        and blue >= red + 25
        and blue >= green + 10
    )


def main_top_bar_anchor_visible(image: Image.Image) -> bool:
    if image.size != (ADB_REF_WIDTH, ADB_REF_HEIGHT):
        return True

    fixed_hits = adb_fixed_point_hits(image, MAIN_TOP_FIXED_POINTS)
    if fixed_hits == len(MAIN_TOP_FIXED_POINTS):
        return True

    block_hits = sum(1 for box in MAIN_TOP_BAR_BLOCKS if adb_box_ratio(image, box, main_top_bar_pixel) >= 0.55)
    return fixed_hits >= 1 and block_hits >= 3


def main_city_toggle_visible(image: Image.Image) -> bool:
    icon_white_ratio = adb_box_ratio(image, MAIN_CITY_TOGGLE_ICON_BLOCK, icon_white_pixel)
    icon_gold_ratio = adb_box_ratio(image, MAIN_CITY_TOGGLE_ICON_BLOCK, gold_brown_pixel)
    icon_nav_ratio = adb_box_ratio(image, MAIN_CITY_TOGGLE_ICON_BLOCK, nav_blue_pixel)
    block_nav_ratio = adb_box_ratio(image, MAIN_CITY_TOGGLE_BLOCK, nav_blue_pixel)
    fixed_hits = (
        adb_fixed_point_hits(image, MAIN_TOGGLE_FIXED_POINTS)
        if image.size == (ADB_REF_WIDTH, ADB_REF_HEIGHT)
        else 0
    )

    legacy_visible = (
        icon_white_ratio >= 0.12
        and icon_gold_ratio >= 0.035
        and (icon_nav_ratio >= 0.10 or block_nav_ratio >= 0.22)
    )
    return fixed_hits >= 2 or (fixed_hits >= 1 and legacy_visible)


def main_screen_visible(image: Image.Image) -> bool:
    return main_avatar_frame_visible(image) and main_top_bar_anchor_visible(image) and main_city_toggle_visible(image)


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
    status_text_box = adb_box(155, row_y - 26, 355, row_y + 28)

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

    if queue_progress_bar_visible(image, row_y):
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


def soldier_quantity_bar_pixel(red: int, green: int, blue: int) -> bool:
    return (
        35 <= red <= 115
        and 170 <= green <= 255
        and 35 <= blue <= 135
        and green >= red + 70
        and green >= blue + 60
    )


def soldier_page_visible(image: Image.Image) -> bool:
    back_ratio = adb_box_ratio(image, SOLDIER_PAGE_BACK_BLOCK, icon_white_pixel)
    tab_blocks = [SOLDIER_SELECTED_TAB_BLOCK, SOLDIER_SPEAR_TAB_BLOCK, SOLDIER_ARCHER_TAB_BLOCK]
    selected_ratios = [adb_box_ratio(image, box, soldier_tab_selected_pixel) for box in tab_blocks]
    blue_ratios = [adb_box_ratio(image, box, soldier_tab_blue_pixel) for box in tab_blocks]
    selected_tab_count = sum(1 for ratio in selected_ratios if ratio >= 0.35)
    visible_tab_count = sum(1 for selected, blue in zip(selected_ratios, blue_ratios) if selected >= 0.35 or blue >= 0.35)
    button_ratio = adb_box_ratio(image, SOLDIER_BOTTOM_BUTTON_BLOCK, soldier_button_pixel)

    return (
        back_ratio >= 0.030
        and selected_tab_count >= 1
        and visible_tab_count >= 3
        and button_ratio >= 0.22
    )


def soldier_quantity_bar_visible(image: Image.Image) -> bool:
    return adb_box_ratio(image, SOLDIER_QUANTITY_BAR_BLOCK, soldier_quantity_bar_pixel) >= 0.12


def soldier_training_started_visible(image: Image.Image) -> bool:
    panel_density = box_density(
        image,
        adb_box(50, 815, 680, 1045),
        lambda r, g, b: 35 <= r <= 95
        and 75 <= g <= 160
        and 120 <= b <= 220
        and b >= r + 55,
    )
    return soldier_page_visible(image) and (not soldier_quantity_bar_visible(image) or panel_density >= 0.25)


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


def find_guided_soldier_train_button(image: Image.Image) -> tuple[int, int] | None:
    if not soldier_page_visible(image) or not soldier_quantity_bar_visible(image):
        return None
    if image.mode != "RGB":
        image = image.convert("RGB")

    left, top, right, bottom = adb_box_to_image(image, SOLDIER_TRAIN_GUIDE_HAND_SCAN_BOX)
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

    _area, (comp_left, comp_top, comp_right, comp_bottom) = best
    comp_width = comp_right - comp_left
    comp_height = comp_bottom - comp_top
    target_x = comp_left + round(comp_width * 0.18)
    target_y = comp_bottom + round(comp_height * 0.22)
    target_x = max(SOLDIER_TRAIN_BUTTON_BLOCK[0], min(SOLDIER_TRAIN_BUTTON_BLOCK[2], target_x))
    target_y = max(SOLDIER_TRAIN_BUTTON_BLOCK[1], min(SOLDIER_TRAIN_BUTTON_BLOCK[3], target_y))
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

    template = load_image_template(BUILDING_TRAIN_ACTION_TEMPLATE)
    if template is not None:
        matches = find_template_matches(
            image,
            template,
            BUILDING_ACTION_SCAN_BOX,
            min_score=0.86,
            search_step=6,
            max_results=1,
        )
        if matches:
            return matches[0].center

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


def available_train_level_xs(image: Image.Image) -> list[int]:
    if not soldier_page_visible(image):
        return []
    return [x for x, _label in TRAIN_LEVEL_CANDIDATES if x <= 690 and train_level_available(image, x)]


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
        user32.SetWindowPos(hwnd, HWND_TOP, left, top, width, height, SWP_NOACTIVATE)

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
        self.root = root
        self.window = window
        self.saved_settings = app.panel_settings(window)
        self.settings_ready = False
        self.status_var = tk.StringVar(master=root, value="已附加，等待操作。")
        self.task_hint_var = tk.StringVar(master=root, value="当前任务：空闲 | 状态：等待\n操作：勾选任务后点击开始任务。")
        self.task_vars: dict[str, tk.BooleanVar] = {}
        self.task_checks: dict[str, tk.Checkbutton] = {}
        self.task_text_labels: dict[str, tk.Widget] = {}
        self.task_countdown_vars: dict[str, tk.StringVar] = {}
        self.soldier_loop_texts: dict[str, str] = {unit_key: "未启动" for unit_key, _unit_label, _row_y in TRAIN_UNITS}
        self.soldier_loop_rotate_index = 0
        self.soldier_loop_after_id: str | None = None
        self.start_btn: tk.Button | None = None
        self.stop_btn: tk.Button | None = None
        self.debug_ranges_var = tk.BooleanVar(master=root, value=bool(self.saved_settings.get("debug_ranges", False)))
        self.debug_check: tk.Checkbutton | None = None
        self.expanded = bool(self.saved_settings.get("expanded", False))
        self.content_top: tk.Toplevel | None = None
        self.content_frame: tk.Frame | None = None
        self.toggle_btn: tk.Button | None = None
        self.opacity_value = int(self.saved_settings.get("opacity", DEFAULT_PANEL_OPACITY))
        self.opacity_value = max(MIN_PANEL_OPACITY, min(MAX_PANEL_OPACITY, self.opacity_value))
        self.opacity_var = tk.IntVar(master=root, value=self.opacity_value)
        try:
            self.assist_interval_value = int(
                self.saved_settings.get("assist_interval", AUTO_ASSIST_DEFAULT_INTERVAL_SECONDS)
            )
        except (TypeError, ValueError):
            self.assist_interval_value = AUTO_ASSIST_DEFAULT_INTERVAL_SECONDS
        self.assist_interval_value = max(
            AUTO_ASSIST_MIN_INTERVAL_SECONDS,
            min(AUTO_ASSIST_MAX_INTERVAL_SECONDS, self.assist_interval_value),
        )
        self.assist_interval_var = tk.IntVar(master=root, value=self.assist_interval_value)
        self.assist_interval_spin: tk.Spinbox | None = None
        self.debug_overlay: DebugRangeOverlay | None = None
        self.debug_ranges: list[DebugRange] = debug_ranges_for_step("home")
        self.soldier_status_popup: tk.Toplevel | None = None
        self.soldier_status_title_var = tk.StringVar(master=root, value="")
        self.soldier_status_summary_var = tk.StringVar(master=root, value="")
        self.soldier_status_row_vars: dict[str, tk.StringVar] = {}
        self.soldier_status_after_id: str | None = None
        self.soldier_status_worker: threading.Thread | None = None
        self.soldier_status_loading = False
        self.soldier_status_snapshot: list[tuple[str, str, int | None]] = []
        self.soldier_status_snapshot_at: float | None = None
        self.soldier_status_summary = ""

        self.top = tk.Toplevel(root)
        self.top.title(self.title_summary())
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", False)
        self.top.attributes("-alpha", self.opacity_value / 100)
        self.top.configure(bg="#1f2937")
        self.top.protocol("WM_DELETE_WINDOW", app.close)

        self._drag_start: tuple[int, int] | None = None
        self.build_ui()
        self.attach()
        if self.debug_ranges_var.get() and self.expanded:
            self.toggle_debug_ranges()

    def build_ui(self) -> None:
        self.top.columnconfigure(0, weight=1)

        title_bar = tk.Frame(self.top, bg="#111827", height=COLLAPSED_CONTROL_HEIGHT)
        title_bar.grid(row=0, column=0, sticky="ew")
        title_bar.grid_propagate(False)
        title_bar.grid_columnconfigure(1, weight=1)
        title_bar.bind("<ButtonPress-1>", self.start_drag)
        title_bar.bind("<B1-Motion>", self.drag_panel)

        self.toggle_btn = tk.Button(
            title_bar,
            text="收起" if self.expanded else "展开",
            command=self.toggle_expanded,
            bd=0,
            bg="#111827",
            fg="#bfdbfe",
            activebackground="#1f2937",
            activeforeground="#ffffff",
            font=("Microsoft YaHei UI", 9, "bold"),
            width=5,
        )
        self.toggle_btn.grid(row=0, column=0, padx=(8, 2), pady=4, sticky="w")

        self.title_label = tk.Label(
            title_bar,
            text=self.title_summary(),
            bg="#111827",
            fg="#f9fafb",
            font=("Microsoft YaHei UI", 10, "bold"),
            anchor="w",
        )
        self.title_label.grid(row=0, column=1, padx=(4, 8), pady=5, sticky="ew")
        self.title_label.bind("<ButtonPress-1>", self.start_drag)
        self.title_label.bind("<B1-Motion>", self.drag_panel)

        self.start_btn = tk.Button(
            title_bar,
            text="开始任务",
            command=lambda: self.app.start_panel_tasks(self),
            bg="#16a34a",
            fg="#ffffff",
            activebackground="#15803d",
            activeforeground="#ffffff",
            bd=0,
            padx=8,
            pady=4,
            width=8,
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        self.start_btn.grid(row=0, column=2, sticky="e", padx=(0, 6), pady=4)

        self.stop_btn = tk.Button(
            title_bar,
            text="停止任务",
            command=self.app.stop_all_tasks,
            bg="#dc2626",
            fg="#ffffff",
            activebackground="#b91c1c",
            activeforeground="#ffffff",
            bd=0,
            padx=8,
            pady=4,
            width=8,
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        self.stop_btn.grid(row=0, column=3, sticky="e", padx=(0, 6), pady=4)

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
        close_btn.grid(row=0, column=4, sticky="e")

        self.content_top = tk.Toplevel(self.root)
        self.content_top.withdraw()
        self.content_top.title(f"{self.title_summary()} | 展开内容")
        self.content_top.overrideredirect(True)
        self.content_top.attributes("-topmost", False)
        self.content_top.attributes("-alpha", self.opacity_value / 100)
        self.content_top.configure(bg="#1f2937")
        self.content_top.protocol("WM_DELETE_WINDOW", self.app.close)
        self.content_top.columnconfigure(0, weight=1)
        self.content_top.rowconfigure(0, weight=1)

        self.content_frame = tk.Frame(self.content_top, bg="#1f2937")
        self.content_frame.grid(row=0, column=0, sticky="nsew")
        self.content_frame.columnconfigure(0, weight=1)

        task_grid = tk.Frame(self.content_frame, bg="#1f2937")
        task_grid.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        task_grid.columnconfigure(0, weight=1)

        saved_tasks = self.saved_settings.get("tasks", {})
        if not isinstance(saved_tasks, dict):
            saved_tasks = {}
        default_tasks = default_panel_settings()["tasks"]

        for index, (task_key, task_label) in enumerate(TASK_DEFINITIONS):
            var = tk.BooleanVar(master=self.top, value=bool(saved_tasks.get(task_key, default_tasks.get(task_key, True))))
            task_cell = tk.Frame(task_grid, bg="#1f2937")
            task_cell.grid(row=index, column=0, sticky="ew", pady=3)
            task_cell.columnconfigure(1, weight=1)

            check = tk.Checkbutton(
                task_cell,
                text="",
                variable=var,
                indicatoron=True,
                bg="#1f2937",
                fg="#d1d5db",
                selectcolor="#111827",
                activebackground="#1f2937",
                activeforeground="#ffffff",
                font=("Microsoft YaHei UI", 10, "bold"),
                anchor="w",
                width=1,
                command=self.save_settings,
            )
            check.grid(row=0, column=0, sticky="w")

            label = tk.Label(
                task_cell,
                text=f"[循环] {task_label}",
                bg="#1f2937",
                fg="#d1d5db",
                font=("Microsoft YaHei UI", 10, "bold"),
                cursor="hand2" if task_key == "train_soldiers" else "",
                anchor="w",
            )
            label.grid(row=0, column=1, sticky="w", padx=(4, 6))
            if task_key == "train_soldiers":
                label.bind("<Button-1>", self.open_soldier_status_popup)
                self.task_text_labels[task_key] = label

            countdown_var = tk.StringVar(master=self.top, value="未启动")
            self.task_countdown_vars[task_key] = countdown_var
            tk.Label(
                task_cell,
                textvariable=countdown_var,
                bg="#1f2937",
                fg="#93c5fd",
                anchor="e",
                font=("Microsoft YaHei UI", 9),
                width=24,
            ).grid(row=0, column=2, sticky="e")

            self.task_vars[task_key] = var
            self.task_checks[task_key] = check
            var.trace_add("write", lambda *_: self.save_settings())

        option_row = tk.Frame(self.content_frame, bg="#1f2937")
        option_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(8, 2))
        option_row.columnconfigure(2, weight=1)

        self.debug_check = tk.Checkbutton(
            option_row,
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
        self.debug_check.grid(row=0, column=0, sticky="w", padx=(0, 12))

        interval_frame = tk.Frame(option_row, bg="#1f2937")
        interval_frame.grid(row=0, column=1, sticky="w", padx=(0, 18))
        interval_frame.columnconfigure(1, weight=1)
        tk.Label(
            interval_frame,
            text="协助间隔",
            bg="#1f2937",
            fg="#d1d5db",
            font=("Microsoft YaHei UI", 9),
        ).grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.assist_interval_spin = tk.Spinbox(
            interval_frame,
            from_=AUTO_ASSIST_MIN_INTERVAL_SECONDS,
            to=AUTO_ASSIST_MAX_INTERVAL_SECONDS,
            increment=5,
            textvariable=self.assist_interval_var,
            width=5,
            justify="center",
            bg="#111827",
            fg="#f9fafb",
            buttonbackground="#374151",
            font=("Microsoft YaHei UI", 9),
        )
        self.assist_interval_spin.grid(row=0, column=1, sticky="ew")
        tk.Label(
            interval_frame,
            text="秒",
            bg="#1f2937",
            fg="#9ca3af",
            font=("Microsoft YaHei UI", 9),
        ).grid(row=0, column=2, sticky="e", padx=(6, 0))

        opacity_frame = tk.Frame(option_row, bg="#1f2937")
        opacity_frame.grid(row=0, column=2, sticky="ew")
        opacity_frame.columnconfigure(1, weight=1)
        tk.Label(
            opacity_frame,
            text="透明度",
            bg="#1f2937",
            fg="#d1d5db",
            font=("Microsoft YaHei UI", 9),
        ).grid(row=0, column=0, sticky="w", padx=(0, 6))
        tk.Scale(
            opacity_frame,
            from_=MIN_PANEL_OPACITY,
            to=MAX_PANEL_OPACITY,
            orient="horizontal",
            variable=self.opacity_var,
            showvalue=True,
            bg="#1f2937",
            fg="#d1d5db",
            troughcolor="#111827",
            highlightthickness=0,
            length=150,
            command=lambda _value: self.on_opacity_changed(),
        ).grid(row=0, column=1, sticky="ew")

        task_hint = tk.Label(
            self.content_frame,
            textvariable=self.task_hint_var,
            bg="#1f2937",
            fg="#d1d5db",
            justify="left",
            anchor="w",
            wraplength=620,
            font=("Microsoft YaHei UI", 9),
        )
        task_hint.grid(row=2, column=0, sticky="ew", padx=10, pady=(8, 6))

        self.assist_interval_var.trace_add("write", lambda *_: self.on_assist_interval_changed())
        self.opacity_var.trace_add("write", lambda *_: self.on_opacity_changed())
        self.settings_ready = True
        self.sync_loop_countdown_labels()
        self.apply_expanded_state()

    def title_summary(self) -> str:
        index = self.window.vm_index or "?"
        adb_text = self.window.adb_serial or "未连接ADB"
        return f"{self.window.title} | index={index} | adb={adb_text}"

    def update_window(self, window: TargetWindow) -> None:
        self.window = window
        self.top.title(self.title_summary())
        self.title_label.configure(text=self.title_summary())
        if self.content_top is not None:
            self.content_top.title(f"{self.title_summary()} | 展开内容")
        self.attach()
        self.refresh_debug_overlay()

    def current_control_height(self) -> int:
        return COLLAPSED_CONTROL_HEIGHT

    def apply_window_alpha(self) -> None:
        self.opacity_value = max(MIN_PANEL_OPACITY, min(MAX_PANEL_OPACITY, int(self.opacity_var.get())))
        self.top.attributes("-alpha", self.opacity_value / 100)
        if self.content_top is not None:
            self.content_top.attributes("-alpha", self.opacity_value / 100)

    def apply_expanded_state(self) -> None:
        if self.toggle_btn is not None:
            self.toggle_btn.configure(text="收起" if self.expanded else "展开")
        if not self.expanded:
            if self.content_top is not None:
                self.content_top.withdraw()
            self.hide_debug_overlay()
        self.attach()

    def toggle_expanded(self) -> None:
        self.expanded = not self.expanded
        self.apply_expanded_state()
        if self.expanded and self.debug_ranges_var.get():
            if self.debug_overlay is None:
                self.debug_overlay = DebugRangeOverlay(self.top, self.window)
            self.debug_overlay.set_ranges(self.debug_ranges)
            self.debug_overlay.refresh()
        self.save_settings()

    def on_opacity_changed(self) -> None:
        try:
            self.apply_window_alpha()
        except tk.TclError:
            return
        self.save_settings()

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
        top = max(0, rect.top - COLLAPSED_CONTROL_HEIGHT)
        width = max(520, rect.width)
        self.set_geometry(width, COLLAPSED_CONTROL_HEIGHT, left, top)

        if self.content_top is not None:
            if self.expanded:
                content_rect = self.expanded_content_rect(rect)
                self.content_top.deiconify()
                self.set_geometry(
                    content_rect.width,
                    content_rect.height,
                    content_rect.left,
                    content_rect.top,
                    window=self.content_top,
                )
            else:
                self.content_top.withdraw()
        self.refresh_debug_overlay()

    def expanded_content_rect(self, fallback_rect: Rect) -> Rect:
        content_rect = get_emulator_content_rect(self.window.hwnd) or fallback_rect
        left = content_rect.left
        top = content_rect.top
        width = max(720, fallback_rect.width, content_rect.width)
        height = max(CONTROL_HEIGHT, content_rect.height)

        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
        if screen_w > left:
            width = min(width, max(360, screen_w - left))
        if screen_h > top:
            height = min(height, max(CONTROL_HEIGHT, screen_h - top))
        return Rect(left, top, left + width, top + height)

    def set_geometry(
        self,
        width: int,
        height: int,
        left: int,
        top: int,
        window: tk.Toplevel | None = None,
    ) -> None:
        target = window or self.top
        target.geometry(f"{width}x{height}+{left}+{top}")
        target.update_idletasks()
        hwnd = tk_top_hwnd(target)
        target.lift()
        user32.SetWindowPos(hwnd, HWND_TOPMOST, left, top, width, height, SWP_NOACTIVATE)
        user32.SetWindowPos(hwnd, HWND_NOTOPMOST, left, top, width, height, SWP_NOACTIVATE)

    def current_task_label(self) -> str:
        current_tasks = getattr(self.app, "current_tasks", {})
        task_key = current_tasks.get(self.window.hwnd)
        if not task_key:
            return "空闲"
        return dict(TASK_DEFINITIONS).get(task_key, task_key)

    def task_status_from_message(self, text: str) -> str:
        if any(word in text for word in ("失败", "超时", "停止", "无法", "仍", "未能", "未验证")):
            return "异常"
        if "跳过" in text:
            return "跳过"
        if any(word in text for word in ("完成", "已", "成功", "消失")):
            return "成功"
        return "执行中"

    def update_task_hint(self, text: str) -> None:
        operation = text.strip()
        if len(operation) > 46:
            operation = operation[:45] + "..."
        task_label = self.current_task_label()
        status = "等待" if task_label == "空闲" else self.task_status_from_message(text)
        self.task_hint_var.set(f"当前任务：{task_label} | 状态：{status}\n操作：{operation}")

    def log(self, text: str) -> None:
        now = datetime.now().strftime("%H:%M:%S")
        self.status_var.set(f"[{now}] {text}")
        self.update_task_hint(text)

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
            self.save_settings()
            return
        self.hide_debug_overlay()
        self.log("已隐藏取色范围。")
        self.save_settings()

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

    def assist_interval_seconds(self) -> int:
        try:
            value = int(self.assist_interval_var.get())
        except (tk.TclError, ValueError):
            value = AUTO_ASSIST_DEFAULT_INTERVAL_SECONDS
        value = max(AUTO_ASSIST_MIN_INTERVAL_SECONDS, min(AUTO_ASSIST_MAX_INTERVAL_SECONDS, value))
        self.assist_interval_value = value
        try:
            if int(self.assist_interval_var.get()) != value:
                self.assist_interval_var.set(value)
        except (tk.TclError, ValueError):
            self.assist_interval_var.set(value)
        return value

    def on_assist_interval_changed(self) -> None:
        self.assist_interval_seconds()
        self.sync_loop_countdown_labels()
        self.save_settings()

    def sync_loop_countdown_labels(self) -> None:
        self.set_task_countdown_text("adventure", f"间隔 {format_duration(ADVENTURE_LOOP_INTERVAL_SECONDS)}")
        self.set_task_countdown_text("auto_assist", f"间隔 {self.assist_interval_seconds()} 秒")
        self.update_soldier_loop_countdown_display()

    def set_task_countdown_text(self, task_key: str, text: str) -> None:
        var = self.task_countdown_vars.get(task_key)
        if var is not None:
            var.set(text)

    def set_task_countdown(self, task_key: str, remaining_seconds: int | None) -> None:
        if remaining_seconds is None:
            if task_key == "adventure":
                self.set_task_countdown_text(task_key, f"间隔 {format_duration(ADVENTURE_LOOP_INTERVAL_SECONDS)}")
            elif task_key == "auto_assist":
                self.set_task_countdown_text(task_key, f"间隔 {self.assist_interval_seconds()} 秒")
            else:
                self.set_task_countdown_text(task_key, "未启动")
            return
        remaining_seconds = max(0, int(remaining_seconds))
        self.set_task_countdown_text(task_key, "检测中" if remaining_seconds == 0 else f"下次 {format_duration(remaining_seconds)}")

    def set_auto_assist_countdown(self, remaining_seconds: int | None) -> None:
        self.set_task_countdown("auto_assist", remaining_seconds)

    def set_soldier_loop_text(self, unit_key: str, text: str) -> None:
        if unit_key in self.soldier_loop_texts:
            self.soldier_loop_texts[unit_key] = text
        self.update_soldier_loop_countdown_display()

    def update_soldier_loop_countdown_display(self) -> None:
        if not self.soldier_loop_texts:
            self.set_task_countdown_text("train_soldiers", "未启动")
            return
        units = list(TRAIN_UNITS)
        unit_key, unit_label, _row_y = units[self.soldier_loop_rotate_index % len(units)]
        self.set_task_countdown_text("train_soldiers", f"{unit_label} {self.soldier_loop_texts.get(unit_key, '未启动')}")

        if self.soldier_loop_after_id is None and self.top.winfo_exists():
            self.soldier_loop_after_id = self.top.after(1500, self.rotate_soldier_loop_countdown)

    def rotate_soldier_loop_countdown(self) -> None:
        self.soldier_loop_after_id = None
        self.soldier_loop_rotate_index = (self.soldier_loop_rotate_index + 1) % max(1, len(TRAIN_UNITS))
        self.update_soldier_loop_countdown_display()

    def save_settings(self) -> None:
        if not getattr(self, "settings_ready", False):
            return
        tasks = {task_key: bool(var.get()) for task_key, var in self.task_vars.items()}
        self.app.save_panel_settings(
            self.window,
            tasks=tasks,
            assist_interval=self.assist_interval_value,
            debug_ranges=bool(self.debug_ranges_var.get()),
            expanded=bool(self.expanded),
            opacity=int(self.opacity_value),
        )

    def reset_task_states(self) -> None:
        for check in self.task_checks.values():
            check.configure(fg="#d1d5db", activeforeground="#ffffff")
        for label in self.task_text_labels.values():
            label.configure(fg="#d1d5db")
        self.task_hint_var.set("当前任务：空闲 | 状态：等待\n操作：勾选任务后点击开始任务。")
        self.soldier_loop_texts = {unit_key: "未启动" for unit_key, _unit_label, _row_y in TRAIN_UNITS}
        self.soldier_loop_rotate_index = 0
        self.sync_loop_countdown_labels()

    def mark_task_done(self, task_key: str) -> None:
        check = self.task_checks.get(task_key)
        if check is not None:
            check.configure(fg="#22c55e", activeforeground="#22c55e")
        label = self.task_text_labels.get(task_key)
        if label is not None:
            label.configure(fg="#22c55e")
        task_label = dict(TASK_DEFINITIONS).get(task_key, task_key)
        self.task_hint_var.set(f"当前任务：{task_label} | 状态：成功\n操作：任务已完成。")

    def open_soldier_status_popup(self, _event=None) -> str:
        if self.soldier_status_popup is not None and self.soldier_status_popup.winfo_exists():
            self.soldier_status_popup.deiconify()
            self.soldier_status_popup.lift()
            self.update_soldier_status_popup_display()
            return "break"

        popup = tk.Toplevel(self.top)
        popup.title("训练士兵状态")
        popup.configure(bg="#111827")
        popup.resizable(False, False)
        popup.attributes("-topmost", False)
        popup.protocol("WM_DELETE_WINDOW", self.close_soldier_status_popup)
        self.soldier_status_popup = popup
        self.soldier_status_snapshot = []
        self.soldier_status_snapshot_at = None
        self.soldier_status_summary = ""
        self.soldier_status_loading = False

        if self.expanded and self.content_top is not None and self.content_top.winfo_viewable():
            x = self.content_top.winfo_rootx() + 24
            y = self.content_top.winfo_rooty() + 24
        else:
            x = self.top.winfo_rootx() + 24
            y = self.top.winfo_rooty() + COLLAPSED_CONTROL_HEIGHT + 8
        popup.geometry(f"430x166+{x}+{y}")

        tk.Label(
            popup,
            textvariable=self.soldier_status_title_var,
            bg="#111827",
            fg="#f9fafb",
            font=("Microsoft YaHei UI", 10, "bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 4))

        self.soldier_status_row_vars = {}
        for row, (_unit_key, unit_label, _row_y) in enumerate(TRAIN_UNITS, start=1):
            tk.Label(
                popup,
                text=f"{unit_label}：",
                bg="#111827",
                fg="#d1d5db",
                font=("Microsoft YaHei UI", 10),
                anchor="w",
                width=7,
            ).grid(row=row, column=0, sticky="w", padx=(12, 2), pady=3)
            var = tk.StringVar(master=popup, value="读取中")
            self.soldier_status_row_vars[unit_label] = var
            tk.Label(
                popup,
                textvariable=var,
                bg="#111827",
                fg="#93c5fd",
                font=("Microsoft YaHei UI", 10, "bold"),
                anchor="w",
                width=26,
            ).grid(row=row, column=1, sticky="w", padx=(2, 12), pady=3)

        tk.Label(
            popup,
            textvariable=self.soldier_status_summary_var,
            bg="#111827",
            fg="#9ca3af",
            font=("Microsoft YaHei UI", 8),
            anchor="w",
        ).grid(row=4, column=0, columnspan=2, sticky="ew", padx=12, pady=(5, 10))

        popup.grid_columnconfigure(1, weight=1)
        self.refresh_soldier_status_popup()
        return "break"

    def refresh_soldier_status_popup(self) -> None:
        if self.soldier_status_popup is None or not self.soldier_status_popup.winfo_exists():
            return

        if not self.soldier_status_snapshot and not self.soldier_status_loading:
            self.soldier_status_loading = True
            self.soldier_status_summary_var.set("读取中...")
            window = self.window

            def _load_status() -> None:
                try:
                    status_snapshot, summary = self.app.read_soldier_status_snapshot(window, ensure_queue=True)
                except Exception as exc:
                    status_snapshot = [(unit_label, "unknown", None) for _unit_key, unit_label, _row_y in TRAIN_UNITS]
                    summary = f"错误：{exc}"

                def _apply_status() -> None:
                    self.soldier_status_loading = False
                    if self.soldier_status_popup is None or not self.soldier_status_popup.winfo_exists():
                        return
                    self.soldier_status_title_var.set(self.title_summary())
                    self.soldier_status_snapshot = status_snapshot
                    self.soldier_status_snapshot_at = time.monotonic()
                    self.soldier_status_summary = summary
                    self.update_soldier_status_popup_display()

                self.app.root.after(0, _apply_status)

            self.soldier_status_worker = threading.Thread(target=_load_status, daemon=True)
            self.soldier_status_worker.start()
        else:
            self.update_soldier_status_popup_display()

        self.soldier_status_after_id = self.soldier_status_popup.after(1000, self.refresh_soldier_status_popup)

    def update_soldier_status_popup_display(self) -> None:
        if self.soldier_status_popup is None or not self.soldier_status_popup.winfo_exists():
            return

        if not self.soldier_status_snapshot:
            return

        elapsed = 0
        if self.soldier_status_snapshot_at is not None:
            elapsed = max(0, int(time.monotonic() - self.soldier_status_snapshot_at))

        self.soldier_status_summary_var.set(self.soldier_status_summary)
        for unit_label, state, initial_remaining in self.soldier_status_snapshot:
            remaining = initial_remaining
            if state == "busy" and initial_remaining is not None:
                remaining = max(0, initial_remaining - elapsed)
            var = self.soldier_status_row_vars.get(unit_label)
            if var is not None:
                var.set(unit_status_display_text(state, remaining))

    def close_soldier_status_popup(self) -> None:
        if self.soldier_status_popup is not None and self.soldier_status_after_id is not None:
            try:
                self.soldier_status_popup.after_cancel(self.soldier_status_after_id)
            except tk.TclError:
                pass
        self.soldier_status_after_id = None
        self.soldier_status_loading = False
        self.soldier_status_snapshot = []
        self.soldier_status_snapshot_at = None
        self.soldier_status_summary = ""
        if self.soldier_status_popup is not None and self.soldier_status_popup.winfo_exists():
            self.soldier_status_popup.destroy()
        self.soldier_status_popup = None

    def destroy(self) -> None:
        self.close_soldier_status_popup()
        if self.soldier_loop_after_id is not None:
            try:
                self.top.after_cancel(self.soldier_loop_after_id)
            except tk.TclError:
                pass
            self.soldier_loop_after_id = None
        self.hide_debug_overlay()
        if self.content_top is not None and self.content_top.winfo_exists():
            self.content_top.destroy()
            self.content_top = None
        self.top.destroy()


class MultiPanelApp:
    def __init__(self, target_hwnd: int | None = None) -> None:
        self.target_hwnd = target_hwnd
        self.closed = False
        self.root = tk.Tk()
        self.root.withdraw()
        self.settings = load_app_settings()
        self.settings_lock = threading.Lock()
        self.panels: dict[int, TargetPanel] = {}
        self.workers: dict[int, threading.Thread] = {}
        self.loop_workers: dict[int, dict[str, threading.Thread]] = {}
        self.soldier_unit_workers: dict[int, dict[str, threading.Thread]] = {}
        self.stop_events: dict[int, threading.Event] = {}
        self.timeout_events: dict[int, threading.Event] = {}
        self.watchdogs: dict[int, threading.Thread] = {}
        self.auto_assist_workers: dict[int, threading.Thread] = {}
        self.action_locks: dict[int, threading.Lock] = {}
        self.current_tasks: dict[int, str] = {}
        self.step_started_at: dict[int, float] = {}
        self.step_signatures: dict[int, str] = {}
        self.soldier_busy_until: dict[int, dict[str, float]] = {}

        self.refresh_targets(force=True)
        self.follow_targets()

    def panel_settings(self, window: TargetWindow) -> dict:
        merged = default_panel_settings()
        windows = self.settings.get("windows", {})
        if not isinstance(windows, dict):
            return merged

        saved: dict | None = None
        for key in window_settings_keys(window):
            candidate = windows.get(key)
            if isinstance(candidate, dict):
                saved = candidate
                break
        if not saved:
            return merged

        saved_tasks = saved.get("tasks")
        if isinstance(saved_tasks, dict):
            merged["tasks"].update({task_key: bool(saved_tasks.get(task_key, merged["tasks"][task_key])) for task_key in merged["tasks"]})
        try:
            merged["assist_interval"] = int(saved.get("assist_interval", merged["assist_interval"]))
        except (TypeError, ValueError):
            pass
        merged["assist_interval"] = max(
            AUTO_ASSIST_MIN_INTERVAL_SECONDS,
            min(AUTO_ASSIST_MAX_INTERVAL_SECONDS, int(merged["assist_interval"])),
        )
        merged["debug_ranges"] = bool(saved.get("debug_ranges", merged["debug_ranges"]))
        merged["expanded"] = bool(saved.get("expanded", merged["expanded"]))
        try:
            merged["opacity"] = int(saved.get("opacity", merged["opacity"]))
        except (TypeError, ValueError):
            pass
        merged["opacity"] = max(MIN_PANEL_OPACITY, min(MAX_PANEL_OPACITY, int(merged["opacity"])))
        return merged

    def save_panel_settings(
        self,
        window: TargetWindow,
        tasks: dict[str, bool],
        assist_interval: int,
        debug_ranges: bool,
        expanded: bool,
        opacity: int,
    ) -> None:
        clean_tasks = {task_key: bool(tasks.get(task_key, True)) for task_key, _label in TASK_DEFINITIONS}
        assist_interval = max(
            AUTO_ASSIST_MIN_INTERVAL_SECONDS,
            min(AUTO_ASSIST_MAX_INTERVAL_SECONDS, int(assist_interval)),
        )
        opacity = max(MIN_PANEL_OPACITY, min(MAX_PANEL_OPACITY, int(opacity)))
        with self.settings_lock:
            windows = self.settings.setdefault("windows", {})
            if not isinstance(windows, dict):
                windows = {}
                self.settings["windows"] = windows
            windows[primary_window_settings_key(window)] = {
                "tasks": clean_tasks,
                "assist_interval": assist_interval,
                "debug_ranges": bool(debug_ranges),
                "expanded": bool(expanded),
                "opacity": opacity,
                "title": window.title,
                "adb_serial": window.adb_serial,
            }
            save_app_settings(self.settings)

    def close(self) -> None:
        self.closed = True
        self.stop_all_tasks()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()

    def refresh_targets(self, force: bool = False) -> list[TargetWindow]:
        if force:
            load_mumu_info(force=True)
        windows = enum_mumu_windows()
        if self.target_hwnd is not None:
            windows = [window for window in windows if window.hwnd == self.target_hwnd]
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

        if self.target_hwnd is not None and not windows and not self.panels:
            self.closed = True
            self.root.after(0, self.root.destroy)
        return windows

    def follow_targets(self) -> None:
        try:
            self.refresh_targets(force=False)
        finally:
            if not self.closed:
                self.root.after(REFRESH_MS, self.follow_targets)

    def start_panel_tasks(self, panel: TargetPanel) -> None:
        task_keys = panel.selected_tasks()
        if not task_keys:
            panel.log("未勾选任务。")
            return
        assist_interval = panel.assist_interval_seconds()
        panel.reset_task_states()
        self.start_worker(panel, task_keys, assist_interval)

    def start_worker(self, panel: TargetPanel, task_keys: list[str], assist_interval: int) -> None:
        hwnd = panel.window.hwnd
        stop_event = self.stop_events.get(hwnd)
        if stop_event is None or stop_event.is_set():
            stop_event = threading.Event()
        timeout_event = self.timeout_events.get(hwnd)
        if timeout_event is None:
            timeout_event = threading.Event()
        self.stop_events[hwnd] = stop_event
        self.timeout_events[hwnd] = timeout_event
        self.action_locks.setdefault(hwnd, threading.Lock())
        self.clear_current_task(panel.window)

        existing_watchdog = self.watchdogs.get(hwnd)
        if existing_watchdog is None or not existing_watchdog.is_alive():
            watchdog = threading.Thread(
                target=self.watchdog_main,
                args=(panel.window, stop_event, timeout_event),
                daemon=True,
            )
            self.watchdogs[hwnd] = watchdog
            watchdog.start()

        task_labels = dict(TASK_DEFINITIONS)
        handlers = self.task_handlers()
        started = 0

        if "adventure" in task_keys:
            if self.start_periodic_loop_worker(
                panel.window,
                "adventure",
                task_labels["adventure"],
                handlers["adventure"],
                ADVENTURE_LOOP_INTERVAL_SECONDS,
                stop_event,
                timeout_event,
            ):
                started += 1

        if "auto_assist" in task_keys:
            if self.start_periodic_loop_worker(
                panel.window,
                "auto_assist",
                task_labels["auto_assist"],
                handlers["auto_assist"],
                assist_interval,
                stop_event,
                timeout_event,
            ):
                started += 1

        if "train_soldiers" in task_keys:
            for unit_key, unit_label, row_y in TRAIN_UNITS:
                if self.start_soldier_unit_loop_worker(
                    panel.window,
                    unit_key,
                    unit_label,
                    row_y,
                    stop_event,
                    timeout_event,
                ):
                    started += 1

        panel.log("循环任务已启动。" if started else "勾选的循环任务已经在运行中。")

    def start_periodic_loop_worker(
        self,
        window: TargetWindow,
        task_key: str,
        task_label: str,
        handler,
        interval_seconds: int,
        stop_event: threading.Event,
        timeout_event: threading.Event,
    ) -> bool:
        hwnd = window.hwnd
        workers = self.loop_workers.setdefault(hwnd, {})
        existing = workers.get(task_key)
        if existing and existing.is_alive():
            return False
        worker = threading.Thread(
            target=self.periodic_task_loop,
            args=(window, task_key, task_label, handler, interval_seconds, stop_event, timeout_event),
            daemon=True,
        )
        workers[task_key] = worker
        worker.start()
        return True

    def start_soldier_unit_loop_worker(
        self,
        window: TargetWindow,
        unit_key: str,
        unit_label: str,
        row_y: int,
        stop_event: threading.Event,
        timeout_event: threading.Event,
    ) -> bool:
        hwnd = window.hwnd
        workers = self.soldier_unit_workers.setdefault(hwnd, {})
        existing = workers.get(unit_key)
        if existing and existing.is_alive():
            return False
        worker = threading.Thread(
            target=self.soldier_unit_loop,
            args=(window, unit_key, unit_label, row_y, stop_event, timeout_event),
            daemon=True,
        )
        workers[unit_key] = worker
        worker.start()
        return True

    def stop_all_tasks(self) -> None:
        running = 0
        for hwnd, worker in list(self.workers.items()):
            if worker.is_alive():
                running += 1
                event = self.stop_events.get(hwnd)
                if event is not None:
                    event.set()
        for hwnd, worker in list(self.auto_assist_workers.items()):
            if worker.is_alive():
                running += 1
                event = self.stop_events.get(hwnd)
                if event is not None:
                    event.set()
        for hwnd, workers in list(self.loop_workers.items()):
            for worker in list(workers.values()):
                if worker.is_alive():
                    running += 1
                    event = self.stop_events.get(hwnd)
                    if event is not None:
                        event.set()
        for hwnd, workers in list(self.soldier_unit_workers.items()):
            for worker in list(workers.values()):
                if worker.is_alive():
                    running += 1
                    event = self.stop_events.get(hwnd)
                    if event is not None:
                        event.set()
        for panel in list(self.panels.values()):
            panel.log("已发送停止指令。" if running else "当前没有正在执行的任务。")

    def worker_alive(self, hwnd: int) -> bool:
        worker = self.workers.get(hwnd)
        assist_worker = self.auto_assist_workers.get(hwnd)
        loop_workers = self.loop_workers.get(hwnd, {})
        soldier_workers = self.soldier_unit_workers.get(hwnd, {})
        return bool(
            (worker and worker.is_alive())
            or (assist_worker and assist_worker.is_alive())
            or any(worker.is_alive() for worker in loop_workers.values())
            or any(worker.is_alive() for worker in soldier_workers.values())
        )

    def cleanup_panel_if_idle(self, window: TargetWindow) -> None:
        hwnd = window.hwnd
        if self.worker_alive(hwnd):
            return
        stop_event = self.stop_events.get(hwnd)
        if stop_event is not None:
            stop_event.set()
        self.stop_events.pop(hwnd, None)
        self.timeout_events.pop(hwnd, None)
        self.watchdogs.pop(hwnd, None)
        self.loop_workers.pop(hwnd, None)
        self.soldier_unit_workers.pop(hwnd, None)
        self.current_tasks.pop(hwnd, None)
        self.step_started_at.pop(hwnd, None)
        self.step_signatures.pop(hwnd, None)
        self.show_debug_step(window, "home")
        self.root.after(0, lambda hwnd=hwnd: self.set_panel_busy(hwnd, False))

    def acquire_action_lock(self, window: TargetWindow, stop_event: threading.Event) -> threading.Lock | None:
        lock = self.action_locks.setdefault(window.hwnd, threading.Lock())
        while not stop_event.is_set():
            if lock.acquire(blocking=False):
                return lock
            time.sleep(0.1)
        return None

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
        self.note_task_step(window, step, unit_label=unit_label, row_y=row_y)
        ranges = debug_ranges_for_step(step, unit_label=unit_label, row_y=row_y)

        def _show() -> None:
            panel = self.panels.get(window.hwnd)
            if panel:
                panel.show_debug_ranges(ranges)

        self.root.after(0, _show)

    def should_stop(self, window: TargetWindow) -> bool:
        event = self.stop_events.get(window.hwnd)
        timeout_event = self.timeout_events.get(window.hwnd)
        return bool((event and event.is_set()) or (timeout_event and timeout_event.is_set()))

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

    def note_task_step(
        self,
        window: TargetWindow,
        step: str,
        unit_label: str = "",
        row_y: int | None = None,
        force: bool = False,
    ) -> None:
        hwnd = window.hwnd
        signature = f"{step}:{unit_label}:{row_y}"
        if force or self.step_signatures.get(hwnd) != signature:
            self.step_signatures[hwnd] = signature
            self.step_started_at[hwnd] = time.monotonic()

    def clear_current_task(self, window: TargetWindow) -> None:
        hwnd = window.hwnd
        self.current_tasks.pop(hwnd, None)
        self.note_task_step(window, "idle", force=True)

    def watchdog_main(
        self,
        window: TargetWindow,
        stop_event: threading.Event,
        timeout_event: threading.Event,
    ) -> None:
        hwnd = window.hwnd
        while not stop_event.is_set():
            time.sleep(1.0)
            if timeout_event.is_set():
                continue
            task_key = self.current_tasks.get(hwnd)
            if not task_key:
                continue
            started_at = self.step_started_at.get(hwnd)
            if started_at is None:
                continue
            elapsed = time.monotonic() - started_at
            step = self.step_signatures.get(hwnd, "unknown")
            if step.startswith("wait_busy:"):
                continue
            if elapsed < TASK_STEP_TIMEOUT_SECONDS:
                continue
            timeout_event.set()
            self.thread_log(
                window,
                f"当前步骤超过 {TASK_STEP_TIMEOUT_SECONDS} 秒，强制停止本任务：{task_key} / {step}。",
            )

    def recover_home_after_timeout(self, window: TargetWindow, stop_event: threading.Event) -> None:
        self.thread_log(window, "尝试返回主界面后继续后续任务。")
        self.show_debug_step(window, "home")
        for attempt in range(12):
            if stop_event.is_set():
                return
            try:
                image, _profile = capture_target(window)
                detection = analyze_screen(image, ADB_PROFILE)
                if main_screen_visible(image) and not detection.adventure_page_visible and not detection.reward_overlay_visible:
                    self.thread_log(window, "已恢复到主界面。")
                    return
            except Exception as exc:
                self.thread_log(window, f"恢复主界面时截图失败：{exc}")
            self.thread_log(window, f"未确认主界面，第 {attempt + 1}/12 次点击左上角返回。")
            tap_target(window, "back")
            time.sleep(0.55)
        self.thread_log(window, "已尝试返回主界面，未能最终确认。")

    def task_handlers(self):
        return {
            "adventure": self.task_adventure,
            "train_soldiers": self.task_train_soldiers,
            "auto_assist": self.task_auto_assist,
        }

    def run_one_task(
        self,
        window: TargetWindow,
        task_key: str,
        task_label: str,
        handler,
        stop_event: threading.Event,
        timeout_event: threading.Event,
        index: int,
        total: int,
    ) -> str:
        if stop_event.is_set():
            self.thread_log(window, "任务已停止。")
            return "stopped"

        lock = self.acquire_action_lock(window, stop_event)
        if lock is None:
            self.thread_log(window, "任务已停止。")
            return "stopped"

        try:
            self.current_tasks[window.hwnd] = task_key
            self.note_task_step(window, f"task:{task_key}", force=True)
            self.thread_log(window, f"开始任务 {index}/{total}：{task_label}")

            result: dict[str, bool] = {"ok": False}
            task_done = threading.Event()

            def _run_handler() -> None:
                try:
                    result["ok"] = bool(handler(window))
                except Exception as exc:
                    traceback.print_exc()
                    self.thread_log(window, f"任务执行异常：{exc}")
                    result["ok"] = False
                finally:
                    task_done.set()

            task_thread = threading.Thread(target=_run_handler, daemon=True)
            task_thread.start()
            while not task_done.wait(0.2):
                if stop_event.is_set() or timeout_event.is_set():
                    break
            if not task_done.is_set() and (stop_event.is_set() or timeout_event.is_set()):
                task_done.wait(5.0)
            ok = result["ok"] if task_done.is_set() else False
            self.clear_current_task(window)

            if timeout_event.is_set():
                self.thread_log(window, f"任务超时：{task_label}，本轮停止并恢复主界面。")
                self.recover_home_after_timeout(window, stop_event)
                timeout_event.clear()
                return "timeout"

            if stop_event.is_set():
                self.thread_log(window, "任务已停止。")
                return "stopped"

            if not ok:
                self.thread_log(window, f"任务未完成：{task_label}")
                self.recover_home_after_timeout(window, stop_event)
                return "failed"

            self.root.after(0, lambda key=task_key, hwnd=window.hwnd: self.mark_task_done(hwnd, key))
            return "ok"
        finally:
            lock.release()

    def run_task_sequence(
        self,
        window: TargetWindow,
        task_keys: list[str],
        task_labels: dict[str, str],
        handlers: dict,
        stop_event: threading.Event,
        timeout_event: threading.Event,
    ) -> bool:
        total = len(task_keys)
        for index, task_key in enumerate(task_keys, start=1):
            handler = handlers.get(task_key)
            task_label = task_labels.get(task_key, task_key)
            if handler is None:
                self.thread_log(window, f"任务未实现：{task_label}")
                continue

            result = self.run_one_task(
                window,
                task_key,
                task_label,
                handler,
                stop_event,
                timeout_event,
                index,
                total,
            )
            if result == "stopped":
                return False
            if result == "failed":
                return False
            if index < total:
                self.thread_log(window, f"{task_label} 已结束，等待 {TASK_BUFFER_SECONDS} 秒后继续。")
                if not self.sleep_with_stop(window, TASK_BUFFER_SECONDS):
                    self.thread_log(window, "任务已停止。")
                    return False
        return True

    def worker_main(
        self,
        window: TargetWindow,
        task_keys: list[str],
        stop_event: threading.Event,
        timeout_event: threading.Event,
    ) -> None:
        task_labels = dict(TASK_DEFINITIONS)
        handlers = self.task_handlers()
        try:
            self.run_task_sequence(
                window,
                task_keys,
                task_labels,
                handlers,
                stop_event,
                timeout_event,
            )
        except Exception as exc:
            traceback.print_exc()
            self.thread_log(window, f"执行失败：{exc}")
        finally:
            self.workers.pop(window.hwnd, None)
            self.root.after(0, lambda hwnd=window.hwnd: self.set_panel_busy(hwnd, False))
            self.cleanup_panel_if_idle(window)

    def panel_assist_interval(self, hwnd: int, fallback: int) -> int:
        panel = self.panels.get(hwnd)
        if panel is None:
            return fallback
        return max(
            AUTO_ASSIST_MIN_INTERVAL_SECONDS,
            min(AUTO_ASSIST_MAX_INTERVAL_SECONDS, int(getattr(panel, "assist_interval_value", fallback))),
        )

    def periodic_task_loop(
        self,
        window: TargetWindow,
        task_key: str,
        task_label: str,
        handler,
        interval_seconds: int,
        stop_event: threading.Event,
        timeout_event: threading.Event,
    ) -> None:
        hwnd = window.hwnd
        try:
            while not stop_event.is_set():
                interval = interval_seconds
                if task_key == "auto_assist":
                    interval = self.panel_assist_interval(hwnd, interval_seconds)
                self.set_panel_task_countdown(hwnd, task_key, 0)
                result = self.run_one_task(
                    window,
                    task_key,
                    task_label,
                    handler,
                    stop_event,
                    timeout_event,
                    1,
                    1,
                )
                if result == "stopped":
                    break
                if result == "failed":
                    self.thread_log(window, f"{task_label} 本轮未完成，等待下次检测。")

                self.thread_log(window, f"{task_label} 将在 {format_duration(interval)} 后再次检测。")
                for remaining in range(interval, 0, -1):
                    if stop_event.is_set():
                        break
                    self.set_panel_task_countdown(hwnd, task_key, remaining)
                    if not self.sleep_with_stop(window, 1.0):
                        break
                if stop_event.is_set():
                    break
        except Exception as exc:
            traceback.print_exc()
            self.thread_log(window, f"{task_label} 循环异常：{exc}")
        finally:
            self.set_panel_task_countdown_text(hwnd, task_key, "已停止")
            workers = self.loop_workers.get(hwnd)
            if workers is not None:
                workers.pop(task_key, None)
                if not workers:
                    self.loop_workers.pop(hwnd, None)
            self.cleanup_panel_if_idle(window)

    def soldier_unit_loop(
        self,
        window: TargetWindow,
        unit_key: str,
        unit_label: str,
        row_y: int,
        stop_event: threading.Event,
        timeout_event: threading.Event,
    ) -> None:
        hwnd = window.hwnd
        try:
            while not stop_event.is_set():
                cached_remaining = self.cached_unit_busy_remaining(window, unit_key)
                if cached_remaining is not None:
                    delay = cached_remaining + SOLDIER_LOOP_COMPLETE_DELAY_SECONDS
                    self.thread_log(window, f"{unit_label} 已在训练中，下次训练检测等待 {format_duration(delay)}。")
                else:
                    self.set_panel_soldier_loop_text(hwnd, unit_key, "检测中")
                    result = self.run_one_task(
                        window,
                        "train_soldiers",
                        f"训练士兵-{unit_label}",
                        lambda target_window, key=unit_key, label=unit_label, y=row_y: self.task_train_one_soldier(
                            target_window,
                            key,
                            label,
                            y,
                        ),
                        stop_event,
                        timeout_event,
                        1,
                        1,
                    )
                    if result == "stopped":
                        break
                    cached_remaining = self.cached_unit_busy_remaining(window, unit_key)
                    delay = (
                        cached_remaining + SOLDIER_LOOP_COMPLETE_DELAY_SECONDS
                        if cached_remaining is not None
                        else SOLDIER_LOOP_FALLBACK_SECONDS
                    )
                    if result == "failed":
                        self.thread_log(window, f"{unit_label} 本轮未完成，{format_duration(delay)} 后重试。")

                for remaining in range(delay, 0, -1):
                    if stop_event.is_set():
                        break
                    self.set_panel_soldier_loop_text(hwnd, unit_key, f"下次 {format_duration(remaining)}")
                    if not self.sleep_with_stop(window, 1.0):
                        break
        except Exception as exc:
            traceback.print_exc()
            self.thread_log(window, f"{unit_label} 循环异常：{exc}")
        finally:
            self.set_panel_soldier_loop_text(hwnd, unit_key, "已停止")
            workers = self.soldier_unit_workers.get(hwnd)
            if workers is not None:
                workers.pop(unit_key, None)
                if not workers:
                    self.soldier_unit_workers.pop(hwnd, None)
            self.cleanup_panel_if_idle(window)

    def set_panel_busy(self, hwnd: int, busy: bool) -> None:
        panel = self.panels.get(hwnd)
        if panel:
            panel.set_busy(busy)

    def mark_task_done(self, hwnd: int, task_key: str) -> None:
        panel = self.panels.get(hwnd)
        if panel:
            panel.mark_task_done(task_key)

    def set_panel_auto_assist_countdown(self, hwnd: int, remaining_seconds: int | None) -> None:
        self.set_panel_task_countdown(hwnd, "auto_assist", remaining_seconds)

    def set_panel_task_countdown(self, hwnd: int, task_key: str, remaining_seconds: int | None) -> None:
        panel = self.panels.get(hwnd)
        if panel is None:
            return

        def _apply() -> None:
            panel.set_task_countdown(task_key, remaining_seconds)

        self.root.after(0, _apply)

    def set_panel_task_countdown_text(self, hwnd: int, task_key: str, text: str) -> None:
        panel = self.panels.get(hwnd)
        if panel is None:
            return

        def _apply() -> None:
            panel.set_task_countdown_text(task_key, text)

        self.root.after(0, _apply)

    def set_panel_soldier_loop_text(self, hwnd: int, unit_key: str, text: str) -> None:
        panel = self.panels.get(hwnd)
        if panel is None:
            return

        def _apply() -> None:
            panel.set_soldier_loop_text(unit_key, text)

        self.root.after(0, _apply)

    def capture_detection(self, window: TargetWindow) -> tuple[Image.Image, ScreenProfile, Detection]:
        image, profile = capture_target(window)
        return image, profile, analyze_screen(image, profile)

    def read_soldier_status_lines(
        self,
        window: TargetWindow,
        ensure_queue: bool = False,
    ) -> tuple[list[tuple[str, str]], str]:
        snapshot, summary = self.read_soldier_status_snapshot(window, ensure_queue=ensure_queue)
        return [(unit_label, unit_status_display_text(state, remaining)) for unit_label, state, remaining in snapshot], summary

    def unit_key_for_label(self, unit_label: str) -> str:
        for unit_key, label, _row_y in TRAIN_UNITS:
            if label == unit_label:
                return unit_key
        return unit_label

    def cached_unit_busy_remaining(self, window: TargetWindow, unit_key: str) -> int | None:
        by_unit = self.soldier_busy_until.get(window.hwnd)
        if not by_unit:
            return None
        until = by_unit.get(unit_key)
        if until is None:
            return None
        remaining = int(round(until - time.monotonic()))
        if remaining > 0:
            return remaining
        by_unit.pop(unit_key, None)
        if not by_unit:
            self.soldier_busy_until.pop(window.hwnd, None)
        return None

    def set_unit_busy_cache(self, window: TargetWindow, unit_key: str, remaining: int | None) -> None:
        if remaining is None:
            return
        remaining = max(0, int(remaining))
        if remaining <= 0:
            return
        self.soldier_busy_until.setdefault(window.hwnd, {})[unit_key] = time.monotonic() + remaining

    def clear_unit_busy_cache(self, window: TargetWindow, unit_key: str) -> None:
        by_unit = self.soldier_busy_until.get(window.hwnd)
        if not by_unit:
            return
        by_unit.pop(unit_key, None)
        if not by_unit:
            self.soldier_busy_until.pop(window.hwnd, None)

    def apply_soldier_busy_cache(
        self,
        window: TargetWindow,
        snapshot: list[tuple[str, str, int | None]],
    ) -> list[tuple[str, str, int | None]]:
        adjusted: list[tuple[str, str, int | None]] = []
        for unit_label, state, remaining in snapshot:
            unit_key = self.unit_key_for_label(unit_label)
            cached_remaining = self.cached_unit_busy_remaining(window, unit_key)
            if state == "busy":
                if remaining is None:
                    remaining = cached_remaining
                else:
                    self.set_unit_busy_cache(window, unit_key, remaining)
                adjusted.append((unit_label, state, remaining))
                continue
            if state == "unknown" and cached_remaining is not None:
                adjusted.append((unit_label, "busy", cached_remaining))
                continue
            if state in {"ready", "idle", "blocked"}:
                self.clear_unit_busy_cache(window, unit_key)
            adjusted.append((unit_label, state, remaining))
        return adjusted

    def read_soldier_status_snapshot(
        self,
        window: TargetWindow,
        ensure_queue: bool = False,
    ) -> tuple[list[tuple[str, str, int | None]], str]:
        image, _profile = capture_target(window)
        if ensure_queue and main_screen_visible(image) and not queue_panel_visible(image):
            tap_target(window, "queue_expand")
            time.sleep(0.45)
            image, _profile = capture_target(window)

        if ensure_queue and queue_panel_visible(image) and not queue_panel_at_top_visible(image):
            for _attempt in range(3):
                swipe_point(window, QUEUE_SCROLL_X, QUEUE_SCROLL_TOP_START_Y, QUEUE_SCROLL_X, QUEUE_SCROLL_TOP_END_Y)
                time.sleep(0.25)
                image, _profile = capture_target(window)
                if queue_panel_at_top_visible(image):
                    break

        if not queue_panel_visible(image):
            summary = "队列未展开"
            snapshot = [(unit_label, "unknown", None) for _unit_key, unit_label, _row_y in TRAIN_UNITS]
            snapshot = self.apply_soldier_busy_cache(window, snapshot)
            return snapshot, summary

        top_visible = queue_panel_at_top_visible(image)
        summary = "队列已展开，本地倒计时" if top_visible else "队列未在顶部，本地倒计时"
        snapshot = [
            (unit_label, *unit_row_status_data(image, row_y))
            for _unit_key, unit_label, row_y in TRAIN_UNITS
        ]
        snapshot = self.apply_soldier_busy_cache(window, snapshot)
        return snapshot, summary

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
        if queue_panel_at_top_visible(image):
            return True

        if not queue_panel_visible(image):
            self.thread_log(window, "展开左侧队列面板。")
            tap_target(window, "queue_expand")
            ok, image = self.wait_for_image(
                window,
                queue_panel_visible,
                "队列面板已展开。",
                "未验证到队列面板展开，停止训练任务。",
                attempts=10,
            )
            if not ok:
                return False

        for attempt in range(5):
            if self.should_stop(window):
                self.thread_log(window, "任务已停止。")
                return False
            self.show_debug_step(window, "queue_panel")
            image, _profile = capture_target(window)
            if queue_panel_at_top_visible(image):
                if attempt > 0:
                    self.thread_log(window, "队列面板已回到顶部。")
                return True
            self.thread_log(window, f"队列面板未在顶部，第 {attempt + 1}/5 次向下拖回顶部。")
            swipe_point(window, QUEUE_SCROLL_X, QUEUE_SCROLL_TOP_START_Y, QUEUE_SCROLL_X, QUEUE_SCROLL_TOP_END_Y)
            if not self.sleep_with_stop(window, 0.35):
                self.thread_log(window, "任务已停止。")
                return False

        self.thread_log(window, "队列面板未能确认回到顶部，停止训练任务。")
        return False

    def collapse_queue_panel_if_visible(self, window: TargetWindow) -> bool:
        if self.should_stop(window):
            self.thread_log(window, "任务已停止。")
            return False

        self.show_debug_step(window, "queue_panel")
        image, _profile = capture_target(window)
        if not queue_panel_visible(image):
            return True

        self.thread_log(window, "训练任务收尾：队列面板仍展开，点击收缩箭头。")
        tap_target(window, "queue_collapse")
        ok, _image = self.wait_for_image(
            window,
            lambda img: not queue_panel_visible(img),
            "队列面板已收起。",
            "点击收缩箭头后仍检测到队列面板，请手动确认。",
            attempts=8,
            interval=0.3,
        )
        return ok

    def refresh_single_soldier_status_cache(
        self,
        window: TargetWindow,
        unit_key: str,
        unit_label: str,
        row_y: int,
    ) -> int | None:
        if self.should_stop(window):
            return None
        if not self.ensure_queue_panel(window):
            return None
        self.show_debug_step(window, "unit_row", unit_label=unit_label, row_y=row_y)
        image, _profile = capture_target(window)
        state, remaining = unit_row_status_data(image, row_y)
        if state == "busy" and remaining is not None:
            self.set_unit_busy_cache(window, unit_key, remaining)
            self.thread_log(window, f"{unit_label} 已读取训练倒计时：{format_duration(remaining)}。")
            return remaining
        if state in {"ready", "idle", "blocked"}:
            self.clear_unit_busy_cache(window, unit_key)
        self.thread_log(window, f"{unit_label} 训练后状态：{unit_status_display_text(state, remaining)}。")
        return None

    def task_train_one_soldier(
        self,
        window: TargetWindow,
        unit_key: str,
        unit_label: str,
        row_y: int,
    ) -> bool:
        cached_remaining = self.cached_unit_busy_remaining(window, unit_key)
        if cached_remaining is not None:
            self.thread_log(window, f"{unit_label} 缓存显示正在训练，剩余 {format_duration(cached_remaining)}，本轮跳过。")
            return True
        if not self.ensure_home_for_training(window):
            return False
        ok = self.train_one_unit(window, unit_key, unit_label, row_y)
        if ok:
            self.refresh_single_soldier_status_cache(window, unit_key, unit_label, row_y)
            self.collapse_queue_panel_if_visible(window)
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
            if not self.train_one_unit(window, unit_key, unit_label, row_y):
                return False
            if not self.sleep_with_stop(window, 0.45):
                self.thread_log(window, "任务已停止。")
                return False
        self.collapse_queue_panel_if_visible(window)
        self.thread_log(window, "士兵训练任务完成。")
        return True

    def wait_for_busy_unit(self, window: TargetWindow, unit_label: str, row_y: int, seconds: int) -> bool:
        wait_seconds = max(0, int(seconds)) + 5
        self.note_task_step(window, "wait_busy", unit_label=unit_label, row_y=row_y, force=True)
        self.thread_log(
            window,
            f"{unit_label} 正在训练，剩余 {format_duration(seconds)}，结束后再等 5 秒重试。",
        )

        end_time = time.monotonic() + wait_seconds
        next_log_at = time.monotonic() + 60
        while time.monotonic() < end_time:
            if self.should_stop(window):
                self.thread_log(window, "任务已停止。")
                return False

            remaining = max(0, round(end_time - time.monotonic()))
            if remaining > 0 and time.monotonic() >= next_log_at:
                self.thread_log(window, f"{unit_label} 等待训练完成，预计还需 {format_duration(remaining)}。")
                next_log_at += 60
            time.sleep(min(1.0, max(0.05, end_time - time.monotonic())))

        if self.should_stop(window):
            self.thread_log(window, "任务已停止。")
            return False
        self.thread_log(window, f"{unit_label} 倒计时已结束，重新检测队列状态。")
        return True

    def read_busy_unit_remaining(self, window: TargetWindow, unit_label: str, row_y: int) -> int | None:
        for attempt in range(1, 4):
            self.show_debug_step(window, "unit_row", unit_label=unit_label, row_y=row_y)
            image, _profile = capture_target(window)
            if unit_row_state(image, row_y) != "busy":
                return None

            remaining = unit_row_remaining_seconds(image, row_y)
            if remaining is not None:
                return remaining

            if attempt < 3:
                self.thread_log(window, f"{unit_label} 正在训练，但倒计时未读准，第 {attempt + 1}/3 次重试。")
                if not self.sleep_with_stop(window, 0.45):
                    self.thread_log(window, "任务已停止。")
                    return None

        return None

    def train_one_unit(self, window: TargetWindow, unit_key: str, unit_label: str, row_y: int) -> bool:
        if self.should_stop(window):
            self.thread_log(window, "任务已停止。")
            return False

        cached_remaining = self.cached_unit_busy_remaining(window, unit_key)
        if cached_remaining is not None:
            self.thread_log(window, f"{unit_label} 缓存显示正在训练，剩余 {format_duration(cached_remaining)}，跳过。")
            return True

        unreadable_busy_count = 0
        while True:
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
                remaining = unit_row_remaining_seconds(image, row_y)
                if remaining is None:
                    remaining = self.read_busy_unit_remaining(window, unit_label, row_y)
                if remaining is None:
                    unreadable_busy_count += 1
                    if unreadable_busy_count >= 2:
                        self.thread_log(window, f"{unit_label} 正在训练，但多次未能读取剩余时间，安全跳过。")
                        return True
                    self.thread_log(window, f"{unit_label} 倒计时未读准，重新检测该兵种状态。")
                    if not self.sleep_with_stop(window, 0.45):
                        self.thread_log(window, "任务已停止。")
                        return False
                    continue
                self.set_unit_busy_cache(window, unit_key, remaining)
                self.thread_log(window, f"{unit_label} 正在训练，剩余 {format_duration(remaining)}，已记录并跳过。")
                return True

            unreadable_busy_count = 0
            if state == "blocked":
                self.thread_log(window, f"{unit_label} 建筑升级中，跳过。")
                return True
            if state not in {"ready", "idle"}:
                self.thread_log(window, f"{unit_label} 状态无法确认，跳过。")
                return True
            break

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

        self.show_debug_step(window, "soldier_page")
        image, _profile = capture_target(window)
        if soldier_training_started_visible(image) and not soldier_quantity_bar_visible(image):
            self.thread_log(window, f"{unit_label} 训练页显示已在训练，点击返回后继续下一个兵种。")
            tap_target(window, "back")
            ok, _image = self.wait_for_image(
                window,
                lambda img: not soldier_page_visible(img),
                f"{unit_label} 已退出训练页。",
                f"{unit_label} 返回后仍在训练页，请手动确认。",
                attempts=10,
            )
            return ok

        self.show_debug_step(window, "train_levels")
        level_choices = list(reversed(available_train_level_xs(image)))
        selected_level_x: int | None = None
        if not level_choices and soldier_quantity_bar_visible(image):
            self.thread_log(window, "未识别到更高白框等级，沿用当前已出现数量条的等级。")
            selected_level_x = -1

        for level_x in level_choices:
            if self.should_stop(window):
                self.thread_log(window, "任务已停止。")
                return False

            self.thread_log(window, f"尝试选择可训练等级，x={level_x}。")
            tap_point(window, level_x, 675)
            if not self.sleep_with_stop(window, 0.35):
                self.thread_log(window, "任务已停止。")
                return False

            image, _profile = capture_target(window)
            if soldier_quantity_bar_visible(image):
                selected_level_x = level_x
                self.thread_log(window, f"已验证等级 x={level_x} 出现绿色数量条。")
                break

            self.thread_log(window, f"等级 x={level_x} 未出现绿色数量条，视为不可训练，尝试低一级。")

        if selected_level_x is None:
            self.thread_log(window, "未找到出现绿色数量条的可训练等级，停止训练任务。")
            return False

        training_started = False
        for train_attempt in range(1, 4):
            if self.should_stop(window):
                self.thread_log(window, "任务已停止。")
                return False

            self.show_debug_step(window, "train_levels")
            image, _profile = capture_target(window)
            guided_train_point = find_guided_soldier_train_button(image)
            if guided_train_point is not None:
                self.thread_log(
                    window,
                    f"识别到训练按钮手势，点击坐标=({guided_train_point[0]}, {guided_train_point[1]})。",
                )
                tap_point(window, guided_train_point[0], guided_train_point[1])
            else:
                self.thread_log(window, "点击训练按钮。")
                tap_target(window, "soldier_train")

            for _ in range(8):
                if not self.sleep_with_stop(window, 0.35):
                    self.thread_log(window, "任务已停止。")
                    return False
                image, _profile = capture_target(window)
                if soldier_training_started_visible(image):
                    self.thread_log(window, f"{unit_label} 数量条已消失，已开始训练。")
                    training_started = True
                    break

            if training_started:
                break
            if train_attempt < 3:
                self.thread_log(window, f"{unit_label} 数量条仍存在，第 {train_attempt + 1}/3 次重试点击训练按钮。")

        if not training_started:
            self.thread_log(window, f"{unit_label} 点击训练后数量条仍未消失，停止训练任务。")
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

    def task_auto_assist(self, window: TargetWindow) -> bool:
        if not is_alive_window(window.hwnd):
            self.thread_log(window, "目标窗口已关闭，跳过。")
            return False
        if not self.ensure_home_screen(window):
            return False
        if self.should_stop(window):
            self.thread_log(window, "任务已停止。")
            return False

        self.show_debug_step(window, "auto_assist")
        image, profile = capture_target(window)
        if not alliance_tab_visible(image, profile):
            self.thread_log(window, "未识别到底部联盟图形，跳过自动协助。")
            return True
        if not auto_assist_handshake_visible(image, profile):
            self.thread_log(window, "未出现联盟协助握手，跳过本次检测。")
            return True

        for attempt in range(1, 3):
            if self.should_stop(window):
                self.thread_log(window, "任务已停止。")
                return False
            self.thread_log(window, f"识别到联盟协助握手，点击处理（第 {attempt}/2 次）。")
            tap_target(window, "auto_assist")
            ok, image = self.wait_for_image(
                window,
                lambda img: not auto_assist_handshake_visible(img, ADB_PROFILE),
                "联盟协助握手已消失，本次协助完成。",
                "点击后仍检测到联盟协助握手。",
                attempts=8,
                interval=0.35,
            )
            if ok:
                if not self.ensure_home_screen(window):
                    return False
                self.show_debug_step(window, "auto_assist")
                image, profile = capture_target(window)
                if not auto_assist_handshake_visible(image, profile):
                    return True
                self.thread_log(window, "返回主界面后仍检测到协助握手，准备重试。")

        self.thread_log(window, "自动协助点击后未通过消失验证。")
        return False

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


def child_python_executable() -> str:
    current = Path(sys.executable)
    pythonw = current.with_name("pythonw.exe")
    return str(pythonw) if pythonw.exists() else sys.executable


def parse_window_hwnd_arg(argv: list[str]) -> int | None:
    if "--window-hwnd" not in argv:
        return None
    index = argv.index("--window-hwnd")
    if index + 1 >= len(argv):
        return None
    try:
        return int(argv[index + 1], 0)
    except ValueError:
        return None


def launch_one_process_per_window() -> None:
    load_mumu_info(force=True)
    windows = enum_mumu_windows()
    script_path = Path(__file__).resolve()
    python_exe = child_python_executable()
    for window in windows:
        subprocess.Popen(
            [python_exe, str(script_path), "--window-hwnd", str(window.hwnd)],
            cwd=str(script_path.parent),
            creationflags=CREATE_NO_WINDOW,
        )


def main() -> None:
    enable_dpi_awareness()
    os.chdir(Path(__file__).resolve().parent)
    target_hwnd = parse_window_hwnd_arg(sys.argv)
    if target_hwnd is None:
        launch_one_process_per_window()
        return
    MultiPanelApp(target_hwnd=target_hwnd).run()


if __name__ == "__main__":
    main()

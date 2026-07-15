"""
多种键鼠注入后端。

游戏（Unity + 新 Input System）经常忽略普通 VK SendInput，
扫描码 / keybd_event / pydirectinput 成功率更高。

按键 hold 尽量短：调度线程在 hold 期间会阻塞，密集点击时会造成系统性晚发。
"""

from __future__ import annotations

import ctypes
import threading
import time
from abc import ABC, abstractmethod
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_EXTENDEDKEY = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

VK_SPACE = 0x20
VK_RETURN = 0x0D
# 扫描码 Set 1
SCAN_SPACE = 0x39
SCAN_ENTER = 0x1C  # 主键盘 Enter

# 默认 hold：够游戏认键，又尽量不挡下一发
DEFAULT_KEY_HOLD = 0.006
DEFAULT_ENTER_HOLD = 0.012
DEFAULT_MOUSE_HOLD = 0.004


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    )


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class INPUTUNION(ctypes.Union):
    _fields_ = (("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT))


class INPUT(ctypes.Structure):
    _fields_ = (("type", wintypes.DWORD), ("union", INPUTUNION))


def _send_input(inputs: list[INPUT]) -> None:
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    sent = user32.SendInput(n, ctypes.byref(arr), ctypes.sizeof(INPUT))
    if sent != n:
        raise OSError(f"SendInput 只发送了 {sent}/{n}")


def _extra() -> ctypes.POINTER(ctypes.c_ulong):
    return ctypes.pointer(ctypes.c_ulong(0))


def _scan_key(
    scan: int,
    hold_s: float = DEFAULT_KEY_HOLD,
    *,
    async_up: bool = False,
) -> float:
    """按下扫描码键，返回 keydown 时刻。async_up=True 时不阻塞调度线程。"""
    down = INPUT(
        type=INPUT_KEYBOARD,
        union=INPUTUNION(ki=KEYBDINPUT(0, scan, KEYEVENTF_SCANCODE, 0, _extra())),
    )
    up = INPUT(
        type=INPUT_KEYBOARD,
        union=INPUTUNION(
            ki=KEYBDINPUT(0, scan, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, _extra())
        ),
    )
    _send_input([down])
    t_down = time.perf_counter()
    if hold_s <= 0:
        _send_input([up])
        return t_down
    if async_up:
        def _up() -> None:
            time.sleep(hold_s)
            try:
                _send_input([up])
            except Exception:
                pass

        threading.Thread(target=_up, daemon=True, name="KeyUp").start()
        return t_down
    time.sleep(hold_s)
    _send_input([up])
    return t_down


def _vk_key(
    vk: int,
    hold_s: float = DEFAULT_KEY_HOLD,
    *,
    async_up: bool = False,
) -> float:
    down = INPUT(
        type=INPUT_KEYBOARD,
        union=INPUTUNION(ki=KEYBDINPUT(vk, 0, 0, 0, _extra())),
    )
    up = INPUT(
        type=INPUT_KEYBOARD,
        union=INPUTUNION(ki=KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, _extra())),
    )
    _send_input([down])
    t_down = time.perf_counter()
    if hold_s <= 0:
        _send_input([up])
        return t_down
    if async_up:
        def _up() -> None:
            time.sleep(hold_s)
            try:
                _send_input([up])
            except Exception:
                pass

        threading.Thread(target=_up, daemon=True, name="KeyUp").start()
        return t_down
    time.sleep(hold_s)
    _send_input([up])
    return t_down


def _mouse_left(hold_s: float = DEFAULT_MOUSE_HOLD) -> float:
    down = INPUT(
        type=INPUT_MOUSE,
        union=INPUTUNION(mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, _extra())),
    )
    up = INPUT(
        type=INPUT_MOUSE,
        union=INPUTUNION(mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, _extra())),
    )
    _send_input([down])
    t_down = time.perf_counter()
    if hold_s > 0:
        time.sleep(hold_s)
    _send_input([up])
    return t_down


class InputBackend(ABC):
    name: str = "base"
    label: str = "base"

    @abstractmethod
    def tap_space(self) -> float:
        """返回 keydown / 动作开始时刻。"""
        ...

    @abstractmethod
    def tap_mouse_left(self) -> float: ...

    @abstractmethod
    def tap_enter(self) -> float:
        """返回 Enter keydown 时刻（应用作关卡 t=0）。"""
        ...

    def tap(self, action: str) -> float:
        if action == "space":
            return self.tap_space()
        if action == "mouse":
            return self.tap_mouse_left()
        if action == "both":
            t = self.tap_space()
            # both 第二下紧跟，不额外长 sleep
            self.tap_mouse_left()
            return t
        if action == "enter":
            return self.tap_enter()
        raise ValueError(action)


class SendInputVkBackend(InputBackend):
    name = "sendinput_vk"
    label = "SendInput VK（旧）"

    def tap_space(self) -> float:
        # 普通点击同步抬起；hold 仅 6ms，绝大多数间隔 >> 此值
        return _vk_key(VK_SPACE, DEFAULT_KEY_HOLD)

    def tap_enter(self) -> float:
        # Enter 异步抬起：立刻返回 keydown，调度线程可马上跟表（含 t≈0 首点）
        return _vk_key(VK_RETURN, DEFAULT_ENTER_HOLD, async_up=True)

    def tap_mouse_left(self) -> float:
        return _mouse_left()


class SendInputScanBackend(InputBackend):
    name = "sendinput_scan"
    label = "SendInput 扫描码（推荐）"

    def tap_space(self) -> float:
        return _scan_key(SCAN_SPACE, DEFAULT_KEY_HOLD)

    def tap_enter(self) -> float:
        return _scan_key(SCAN_ENTER, DEFAULT_ENTER_HOLD, async_up=True)

    def tap_mouse_left(self) -> float:
        return _mouse_left()


class KeybdEventBackend(InputBackend):
    name = "keybd_event"
    label = "keybd_event 扫描码"

    def tap_space(self) -> float:
        user32.keybd_event(VK_SPACE, SCAN_SPACE, 0, 0)
        t_down = time.perf_counter()
        time.sleep(DEFAULT_KEY_HOLD)
        user32.keybd_event(VK_SPACE, SCAN_SPACE, KEYEVENTF_KEYUP, 0)
        return t_down

    def tap_enter(self) -> float:
        user32.keybd_event(VK_RETURN, SCAN_ENTER, 0, 0)
        t_down = time.perf_counter()

        def _up() -> None:
            time.sleep(DEFAULT_ENTER_HOLD)
            try:
                user32.keybd_event(VK_RETURN, SCAN_ENTER, KEYEVENTF_KEYUP, 0)
            except Exception:
                pass

        threading.Thread(target=_up, daemon=True, name="KeyUp").start()
        return t_down

    def tap_mouse_left(self) -> float:
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        t_down = time.perf_counter()
        time.sleep(DEFAULT_MOUSE_HOLD)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        return t_down


class PyDirectInputBackend(InputBackend):
    name = "pydirectinput"
    label = "PyDirectInput"

    def __init__(self) -> None:
        import pydirectinput

        pydirectinput.PAUSE = 0
        pydirectinput.FAILSAFE = False
        self._pdi = pydirectinput

    def tap_space(self) -> float:
        self._pdi.keyDown("space")
        t_down = time.perf_counter()
        time.sleep(DEFAULT_KEY_HOLD)
        self._pdi.keyUp("space")
        return t_down

    def tap_enter(self) -> float:
        self._pdi.keyDown("enter")
        t_down = time.perf_counter()
        pdi = self._pdi

        def _up() -> None:
            time.sleep(DEFAULT_ENTER_HOLD)
            try:
                pdi.keyUp("enter")
            except Exception:
                pass

        threading.Thread(target=_up, daemon=True, name="KeyUp").start()
        return t_down

    def tap_mouse_left(self) -> float:
        self._pdi.mouseDown()
        t_down = time.perf_counter()
        time.sleep(DEFAULT_MOUSE_HOLD)
        self._pdi.mouseUp()
        return t_down


class Win32ApiBackend(InputBackend):
    name = "win32api"
    label = "win32api.keybd_event"

    def __init__(self) -> None:
        import win32api
        import win32con

        self._api = win32api
        self._con = win32con

    def tap_space(self) -> float:
        self._api.keybd_event(VK_SPACE, SCAN_SPACE, 0, 0)
        t_down = time.perf_counter()
        time.sleep(DEFAULT_KEY_HOLD)
        self._api.keybd_event(VK_SPACE, SCAN_SPACE, self._con.KEYEVENTF_KEYUP, 0)
        return t_down

    def tap_enter(self) -> float:
        self._api.keybd_event(VK_RETURN, SCAN_ENTER, 0, 0)
        t_down = time.perf_counter()
        api, con = self._api, self._con

        def _up() -> None:
            time.sleep(DEFAULT_ENTER_HOLD)
            try:
                api.keybd_event(VK_RETURN, SCAN_ENTER, con.KEYEVENTF_KEYUP, 0)
            except Exception:
                pass

        threading.Thread(target=_up, daemon=True, name="KeyUp").start()
        return t_down

    def tap_mouse_left(self) -> float:
        self._api.mouse_event(self._con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        t_down = time.perf_counter()
        time.sleep(DEFAULT_MOUSE_HOLD)
        self._api.mouse_event(self._con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        return t_down


def available_backends() -> list[InputBackend]:
    items: list[InputBackend] = [
        SendInputScanBackend(),
        KeybdEventBackend(),
        SendInputVkBackend(),
    ]
    try:
        items.insert(1, PyDirectInputBackend())
    except Exception:
        pass
    try:
        items.append(Win32ApiBackend())
    except Exception:
        pass
    return items


def get_backend(name: str) -> InputBackend:
    for b in available_backends():
        if b.name == name:
            return b
    return SendInputScanBackend()


BACKEND_CHOICES = [
    ("sendinput_scan", "SendInput 扫描码（推荐）"),
    ("pydirectinput", "PyDirectInput"),
    ("keybd_event", "keybd_event 扫描码"),
    ("win32api", "win32api"),
    ("sendinput_vk", "SendInput VK（旧）"),
]

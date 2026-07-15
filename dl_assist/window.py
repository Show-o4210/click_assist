"""查找并前置 Dancing Line 游戏窗口。"""

from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

EnumWindows = user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
GetWindowTextW = user32.GetWindowTextW
GetWindowTextLengthW = user32.GetWindowTextLengthW
IsWindowVisible = user32.IsWindowVisible
SetForegroundWindow = user32.SetForegroundWindow
ShowWindow = user32.ShowWindow
GetForegroundWindow = user32.GetForegroundWindow
AttachThreadInput = user32.AttachThreadInput
GetWindowThreadProcessId = user32.GetWindowThreadProcessId

GetCurrentThreadId = kernel32.GetCurrentThreadId
OpenProcess = kernel32.OpenProcess
CloseHandle = kernel32.CloseHandle
QueryFullProcessImageNameW = getattr(kernel32, "QueryFullProcessImageNameW", None)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SW_RESTORE = 9

# 进程文件名（小写）
EXE_NAMES = {"dancing line.exe", "dancingline.exe"}


def _window_title(hwnd: int) -> str:
    n = GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _process_exe_name(pid: int) -> str:
    if not QueryFullProcessImageNameW:
        return ""
    h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(512)
        size = wintypes.DWORD(512)
        if QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
    finally:
        CloseHandle(h)
    return ""


def find_game_hwnds() -> list[tuple[int, str]]:
    """返回 [(hwnd, title), ...]，优先匹配 Dancing Line.exe 进程。"""
    found: list[tuple[int, str, int]] = []  # hwnd, title, score

    def callback(hwnd, _lparam):
        if not IsWindowVisible(hwnd):
            return True
        title = _window_title(hwnd)
        if not title:
            return True

        pid = wintypes.DWORD(0)
        GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        exe = _process_exe_name(int(pid.value))
        score = 0
        if exe in EXE_NAMES:
            score = 100
        else:
            # 回退：标题恰好是游戏名（避免匹配带路径的编辑器标题）
            t = title.strip().lower()
            if t == "dancing line" or t.startswith("dancing line "):
                score = 50
            else:
                return True

        found.append((int(hwnd), title, score))
        return True

    EnumWindows(EnumWindowsProc(callback), 0)
    found.sort(key=lambda x: -x[2])
    return [(h, t) for h, t, _ in found]


def is_game_foreground() -> bool:
    """游戏是否已在前台（用于热路径跳过重复 focus）。"""
    fg = int(GetForegroundWindow() or 0)
    if not fg:
        return False
    for hwnd, _ in find_game_hwnds():
        if hwnd == fg:
            return True
    return False


def focus_game(retries: int = 2) -> tuple[bool, str]:
    windows = find_game_hwnds()
    if not windows:
        return False, "未找到游戏窗口（Dancing Line.exe）"

    hwnd, title = windows[0]
    # 已在前台：立刻返回，不 sleep
    if int(GetForegroundWindow() or 0) == hwnd:
        return True, f"已在前台: {title}"

    for _ in range(retries):
        try:
            ShowWindow(hwnd, SW_RESTORE)
            fg = GetForegroundWindow()
            fg_tid = GetWindowThreadProcessId(fg, None)
            cur_tid = GetCurrentThreadId()
            target_tid = GetWindowThreadProcessId(hwnd, None)
            if fg_tid and fg_tid != cur_tid:
                AttachThreadInput(cur_tid, fg_tid, True)
            if target_tid and target_tid != cur_tid:
                AttachThreadInput(cur_tid, target_tid, True)
            SetForegroundWindow(hwnd)
            if fg_tid and fg_tid != cur_tid:
                AttachThreadInput(cur_tid, fg_tid, False)
            if target_tid and target_tid != cur_tid:
                AttachThreadInput(cur_tid, target_tid, False)
        except Exception as e:
            return False, f"前置失败: {e}"
        time.sleep(0.01)
        if int(GetForegroundWindow()) == hwnd:
            return True, f"已前置: {title}"
    return True, f"已请求前置: {title}"

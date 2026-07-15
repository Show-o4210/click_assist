from __future__ import annotations

import time

from . import window
from .input_backends import InputBackend, get_backend


class Clicker:
    """统一点击入口：可选前置窗口 + 可切换注入后端。"""

    def __init__(
        self,
        action: str = "space",
        backend_name: str = "sendinput_scan",
        focus_before_click: bool = True,
    ) -> None:
        self.action = action  # space | mouse | both
        # 仅控制「单次试发 / 开局准备」是否前置；运行中调度走 focus=False
        self.focus_before_click = focus_before_click
        self._backend: InputBackend = get_backend(backend_name)
        self.last_focus_msg = ""

    @property
    def backend_name(self) -> str:
        return self._backend.name

    def set_backend(self, name: str) -> None:
        self._backend = get_backend(name)

    def set_action(self, action: str) -> None:
        self.action = action

    def prepare_focus(self) -> str:
        """
        开局前前置一次游戏窗口。
        调度线程内的每次点击不应再 focus（否则每下多 10~30ms 误差）。
        """
        if not self.focus_before_click:
            self.last_focus_msg = "focus disabled"
            return self.last_focus_msg
        ok, msg = window.focus_game(retries=2)
        self.last_focus_msg = msg
        if ok and not msg.startswith("已在前台"):
            # 刚抢到前台时给游戏极短稳定时间；已在前台则不 sleep
            time.sleep(0.012)
        return msg

    def _maybe_focus(self) -> None:
        if not self.focus_before_click:
            return
        # 已在前台则零开销
        if window.is_game_foreground():
            self.last_focus_msg = "已在前台"
            return
        ok, msg = window.focus_game(retries=1)
        self.last_focus_msg = msg
        if ok and not msg.startswith("已在前台"):
            time.sleep(0.008)

    def click(self, *, focus: bool | None = None) -> float:
        """
        注入一次点击，返回 keydown / 动作开始时刻（perf_counter）。
        focus=None → 使用 focus_before_click（试发默认开）
        focus=False → 热路径，绝不前置窗口
        """
        do_focus = self.focus_before_click if focus is None else focus
        if do_focus:
            self._maybe_focus()
        return self._backend.tap(self.action)

    def press_enter(self, *, focus: bool | None = None) -> float:
        """
        开局 Enter。返回 keydown 时刻的 perf_counter（作为时间轴 t=0）。
        """
        do_focus = self.focus_before_click if focus is None else focus
        if do_focus:
            self._maybe_focus()
        return self._backend.tap_enter()

    def test_once(self) -> str:
        t0 = time.perf_counter()
        try:
            self.click(focus=True)
            dt = (time.perf_counter() - t0) * 1000
            return (
                f"OK backend={self._backend.name} action={self.action} "
                f"{dt:.1f}ms | {self.last_focus_msg}"
            )
        except Exception as e:
            return f"FAIL backend={self._backend.name}: {e}"

    def test_enter(self) -> str:
        t0 = time.perf_counter()
        try:
            kd = self.press_enter(focus=True)
            dt = (time.perf_counter() - t0) * 1000
            return (
                f"OK ENTER backend={self._backend.name} {dt:.1f}ms "
                f"keydown@{kd:.6f} | {self.last_focus_msg}"
            )
        except Exception as e:
            return f"FAIL ENTER: {e}"

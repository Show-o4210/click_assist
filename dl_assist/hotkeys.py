"""全局热键：F8 播放/暂停，F6 重置。"""

from __future__ import annotations

from typing import Callable


class HotkeyHub:
    def __init__(self) -> None:
        self._impl = None
        self._mode = ""

    @property
    def mode(self) -> str:
        return self._mode

    def start(
        self,
        *,
        on_toggle: Callable[[], None],
        on_reset: Callable[[], None],
    ) -> str:
        self.stop()
        try:
            self._start_pynput(on_toggle, on_reset)
            self._mode = "pynput"
            return self._mode
        except Exception as e1:
            try:
                self._start_keyboard(on_toggle, on_reset)
                self._mode = "keyboard"
                return self._mode
            except Exception as e2:
                raise RuntimeError(f"热键注册失败: pynput={e1}; keyboard={e2}") from e2

    def _start_pynput(self, on_toggle, on_reset) -> None:
        from pynput import keyboard

        h = keyboard.GlobalHotKeys(
            {
                "<f8>": on_toggle,
                "<f6>": on_reset,
            }
        )
        h.start()
        self._impl = ("pynput", h)

    def _start_keyboard(self, on_toggle, on_reset) -> None:
        import keyboard as kb

        kb.add_hotkey("f8", on_toggle, suppress=False)
        kb.add_hotkey("f6", on_reset, suppress=False)
        self._impl = ("keyboard", kb)

    def stop(self) -> None:
        if not self._impl:
            return
        kind, obj = self._impl
        try:
            if kind == "pynput":
                obj.stop()
            else:
                try:
                    obj.unhook_all_hotkeys()
                except Exception:
                    obj.unhook_all()
        except Exception:
            pass
        self._impl = None
        self._mode = ""

from __future__ import annotations

import ctypes
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from .clicker import Clicker
from .data import build_schedule
from .segments import LevelSegments, load_level_segments
from .tune import estimate_level_duration_s

# 同刻多击之间的最小间隔（游戏需要分开两次输入）
SAME_T_GAP = 0.012

# 忙等阈值：最后这段纯 spin，误差通常 <1ms
SPIN_REMAIN_S = 0.0012

# Enter keydown → 游戏内部 t=0 的经验偏移（ms）
DEFAULT_ENTER_T0_DELAY_MS = 16.0


def timer_period(enable: bool) -> None:
    winmm = ctypes.WinDLL("winmm")
    if enable:
        winmm.timeBeginPeriod(1)
    else:
        winmm.timeEndPeriod(1)


def _boost_thread_priority() -> None:
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.GetCurrentThread()
        kernel32.SetThreadPriority(handle, 2)  # THREAD_PRIORITY_HIGHEST
    except Exception:
        pass


@dataclass
class FireLog:
    index: int
    official_t: float
    rel_t: float
    planned_wall: float
    actual_wall: float
    err_ms: float
    note: str = ""


@dataclass
class Shared:
    level: str = ""
    schedule: list[float] = field(default_factory=list)
    latency_ms: float = 0.0
    enter_t0_delay_ms: float = DEFAULT_ENTER_T0_DELAY_MS
    dry_run: bool = False
    running: bool = False
    paused: bool = False
    # 官方时间轴 t=0 对应的 wall 时刻
    wall0: float | None = None
    # 暂停时冻结的游戏时间（秒）；暂停期间 UI 用此值，不随 wall 走
    pause_elapsed: float | None = None
    enter_keydown: float | None = None
    next_index: int = 0
    status: str = "待命"
    logs: list[FireLog] = field(default_factory=list)
    last_flash_until: float = 0.0
    table_warnings: list[str] = field(default_factory=list)
    # 段落延迟（不改表）；duration 用于 t→% 映射
    segments: LevelSegments = field(default_factory=LevelSegments)
    duration_s: float = 0.0


class Engine:
    def __init__(
        self,
        clicker: Clicker,
        on_change: Callable[[], None] | None = None,
        enter_t0_delay_ms: float = DEFAULT_ENTER_T0_DELAY_MS,
    ) -> None:
        self.clicker = clicker
        self.on_change = on_change or (lambda: None)
        self.s = Shared(enter_t0_delay_ms=enter_t0_delay_ms)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._ignore_hotkey_until = 0.0
        # pause 请求：线程退出时不要当成「序列结束」
        self._pause_requested = False

    def _emit(self) -> None:
        try:
            self.on_change()
        except Exception:
            pass

    def load(
        self,
        level: str,
        raw_times: list[float],
        *,
        skip_zeros: bool = True,
        latency: float = 0.0,
        dry: bool = False,
    ) -> None:
        self.reset()
        sched, warns = build_schedule(raw_times, skip_zeros, sanitize=True)
        segs = load_level_segments(level)
        if segs.duration_s <= 0:
            segs.duration_s = estimate_level_duration_s(level, sched).seconds
        n_bands = len(segs.bands)
        with self._lock:
            self.s.level = level
            self.s.schedule = sched
            self.s.latency_ms = latency
            self.s.dry_run = dry
            self.s.table_warnings = list(warns)
            self.s.segments = segs
            self.s.duration_s = float(segs.duration_s)
            warn_bit = f" | ⚠{len(warns)}" if warns else ""
            seg_bit = f" | 段延迟×{n_bands}" if n_bands else ""
            if not sched:
                self.s.status = "无点击数据"
            else:
                self.s.status = (
                    f"已载入 {level} | {len(sched)} 点 | "
                    f"{sched[0]:.3f}s → {sched[-1]:.3f}s | F8 开始"
                    f"{seg_bit}{warn_bit}"
                )
        self._emit()

    def set_latency(self, ms: float) -> None:
        with self._lock:
            self.s.latency_ms = float(ms)
            self.s.status = f"延迟 = {ms:+.1f} ms"
        self._emit()

    def reload_segments(self) -> None:
        """失败微调保存后热加载段落延迟，无需整关重载。"""
        with self._lock:
            level = self.s.level
            sched = list(self.s.schedule)
        if not level:
            return
        segs = load_level_segments(level)
        if segs.duration_s <= 0:
            segs.duration_s = estimate_level_duration_s(level, sched).seconds
        with self._lock:
            self.s.segments = segs
            self.s.duration_s = float(segs.duration_s)
            n = len(segs.bands)
            self.s.status = f"段落延迟已更新 ×{n}"
        self._emit()

    def _effective_latency_s(self, note_t: float) -> float:
        """全局 latency + 段落 latency（秒）。"""
        base = self.s.latency_ms / 1000.0
        segs = self.s.segments
        if segs and segs.bands:
            base += segs.latency_ms_at_time(note_t) / 1000.0
        return base

    def set_enter_t0_delay(self, ms: float) -> None:
        with self._lock:
            self.s.enter_t0_delay_ms = float(ms)
        self._emit()

    def set_dry(self, dry: bool) -> None:
        with self._lock:
            self.s.dry_run = bool(dry)
        self._emit()

    # ------------------------------------------------------------------
    # F8: 播放 / 暂停 切换；F6: 重置
    # ------------------------------------------------------------------

    def toggle_play(self) -> None:
        """F8：未运行→开局；运行中→暂停；已暂停→继续。"""
        if time.perf_counter() < self._ignore_hotkey_until:
            return
        with self._lock:
            running = self.s.running
            paused = self.s.paused
        if running:
            self.pause()
        elif paused:
            self.resume()
        else:
            self.start()

    def pause(self) -> None:
        """真暂停：冻结当前播放位置，不重置 next_index / 时间轴。"""
        with self._lock:
            if not self.s.running or self.s.paused:
                return
            if self.s.wall0 is not None:
                self.s.pause_elapsed = time.perf_counter() - self.s.wall0
            else:
                self.s.pause_elapsed = 0.0
            self.s.running = False
            self.s.paused = True
            pe = self.s.pause_elapsed
            ni = self.s.next_index
            self.s.status = f"已暂停 @ {pe:.3f}s | 下一拍 #{ni + 1} | F8 继续"
            self._pause_requested = True

        self._stop.set()
        t = self._thread
        self._thread = None
        if t and t.is_alive() and threading.current_thread() is not t:
            t.join(timeout=1.0)
        self._stop = threading.Event()
        self._pause_requested = False
        self._emit()

    def resume(self) -> None:
        """从暂停点继续（不再按 Enter）。"""
        with self._lock:
            if not self.s.paused:
                return
            sched = list(self.s.schedule)
            if not sched:
                self.s.status = "无数据"
                self._emit()
                return
            elapsed = float(self.s.pause_elapsed or 0.0)
            start_i = self.s.next_index
            wall0 = time.perf_counter() - elapsed
            self.s.wall0 = wall0
            self.s.pause_elapsed = None
            self.s.paused = False
            self.s.running = True
            self.s.status = (
                f"继续 | t={elapsed:.3f}s | 从 #{start_i + 1} | "
                f"lat={self.s.latency_ms:+.1f}ms"
            )
            self._stop = threading.Event()
            self._pause_requested = False

        if start_i >= len(sched):
            with self._lock:
                self.s.running = False
                self.s.paused = False
                self.s.status = "序列已结束"
            self._emit()
            return

        self._thread = threading.Thread(
            target=self._run_absolute,
            args=(sched, wall0, start_i),
            daemon=True,
            name="DLAbsolute",
        )
        self._thread.start()
        self._emit()

    def reset(self) -> None:
        """F6：停止并清零位置。"""
        self._pause_requested = False
        self._stop.set()
        t = self._thread
        self._thread = None
        if t and t.is_alive() and threading.current_thread() is not t:
            t.join(timeout=1.0)
        with self._lock:
            self.s.running = False
            self.s.paused = False
            self.s.wall0 = None
            self.s.pause_elapsed = None
            self.s.enter_keydown = None
            self.s.next_index = 0
            self.s.logs.clear()
            self.s.status = "已重置 — F8 开始"
            self._stop = threading.Event()
            self._pause_requested = False
        self._emit()

    # 兼容旧调用名
    def stop(self) -> None:
        self.reset()

    def request_start(self) -> None:
        self.toggle_play()

    def start(self) -> None:
        """
        开局：前置窗口 → Enter → wall0 = keydown + t0_delay
        → 按 wall0 + schedule[i] + latency 触发。
        """
        self.reset()
        with self._lock:
            sched = list(self.s.schedule)
            if not sched:
                self.s.status = "无数据，无法启动"
                self._emit()
                return
            dry = self.s.dry_run
            latency_ms = self.s.latency_ms
            t0_delay_ms = self.s.enter_t0_delay_ms
            self.s.running = True
            self.s.paused = False
            self.s.pause_elapsed = None
            self.s.next_index = 0
            self.s.logs.clear()
            self._stop = threading.Event()
            self._pause_requested = False

        focus_msg = self.clicker.prepare_focus()

        if not dry:
            try:
                self._ignore_hotkey_until = time.perf_counter() + 0.25
                keydown = self.clicker.press_enter(focus=False)
            except Exception as e:
                with self._lock:
                    self.s.running = False
                    self.s.status = f"Enter 失败: {e}"
                self._emit()
                return
        else:
            keydown = time.perf_counter()

        wall0 = keydown + t0_delay_ms / 1000.0

        with self._lock:
            self.s.enter_keydown = keydown
            self.s.wall0 = wall0
            self.s.status = (
                f"运行中 | {len(sched)} 点 | lat={latency_ms:+.1f}ms | {focus_msg}"
            )
        self._emit()

        self._thread = threading.Thread(
            target=self._run_absolute,
            args=(sched, wall0, 0),
            daemon=True,
            name="DLAbsolute",
        )
        self._thread.start()

    # ------------------------------------------------------------------
    # Scheduler
    # ------------------------------------------------------------------

    def _run_absolute(self, sched: list[float], wall0: float, start_i: int) -> None:
        timer_period(True)
        _boost_thread_priority()
        try:
            i = start_i
            n = len(sched)
            while i < n and not self._stop.is_set():
                with self._lock:
                    dry = self.s.dry_run
                group_t = sched[i]
                if not self._wait_for_note(wall0, group_t):
                    break
                first = True
                while i < n and abs(sched[i] - group_t) < 1e-9:
                    if self._stop.is_set():
                        break
                    if not first:
                        time.sleep(SAME_T_GAP)
                    with self._lock:
                        latency = self._effective_latency_s(sched[i])
                    planned = wall0 + sched[i] + latency
                    self._do_fire(i, sched[i], sched[i], planned, dry, "")
                    first = False
                    i += 1
                with self._lock:
                    self.s.next_index = i

            with self._lock:
                if self._pause_requested or self.s.paused:
                    # pause() 已写好状态
                    pass
                elif self._stop.is_set():
                    # reset 等
                    pass
                else:
                    self.s.status = "序列结束"
                    self.s.running = False
                    self.s.paused = False
            self._emit()
        finally:
            timer_period(False)

    def _wait_for_note(self, wall0: float, note_t: float) -> bool:
        """等待一拍；等待期间实时响应全局延迟微调。"""
        stop = self._stop
        while True:
            if stop.is_set():
                return False
            with self._lock:
                latency = self._effective_latency_s(note_t)
            deadline = wall0 + note_t + latency
            remain = deadline - time.perf_counter()
            if remain <= 0:
                return True
            # 长睡眠切成小片，保证热键修改后能很快重算下一拍。
            if remain > 0.040:
                time.sleep(min(remain - 0.012, 0.020))
            elif remain > 0.008:
                time.sleep(min(remain - 0.002, 0.004))
            elif remain > SPIN_REMAIN_S:
                time.sleep(0.0004)

    def _do_fire(
        self,
        index: int,
        official_t: float,
        rel_t: float,
        planned_wall: float,
        dry: bool,
        note: str,
    ) -> None:
        if dry:
            actual = time.perf_counter()
        else:
            self._ignore_hotkey_until = time.perf_counter() + 0.12
            actual = self.clicker.click(focus=False)

        err = (actual - planned_wall) * 1000.0
        with self._lock:
            self.s.next_index = index + 1
            self.s.last_flash_until = actual + 0.12
            self.s.logs.append(
                FireLog(index, official_t, rel_t, planned_wall, actual, err, note)
            )
            if len(self.s.logs) > 50:
                self.s.logs = self.s.logs[-50:]
            self.s.status = (
                f"#{index + 1}/{len(self.s.schedule)} "
                f"t={official_t:.3f}s err={err:+.1f}ms"
            )
        self._emit()

    def snapshot(self) -> dict:
        with self._lock:
            s = self.s
            game_rel = None
            game_official = None
            if s.paused and s.pause_elapsed is not None:
                game_rel = s.pause_elapsed
                game_official = s.pause_elapsed
            elif s.wall0 is not None:
                elapsed = time.perf_counter() - s.wall0
                game_rel = elapsed
                game_official = elapsed
            # 下一拍有效延迟（含段落）
            next_lat = s.latency_ms
            if s.schedule and 0 <= s.next_index < len(s.schedule):
                next_lat = s.latency_ms + s.segments.latency_ms_at_time(
                    s.schedule[s.next_index]
                )
            return {
                "level": s.level,
                "schedule": list(s.schedule),
                "latency_ms": s.latency_ms,
                "enter_t0_delay_ms": s.enter_t0_delay_ms,
                "dry_run": s.dry_run,
                "running": s.running,
                "paused": s.paused,
                "wall0": s.wall0,
                "pause_elapsed": s.pause_elapsed,
                "enter_keydown": s.enter_keydown,
                "next_index": s.next_index,
                "status": s.status,
                "logs": list(s.logs),
                "table_warnings": list(s.table_warnings),
                "game_rel": game_rel,
                "game_official": game_official,
                "flash": time.perf_counter() < s.last_flash_until,
                "backend": self.clicker.backend_name,
                "duration_s": s.duration_s,
                "segment_bands": len(s.segments.bands),
                "next_effective_latency_ms": next_lat,
            }

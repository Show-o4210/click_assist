"""主控制界面（PySide6）— 精简版。"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import theme as T
from .clicker import Clicker
from .data import LAST_LEVEL_SOURCES
from .engine import Engine
from .fail_tune import FailTuneDialog
from .hotkeys import HotkeyHub
from .level_names import combo_level_key, display_name, fill_level_combo, zh_name
from .note_editor import NoteEditorDialog
from .theme import APP_QSS
from .widgets import TimelineWidget, UiBridge


def _btn(text: str, accent: str) -> QPushButton:
    b = QPushButton(text)
    b.setProperty("accent", accent)
    return b


class AssistApp(QMainWindow):
    def __init__(
        self,
        levels: dict[str, list[float]],
        level: str,
        latency: float = 0.0,
        *,
        base_levels: dict[str, list[float]] | None = None,
        backend: str = "sendinput_scan",
        action: str = "space",
    ) -> None:
        super().__init__()
        self.levels = levels
        self.raw = levels
        self.base_levels = (
            base_levels
            if base_levels is not None
            else {k: list(v) for k, v in levels.items()}
        )

        self.setWindowTitle("跳舞的线 · 点击辅助")
        self.setMinimumSize(720, 520)
        self.resize(820, 600)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        self.clicker = Clicker(
            action=action, backend_name=backend, focus_before_click=True
        )
        self.engine = Engine(self.clicker, on_change=self._on_engine_change)
        self.hotkeys = HotkeyHub()
        self.bridge = UiBridge(self)
        self._dirty = True
        self._editor: NoteEditorDialog | None = None
        self._fail_tune: FailTuneDialog | None = None

        self._build(level, latency)
        self._reload()
        self._bind_hotkeys()

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._draw)
        self._timer.start()

    def _build(self, level: str, latency: float) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

        # row: level + latency + buttons
        bar = QHBoxLayout()
        bar.setSpacing(8)

        bar.addWidget(self._muted("关卡"))
        self.level_combo = QComboBox()
        self.level_combo.setMinimumWidth(200)
        self.level_combo.setToolTip("显示：中文 · 内部键（与官方表/JSON 文件名一致）")
        fill_level_combo(self.level_combo, list(self.levels.keys()), level)
        self.level_combo.currentIndexChanged.connect(lambda _i: self._reload())
        bar.addWidget(self.level_combo)

        bar.addWidget(self._muted("延迟 ms"))
        self.lat_spin = QDoubleSpinBox()
        self.lat_spin.setRange(-200.0, 200.0)
        self.lat_spin.setDecimals(1)
        self.lat_spin.setSingleStep(1.0)
        self.lat_spin.setValue(float(latency))
        self.lat_spin.setSuffix(" ms")
        self.lat_spin.setFixedWidth(110)
        self.lat_spin.setToolTip("正数=更晚（治抢拍），负数=更早")
        self.lat_spin.valueChanged.connect(self._on_latency)
        bar.addWidget(self.lat_spin)

        self.btn_play = _btn("F8 播放/暂停", "green")
        self.btn_play.clicked.connect(self.engine.toggle_play)
        self.btn_reset = _btn("F6 重置", "red")
        self.btn_reset.clicked.connect(self.engine.reset)
        self.btn_edit = _btn("编辑表", "orange")
        self.btn_edit.clicked.connect(self._open_editor)
        self.btn_fail = _btn("失败微调", "blue")
        self.btn_fail.setToolTip(
            "按失败进度 % 加「段落延迟」（不改表，推荐）；"
            "段内等量平移、段外不动，避免拖歪原本准的拍"
        )
        self.btn_fail.clicked.connect(self._open_fail_tune)
        bar.addWidget(self.btn_play)
        bar.addWidget(self.btn_reset)
        bar.addWidget(self.btn_edit)
        bar.addWidget(self.btn_fail)
        bar.addStretch(1)

        self.table_info = QLabel("")
        self.table_info.setStyleSheet(
            f"color: {T.GREEN}; font-family: Consolas; font-size: 11px; font-weight: 700;"
        )
        bar.addWidget(self.table_info)
        root.addLayout(bar)

        self.status_label = QLabel("待命")
        self.status_label.setStyleSheet("font-weight: 700; font-size: 13px;")
        root.addWidget(self.status_label)

        self.meta_label = QLabel("")
        self.meta_label.setStyleSheet(
            f"color: {T.MUTED}; font-family: Consolas; font-size: 11px;"
        )
        root.addWidget(self.meta_label)

        self.countdown_label = QLabel("NEXT —")
        self.countdown_label.setStyleSheet(
            f"color: {T.YELLOW}; font-family: Consolas; font-size: 16px; font-weight: 700;"
        )
        root.addWidget(self.countdown_label)

        self.cv_full = TimelineWidget(full=True, interactive=False)
        self.cv_full.setFixedHeight(64)
        root.addWidget(self.cv_full)

        self.cv_zoom = TimelineWidget(full=False, interactive=False, zoom_half=2.5)
        self.cv_zoom.setFixedHeight(76)
        root.addWidget(self.cv_zoom)

        lists = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(self._muted("时间表"))
        self.list_sched = QListWidget()
        self.list_sched.setUniformItemSizes(True)
        left.addWidget(self.list_sched)
        lists.addLayout(left, 1)

        right = QVBoxLayout()
        right.addWidget(self._muted("日志"))
        self.list_log = QListWidget()
        self.list_log.setUniformItemSizes(True)
        right.addWidget(self.list_log)
        lists.addLayout(right, 1)
        root.addLayout(lists, 1)

    @staticmethod
    def _muted(text: str) -> QLabel:
        lab = QLabel(text)
        lab.setStyleSheet(f"color: {T.MUTED};")
        return lab

    def _on_latency(self, v: float) -> None:
        self.engine.set_latency(float(v))

    def _latency_ms(self) -> float:
        return float(self.lat_spin.value())

    def _current_level(self) -> str:
        return combo_level_key(self.level_combo)

    def _open_editor(self) -> None:
        name = self._current_level()
        if self._editor is not None and self._editor.isVisible():
            self._editor.raise_()
            self._editor.activateWindow()
            if name:
                self._editor.set_level(name)
            return
        self._editor = NoteEditorDialog(
            self.levels,
            name or next(iter(self.levels), ""),
            base_levels=self.base_levels,
            parent=self,
        )
        self._editor.saved.connect(self._on_editor_saved)
        self._editor.show()

    def _open_fail_tune(self) -> None:
        name = self._current_level()
        if self._fail_tune is not None and self._fail_tune.isVisible():
            self._fail_tune.raise_()
            self._fail_tune.activateWindow()
            return
        self._fail_tune = FailTuneDialog(
            self.levels,
            name or next(iter(self.levels), ""),
            parent=self,
        )
        self._fail_tune.applied.connect(self._on_fail_tune_applied)
        self._fail_tune.segments_changed.connect(self._on_segments_changed)
        self._fail_tune.show()

    def _on_fail_tune_applied(self, name: str, times) -> None:
        """times 为 list 表示改了表；None 表示只改了段落延迟。"""
        if times is not None:
            self.levels[name] = list(times)
            self.raw[name] = list(times)
            LAST_LEVEL_SOURCES[name] = "override"
            if self._current_level() == name:
                self._reload()
            self.status_label.setText(
                f"已保存改表 {display_name(name)}（{len(times)} 点）"
            )
        else:
            if self._current_level() == name:
                self.engine.reload_segments()
            self.status_label.setText(f"段落延迟已更新 · {display_name(name)}")

    def _on_segments_changed(self, name: str) -> None:
        if self._current_level() == name:
            self.engine.reload_segments()

    def _on_editor_saved(self, name: str, times: list) -> None:
        self.levels[name] = list(times)
        self.raw[name] = list(times)
        LAST_LEVEL_SOURCES[name] = "override"
        if self._current_level() == name:
            self._reload()
        self.status_label.setText(f"已保存 {display_name(name)}（{len(times)} 点）")

    def _reload(self) -> None:
        name = self._current_level()
        if name not in self.raw:
            return
        raw_times = self.raw[name]
        self.engine.load(
            name,
            raw_times,
            skip_zeros=True,
            latency=self._latency_ms(),
            dry=False,
        )
        snap = self.engine.snapshot()
        sched = snap["schedule"]
        self.list_sched.clear()
        if sched:
            t0 = sched[0]
            self.list_sched.addItems(
                [
                    f"#{i + 1:4d}  {t:10.4f}s  +{t - t0:8.4f}"
                    for i, t in enumerate(sched)
                ]
            )

        src = LAST_LEVEL_SOURCES.get(name, "?")
        src_label = {
            "guide": "引导",
            "official": "官方",
            "override": "覆盖",
        }.get(src, src)
        self.table_info.setText(
            f"{zh_name(name)} · {src_label} · {len(sched)} 点"
            + (f" · 末 {sched[-1]:.1f}s" if sched else "")
        )

        warns = list(snap.get("table_warnings") or [])
        if warns:
            self.list_log.clear()
            self.list_log.addItems([f"! {w}" for w in warns[:8]])
            self._dirty = False

    def _on_engine_change(self) -> None:
        self.bridge.post(self._mark_dirty)

    def _mark_dirty(self) -> None:
        self._dirty = True

    def _bind_hotkeys(self) -> None:
        def ui(fn):
            return lambda: self.bridge.post(fn)

        mode = self.hotkeys.start(
            on_toggle=ui(self.engine.toggle_play),
            on_reset=ui(self.engine.reset),
        )
        self.status_label.setText(f"待命 · 热键[{mode}] F8/F6")

    def _draw(self) -> None:
        snap = self.engine.snapshot()
        sched = snap["schedule"]
        go = snap["game_official"]
        gr = snap["game_rel"]
        ni = snap["next_index"]
        n = len(sched)

        if snap["running"]:
            flag = "RUN"
        elif snap.get("paused"):
            flag = "PAUSE"
        else:
            flag = "IDLE"
        if snap["flash"]:
            flag += " ★"
        self.status_label.setText(f"[{flag}] {snap['status']}")

        level_disp = display_name(snap["level"]) if snap.get("level") else ""
        if gr is None:
            self.meta_label.setText(f"{level_disp} · {n} 点 · F8 开始")
            self.countdown_label.setText("NEXT —")
        else:
            eff = snap.get("next_effective_latency_ms", snap["latency_ms"])
            seg_n = snap.get("segment_bands") or 0
            seg_bit = f" · seg×{seg_n}" if seg_n else ""
            self.meta_label.setText(
                f"{level_disp} · t={go:7.3f}s · #{min(ni + 1, n)}/{n} · "
                f"lat={eff:+.1f}ms{seg_bit}"
            )
            if ni < n:
                lat_s = float(eff) / 1000.0
                remain = sched[ni] + lat_s - gr
                self.countdown_label.setText(
                    f"NEXT #{ni + 1}  {sched[ni]:.4f}s  in {remain:+.3f}s"
                )
            else:
                self.countdown_label.setText("NEXT — done")

        self.cv_full.set_data(
            sched, playhead=go, next_index=ni, flash=bool(snap["flash"])
        )
        self.cv_zoom.set_data(
            sched, playhead=go, next_index=ni, flash=bool(snap["flash"])
        )

        if self._dirty:
            self.list_log.clear()
            for ev in reversed(snap["logs"][-18:]):
                self.list_log.addItem(
                    f"#{ev.index + 1:3d}  {ev.official_t:7.3f}s  "
                    f"err={ev.err_ms:+6.1f}ms"
                )
            if n and 0 <= ni < n:
                self.list_sched.setCurrentRow(ni)
                item = self.list_sched.item(ni)
                if item:
                    self.list_sched.scrollToItem(item)
            self._dirty = False

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            self.engine.reset()
            self.hotkeys.stop()
        except Exception:
            pass
        if self._editor is not None:
            try:
                self._editor.close()
            except Exception:
                pass
        if self._fail_tune is not None:
            try:
                self._fail_tune.close()
            except Exception:
                pass
        event.accept()

    def run(self) -> int:
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        app.setStyle("Fusion")
        if not app.styleSheet():
            app.setStyleSheet(APP_QSS)
        self.show()
        return app.exec()

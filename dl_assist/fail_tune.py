"""失败百分比 → 段落延迟（推荐）/ 改表（激进，仅备用）。"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import theme as T
from .data import LAST_LEVEL_SOURCES, save_override_table
from .level_names import combo_level_key, display_name, fill_level_combo
from .segments import (
    band_from_fail,
    clear_level_segments,
    density_in_window,
    fail_center_time,
    half_window_s_to_pct,
    load_level_segments,
    merge_add_band,
    preview_segment_effect,
    save_level_segments,
)
from .tune import (
    apply_fail_tune,
    estimate_level_duration_s,
    percent_to_seconds,
    preview_lines,
)


class FailTuneDialog(QDialog):
    """
    默认：给失败点附近加「段落延迟」，不改点击表。
    段内等量平移 → 相对节奏不变；段外不动 → 原本准的地方不被拖歪。
    """

    # level, new times | None means times unchanged (segment only)
    applied = Signal(str, object)
    segments_changed = Signal(str)  # level

    def __init__(
        self,
        levels: dict[str, list[float]],
        level: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("失败微调")
        self.setMinimumSize(560, 480)
        self.resize(600, 540)
        self.levels = levels
        self._level = level if level in levels else (next(iter(levels), ""))

        self._build()
        self._sync_duration_hint()
        self._refresh_preview()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        tip = QLabel(
            "推荐用「段落延迟」：不改时间表，只在失败进度附近临时加减延迟。\n"
            "段内所有点一起平移（相对间隔不变），段外完全不动——"
            "避免「改完这一段，别处又开始错拍」。\n"
            "高频关尤其不要用「改表」模式。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet(f"color: {T.MUTED};")
        root.addWidget(tip)

        row1 = QHBoxLayout()
        row1.addWidget(self._muted("关卡"))
        self.level_combo = QComboBox()
        fill_level_combo(
            self.level_combo, list(self.levels.keys()), self._level
        )
        self.level_combo.currentIndexChanged.connect(self._on_level)
        row1.addWidget(self.level_combo, 1)

        row1.addWidget(self._muted("模式"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("段落延迟（推荐，不改表）", "segment")
        self.mode_combo.addItem("只改失败前 N 拍（改表）", "last_n")
        self.mode_combo.addItem("时间窗平移（改表·旧·慎用）", "window")
        self.mode_combo.setToolTip(
            "段落延迟：运行时叠加，可撤销。\n"
            "只改 N 拍：只动失败前几下，影响面最小。\n"
            "时间窗：旧逻辑，高频关容易拖歪邻拍。"
        )
        self.mode_combo.currentIndexChanged.connect(self._refresh_preview)
        row1.addWidget(self.mode_combo)
        root.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(self._muted("失败进度"))
        self.pct_spin = QDoubleSpinBox()
        self.pct_spin.setRange(0.1, 100.0)
        self.pct_spin.setDecimals(1)
        self.pct_spin.setSingleStep(0.5)
        self.pct_spin.setValue(50.0)
        self.pct_spin.setSuffix(" %")
        self.pct_spin.setFixedWidth(100)
        self.pct_spin.valueChanged.connect(self._refresh_preview)
        row2.addWidget(self.pct_spin)

        row2.addWidget(self._muted("原因"))
        self.reason_combo = QComboBox()
        self.reason_combo.addItem("抢拍（太快→推后）", "early")
        self.reason_combo.addItem("偏晚（太慢→提前）", "late")
        self.reason_combo.currentIndexChanged.connect(self._refresh_preview)
        row2.addWidget(self.reason_combo)

        row2.addWidget(self._muted("调整量"))
        self.delta_spin = QDoubleSpinBox()
        self.delta_spin.setRange(1.0, 80.0)
        self.delta_spin.setDecimals(1)
        self.delta_spin.setSingleStep(1.0)
        self.delta_spin.setValue(8.0)
        self.delta_spin.setSuffix(" ms")
        self.delta_spin.setFixedWidth(90)
        self.delta_spin.setToolTip("建议 5–12ms 小步；高频关更要小")
        self.delta_spin.valueChanged.connect(self._refresh_preview)
        row2.addWidget(self.delta_spin)
        root.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(self._muted("窗口 ±"))
        self.win_spin = QDoubleSpinBox()
        self.win_spin.setRange(0.15, 6.0)
        self.win_spin.setDecimals(2)
        self.win_spin.setSingleStep(0.25)
        self.win_spin.setValue(1.2)
        self.win_spin.setSuffix(" s")
        self.win_spin.setFixedWidth(90)
        self.win_spin.setToolTip("影响范围半宽；高频/密集团可先用 0.6–1.0s")
        self.win_spin.valueChanged.connect(self._refresh_preview)
        row3.addWidget(self.win_spin)

        row3.addWidget(self._muted("中心提前"))
        self.bias_spin = QDoubleSpinBox()
        self.bias_spin.setRange(0.0, 3.0)
        self.bias_spin.setDecimals(2)
        self.bias_spin.setSingleStep(0.1)
        self.bias_spin.setValue(0.35)
        self.bias_spin.setSuffix(" s")
        self.bias_spin.setFixedWidth(90)
        self.bias_spin.valueChanged.connect(self._refresh_preview)
        row3.addWidget(self.bias_spin)

        row3.addWidget(self._muted("淡入宽"))
        self.soft_spin = QDoubleSpinBox()
        self.soft_spin.setRange(0.0, 8.0)
        self.soft_spin.setDecimals(1)
        self.soft_spin.setSingleStep(0.5)
        self.soft_spin.setValue(1.0)
        self.soft_spin.setSuffix(" %")
        self.soft_spin.setFixedWidth(80)
        self.soft_spin.setToolTip("段落两端用多少进度百分比淡入/淡出，避免硬切")
        self.soft_spin.valueChanged.connect(self._refresh_preview)
        row3.addWidget(self.soft_spin)

        row3.addWidget(self._muted("N 拍"))
        self.n_spin = QDoubleSpinBox()
        self.n_spin.setRange(1, 12)
        self.n_spin.setDecimals(0)
        self.n_spin.setSingleStep(1)
        self.n_spin.setValue(2)
        self.n_spin.setFixedWidth(60)
        self.n_spin.setToolTip("「只改失败前 N 拍」模式下改几下")
        self.n_spin.valueChanged.connect(self._refresh_preview)
        row3.addWidget(self.n_spin)
        row3.addStretch(1)
        root.addLayout(row3)

        row4 = QHBoxLayout()
        row4.addWidget(self._muted("总长 s"))
        self.dur_spin = QDoubleSpinBox()
        self.dur_spin.setRange(5.0, 600.0)
        self.dur_spin.setDecimals(2)
        self.dur_spin.setSingleStep(1.0)
        self.dur_spin.setFixedWidth(110)
        self.dur_spin.valueChanged.connect(self._refresh_preview)
        row4.addWidget(self.dur_spin)

        self.dur_hint = QLabel("")
        self.dur_hint.setStyleSheet(
            f"color: {T.GREEN}; font-family: Consolas; font-size: 11px;"
        )
        row4.addWidget(self.dur_hint, 1)
        root.addLayout(row4)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setStyleSheet(
            f"font-family: Consolas, 'Cascadia Mono', monospace; font-size: 11px;"
            f"background: {T.INPUT_BG}; color: {T.FG};"
        )
        root.addWidget(self.preview, 1)

        btns = QHBoxLayout()
        self.btn_clear = QPushButton("清除本关段落")
        self.btn_clear.setProperty("accent", "red")
        self.btn_clear.setToolTip("删掉本关所有段落延迟，回到纯表+全局延迟")
        self.btn_clear.clicked.connect(self._clear_segments)
        self.btn_undo_last = QPushButton("撤销上一条段落")
        self.btn_undo_last.clicked.connect(self._undo_last_band)
        btns.addWidget(self.btn_clear)
        btns.addWidget(self.btn_undo_last)
        btns.addStretch(1)
        self.btn_preview = QPushButton("刷新预览")
        self.btn_preview.clicked.connect(self._refresh_preview)
        self.btn_apply = QPushButton("应用")
        self.btn_apply.setProperty("accent", "yellow")
        self.btn_apply.clicked.connect(self._apply)
        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.reject)
        btns.addWidget(self.btn_preview)
        btns.addWidget(self.btn_apply)
        btns.addWidget(self.btn_close)
        root.addLayout(btns)

    @staticmethod
    def _muted(text: str) -> QLabel:
        lab = QLabel(text)
        lab.setStyleSheet(f"color: {T.MUTED};")
        return lab

    def _on_level(self, _i: int = 0) -> None:
        self._level = combo_level_key(self.level_combo)
        self._sync_duration_hint()
        self._refresh_preview()

    def _signed_delta_ms(self) -> float:
        mag = abs(float(self.delta_spin.value()))
        if self.reason_combo.currentData() == "late":
            return -mag
        return mag

    def _mode(self) -> str:
        return str(self.mode_combo.currentData() or "segment")

    def _sync_duration_hint(self) -> None:
        name = combo_level_key(self.level_combo)
        times = list(self.levels.get(name, []))
        segs = load_level_segments(name)
        if segs.duration_s > 0:
            dur = segs.duration_s
            src = "已存段落"
        else:
            est = estimate_level_duration_s(name, times)
            dur = est.seconds
            src = est.source
        self.dur_spin.blockSignals(True)
        self.dur_spin.setValue(dur)
        self.dur_spin.blockSignals(False)
        table_end = times[-1] if times else 0.0
        self.dur_hint.setText(
            f"{dur:.2f}s（{src}）· 表末 {table_end:.2f}s · "
            f"{len(times)} 点 · 已有段落 {len(segs.bands)}"
        )

    def _density_note(self, times: list[float], duration_s: float) -> list[str]:
        center = fail_center_time(
            float(self.pct_spin.value()),
            duration_s,
            float(self.bias_spin.value()),
        )
        dens = density_in_window(
            times,
            center_t=center,
            half_window_s=float(self.win_spin.value()),
        )
        lines = []
        if dens["count"] <= 0:
            return ["窗口内无点击点"]
        avg = dens["avg_gap_ms"]
        mn = dens["min_gap_ms"]
        lines.append(
            f"窗口内 #{dens['first_index'] + 1}–#{dens['last_index'] + 1} "
            f"共 {dens['count']} 点"
            + (
                f" · 均间隔 {avg:.0f}ms · 最小 {mn:.0f}ms"
                if avg is not None and mn is not None
                else ""
            )
        )
        if dens["dense"]:
            lines.append(
                "⚠ 高频/密集段：请用「段落延迟」+ 小步 5–10ms；"
                "改表极易把原本准的邻拍带歪。"
            )
            if float(self.delta_spin.value()) > 12:
                lines.append("  → 建议把调整量降到 ≤10ms 再试。")
            if float(self.win_spin.value()) > 1.5:
                lines.append("  → 建议窗口 ±0.6～1.2s，别一次罩太大。")
        return lines

    def _build_extra_band(self, duration_s: float):
        half_pct = half_window_s_to_pct(float(self.win_spin.value()), duration_s)
        bias_pct = 100.0 * float(self.bias_spin.value()) / max(0.01, duration_s)
        return band_from_fail(
            fail_percent=float(self.pct_spin.value()),
            delta_ms=self._signed_delta_ms(),
            half_window_pct=half_pct,
            center_bias_pct=bias_pct,
            soft_pct=float(self.soft_spin.value()),
            note=(
                f"fail@{float(self.pct_spin.value()):.1f}% "
                f"{'early' if self._signed_delta_ms() >= 0 else 'late'}"
            ),
        )

    def _refresh_preview(self) -> None:
        name = combo_level_key(self.level_combo)
        times = list(self.levels.get(name, []))
        duration_s = float(self.dur_spin.value())
        mode = self._mode()
        delta = self._signed_delta_ms()
        fail_pct = float(self.pct_spin.value())
        fail_t = percent_to_seconds(fail_pct, duration_s)

        head = [
            f"关卡 {display_name(name)} · 失败 {fail_pct:.1f}% ≈ {fail_t:.2f}s",
            f"方向：{'抢拍→推后' if delta >= 0 else '偏晚→提前'}  {delta:+.1f} ms",
            f"模式：{self.mode_combo.currentText()}",
            "",
        ]
        head.extend(self._density_note(times, duration_s))
        head.append("")

        if mode == "segment":
            segs = load_level_segments(name)
            segs.duration_s = duration_s
            extra = self._build_extra_band(duration_s)
            head.append(
                f"将追加段落：{extra.from_pct:.1f}%–{extra.to_pct:.1f}%  "
                f"lat={extra.ms:+.1f}ms  soft={extra.soft_pct:.1f}%"
            )
            head.append("（点击表不变；可「撤销上一条」/「清除本关段落」）")
            head.append("")
            head.extend(preview_segment_effect(times, segs, extra=extra))
            if segs.bands:
                head.append("")
                head.append(f"已有段落 {len(segs.bands)} 条：")
                for i, b in enumerate(segs.bands, 1):
                    head.append(
                        f"  [{i}] {b.from_pct:.1f}–{b.to_pct:.1f}%  "
                        f"{b.ms:+.1f}ms  {b.note}"
                    )
        elif mode == "last_n":
            n = int(self.n_spin.value())
            center = fail_center_time(fail_pct, duration_s, float(self.bias_spin.value()))
            # 失败点前最后一个 ≤ center 的点，再往前共 N 个
            idx = -1
            for i, t in enumerate(times):
                if t <= center + 1e-9:
                    idx = i
            if idx < 0 and times:
                idx = 0
            if idx < 0:
                head.append("无点可改")
            else:
                lo = max(0, idx - n + 1)
                hi = idx
                head.append(f"将只改 #{lo + 1}–#{hi + 1}（失败前最多 {n} 拍）")
                head.append("⚠ 会写入 level_overrides.json（改表）")
                for i in range(lo, hi + 1):
                    old = times[i]
                    new = max(0.0, old + delta / 1000.0)
                    head.append(
                        f"  #{i + 1:4d}  {old:8.4f}s → {new:8.4f}s  ({delta:+.1f}ms)"
                    )
        else:
            # 旧时间窗
            new_times, report = apply_fail_tune(
                times,
                fail_percent=fail_pct,
                delta_ms=delta,
                level=name,
                duration_s=duration_s,
                half_window_s=float(self.win_spin.value()),
                center_bias_s=float(self.bias_spin.value()),
                taper=True,
                duration_source="manual",
            )
            head.append("⚠ 旧模式：会改时间戳，高频关易伤邻拍")
            head.extend(preview_lines(report, times, new_times))

        self.preview.setPlainText("\n".join(head))

    def _apply(self) -> None:
        name = combo_level_key(self.level_combo)
        times = list(self.levels.get(name, []))
        if not times:
            QMessageBox.warning(self, "无法应用", "当前关卡无点击数据。")
            return
        mode = self._mode()
        duration_s = float(self.dur_spin.value())
        delta = self._signed_delta_ms()
        fail_pct = float(self.pct_spin.value())

        dens = density_in_window(
            times,
            center_t=fail_center_time(
                fail_pct, duration_s, float(self.bias_spin.value())
            ),
            half_window_s=float(self.win_spin.value()),
        )
        if dens.get("dense") and mode != "segment":
            r = QMessageBox.question(
                self,
                "高频段警告",
                "检测为高频/密集段。改表很容易把原本准的地方带歪。\n"
                "建议改用「段落延迟」模式。\n\n仍要继续改表吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if r != QMessageBox.StandardButton.Yes:
                self.mode_combo.setCurrentIndex(0)
                self._refresh_preview()
                return

        if mode == "segment":
            band = self._build_extra_band(duration_s)
            msg = (
                f"追加段落延迟（不改表）\n"
                f"{name}  {band.from_pct:.1f}%–{band.to_pct:.1f}%  "
                f"{band.ms:+.1f}ms\n\n"
                f"写入 level_segment_latency.json？"
            )
            if (
                QMessageBox.question(
                    self,
                    "确认",
                    msg,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                != QMessageBox.StandardButton.Yes
            ):
                return
            segs = merge_add_band(name, band, duration_s)
            self.segments_changed.emit(name)
            self.applied.emit(name, None)
            self._sync_duration_hint()
            self._refresh_preview()
            QMessageBox.information(
                self,
                "已保存",
                f"已追加段落（共 {len(segs.bands)} 条）。\n"
                "再跑一局验证；过了可再小步追加，或「撤销上一条」。",
            )
            return

        if mode == "last_n":
            n = int(self.n_spin.value())
            center = fail_center_time(
                fail_pct, duration_s, float(self.bias_spin.value())
            )
            idx = -1
            for i, t in enumerate(times):
                if t <= center + 1e-9:
                    idx = i
            if idx < 0:
                QMessageBox.warning(self, "无法应用", "找不到失败点前的点击。")
                return
            lo = max(0, idx - n + 1)
            after = list(times)
            for i in range(lo, idx + 1):
                after[i] = max(0.0, after[i] + delta / 1000.0)
            after = sorted(after)
            msg = (
                f"改表：只动 #{lo + 1}–#{idx + 1}（{idx - lo + 1} 点）\n"
                f"{delta:+.1f}ms → level_overrides.json？"
            )
            if (
                QMessageBox.question(
                    self,
                    "确认改表",
                    msg,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                != QMessageBox.StandardButton.Yes
            ):
                return
            path = save_override_table(name, after)
            self.levels[name] = list(after)
            LAST_LEVEL_SOURCES[name] = "override"
            self.applied.emit(name, list(after))
            self._refresh_preview()
            QMessageBox.information(self, "已保存", f"已写入 {path.name}")
            return

        # window mode
        new_times, report = apply_fail_tune(
            times,
            fail_percent=fail_pct,
            delta_ms=delta,
            level=name,
            duration_s=duration_s,
            half_window_s=float(self.win_spin.value()),
            center_bias_s=float(self.bias_spin.value()),
            taper=True,
            duration_source="manual",
        )
        if report.count <= 0:
            QMessageBox.warning(self, "无法应用", report.note or "无点")
            return
        if (
            QMessageBox.question(
                self,
                "确认改表",
                f"时间窗平移 {report.count} 点，写入 overrides？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        path = save_override_table(name, new_times)
        self.levels[name] = list(new_times)
        LAST_LEVEL_SOURCES[name] = "override"
        self.applied.emit(name, list(new_times))
        self._refresh_preview()
        QMessageBox.information(self, "已保存", f"已写入 {path.name}\n{report.note}")

    def _undo_last_band(self) -> None:
        name = combo_level_key(self.level_combo)
        segs = load_level_segments(name)
        if not segs.bands:
            QMessageBox.information(self, "撤销", "本关没有段落可撤。")
            return
        removed = segs.bands.pop()
        save_level_segments(name, segs)
        self.segments_changed.emit(name)
        self.applied.emit(name, None)
        self._sync_duration_hint()
        self._refresh_preview()
        QMessageBox.information(
            self,
            "已撤销",
            f"已去掉：{removed.from_pct:.1f}–{removed.to_pct:.1f}% "
            f"{removed.ms:+.1f}ms",
        )

    def _clear_segments(self) -> None:
        name = combo_level_key(self.level_combo)
        if not load_level_segments(name).bands:
            QMessageBox.information(self, "清除", "本关没有段落。")
            return
        if (
            QMessageBox.question(
                self,
                "清除段落",
                f"清除 {name} 的全部段落延迟？\n（点击表与全局延迟不受影响）",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        clear_level_segments(name)
        self.segments_changed.emit(name)
        self.applied.emit(name, None)
        self._sync_duration_hint()
        self._refresh_preview()

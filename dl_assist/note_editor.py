"""音符/点击时间表编辑器 — 改完保存写入 level_overrides.json。"""

from __future__ import annotations

from PySide6.QtCore import QItemSelectionModel, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import theme as T
from .data import LAST_LEVEL_SOURCES, has_override_table, save_override_table
from .level_names import combo_level_key, display_name, fill_level_combo
from .widgets import TimelineWidget


class NoteEditorDialog(QDialog):
    saved = Signal(str, list)  # level, times

    def __init__(
        self,
        levels: dict[str, list[float]],
        level: str,
        *,
        base_levels: dict[str, list[float]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑点击表")
        self.setMinimumSize(820, 540)
        self.resize(900, 600)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )

        self.levels = levels
        self.base_levels = base_levels if base_levels is not None else dict(levels)
        self._times: list[float] = []
        self._undo: list[list[float]] = []
        self._dirty = False
        self._block_table = False
        self._level_name = level if level in levels else (next(iter(levels), ""))

        self._build()
        QShortcut(QKeySequence.StandardKey.Save, self, self._save)
        QShortcut(QKeySequence.StandardKey.Undo, self, self._undo_act)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, self._delete_selected)

        names = list(levels.keys())
        cur = self._level_name if self._level_name in levels else (names[0] if names else "")
        fill_level_combo(self.level_combo, names, cur)
        self._level_name = combo_level_key(self.level_combo)
        self._load_level(self._level_name)

    def set_level(self, name: str) -> None:
        if name not in self.levels:
            return
        for i in range(self.level_combo.count()):
            if self.level_combo.itemData(i) == name:
                self.level_combo.setCurrentIndex(i)
                return

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

        bar = QHBoxLayout()
        bar.addWidget(self._muted("关卡"))
        self.level_combo = QComboBox()
        self.level_combo.setMinimumWidth(200)
        self.level_combo.currentIndexChanged.connect(self._on_level_index)
        bar.addWidget(self.level_combo)

        self.info_label = QLabel("")
        self.info_label.setStyleSheet(
            f"color: {T.GREEN}; font-family: Consolas; font-weight: 700;"
        )
        bar.addWidget(self.info_label)
        bar.addStretch(1)
        self.dirty_label = QLabel("")
        self.dirty_label.setStyleSheet(f"color: {T.YELLOW}; font-weight: 700;")
        bar.addWidget(self.dirty_label)
        root.addLayout(bar)

        edit = QHBoxLayout()
        edit.addWidget(self._btn("+", self._insert, "green"))
        edit.addWidget(self._btn("−", self._delete_selected, "red"))
        edit.addWidget(self._muted("时间"))
        self.insert_spin = QDoubleSpinBox()
        self.insert_spin.setRange(0.0, 9999.0)
        self.insert_spin.setDecimals(4)
        self.insert_spin.setSingleStep(0.05)
        self.insert_spin.setSuffix(" s")
        self.insert_spin.setFixedWidth(110)
        edit.addWidget(self.insert_spin)
        edit.addWidget(self._muted("微调"))
        self.nudge_spin = QDoubleSpinBox()
        self.nudge_spin.setRange(0.1, 2000.0)
        self.nudge_spin.setDecimals(1)
        self.nudge_spin.setValue(10.0)
        self.nudge_spin.setSuffix(" ms")
        self.nudge_spin.setFixedWidth(90)
        edit.addWidget(self.nudge_spin)
        edit.addWidget(self._btn("←", lambda: self._nudge(-1)))
        edit.addWidget(self._btn("→", lambda: self._nudge(+1)))
        edit.addStretch(1)
        edit.addWidget(self._btn("撤销", self._undo_act))
        edit.addWidget(self._btn("保存", self._save, "yellow"))
        root.addLayout(edit)

        self.tl = TimelineWidget(full=True, interactive=True)
        self.tl.setMinimumHeight(72)
        self.tl.note_clicked.connect(self._on_tl_click)
        self.tl.note_dragged.connect(self._on_tl_drag)
        self.tl.time_clicked.connect(lambda t: self.insert_spin.setValue(max(0.0, t)))
        root.addWidget(self.tl)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["#", "时间 (s)", "间隔"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.itemSelectionChanged.connect(self._on_table_sel)
        self.table.itemChanged.connect(self._on_table_edit)
        root.addWidget(self.table, 1)

    def _btn(self, text: str, slot, accent: str | None = None) -> QPushButton:
        b = QPushButton(text)
        if accent:
            b.setProperty("accent", accent)
        b.clicked.connect(slot)
        return b

    def _muted(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setStyleSheet(f"color: {T.MUTED};")
        return lab

    def _push_undo(self) -> None:
        self._undo.append(list(self._times))
        if len(self._undo) > 60:
            self._undo = self._undo[-60:]
        self._dirty = True
        self.dirty_label.setText("● 未保存")

    def _load_level(self, name: str) -> None:
        if not name:
            return
        self._level_name = name
        self._times = list(self.levels.get(name, []))
        self._undo.clear()
        self._dirty = False
        self.dirty_label.setText("")
        src = LAST_LEVEL_SOURCES.get(name, "?")
        tag = {"guide": "引导", "official": "官方", "override": "覆盖"}.get(src, src)
        if has_override_table(name):
            tag += "/JSON"
        self.info_label.setText(f"{display_name(name)} · {tag} · {len(self._times)} 点")
        self._refresh()

    def _on_level_index(self, _i: int = 0) -> None:
        name = combo_level_key(self.level_combo)
        if name == self._level_name:
            return
        if self._dirty:
            r = QMessageBox.question(
                self,
                "未保存",
                "切换将丢弃未保存修改，继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if r != QMessageBox.StandardButton.Yes:
                self.level_combo.blockSignals(True)
                self.set_level(self._level_name)
                self.level_combo.blockSignals(False)
                return
        self._load_level(name)

    def _selected(self) -> list[int]:
        return sorted({i.row() for i in self.table.selectionModel().selectedRows()})

    def _refresh(self) -> None:
        sel = set(self._selected()) | self.tl.selected()
        center = self._times[min(sel)] if sel and self._times else (
            self._times[0] if self._times else None
        )
        self.tl.set_data(
            self._times, playhead=center, next_index=-1, selected=sel
        )
        self._fill_table(sel)
        n = len(self._times)
        if n:
            self.info_label.setText(
                f"{n} 点 · {self._times[0]:.3f}s → {self._times[-1]:.3f}s"
            )
        else:
            self.info_label.setText("0 点")

    def _fill_table(self, sel: set[int]) -> None:
        self._block_table = True
        t = self.table
        t.setRowCount(len(self._times))
        for i, tm in enumerate(self._times):
            delta = (tm - self._times[i - 1]) if i else 0.0
            cells = [
                QTableWidgetItem(f"{i + 1}"),
                QTableWidgetItem(f"{tm:.4f}"),
                QTableWidgetItem(f"{delta:+.4f}" if i else "—"),
            ]
            cells[0].setFlags(cells[0].flags() & ~Qt.ItemFlag.ItemIsEditable)
            cells[2].setFlags(cells[2].flags() & ~Qt.ItemFlag.ItemIsEditable)
            for c, it in enumerate(cells):
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                t.setItem(i, c, it)
        sm = t.selectionModel()
        sm.clearSelection()
        first = True
        for i in sorted(sel):
            if 0 <= i < t.rowCount():
                flag = (
                    QItemSelectionModel.SelectionFlag.ClearAndSelect
                    if first
                    else QItemSelectionModel.SelectionFlag.Select
                )
                sm.select(
                    t.model().index(i, 0),
                    flag | QItemSelectionModel.SelectionFlag.Rows,
                )
                first = False
        self._block_table = False

    def _on_table_sel(self) -> None:
        if self._block_table:
            return
        rows = self._selected()
        self.tl.set_selected(set(rows))
        if rows and 0 <= rows[0] < len(self._times):
            self.insert_spin.setValue(self._times[rows[0]])

    def _on_table_edit(self, item: QTableWidgetItem) -> None:
        if self._block_table or item.column() != 1:
            return
        row = item.row()
        try:
            val = float(item.text().replace(",", "."))
        except ValueError:
            self._block_table = True
            item.setText(f"{self._times[row]:.4f}")
            self._block_table = False
            return
        if abs(val - self._times[row]) < 1e-9:
            return
        self._push_undo()
        self._times[row] = max(0.0, val)
        self._refresh()

    def _on_tl_click(self, index: int) -> None:
        self._block_table = True
        self.table.clearSelection()
        if 0 <= index < self.table.rowCount():
            self.table.selectRow(index)
            self.table.scrollToItem(self.table.item(index, 0))
        self._block_table = False
        if 0 <= index < len(self._times):
            self.insert_spin.setValue(self._times[index])
        self.tl.set_selected({index})

    def _on_tl_drag(self, index: int, new_t: float) -> None:
        if not (0 <= index < len(self._times)):
            return
        self._push_undo()
        self._times[index] = max(0.0, new_t)
        self._refresh()
        self._block_table = True
        self.table.selectRow(index)
        self._block_table = False

    def _insert(self) -> None:
        t = float(self.insert_spin.value())
        self._push_undo()
        self._times.append(t)
        self._times.sort()
        self._refresh()
        try:
            idx = self._times.index(t)
        except ValueError:
            idx = 0
        self._block_table = True
        self.table.selectRow(idx)
        self._block_table = False

    def _delete_selected(self) -> None:
        rows = self._selected()
        if not rows:
            return
        self._push_undo()
        for i in reversed(rows):
            if 0 <= i < len(self._times):
                del self._times[i]
        self._refresh()

    def _nudge(self, steps: int) -> None:
        rows = self._selected()
        if not rows:
            return
        delta = steps * float(self.nudge_spin.value()) / 1000.0
        self._push_undo()
        for i in rows:
            if 0 <= i < len(self._times):
                self._times[i] = max(0.0, self._times[i] + delta)
        self._refresh()
        self._block_table = True
        for i in rows:
            if 0 <= i < self.table.rowCount():
                self.table.selectRow(i)
        self._block_table = False

    def _undo_act(self) -> None:
        if not self._undo:
            return
        self._times = self._undo.pop()
        self._dirty = bool(self._undo) or True
        self.dirty_label.setText("● 未保存")
        self._refresh()

    def _save(self) -> None:
        name = combo_level_key(self.level_combo) or self._level_name
        if not name:
            return
        path = save_override_table(name, self._times)
        self.levels[name] = list(self._times)
        LAST_LEVEL_SOURCES[name] = "override"
        self._dirty = False
        self.dirty_label.setText("")
        self.saved.emit(name, list(self._times))
        self.info_label.setText(
            f"已保存 {display_name(name)} · {len(self._times)} 点 → {path.name}"
        )

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._dirty:
            r = QMessageBox.question(
                self,
                "未保存",
                "有未保存修改，确定关闭？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if r != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        event.accept()

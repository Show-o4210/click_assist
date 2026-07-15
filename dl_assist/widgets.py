"""PySide6 共用控件：时间轴、线程安全回调桥。"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from . import theme as T


class UiBridge(QObject):
    """把热键/引擎线程回调安全投递到 GUI 线程。"""

    invoke = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.invoke.connect(self._run)

    @staticmethod
    def _run(fn: object) -> None:
        if callable(fn):
            try:
                fn()  # type: ignore[operator]
            except Exception:
                pass

    def post(self, fn: Callable[[], None]) -> None:
        self.invoke.emit(fn)


class TimelineWidget(QWidget):
    """
    点击时间轴可视化。
    - full=True：显示全曲
    - full=False：以 playhead 为中心的近景
    可交互：点击选点、拖拽改时间（用于音符编辑器）。
    """

    note_clicked = Signal(int)  # index
    note_dragged = Signal(int, float)  # index, new_time
    time_clicked = Signal(float)  # empty area → absolute time
    selection_changed = Signal(int)  # -1 = none

    def __init__(
        self,
        *,
        full: bool = True,
        interactive: bool = False,
        zoom_half: float = 2.5,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.full = full
        self.interactive = interactive
        self.zoom_half = zoom_half
        self.setMinimumHeight(64 if full else 76)
        self.setMouseTracking(True)

        self._times: list[float] = []
        self._playhead: float | None = None
        self._next_i: int = 0
        self._selected: set[int] = set()
        self._flash = False
        self._drag_i: int | None = None
        self._view0 = 0.0
        self._view1 = 1.0

    # ---- public API ----

    def set_data(
        self,
        times: list[float],
        *,
        playhead: float | None = None,
        next_index: int = 0,
        selected: set[int] | None = None,
        flash: bool = False,
    ) -> None:
        self._times = list(times)
        self._playhead = playhead
        self._next_i = next_index
        if selected is not None:
            self._selected = set(selected)
        self._flash = flash
        self.update()

    def set_selected(self, indices: set[int] | list[int]) -> None:
        self._selected = set(indices)
        self.update()

    def selected(self) -> set[int]:
        return set(self._selected)

    # ---- geometry ----

    def _recompute_view(self) -> None:
        if not self._times:
            self._view0, self._view1 = 0.0, 1.0
            return
        t0, t_end = self._times[0], self._times[-1]
        if self.full:
            self._view0 = t0 - 0.5
            self._view1 = t_end + 0.5
        else:
            center = self._playhead if self._playhead is not None else t0
            self._view0 = center - self.zoom_half
            self._view1 = center + self.zoom_half
        if self._view1 - self._view0 < 0.001:
            self._view1 = self._view0 + 0.001

    def _x_of(self, t: float) -> float:
        pad = 14.0
        w = max(self.width(), 120)
        span = self._view1 - self._view0
        return pad + (t - self._view0) / span * (w - 2 * pad)

    def _t_of(self, x: float) -> float:
        pad = 14.0
        w = max(self.width(), 120)
        span = self._view1 - self._view0
        return self._view0 + (x - pad) / max(w - 2 * pad, 1.0) * span

    def _hit_index(self, x: float, y: float, radius: float = 10.0) -> int | None:
        cy = self.height() / 2 + 4
        if abs(y - cy) > radius + 8:
            return None
        best: int | None = None
        best_d = radius
        for i, t in enumerate(self._times):
            if t < self._view0 - 0.05 or t > self._view1 + 0.05:
                continue
            d = abs(self._x_of(t) - x)
            if d <= best_d:
                best_d = d
                best = i
        return best

    # ---- paint ----

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        self._recompute_view()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(T.INPUT_BG))

        w, h = self.width(), self.height()
        pad = 14.0
        y = h / 2 + 4

        if not self._times:
            p.setPen(QColor(T.MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "无数据")
            return

        # axis
        p.setPen(QPen(QColor(T.AXIS), 2))
        p.drawLine(QPointF(pad, y), QPointF(w - pad, y))

        # segments
        p.setPen(QPen(QColor(T.LINE), 2))
        for a, b in zip(self._times, self._times[1:]):
            if b < self._view0 or a > self._view1:
                continue
            p.drawLine(QPointF(self._x_of(a), y), QPointF(self._x_of(b), y))

        play = self._playhead
        for i, t in enumerate(self._times):
            if t < self._view0 - 0.02 or t > self._view1 + 0.02:
                continue
            x = self._x_of(t)
            r = 7.0 if i == 0 else 4.5
            if i in self._selected:
                color = QColor(T.ORANGE)
            elif i == 0:
                color = QColor(T.RED)
            elif play is not None and t <= play + 1e-4:
                color = QColor(T.GREEN)
            else:
                color = QColor(T.BLUE)

            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x, y), r, r)
            p.setPen(QPen(color, 1.5))
            p.drawLine(QPointF(x, y - r - 3), QPointF(x, y + r + 3))

            if i == self._next_i:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(T.YELLOW), 2))
                p.drawEllipse(QPointF(x, y), r + 5, r + 5)

        if play is not None:
            x = self._x_of(play)
            p.setPen(QPen(QColor(T.YELLOW), 2))
            p.drawLine(QPointF(x, 4), QPointF(x, h - 16))
            tri = QPolygonF(
                [QPointF(x - 6, 4), QPointF(x + 6, 4), QPointF(x, 14)]
            )
            p.setBrush(QColor(T.YELLOW))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPolygon(tri)

        if self._flash:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(T.RED), 3))
            p.drawRect(QRectF(1, 1, w - 2, h - 2))

        # time labels at edges
        p.setPen(QColor(T.MUTED))
        p.drawText(int(pad), h - 4, f"{self._view0:.1f}s")
        right = f"{self._view1:.1f}s"
        p.drawText(int(w - pad - p.fontMetrics().horizontalAdvance(right)), h - 4, right)

    # ---- mouse ----

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        idx = self._hit_index(pos.x(), pos.y())
        if idx is not None:
            mods = event.modifiers()
            if mods & Qt.KeyboardModifier.ControlModifier:
                if idx in self._selected:
                    self._selected.discard(idx)
                else:
                    self._selected.add(idx)
            elif mods & Qt.KeyboardModifier.ShiftModifier and self._selected:
                a = min(self._selected)
                lo, hi = min(a, idx), max(a, idx)
                self._selected = set(range(lo, hi + 1))
            else:
                self._selected = {idx}
            self.note_clicked.emit(idx)
            self.selection_changed.emit(idx)
            if self.interactive:
                self._drag_i = idx
            self.update()
        else:
            t = max(0.0, self._t_of(pos.x()))
            if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                self._selected.clear()
                self.selection_changed.emit(-1)
            self.time_clicked.emit(t)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_i is None or not self.interactive:
            return
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        t = max(0.0, self._t_of(event.position().x()))
        # live preview
        if 0 <= self._drag_i < len(self._times):
            self._times[self._drag_i] = t
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._drag_i is not None and self.interactive:
            t = max(0.0, self._t_of(event.position().x()))
            i = self._drag_i
            self._drag_i = None
            self.note_dragged.emit(i, t)
        else:
            self._drag_i = None

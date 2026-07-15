"""段落延迟：不改点击表，只在指定进度区间叠加 latency。

相对改绝对时间戳：
- 段内所有点等量平移 → 段内相对节奏（间隔）保持不变
- 段外完全不动 → 原本准的地方不会被拖歪
- 可撤销、可叠加、可小步试

高频关尤其重要：改表会破坏密集点间距；段落延迟只平移相位。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .paths import LEVEL_SEGMENTS_PATH
from .tune import estimate_level_duration_s, percent_to_seconds, window_indices


@dataclass
class LatencyBand:
    """一条进度区间上的额外延迟（ms）。正=更晚（治抢拍）。"""

    from_pct: float
    to_pct: float
    ms: float
    # 两端各用 soft_pct 百分比做线性淡入/淡出，避免硬切导致接缝处错拍
    soft_pct: float = 1.0
    note: str = ""

    def clamp(self) -> LatencyBand:
        a = max(0.0, min(100.0, float(self.from_pct)))
        b = max(0.0, min(100.0, float(self.to_pct)))
        if b < a:
            a, b = b, a
        # 至少 0.2% 宽，避免零宽
        if b - a < 0.2:
            mid = (a + b) / 2.0
            a = max(0.0, mid - 0.1)
            b = min(100.0, mid + 0.1)
        return LatencyBand(
            from_pct=a,
            to_pct=b,
            ms=float(self.ms),
            soft_pct=max(0.0, float(self.soft_pct)),
            note=str(self.note or ""),
        )

    def weight_at(self, pct: float) -> float:
        """0..1，中间满量，两端 soft 淡入淡出。"""
        b = self.clamp()
        p = float(pct)
        if p < b.from_pct or p > b.to_pct:
            return 0.0
        soft = min(b.soft_pct, (b.to_pct - b.from_pct) / 2.0)
        if soft <= 1e-9:
            return 1.0
        # 左缘淡入
        if p < b.from_pct + soft:
            return (p - b.from_pct) / soft
        # 右缘淡出
        if p > b.to_pct - soft:
            return (b.to_pct - p) / soft
        return 1.0


@dataclass
class LevelSegments:
    duration_s: float = 0.0
    bands: list[LatencyBand] = field(default_factory=list)

    def latency_ms_at_pct(self, pct: float) -> float:
        return sum(band.ms * band.weight_at(pct) for band in self.bands)

    def latency_ms_at_time(self, t: float) -> float:
        dur = max(0.01, float(self.duration_s) or 0.01)
        pct = 100.0 * float(t) / dur
        return self.latency_ms_at_pct(pct)


def _parse_band(raw: dict) -> LatencyBand | None:
    try:
        return LatencyBand(
            from_pct=float(raw["from_pct"]),
            to_pct=float(raw["to_pct"]),
            ms=float(raw["ms"]),
            soft_pct=float(raw.get("soft_pct", 1.0)),
            note=str(raw.get("note", "")),
        ).clamp()
    except (KeyError, TypeError, ValueError):
        return None


def load_all_segments(path: Path | None = None) -> dict[str, LevelSegments]:
    path = path or LEVEL_SEGMENTS_PATH
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, LevelSegments] = {}
    for name, val in raw.items():
        if not isinstance(val, dict):
            continue
        bands_raw = val.get("bands") or []
        bands: list[LatencyBand] = []
        if isinstance(bands_raw, list):
            for item in bands_raw:
                if isinstance(item, dict):
                    b = _parse_band(item)
                    if b is not None:
                        bands.append(b)
        out[str(name)] = LevelSegments(
            duration_s=float(val.get("duration_s") or 0.0),
            bands=bands,
        )
    return out


def load_level_segments(level: str, path: Path | None = None) -> LevelSegments:
    return load_all_segments(path).get(level, LevelSegments())


def save_all_segments(data: dict[str, LevelSegments], path: Path | None = None) -> Path:
    path = path or LEVEL_SEGMENTS_PATH
    payload: dict[str, dict] = {}
    for name, ls in sorted(data.items(), key=lambda kv: kv[0].lower()):
        if not ls.bands and not ls.duration_s:
            continue
        payload[name] = {
            "duration_s": float(ls.duration_s),
            "bands": [asdict(b.clamp()) for b in ls.bands],
        }
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


def save_level_segments(level: str, segs: LevelSegments, path: Path | None = None) -> Path:
    all_data = load_all_segments(path)
    if not segs.bands:
        all_data.pop(level, None)
    else:
        all_data[level] = segs
    return save_all_segments(all_data, path)


def clear_level_segments(level: str, path: Path | None = None) -> bool:
    all_data = load_all_segments(path)
    if level not in all_data:
        return False
    del all_data[level]
    save_all_segments(all_data, path)
    return True


def band_from_fail(
    *,
    fail_percent: float,
    delta_ms: float,
    half_window_pct: float = 2.5,
    center_bias_pct: float = 0.5,
    soft_pct: float = 1.0,
    note: str = "",
) -> LatencyBand:
    """
    失败 % → 一条段落带。

    center 略提前（失败提示常晚于真正拐错的拍）。
    half_window_pct：半宽（进度百分点），默认约 ±2.5%。
    """
    center = max(0.0, float(fail_percent) - float(center_bias_pct))
    half = max(0.3, float(half_window_pct))
    return LatencyBand(
        from_pct=center - half,
        to_pct=center + half,
        ms=float(delta_ms),
        soft_pct=float(soft_pct),
        note=note or f"fail@{fail_percent:.1f}%",
    ).clamp()


def half_window_s_to_pct(half_window_s: float, duration_s: float) -> float:
    dur = max(0.01, float(duration_s))
    return 100.0 * max(0.05, float(half_window_s)) / dur


def density_in_window(
    times: list[float],
    *,
    center_t: float,
    half_window_s: float,
) -> dict:
    """分析窗口内点击密度，供 UI 提示。"""
    lo, hi = window_indices(times, center_t, half_window_s)
    if lo < 0 or not times:
        return {
            "count": 0,
            "avg_gap_ms": None,
            "min_gap_ms": None,
            "dense": False,
            "first_index": -1,
            "last_index": -1,
        }
    n = hi - lo + 1
    gaps = []
    for i in range(lo + 1, hi + 1):
        gaps.append((times[i] - times[i - 1]) * 1000.0)
    avg = sum(gaps) / len(gaps) if gaps else None
    mn = min(gaps) if gaps else None
    # 平均间隔 < 90ms 视为高频段
    dense = bool(avg is not None and avg < 90.0) or n >= 12
    return {
        "count": n,
        "avg_gap_ms": avg,
        "min_gap_ms": mn,
        "dense": dense,
        "first_index": lo,
        "last_index": hi,
    }


def preview_segment_effect(
    times: list[float],
    segs: LevelSegments,
    *,
    extra: LatencyBand | None = None,
) -> list[str]:
    """预览：段延迟对哪些点有可感影响（|lat|>=0.5ms）。"""
    bands = list(segs.bands)
    if extra is not None:
        bands = bands + [extra]
    probe = LevelSegments(duration_s=segs.duration_s, bands=bands)
    lines: list[str] = []
    if not times:
        return ["空表"]
    affected = []
    for i, t in enumerate(times):
        ms = probe.latency_ms_at_time(t)
        if abs(ms) >= 0.5:
            affected.append((i, t, ms))
    lines.append(f"当前段落数 {len(bands)} · 受影响点 {len(affected)}")
    if not affected:
        lines.append("（几乎无点落入区间；可加大窗口或检查总长）")
        return lines
    # 抽样
    step = 1 if len(affected) <= 14 else max(1, len(affected) // 12)
    for j, (i, t, ms) in enumerate(affected):
        if j % step != 0 and j != len(affected) - 1:
            continue
        pct = 100.0 * t / max(0.01, probe.duration_s)
        lines.append(f"  #{i + 1:4d}  t={t:7.3f}s  ({pct:5.1f}%)  lat={ms:+6.1f}ms")
    if len(affected) > 14:
        lines.append(f"  … 共 {len(affected)} 点")
    return lines


def merge_add_band(level: str, band: LatencyBand, duration_s: float) -> LevelSegments:
    """追加一条 band 并保存。"""
    segs = load_level_segments(level)
    if duration_s > 0:
        segs.duration_s = float(duration_s)
    elif segs.duration_s <= 0:
        segs.duration_s = 60.0
    segs.bands.append(band.clamp())
    save_level_segments(level, segs)
    return segs


def ensure_duration(level: str, times: list[float], duration_s: float | None = None) -> float:
    if duration_s is not None and duration_s > 0:
        return float(duration_s)
    segs = load_level_segments(level)
    if segs.duration_s > 0:
        return segs.duration_s
    return estimate_level_duration_s(level, times).seconds


def fail_center_time(
    fail_percent: float,
    duration_s: float,
    center_bias_s: float,
) -> float:
    fail_t = percent_to_seconds(fail_percent, duration_s)
    return max(0.0, fail_t - center_bias_s)

"""按失败百分比对点击表做局部微调。

游戏失败时会显示进度 %，大致对应关卡/音乐进度。
不必手搓每个点：输入失败 % + 抢拍/偏晚，自动平移失败点附近一小段。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

@dataclass(frozen=True)
class DurationEstimate:
    seconds: float
    source: str  # audio | table | default


@dataclass(frozen=True)
class TuneReport:
    fail_percent: float
    duration_s: float
    duration_source: str
    center_t: float
    half_window_s: float
    delta_ms: float
    first_index: int  # inclusive, 0-based
    last_index: int  # inclusive, 0-based
    count: int
    t_lo: float
    t_hi: float
    note: str = ""


def estimate_level_duration_s(
    level: str,
    times: list[float],
    *,
    prefer_audio: bool = True,
) -> DurationEstimate:
    """
    估算「100% 进度」对应的秒数。

    使用点击表末点估算。百分比本就不精确，这里只求稳定映射。
    """
    table_end = float(times[-1]) if times else 0.0
    if table_end > 1.0:
        return DurationEstimate(table_end, "table")
    return DurationEstimate(60.0, "default")


def percent_to_seconds(percent: float, duration_s: float) -> float:
    p = max(0.0, min(100.0, float(percent)))
    return (p / 100.0) * max(0.01, float(duration_s))


def nearest_index(times: list[float], t: float) -> int:
    if not times:
        return -1
    best_i = 0
    best_d = abs(times[0] - t)
    for i in range(1, len(times)):
        d = abs(times[i] - t)
        if d < best_d:
            best_d = d
            best_i = i
    return best_i


def window_indices(
    times: list[float],
    center_t: float,
    half_window_s: float,
) -> tuple[int, int]:
    """返回 [lo, hi] 闭区间下标；无命中时返回 (-1, -1)。"""
    if not times:
        return -1, -1
    half = max(0.05, float(half_window_s))
    lo_t = center_t - half
    hi_t = center_t + half
    lo = -1
    hi = -1
    for i, tm in enumerate(times):
        if lo_t - 1e-12 <= tm <= hi_t + 1e-12:
            if lo < 0:
                lo = i
            hi = i
    if lo < 0:
        # 窗口内无点：退化为最近一点
        i = nearest_index(times, center_t)
        return i, i
    return lo, hi


def _taper_weight(t: float, center_t: float, half_window_s: float) -> float:
    """中心 1.0，边缘 0.0 的余弦半窗；无 taper 时由调用方固定 1.0。"""
    half = max(1e-6, half_window_s)
    x = abs(t - center_t) / half
    if x >= 1.0:
        return 0.0
    # 0.5 + 0.5*cos(pi*x)：中心满量，边缘平滑到 0
    return 0.5 + 0.5 * math.cos(math.pi * x)


def apply_fail_tune(
    times: list[float],
    *,
    fail_percent: float,
    delta_ms: float,
    level: str = "",
    duration_s: float | None = None,
    half_window_s: float = 1.5,
    # 失败提示通常出现在「已经拐错」之后，中心略提前
    center_bias_s: float = 0.35,
    taper: bool = True,
    duration_source: str | None = None,
) -> tuple[list[float], TuneReport]:
    """
    按失败百分比，对附近点击做时间平移。

    delta_ms:
      正数 = 整体更晚（治抢拍）
      负数 = 整体更早（治偏晚）

    返回 (新表, 报告)。原表不修改。
    """
    if not times:
        est = estimate_level_duration_s(level, times)
        return [], TuneReport(
            fail_percent=fail_percent,
            duration_s=duration_s or est.seconds,
            duration_source=duration_source or est.source,
            center_t=0.0,
            half_window_s=half_window_s,
            delta_ms=delta_ms,
            first_index=-1,
            last_index=-1,
            count=0,
            t_lo=0.0,
            t_hi=0.0,
            note="空表，无法微调",
        )

    if duration_s is None or duration_s <= 0:
        est = estimate_level_duration_s(level, times)
        duration_s = est.seconds
        duration_source = est.source
    else:
        duration_source = duration_source or "manual"

    fail_t = percent_to_seconds(fail_percent, duration_s)
    center_t = max(0.0, fail_t - float(center_bias_s))
    half = max(0.05, float(half_window_s))
    lo, hi = window_indices(times, center_t, half)
    if lo < 0:
        return list(times), TuneReport(
            fail_percent=fail_percent,
            duration_s=duration_s,
            duration_source=duration_source or "?",
            center_t=center_t,
            half_window_s=half,
            delta_ms=delta_ms,
            first_index=-1,
            last_index=-1,
            count=0,
            t_lo=center_t - half,
            t_hi=center_t + half,
            note="未找到附近点击",
        )

    delta_s = float(delta_ms) / 1000.0
    out = list(times)
    for i in range(lo, hi + 1):
        if taper:
            w = _taper_weight(times[i], center_t, half)
        else:
            w = 1.0
        out[i] = max(0.0, times[i] + delta_s * w)

    # 局部平移后可能与邻点交叉：整表稳定排序并去重（极近合并）
    out = _stabilize_order(out)

    # 排序后下标可能变；用时间范围再报告
    t_lo = times[lo]
    t_hi = times[hi]
    note = (
        f"{fail_percent:.1f}% → t≈{fail_t:.2f}s，"
        f"中心 {center_t:.2f}s（提前 {center_bias_s:.2f}s），"
        f"#{lo + 1}–#{hi + 1}（{hi - lo + 1} 点）"
        f"{' 锥形衰减' if taper else ' 等量平移'} "
        f"{delta_ms:+.1f}ms"
    )
    return out, TuneReport(
        fail_percent=float(fail_percent),
        duration_s=float(duration_s),
        duration_source=duration_source or "?",
        center_t=center_t,
        half_window_s=half,
        delta_ms=float(delta_ms),
        first_index=lo,
        last_index=hi,
        count=hi - lo + 1,
        t_lo=t_lo,
        t_hi=t_hi,
        note=note,
    )


def _stabilize_order(times: list[float], eps: float = 1e-4) -> list[float]:
    """排序；过近的点拉开到 eps，避免同刻叠成一团。"""
    if not times:
        return []
    s = sorted(float(t) for t in times)
    out = [max(0.0, s[0])]
    for t in s[1:]:
        t = max(0.0, t)
        if t < out[-1] + eps:
            t = out[-1] + eps
        out.append(t)
    return out


def preview_lines(report: TuneReport, times_before: list[float], times_after: list[float]) -> list[str]:
    """给人看的预览文本。"""
    lines = [
        report.note or "—",
        f"总长基准 {report.duration_s:.2f}s（{report.duration_source}）",
        f"窗口 [{report.t_lo:.3f}s .. {report.t_hi:.3f}s]  "
        f"Δ={report.delta_ms:+.1f} ms",
    ]
    if report.count <= 0 or report.first_index < 0:
        return lines
    # 最多展示 12 个点的前后对比
    lo, hi = report.first_index, report.last_index
    step = 1
    span = hi - lo + 1
    if span > 12:
        step = max(1, span // 12)
    lines.append("点位对比（旧 → 新）:")
    for i in range(lo, hi + 1, step):
        if i >= len(times_before):
            break
        old = times_before[i]
        # 微调后可能排序，按最近新点近似
        new = times_after[i] if i < len(times_after) else old
        # 若 stabilize 后下标漂移，用时间邻域找
        if abs(new - old) > abs(report.delta_ms) / 1000.0 + 0.05:
            # 找最接近 old+delta 的点
            target = old + report.delta_ms / 1000.0
            j = nearest_index(times_after, target)
            new = times_after[j] if j >= 0 else old
        dms = (new - old) * 1000.0
        lines.append(f"  #{i + 1:4d}  {old:8.4f}s → {new:8.4f}s  ({dms:+.1f}ms)")
    if span > 12:
        lines.append(f"  … 共 {report.count} 点（已抽样显示）")
    return lines

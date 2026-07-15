from __future__ import annotations

import json
import re
from pathlib import Path

from .paths import (
    CACHE_PATH,
    DEFAULT_BUNDLE,
    LEVEL_LATENCY_PATH,
    OVERRIDES_JSON,
    ROOT_DIR,
    SOUNDS_DIR,
    TABLES_OFFICIAL_DIR,
    TABLES_OVERRIDE_DIR,
)

# 解析一行里的浮点（兼容 "1.23" / "1,23" / 前后空白）
_FLOAT_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def parse_times_text(text: str) -> list[float]:
    """
    把文本解析成点击时间列表。
    无条数上限；支持每行一个数，或逗号/空白分隔。
    """
    if not text:
        return []
    # 统一换行
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # 去 BOM
    if text.startswith("\ufeff"):
        text = text[1:]

    times: list[float] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        # 允许 "1.0, 2.0" 或 "1.0 2.0"
        parts = re.split(r"[,;\s]+", line)
        for part in parts:
            if not part:
                continue
            part = part.replace(",", ".")  # 欧式小数
            try:
                times.append(float(part))
            except ValueError:
                m = _FLOAT_RE.search(part)
                if m:
                    try:
                        times.append(float(m.group(0)))
                    except ValueError:
                        pass
    return times


def load_times_from_bundle(bundle_path: Path) -> dict[str, list[float]]:
    try:
        import UnityPy
    except ImportError:
        if CACHE_PATH.is_file():
            try:
                with CACHE_PATH.open("r", encoding="utf-8") as f:
                    raw = json.load(f)
                return {k: [float(x) for x in v] for k, v in raw.items()}
            except Exception:
                pass
        raise ImportError(
            "未安装 UnityPy，且无法加载缓存。若要直接解析 Unity Bundle，请安装 UnityPy: pip install UnityPy"
        )

    if not bundle_path.is_file():
        raise FileNotFoundError(f"找不到 bundle: {bundle_path}")

    env = UnityPy.load(str(bundle_path))
    levels: dict[str, list[float]] = {}
    for obj in env.objects:
        # 只读 TextAsset；跳过 AssetBundle 容器等
        type_name = getattr(obj.type, "name", None) or str(obj.type)
        if type_name != "TextAsset":
            continue
        data = obj.read()
        name = getattr(data, "m_Name", None) or getattr(data, "name", None) or ""
        if not name:
            continue

        script = getattr(data, "m_Script", None)
        if script is None:
            script = getattr(data, "script", None)
        if script is None:
            continue

        if isinstance(script, bytes):
            text = script.decode("utf-8", errors="replace")
        else:
            text = str(script)

        times = parse_times_text(text)
        if times:
            levels[name] = times

    return dict(sorted(levels.items(), key=lambda kv: kv[0].lower()))


def load_times_from_txt_dir(directory: Path) -> dict[str, list[float]]:
    """从目录加载 *.txt，文件名（无后缀）= 关卡名。"""
    if not directory.is_dir():
        return {}
    out: dict[str, list[float]] = {}
    for path in sorted(directory.glob("*.txt")):
        if path.name.upper() == "README.TXT":
            continue
        name = path.stem
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8-sig")
        times = parse_times_text(text)
        if times:
            out[name] = times
    return out


def merge_levels(
    official: dict[str, list[float]],
    override: dict[str, list[float]],
) -> tuple[dict[str, list[float]], dict[str, str]]:
    """
    覆盖合并：override 同名关卡整表替换。
    返回 (merged, sources) sources[name] = 'official' | 'override'
    """
    merged = dict(official)
    sources = {k: "official" for k in official}
    for name, times in override.items():
        merged[name] = list(times)
        sources[name] = "override"
    return (
        dict(sorted(merged.items(), key=lambda kv: kv[0].lower())),
        sources,
    )


# 最近一次 load_or_build_cache 的数据来源：official | guide | override
LAST_LEVEL_SOURCES: dict[str, str] = {}


def load_or_build_cache(
    bundle_path: Path | None = None,
    force: bool = False,
    apply_override: bool = True,
    use_scene_guide: bool = True,
    force_scene_guide: bool = False,
    *,
    quiet: bool = False,
    update_sources: bool = True,
) -> dict[str, list[float]]:
    """
    加载点击表，优先级：
      level_overrides.json / tables/*.txt > 场景引导 HintTap > LevelClickTimes

    quiet: 不打印进度
    update_sources: 是否写入全局 LAST_LEVEL_SOURCES
    """
    bundle_path = bundle_path or DEFAULT_BUNDLE
    official = _load_official(bundle_path, force=force)
    sources: dict[str, str] = {k: "official" for k in official}
    base = dict(official)

    if use_scene_guide:
        try:
            from .scene_guide import (
                load_or_build_scene_guide_cache,
                prefer_guide_times,
            )

            guide_cache = ROOT_DIR / "level_scene_guide_cache.json"
            guide = load_or_build_scene_guide_cache(
                force=force or force_scene_guide,
                progress=(
                    not quiet
                    and (
                        force
                        or force_scene_guide
                        or not guide_cache.is_file()
                    )
                ),
            )
            n_guide = 0
            n_richer = 0
            for name, otimes in list(base.items()):
                gtimes = guide.get(name)
                chosen, src = prefer_guide_times(otimes, gtimes)
                if src == "guide":
                    n_guide += 1
                    if gtimes and (
                        len(gtimes) > len(otimes)
                        or (gtimes and otimes and gtimes[-1] > otimes[-1] + 0.5)
                    ):
                        n_richer += 1
                base[name] = chosen
                sources[name] = src
            for name, gtimes in guide.items():
                if name not in base and gtimes:
                    base[name] = list(gtimes)
                    sources[name] = "guide"
                    n_guide += 1
            if not quiet:
                print(
                    f"[*] 场景引导 HintTap：采用 {n_guide} 关"
                    f"（其中明显更完整 {n_richer} 关）"
                )
        except Exception as e:
            if not quiet:
                print(f"[!] 场景引导加载失败，回退官方表: {e}")

    if apply_override:
        # JSON 优先，再合并旧 tables/*.txt（同名以 JSON 为准）
        override: dict[str, list[float]] = {}
        txt_ov = load_times_from_txt_dir(TABLES_OVERRIDE_DIR)
        if txt_ov:
            override.update(txt_ov)
        json_ov = load_overrides_json()
        if json_ov:
            override.update(json_ov)
        if override:
            base, ov_sources = merge_levels(base, override)
            for name, src in ov_sources.items():
                if src == "override":
                    sources[name] = "override"
            n_over = sum(1 for v in sources.values() if v == "override")
            if not quiet and n_over:
                print(f"[*] 用户覆盖：{n_over} 关")

    if update_sources:
        LAST_LEVEL_SOURCES.clear()
        LAST_LEVEL_SOURCES.update(sources)
    return dict(sorted(base.items(), key=lambda kv: kv[0].lower()))


def _load_official(bundle_path: Path, force: bool = False) -> dict[str, list[float]]:
    if not force and CACHE_PATH.is_file():
        try:
            need_rebuild = False
            if bundle_path.is_file():
                try:
                    import UnityPy
                    if CACHE_PATH.stat().st_mtime < bundle_path.stat().st_mtime:
                        need_rebuild = True
                except ImportError:
                    pass
            
            if not need_rebuild:
                with CACHE_PATH.open("r", encoding="utf-8") as f:
                    raw = json.load(f)
                # 兼容旧缓存：确保是完整 list
                return {k: [float(x) for x in v] for k, v in raw.items()}
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    print(f"[*] 解析 bundle: {bundle_path}")
    levels = load_times_from_bundle(bundle_path)
    with CACHE_PATH.open("w", encoding="utf-8") as f:
        # 不缩写、不截断
        json.dump(levels, f, indent=2, ensure_ascii=False)
    print(f"[*] 缓存 {len(levels)} 关 -> {CACHE_PATH.name}")
    return levels


def export_official_tables(
    levels: dict[str, list[float]] | None = None,
    out_dir: Path | None = None,
    bundle_path: Path | None = None,
) -> Path:
    """导出每关完整点击表到 txt，便于核对「有没有被截断」。"""
    out_dir = out_dir or TABLES_OFFICIAL_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    if levels is None:
        levels = _load_official(bundle_path or DEFAULT_BUNDLE, force=True)

    stats_lines = [
        "# level,count,first,last,source",
    ]
    for name, times in levels.items():
        path = out_dir / f"{name}.txt"
        body = "\n".join(_fmt_time(t) for t in times)
        # 始终换行结尾，与官方一致
        path.write_text(body + "\n", encoding="utf-8")
        stats_lines.append(
            f"{name},{len(times)},{times[0]:.6f},{times[-1]:.6f},official"
        )

    (out_dir / "_stats.csv").write_text("\n".join(stats_lines) + "\n", encoding="utf-8")
    (out_dir / "README.txt").write_text(
        "官方 LevelClickTimes 完整导出（脚本无条数上限）。\n"
        "若要改某一关：复制到 ../tables/同名.txt 后重启工具，将整关覆盖官方表。\n"
        "格式：每行一个秒数（从关卡时间轴 0 起的绝对时间）。\n",
        encoding="utf-8",
    )
    return out_dir


def _fmt_time(t: float) -> str:
    # 保留足够精度，去掉多余 0
    s = f"{t:.6f}".rstrip("0").rstrip(".")
    return s if s else "0"


def verify_tables(
    bundle_path: Path | None = None,
) -> list[str]:
    """核对 bundle / cache / 导出 条数是否一致。返回报告行。"""
    bundle_path = bundle_path or DEFAULT_BUNDLE
    fresh = load_times_from_bundle(bundle_path)
    longest = max(fresh.items(), key=lambda kv: len(kv[1]))
    shortest = min(fresh.items(), key=lambda kv: len(kv[1]))
    lines = [
        f"bundle 关卡数: {len(fresh)}",
        f"总点击数: {sum(len(v) for v in fresh.values())}",
        f"最长: {longest[0]} n={len(longest[1])} end={longest[1][-1]:.4f}",
        f"最短: {shortest[0]} n={len(shortest[1])} end={shortest[1][-1]:.4f}",
        "（脚本无条数硬限制；以下为 bundle 原文解析结果）",
        "— 各关 —",
    ]
    for name, times in fresh.items():
        lines.append(
            f"  {name:<22} n={len(times):4d}  "
            f"[{times[0]:.4f} .. {times[-1]:.4f}]"
        )

    if CACHE_PATH.is_file():
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        for name, times in fresh.items():
            c = cache.get(name)
            if c is None:
                lines.append(f"  ! cache 缺: {name}")
            elif len(c) != len(times):
                lines.append(
                    f"  ! cache 条数不一致 {name}: cache={len(c)} bundle={len(times)}"
                )
    return lines


def first_meaningful_index(times: list[float], eps: float = 0.05) -> int:
    for i, t in enumerate(times):
        if t >= eps:
            return i
    return 0


def sanitize_click_times(
    times: list[float],
    *,
    big_rewind_s: float = 1.0,
) -> tuple[list[float], list[str]]:
    """
    清洗官方表异常，返回 (clean, warnings)。

    - 丢掉开头「比下一点还晚」的离群点（如 West 首点 2.75→1.04）
    - 时间大幅回绕（如 Chaos 106→29）时截断后续脏尾，避免整段瞬间连打后提前结束
    - 小幅回绕则跳过该点，保持非递减

    注意：若官方表本身就比歌曲短（如 ThirdAnniversary 表到 125s、音频 160s），
    这里不会凭空补点，只会在警告里说明「表在末点结束」。
    """
    if not times:
        return [], []
    warns: list[str] = []
    i0 = 0
    while i0 < len(times) - 1 and times[i0] > times[i0 + 1] + 1e-9:
        warns.append(
            f"丢弃开头逆序点 #{i0 + 1} t={times[i0]:.4f}（下一点 {times[i0 + 1]:.4f}）"
        )
        i0 += 1

    out: list[float] = [times[i0]]
    for j in range(i0 + 1, len(times)):
        t = times[j]
        prev = out[-1]
        if t + 1e-9 >= prev:
            out.append(t)
            continue
        delta = prev - t
        if delta >= big_rewind_s:
            dropped = len(times) - j
            warns.append(
                f"检测到时间回绕 #{j + 1}: {prev:.4f}→{t:.4f}，"
                f"截断后续 {dropped} 点（避免脏尾提前结束）"
            )
            break
        warns.append(f"跳过小幅回绕点 #{j + 1}: {prev:.4f}→{t:.4f}")
    return out, warns


def build_schedule(
    raw_times: list[float],
    skip_leading_zeros: bool,
    *,
    sanitize: bool = True,
) -> tuple[list[float], list[str]]:
    """
    构建实际调度表。
    返回 (schedule, warnings)。
    只会去掉开头占位 0 / 脏点 / 回绕尾，绝不因条数上限截断。
    """
    warns: list[str] = []
    if not raw_times:
        return [], ["无点击数据"]

    times = list(raw_times)
    if skip_leading_zeros:
        i0 = first_meaningful_index(times)
        if i0 > 0:
            warns.append(f"跳过开头占位 {i0} 点（t≈0）")
            times = times[i0:]

    if sanitize:
        times, w2 = sanitize_click_times(times)
        warns.extend(w2)

    return times, warns


def diagnose_level_table(
    name: str,
    times: list[float],
    *,
    check_audio: bool = True,
) -> list[str]:
    """生成关卡表质量提示（表是否回绕、是否明显短于音频等）。"""
    notes: list[str] = []
    if not times:
        return ["空表"]
    notes.append(f"n={len(times)} 首点={times[0]:.3f}s 末点={times[-1]:.3f}s")
    rew = sum(1 for i in range(1, len(times)) if times[i] + 1e-9 < times[i - 1])
    if rew:
        notes.append(f"原始表含 {rew} 处时间回绕（调度前会清洗）")
    if check_audio:
        audio_s = try_audio_length_seconds(name)
        if audio_s is not None and audio_s > 5:
            missing = audio_s - times[-1]
            if missing > 8.0:
                notes.append(
                    f"⚠ 官方表末点 {times[-1]:.1f}s，音频约 {audio_s:.1f}s，"
                    f"后半约缺 {missing:.0f}s 点击数据（非脚本截断；需 tables/ 补全）"
                )
            elif times[-1] > audio_s + 5:
                notes.append(
                    f"表末点 {times[-1]:.1f}s 晚于音频约 {audio_s:.1f}s（可能含尾奏后点）"
                )
    return notes


def try_audio_length_seconds(level_name: str) -> float | None:
    """
    尝试从 sounds_assets_level*.bundle 读 AudioClip 时长。
    仅部分关有独立音频包；失败返回 None。
    """
    if not SOUNDS_DIR.is_dir():
        return None
    key = level_name.lower().replace(" ", "").replace("_", "")
    # 常见命名：levelthirdanniversary / levelplains_remix
    candidates = [
        SOUNDS_DIR / f"sounds_assets_level{level_name.lower()}.bundle",
        SOUNDS_DIR / f"sounds_assets_level{key}.bundle",
    ]
    # plains remix 等
    if "remix" in key:
        candidates.append(
            SOUNDS_DIR / f"sounds_assets_level{key.replace('remix', '_remix')}.bundle"
        )
    for path in candidates:
        if not path.is_file():
            continue
        try:
            import UnityPy

            env = UnityPy.load(str(path))
            for obj in env.objects:
                tn = getattr(obj.type, "name", None) or str(obj.type)
                if tn != "AudioClip":
                    continue
                data = obj.read()
                length = getattr(data, "m_Length", None)
                if length is None:
                    length = getattr(data, "length", None)
                if length is not None and float(length) > 1.0:
                    return float(length)
        except Exception:
            continue
    # 模糊：文件名包含关卡名
    try:
        for path in SOUNDS_DIR.glob("sounds_assets_level*.bundle"):
            stem = path.stem.lower().replace("sounds_assets_level", "").replace("_", "")
            if key in stem or stem in key:
                try:
                    import UnityPy

                    env = UnityPy.load(str(path))
                    for obj in env.objects:
                        tn = getattr(obj.type, "name", None) or str(obj.type)
                        if tn != "AudioClip":
                            continue
                        data = obj.read()
                        length = getattr(data, "m_Length", None) or getattr(
                            data, "length", None
                        )
                        if length is not None and float(length) > 1.0:
                            return float(length)
                except Exception:
                    continue
    except Exception:
        pass
    return None


def load_level_latencies() -> dict[str, float]:
    """每关 latency 覆盖（ms）。"""
    if not LEVEL_LATENCY_PATH.is_file():
        return {}
    try:
        with LEVEL_LATENCY_PATH.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        return {str(k): float(v) for k, v in raw.items()}
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}


def save_level_latency(level: str, latency_ms: float) -> None:
    data = load_level_latencies()
    data[level] = float(latency_ms)
    with LEVEL_LATENCY_PATH.open("w", encoding="utf-8") as f:
        json.dump(dict(sorted(data.items())), f, indent=2, ensure_ascii=False)


def clear_level_latency(level: str) -> None:
    data = load_level_latencies()
    if level in data:
        del data[level]
        with LEVEL_LATENCY_PATH.open("w", encoding="utf-8") as f:
            json.dump(dict(sorted(data.items())), f, indent=2, ensure_ascii=False)


def resolve_level_name(levels: dict[str, list[float]], query: str) -> str | None:
    """解析关卡名：英文键 / 中文名 / 别名 / 唯一子串。"""
    from .level_names import resolve_level_key

    return resolve_level_key(levels, query)


def ensure_override_dir() -> Path:
    """兼容旧 tables/ 目录。"""
    TABLES_OVERRIDE_DIR.mkdir(parents=True, exist_ok=True)
    return TABLES_OVERRIDE_DIR


def load_overrides_json() -> dict[str, list[float]]:
    """读取 level_overrides.json。"""
    if not OVERRIDES_JSON.is_file():
        return {}
    try:
        with OVERRIDES_JSON.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return {}
        out: dict[str, list[float]] = {}
        for k, v in raw.items():
            if isinstance(v, list):
                out[str(k)] = [float(x) for x in v]
        return out
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}


def save_overrides_json(data: dict[str, list[float]]) -> Path:
    """整文件写回 level_overrides.json。"""
    cleaned = {
        name: [max(0.0, float(t)) for t in sorted(times) if t == t]
        for name, times in sorted(data.items(), key=lambda kv: kv[0].lower())
    }
    with OVERRIDES_JSON.open("w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=2, ensure_ascii=False)
    return OVERRIDES_JSON


def load_override_table(level: str) -> list[float] | None:
    """某关覆盖表：JSON 优先，其次 tables/*.txt。"""
    data = load_overrides_json()
    if level in data and data[level]:
        return list(data[level])
    path = TABLES_OVERRIDE_DIR / f"{level.strip()}.txt"
    if path.is_file():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8-sig")
        times = parse_times_text(text)
        return times if times else None
    return None


def save_override_table(level: str, times: list[float]) -> Path:
    """
    将完整点击表写入 level_overrides.json（合并更新该关）。
    """
    data = load_overrides_json()
    cleaned = sorted(float(t) for t in times if t == t)
    cleaned = [max(0.0, t) for t in cleaned]
    data[level.strip()] = cleaned
    return save_overrides_json(data)


def delete_override_table(level: str) -> bool:
    """从 JSON（及旧 txt）删除该关覆盖。"""
    removed = False
    data = load_overrides_json()
    name = level.strip()
    if name in data:
        del data[name]
        save_overrides_json(data)
        removed = True
    path = TABLES_OVERRIDE_DIR / f"{name}.txt"
    if path.is_file():
        path.unlink()
        removed = True
    return removed


def has_override_table(level: str) -> bool:
    name = level.strip()
    data = load_overrides_json()
    if name in data:
        return True
    return (TABLES_OVERRIDE_DIR / f"{name}.txt").is_file()

"""
从关卡场景 bundle 提取游戏内「引导点击」时间。

权威来源不是 preload 的 LevelClickTimes 文本表，而是场景里
HintTapField 组件（字段 triggerTime + triggerTapDistance / GoodTapSprite）。

多数关两者一致；部分关（ThirdAnniversary / Pirates / Chaos 等）
场景引导更长、顺序更正确。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .paths import GAME_DIR, ROOT_DIR

SCENE_GUIDE_CACHE = ROOT_DIR / "level_scene_guide_cache.json"
SCENES_DIR = (
    GAME_DIR
    / "Dancing Line_Data"
    / "StreamingAssets"
    / "aa"
    / "StandaloneWindows64"
)

# LevelClickTimes 关卡名 → 场景 bundle 文件名（不含路径）
# 未列出的会做模糊匹配
LEVEL_SCENE_BUNDLE: dict[str, str] = {
    "Africa": "scenes_scenes_levelafrica.bundle",
    "AllAboutUs": "scenes_scenes_levelallaboutus.bundle",
    "Alley": "scenes_scenes_levelalley.bundle",
    "Autumn": "scenes_scenes_levelautumnb.bundle",
    "Basketball": "scenes_scenes_levelbasketball.bundle",
    "Beginning": "scenes_scenes_levelbeginning.bundle",
    "Cathedral": "scenes_scenes_levelcathedral_b.bundle",
    "Chaos": "scenes_scenes_levelchaos.bundle",
    "China": "scenes_scenes_levelchinab.bundle",
    "Christmas": "scenes_scenes_levelchristmas.bundle",
    "ChristmasEve": "scenes_scenes_levelchristmaseve.bundle",
    "Comegetit": "scenes_scenes_levelcomegetit.bundle",
    "Crystal": "scenes_scenes_levelcrystals.bundle",
    "Desert": "scenes_scenes_leveldesert.bundle",
    "Dragon": "scenes_scenes_leveldragon.bundle",
    "Duck": "scenes_scenes_levelduck.bundle",
    "EarthDay": "scenes_scenes_levelearthdayb.bundle",
    "EarthDayRemix": "scenes_scenes_levelearthdayremix.bundle",
    "Easter": "scenes_scenes_leveleaster.bundle",
    "EpicCathedral": "scenes_scenes_levelepiccathedral.bundle",
    "Fantasy": "scenes_scenes_levelfantasy.bundle",
    "Football": "scenes_scenes_levelfootball.bundle",
    "HalloweenRemix": "scenes_scenes_levelhalloweenremix.bundle",
    "Haloween": "scenes_scenes_levelhaloween.bundle",
    "Heaven": "scenes_scenes_levelheaven.bundle",
    "Heaven_color": "scenes_scenes_levelheaven_color.bundle",
    "HipHop": "scenes_scenes_levelhiphop.bundle",
    "LoveStory": "scenes_scenes_levellovestory.bundle",
    "Maze": "scenes_scenes_levelmaze.bundle",
    "Mountains": "scenes_scenes_levelmountainsb.bundle",
    "Mystery": "scenes_scenes_levelmystery.bundle",
    "Ocean": "scenes_scenes_levelocean.bundle",
    "Park": "scenes_scenes_levelpark.bundle",
    "Piano": "scenes_scenes_levelpiano.bundle",
    "PianoRemix": "scenes_scenes_levelpianoremixb.bundle",
    "Pirates": "scenes_scenes_levelpirates.bundle",
    "Plains": "scenes_scenes_levelplains.bundle",
    "PlainsRemix": "scenes_scenes_levelplains_remix.bundle",
    "Race": "scenes_scenes_levelrace.bundle",
    "Samurai": "scenes_scenes_levelsamurai.bundle",
    "Spring": "scenes-internal_scenes_levelspring.bundle",
    "SpringAwake": "scenes-internal_scenes_levelspringawake.bundle",
    "SpringFestival": "scenes_scenes_levelspringfestival.bundle",
    "Storm": "scenes_scenes_levelstorm.bundle",
    "StormRemix": "scenes_scenes_levelstormremix.bundle",
    "Taurus": "scenes_scenes_leveltaurus.bundle",
    "TheEnd": "scenes_scenes_leveltheend.bundle",
    "TheExodus": "scenes_scenes_leveltheexodus.bundle",
    "TheJournay": "scenes_scenes_levelthejournay.bundle",
    "TheSpace": "scenes_scenes_levelthespace.bundle",
    "TheWar": "scenes_scenes_levelthewar.bundle",
    "TheWizardOfOz": "scenes_scenes_levelthewizardofoz.bundle",
    "ThirdAnniversary": "scenes_scenes_levelthirdanniversary.bundle",
    "Valentines": "scenes_scenes_levelvalentines.bundle",
    "VideoGame": "scenes_scenes_levelvideogame.bundle",
    "West": "scenes_scenes_levelwest.bundle",
    "WinterHouseRemix": "scenes_scenes_levelwinter_remix.bundle",
    # Seasons / ComingSoon 可能无独立场景或命名特殊
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def resolve_scene_bundle(level_name: str) -> Path | None:
    if not SCENES_DIR.is_dir():
        return None
    mapped = LEVEL_SCENE_BUNDLE.get(level_name)
    if mapped:
        p = SCENES_DIR / mapped
        if p.is_file():
            return p
    key = _norm(level_name)
    best: Path | None = None
    best_score = 0
    for p in SCENES_DIR.glob("scenes*.bundle"):
        m = re.search(r"level([a-z0-9_]+)\.bundle$", p.name.lower())
        if not m:
            continue
        bn = _norm(m.group(1))
        score = 0
        if bn == key:
            score = 100
        elif bn.rstrip("b") == key or key.rstrip("b") == bn:
            score = 90
        elif key in bn:
            score = 50 + len(key)
        elif bn in key and len(bn) >= 5:
            score = 40 + len(bn)
        if score > best_score:
            best_score = score
            best = p
    return best if best_score >= 40 else None


def extract_hint_tap_times(scene_path: Path) -> list[float]:
    """
    读取场景中 HintTapField 风格组件的 triggerTime。
    判定：含 triggerTime，且含 triggerTapDistance 或 triggerGreatDevTime
    （对应 GoodTapSprite / NormalTapSprite 引导点）。
    """
    try:
        import UnityPy
    except ImportError:
        return []

    env = UnityPy.load(str(scene_path))
    times: list[float] = []
    for obj in env.objects:
        type_name = getattr(obj.type, "name", None) or str(obj.type)
        if type_name != "MonoBehaviour":
            continue
        try:
            tree = obj.read_typetree()
        except Exception:
            continue
        if not tree or "triggerTime" not in tree:
            continue
        if "triggerTapDistance" not in tree and "triggerGreatDevTime" not in tree:
            continue
        # 禁用的不采
        if tree.get("m_Enabled", 1) in (0, False):
            continue
        try:
            times.append(float(tree["triggerTime"]))
        except (TypeError, ValueError):
            continue
    times.sort()
    return times


def load_or_build_scene_guide_cache(
    force: bool = False,
    progress: bool | None = None,
) -> dict[str, list[float]]:
    """
    扫描各关场景，缓存引导点击表。
    progress 默认 True（打印进度）。
    """
    if progress is None:
        progress = True

    if not force and SCENE_GUIDE_CACHE.is_file():
        try:
            with SCENE_GUIDE_CACHE.open("r", encoding="utf-8") as f:
                raw = json.load(f)
            return {k: [float(x) for x in v] for k, v in raw.items()}
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    if not SCENES_DIR.is_dir():
        if progress:
            print(f"[!] 找不到场景目录: {SCENES_DIR}")
        return {}

    names = sorted(LEVEL_SCENE_BUNDLE.keys())
    out: dict[str, list[float]] = {}
    if progress:
        print(f"[*] 从场景提取引导点击（HintTapField/triggerTime），共 {len(names)} 关…")

    for i, name in enumerate(names, 1):
        path = resolve_scene_bundle(name)
        if not path:
            if progress:
                print(f"  [{i}/{len(names)}] {name}: 无场景 bundle")
            continue
        try:
            times = extract_hint_tap_times(path)
        except Exception as e:
            if progress:
                print(f"  [{i}/{len(names)}] {name}: 失败 {e}")
            continue
        if times:
            out[name] = times
            if progress:
                print(
                    f"  [{i}/{len(names)}] {name}: n={len(times)} "
                    f"[{times[0]:.3f} .. {times[-1]:.3f}] <- {path.name}"
                )
        elif progress:
            print(f"  [{i}/{len(names)}] {name}: 0 点 <- {path.name}")

    with SCENE_GUIDE_CACHE.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    if progress:
        print(f"[*] 场景引导缓存 {len(out)} 关 -> {SCENE_GUIDE_CACHE.name}")
    return out


def compare_guide_vs_official(
    official: dict[str, list[float]],
    guide: dict[str, list[float]],
) -> list[str]:
    """生成对比报告行。"""
    lines = [
        "level,official_n,official_end,guide_n,guide_end,delta_n,delta_end_s,note",
    ]
    for name in sorted(set(official) | set(guide)):
        o = official.get(name) or []
        g = guide.get(name) or []
        if not o and not g:
            continue
        if not g:
            note = "no_scene_guide"
        elif not o:
            note = "guide_only"
        elif len(g) > len(o) + 5 or (g and o and g[-1] - o[-1] > 2):
            note = "guide_richer"
        elif len(o) > len(g) + 5 or (g and o and o[-1] - g[-1] > 2):
            note = "official_richer"
        else:
            note = "similar"
        lines.append(
            f"{name},{len(o)},{o[-1] if o else ''},"
            f"{len(g)},{g[-1] if g else ''},"
            f"{len(g) - len(o)},{(g[-1] - o[-1]) if (g and o) else ''},{note}"
        )
    return lines


def prefer_guide_times(
    official: list[float],
    guide: list[float] | None,
    *,
    prefer_longer: bool = True,
) -> tuple[list[float], str]:
    """
    选择更权威的时间表。
    默认：场景引导存在且（点数更多或末点更晚）时用引导，否则官方。
    返回 (times, source) source in official|guide|guide_fallback_official
    """
    if not guide:
        return list(official), "official"
    if not official:
        return list(guide), "guide"
    if not prefer_longer:
        return list(guide), "guide"
    # Chaos 类：点数相同但末点因官方回绕而假短 → 用引导
    if len(guide) >= len(official) and guide[-1] >= official[-1] - 0.05:
        # 若引导明显更长，或点数更多
        if len(guide) > len(official) or guide[-1] > official[-1] + 0.5:
            return list(guide), "guide"
        # 点数相同末点相近：引导通常顺序正确（无脏尾），优先引导
        return list(guide), "guide"
    if guide[-1] > official[-1] + 1.0 or len(guide) > len(official) + 3:
        return list(guide), "guide"
    # 官方更长时保留官方
    if official[-1] > guide[-1] + 1.0 or len(official) > len(guide) + 3:
        return list(official), "official"
    # 默认场景引导（游戏内实际用的 HintTap）
    return list(guide), "guide"

from __future__ import annotations

from pathlib import Path

import sys

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT_DIR = PACKAGE_DIR.parent  # click_assist/
GAME_DIR = ROOT_DIR.parent  # Dancing Line/

# 寻找同目录下的 preload_assets_levelclicktimes.bundle
def _find_bundle() -> Path:
    # 候选目录列表
    candidates = [
        ROOT_DIR,  # 源码运行时的 click_assist 根目录
        Path.cwd(),  # 当前工作目录
    ]
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后的可执行文件所在目录
        candidates.append(Path(sys.executable).resolve().parent)
    if sys.argv:
        # 入口脚本所在目录
        candidates.append(Path(sys.argv[0]).resolve().parent)
        
    for d in candidates:
        p = d / "preload_assets_levelclicktimes.bundle"
        if p.exists():
            return p
            
    # 默认回退路径
    return (
        GAME_DIR
        / "Dancing Line_Data"
        / "StreamingAssets"
        / "aa"
        / "StandaloneWindows64"
        / "preload_assets_levelclicktimes.bundle"
    )

DEFAULT_BUNDLE = _find_bundle()
CACHE_PATH = ROOT_DIR / "level_click_times_cache.json"
# 每关单独延迟记忆（ms）— 仍可读旧文件，主界面不再强推
LEVEL_LATENCY_PATH = ROOT_DIR / "level_latency.json"
# 段落延迟（不改点击表）：{ "LevelName": { "duration_s": 120, "bands": [...] } }
LEVEL_SEGMENTS_PATH = ROOT_DIR / "level_segment_latency.json"
# 用户编辑后的点击表覆盖（JSON：{ "LevelName": [t0, t1, ...] }）
OVERRIDES_JSON = ROOT_DIR / "level_overrides.json"
# 从 bundle 导出的完整官方表（只读参考 / CLI --export）
TABLES_OFFICIAL_DIR = ROOT_DIR / "tables_official"
# 旧版 txt 覆盖目录（仍兼容加载）
TABLES_OVERRIDE_DIR = ROOT_DIR / "tables"
# 关卡音频（部分关有独立 bundle，可用来对比表是否盖满全曲）
SOUNDS_DIR = (
    GAME_DIR
    / "Dancing Line_Data"
    / "StreamingAssets"
    / "aa"
    / "StandaloneWindows64"
)

from __future__ import annotations

from pathlib import Path

import sys

PACKAGE_DIR = Path(__file__).resolve().parent

if getattr(sys, 'frozen', False):
    ROOT_DIR = Path(sys.executable).resolve().parent
else:
    ROOT_DIR = PACKAGE_DIR.parent  # click_assist/

# 每关单独延迟记忆（ms）— 仍可读旧文件，主界面不再强推
LEVEL_LATENCY_PATH = ROOT_DIR / "level_latency.json"
# 段落延迟（不改点击表）：{ "LevelName": { "duration_s": 120, "bands": [...] } }
LEVEL_SEGMENTS_PATH = ROOT_DIR / "level_segment_latency.json"
# 用户编辑后的点击表覆盖（JSON：{ "LevelName": [t0, t1, ...] }）
OVERRIDES_JSON = ROOT_DIR / "level_overrides.json"
# 软件内置的官方点击表
TABLES_OFFICIAL_DIR = ROOT_DIR / "tables_official"
# 旧版 txt 覆盖目录（仍兼容加载）
TABLES_OVERRIDE_DIR = ROOT_DIR / "tables"

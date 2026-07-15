#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dancing Line 点击辅助 — 入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from dl_assist.data import (  # noqa: E402
    LAST_LEVEL_SOURCES,
    build_schedule,
    ensure_override_dir,
    export_official_tables,
    load_or_build_cache,
    resolve_level_name,
    verify_tables,
)
from dl_assist.level_names import display_name  # noqa: E402
from dl_assist.data import _load_official  # noqa: E402
from dl_assist.engine import timer_period  # noqa: E402
from dl_assist.gui import AssistApp  # noqa: E402
from dl_assist.paths import DEFAULT_BUNDLE  # noqa: E402
from dl_assist.scene_guide import (  # noqa: E402
    compare_guide_vs_official,
    load_or_build_scene_guide_cache,
)
from dl_assist.theme import APP_QSS  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="DL Click Assist")
    p.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    p.add_argument("--level", "-l", default="Beginning")
    p.add_argument(
        "--latency",
        type=float,
        default=0.0,
        help="整体延迟 ms：正数=更晚，负数=更早",
    )
    p.add_argument(
        "--enter-t0-delay",
        type=float,
        default=None,
        help="Enter→游戏 t0 补偿 ms（默认 16）",
    )
    p.add_argument("--refresh-cache", action="store_true")
    p.add_argument("--refresh-scene-guide", action="store_true")
    p.add_argument(
        "--no-scene-guide",
        action="store_true",
        help="仅用 LevelClickTimes 官方文本",
    )
    p.add_argument("--list", action="store_true")
    p.add_argument("--export", action="store_true", help="导出官方表到 tables_official/")
    p.add_argument("--compare-guide", action="store_true")
    p.add_argument("--verify", action="store_true")
    p.add_argument("--edit-notes", action="store_true", help="仅打开表编辑器")
    args = p.parse_args(argv)

    if args.verify:
        for line in verify_tables(args.bundle):
            print(line)
        return 0

    if args.compare_guide:
        try:
            official = _load_official(args.bundle, force=args.refresh_cache)
            guide = load_or_build_scene_guide_cache(
                force=args.refresh_scene_guide or args.refresh_cache
            )
            lines = list(compare_guide_vs_official(official, guide))
            for line in lines:
                print(line)
            richer = sum(1 for ln in lines if "guide_richer" in ln)
            print(f"# guide_richer levels: {richer}")
        except Exception as e:
            print(f"[!] 对比失败: {e}")
            return 1
        return 0

    if args.export:
        try:
            out = export_official_tables(bundle_path=args.bundle)
            ensure_override_dir()
            print(f"[*] 已导出 -> {out}")
        except Exception as e:
            print(f"[!] 导出失败: {e}")
            return 1
        return 0

    try:
        levels = load_or_build_cache(
            args.bundle,
            force=args.refresh_cache,
            use_scene_guide=not args.no_scene_guide,
            force_scene_guide=args.refresh_scene_guide,
        )
        ensure_override_dir()
    except Exception as e:
        print(f"[!] 加载失败: {e}")
        return 1

    if args.list:
        for i, (n, t) in enumerate(levels.items(), 1):
            s, warns = build_schedule(t, skip_leading_zeros=True)
            src = LAST_LEVEL_SOURCES.get(n, "?")
            flag = " ⚠" if warns else ""
            label = display_name(n)
            if s:
                print(
                    f"{i:3d} {label:<28}  key={n:<20} n={len(s):4d} "
                    f"{s[0]:.3f}→{s[-1]:.3f} src={src}{flag}"
                )
            else:
                print(f"{i:3d} {label:<28}  key={n:<20} n=0 src={src}{flag}")
        print(f"合计 {sum(len(t) for t in levels.values())} 点 / {len(levels)} 关")
        return 0

    level = resolve_level_name(levels, args.level) or next(iter(levels))
    base_levels = _snapshot_base(
        args.bundle,
        use_scene_guide=not args.no_scene_guide,
        current=levels,
    )

    if args.edit_notes:
        return _run_editor_only(levels, level, base_levels)

    timer_period(True)
    try:
        qt_app = QApplication.instance() or QApplication(sys.argv)
        qt_app.setStyle("Fusion")
        qt_app.setStyleSheet(APP_QSS)

        app = AssistApp(
            levels=levels,
            level=level,
            latency=args.latency,
            base_levels=base_levels,
        )
        if args.enter_t0_delay is not None:
            app.engine.set_enter_t0_delay(args.enter_t0_delay)
        app.show()
        return qt_app.exec()
    finally:
        timer_period(False)


def _snapshot_base(
    bundle,
    *,
    use_scene_guide: bool,
    current: dict[str, list[float]],
) -> dict[str, list[float]]:
    try:
        base = load_or_build_cache(
            bundle,
            force=False,
            apply_override=False,
            use_scene_guide=use_scene_guide,
            force_scene_guide=False,
            quiet=True,
            update_sources=False,
        )
        return {k: list(v) for k, v in base.items()}
    except Exception:
        return {k: list(v) for k, v in current.items()}


def _run_editor_only(
    levels: dict[str, list[float]],
    level: str,
    base_levels: dict[str, list[float]],
) -> int:
    from dl_assist.note_editor import NoteEditorDialog

    qt_app = QApplication.instance() or QApplication(sys.argv)
    qt_app.setStyle("Fusion")
    qt_app.setStyleSheet(APP_QSS)
    dlg = NoteEditorDialog(levels, level, base_levels=base_levels)
    dlg.show()
    return qt_app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

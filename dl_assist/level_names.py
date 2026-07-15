"""关卡内部键（LevelClickTimes / 文件名）↔ 中文显示名。

内部逻辑、JSON 覆盖、官方表一律使用英文键；
界面下拉框显示「中文 · EnglishKey」，便于对照游戏内名称。
"""

from __future__ import annotations

# 与 preload LevelClickTimes / tables_official 文件名一一对应。
# 中文名按国服/社区常用译名；个别键本身有历史拼写（Haloween、TheJournay）。
LEVEL_ZH: dict[str, str] = {
    "Africa": "非洲",
    "AllAboutUs": "关于我们",
    "Alley": "小巷",
    "Autumn": "秋天",
    "Basketball": "篮球",
    "Beginning": "启程",
    "Cathedral": "大教堂",
    "Chaos": "混沌",
    "China": "中国",
    "Christmas": "圣诞节",
    "ChristmasEve": "平安夜",
    "Comegetit": "来吧",
    "ComingSoon": "即将推出",
    "Crystal": "水晶",
    "Desert": "沙漠",
    "Dragon": "龙",
    "Duck": "小黄鸭",
    "EarthDay": "地球日",
    "EarthDayRemix": "地球日·混音",
    "Easter": "复活节",
    "EpicCathedral": "史诗大教堂",
    "Fantasy": "奇幻",
    "Football": "足球",
    "HalloweenRemix": "万圣节·混音",
    "Haloween": "万圣节",
    "Heaven": "天堂",
    "Heaven_color": "天堂·彩色",
    "HipHop": "嘻哈",
    "LoveStory": "爱情故事",
    "Maze": "迷宫",
    "Mountains": "山脉",
    "Mystery": "神秘",
    "Ocean": "海洋",
    "Park": "公园",
    "Piano": "钢琴",
    "PianoRemix": "钢琴·混音",
    "Pirates": "海盗",
    "Plains": "平原",
    "PlainsRemix": "平原·混音",
    "Race": "竞速",
    "Samurai": "武士",
    "Seasons": "四季",
    "Spring": "春天",
    "SpringAwake": "春醒",
    "SpringFestival": "新春",
    "Storm": "风暴",
    "StormRemix": "风暴·混音",
    "Taurus": "金牛座",
    "TheEnd": "终点",
    "TheExodus": "出埃及记",
    "TheJournay": "旅途",
    "TheSpace": "太空",
    "TheWar": "战争",
    "TheWizardOfOz": "绿野仙踪",
    "ThirdAnniversary": "三周年",
    "Valentines": "情人节",
    "VideoGame": "电子游戏",
    "West": "西部",
    "WinterHouseRemix": "冬日小屋·混音",
}

# 中文 → 英文键（同名唯一）
_ZH_TO_KEY: dict[str, str] = {zh: key for key, zh in LEVEL_ZH.items()}

# 常见别名 / 简称 → 英文键
_ALIASES: dict[str, str] = {
    "开始": "Beginning",
    "起点": "Beginning",
    "出埃及": "TheExodus",
    "绿野": "TheWizardOfOz",
    "仙踪": "TheWizardOfOz",
    "周年": "ThirdAnniversary",
    "三周年庆": "ThirdAnniversary",
    "春节": "SpringFestival",
    "春节点": "SpringFestival",
    "旅程": "TheJournay",
    "journey": "TheJournay",
    "halloween": "Haloween",
    "冬日小屋": "WinterHouseRemix",
    "冬日": "WinterHouseRemix",
    "彩色天堂": "Heaven_color",
    "史诗教堂": "EpicCathedral",
    "地球日remix": "EarthDayRemix",
    "钢琴remix": "PianoRemix",
    "平原remix": "PlainsRemix",
    "风暴remix": "StormRemix",
    "万圣节remix": "HalloweenRemix",
}


def zh_name(level_key: str) -> str:
    """英文键 → 中文；未知键原样返回。"""
    return LEVEL_ZH.get(level_key, level_key)


def display_name(level_key: str) -> str:
    """下拉框展示：有中文则「中文 · Key」，否则仅 Key。"""
    zh = LEVEL_ZH.get(level_key)
    if zh and zh != level_key:
        return f"{zh} · {level_key}"
    return level_key


def key_from_display(text: str) -> str:
    """
    从展示文本或任意输入还原英文键。
    支持「中文 · Key」、纯中文、纯英文。
    """
    if not text:
        return ""
    s = text.strip()
    if " · " in s:
        # 取最后一段英文键（中文里一般不含该分隔）
        right = s.rsplit(" · ", 1)[-1].strip()
        if right:
            return right
    if s in LEVEL_ZH:
        return s
    if s in _ZH_TO_KEY:
        return _ZH_TO_KEY[s]
    low = s.lower()
    if low in _ALIASES:
        return _ALIASES[low]
    if s in _ALIASES:
        return _ALIASES[s]
    return s


def resolve_level_key(levels: dict | list | set, query: str) -> str | None:
    """
    在 levels（键集合或 dict）中解析 query → 英文关卡键。
    匹配顺序：精确键 → 中文/别名 → 忽略大小写 → 唯一子串。
    """
    if not query:
        return None
    keys = list(levels.keys()) if isinstance(levels, dict) else list(levels)
    if not keys:
        return None
    keyset = set(keys)

    q = query.strip()
    if q in keyset:
        return q

    # 展示串 / 中文 / 别名
    cand = key_from_display(q)
    if cand in keyset:
        return cand
    if cand in LEVEL_ZH and LEVEL_ZH[cand] and cand in keyset:
        return cand
    # 纯中文写在 LEVEL_ZH values
    if q in _ZH_TO_KEY and _ZH_TO_KEY[q] in keyset:
        return _ZH_TO_KEY[q]
    low = q.lower()
    if low in _ALIASES and _ALIASES[low] in keyset:
        return _ALIASES[low]

    lower_map = {k.lower(): k for k in keys}
    if low in lower_map:
        return lower_map[low]
    if cand.lower() in lower_map:
        return lower_map[cand.lower()]

    # 中文子串唯一命中
    zh_hits = [k for k, zh in LEVEL_ZH.items() if k in keyset and q in zh]
    if len(zh_hits) == 1:
        return zh_hits[0]

    hits = [k for k in keys if low in k.lower()]
    if len(hits) == 1:
        return hits[0]
    # 展示名子串
    hits2 = [
        k
        for k in keys
        if low in display_name(k).lower() or q in zh_name(k)
    ]
    if len(hits2) == 1:
        return hits2[0]
    return None


def fill_level_combo(combo, level_keys: list[str], current: str | None = None) -> None:
    """填充 QComboBox：显示中文，userData=英文键。"""
    combo.blockSignals(True)
    combo.clear()
    keys = list(level_keys)
    for key in keys:
        combo.addItem(display_name(key), key)
    if current and current in keys:
        combo.setCurrentIndex(keys.index(current))
    elif keys:
        combo.setCurrentIndex(0)
    combo.blockSignals(False)


def combo_level_key(combo) -> str:
    """读取关卡下拉当前英文键。"""
    data = combo.currentData()
    if data:
        return str(data)
    return key_from_display(combo.currentText())

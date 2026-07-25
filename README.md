# 跳舞的线 · 点击辅助（DL Click Assist）

使用软件内置的点击时间表，按表自动点击。
GUI（PySide6）支持选关、全局延迟、可视化改表，以及可选的「失败段落延迟」。

> **定位**：学习 / 研究 / 自用辅助，**不是**稳定通关外挂。  
> 点击表本身可能有误差，热键与注入也有抖动——**精度有上限**，本仓库不再追求「必过」。

**许可**：MIT（见 [LICENSE](LICENSE)）

---

## 功能一览

| 功能 | 说明 |
|------|------|
| 自动跟表点击 | Enter 开局 + 按时间轴空格 |
| 中文关卡名 | 下拉显示「中文 · 内部键」，与资源表对齐 |
| 全局延迟 | 整关 ±ms，治整体抢拍/偏晚 |
| 编辑表 | 时间轴拖拽 / 表格改点，写入 `level_overrides.json` |
| 失败微调 | 默认**段落延迟**（不改表）；可撤销 |
| 数据源合并 | 用户覆盖 > 内置官方点击表 |

---

## 环境

- Windows（当前注入与热键按 Win 实现）
- Python 3.10+（建议 3.11+）
- 软件无需读取或解包游戏安装目录

---

## 安装与启动

```powershell
cd path\to\click_assist
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

建议**以管理员身份**运行（全局热键 F8/F6、键鼠注入更稳）。

常用参数：

```powershell
python main.py --level Beginning --latency 12
python main.py --level 启程
python main.py --list
python main.py --verify
python main.py --edit-notes --level 海盗
```

---

## 热键

| 键 | 作用 |
|----|------|
| **F8** | 播放 / 暂停（未开始：Enter 开局并跟表；运行中暂停；暂停后再按继续） |
| **F6** | 重置（停表并回到起点） |
| **F7** | 下一拍及后续点击提前 5ms（可连续按） |
| **F9** | 下一拍及后续点击延迟 5ms（可连续按） |

暂停会冻结当前时间轴位置，方便对照；继续从同一时刻接着打。
F7/F9 会立即修改主界面的全局延迟；即使下一拍正在等待，也会按新值重新计算。

---

## 使用流程

1. 游戏进入关卡**准备界面**（尚未开跑）
2. 本工具选好关卡（中文名或内部键均可认）
3. 需要时调「延迟 ms」：**正数更晚**（治抢拍），**负数更早**
4. **F8** → 自动 Enter 并跟表
5. 中途 **F8** 暂停 / **F6** 重来

计时关系：

```text
deadline = Enter_keydown + enter_t0_delay(≈16ms) + t[i]
         + 全局 latency_ms + 段落 latency(t)
```

- 日志里 `err≈0` 只表示**脚本按计划点火准**；耳朵/画面仍偏，请调延迟或表
- 默认注入：`sendinput_scan` + 空格

---

## 关卡名对照

内部键与 `tables_official/*.txt`、JSON 覆盖的字段名一致。  
界面显示为 **中文 · Key**。完整映射见 `dl_assist/level_names.py`。

| 中文 | 内部键 | 中文 | 内部键 |
|------|--------|------|--------|
| 启程 | Beginning | 沙漠 | Desert |
| 风暴 | Storm | 中国 | China |
| 平原 | Plains | 大教堂 | Cathedral |
| 山脉 | Mountains | 圣诞节 | Christmas |
| 春天 | Spring | 钢琴 | Piano |
| 天堂 | Heaven | 万圣节 | Haloween |
| 海洋 | Ocean | 西部 | West |
| 奇幻 | Fantasy | 篮球 | Basketball |
| 迷宫 | Maze | 终点 | TheEnd |
| 足球 | Football | 旅途 | TheJournay |
| 水晶 | Crystal | 战争 | TheWar |
| 太空 | TheSpace | 竞速 | Race |
| 出埃及记 | TheExodus | 绿野仙踪 | TheWizardOfOz |
| 海盗 | Pirates | 武士 | Samurai |
| 混沌 | Chaos | 三周年 | ThirdAnniversary |
| 关于我们 | AllAboutUs | 地球日 | EarthDay |
| 新春 | SpringFestival | 情人节 | Valentines |
| 爱情故事 | LoveStory | 嘻哈 | HipHop |
| 小黄鸭 | Duck | 龙 | Dragon |
| 非洲 | Africa | 小巷 | Alley |
| 秋天 | Autumn | 平安夜 | ChristmasEve |
| 来吧 | Comegetit | 复活节 | Easter |
| 史诗大教堂 | EpicCathedral | 神秘 | Mystery |
| 公园 | Park | 四季 | Seasons |
| 春醒 | SpringAwake | 金牛座 | Taurus |
| 电子游戏 | VideoGame | 即将推出 | ComingSoon |
| 钢琴·混音 | PianoRemix | 平原·混音 | PlainsRemix |
| 风暴·混音 | StormRemix | 地球日·混音 | EarthDayRemix |
| 万圣节·混音 | HalloweenRemix | 冬日小屋·混音 | WinterHouseRemix |
| 天堂·彩色 | Heaven_color | | |

> 历史拼写保留：`Haloween`（非 Halloween）、`TheJournay`（非 Journey），与游戏资源一致。

CLI 可用中文或键：`--level 启程` / `--level Beginning`。

---

## 数据源优先级

1. **`level_overrides.json`**（编辑器 / 改表微调）及兼容 `tables/*.txt`
2. **`tables_official/*.txt`**（随软件提供的内置点击表）

### 编辑点击表

主界面 **「编辑表」**，或 `python main.py --edit-notes`。

- 时间轴拖拽 / 表格改秒数 / ±ms
- **保存** → `level_overrides.json`，主界面即时生效
- Ctrl+S 保存，Delete 删点，Ctrl+Z 撤销

```json
{
  "Beginning": [0.9323, 1.487, 2.0737]
}
```

表比歌曲短时，只能在编辑器里人工补点（工具不会凭空生成）。

---

## 失败微调（可选）

默认写入 **段落延迟** `level_segment_latency.json`，**不改**点击表：

- 段内等量平移 → 相对间隔不变  
- 段外不动  
- 可「撤销上一条」/「清除本关段落」

也提供「只改失败前 N 拍」「时间窗平移」等改表模式，高频关慎用。

| 现象 | 建议 |
|------|------|
| 整关抢拍 | 全局延迟 **+10～+30** |
| 整关偏晚 | 全局延迟负数，或减小 `--enter-t0-delay` |
| 某一进度老挂 | 失败微调 → 段落延迟，**5～12ms** 小步 |
| 后半没点 | 表偏短 → 编辑表补全 |

---

## 已知上限（请先读）

1. **内置时间表并不完美**
   部分关可能回绕、偏短或与实机判定不一致，并非逐帧真理。

2. **热键与注入有抖动**  
   F8、Enter、空格经系统消息队列，毫秒级误差正常；`err≈0` ≠ 游戏内必准。

3. **进度 % 只是粗对齐**  
   失败界面百分比 ≈ 关卡进度，映射到时间会有偏差。

4. **高频段极难「调一点就过」**  
   点距 50～100ms 时，局部改表很容易拖歪邻拍；段落延迟也只能做相位微调。

**结论**：本工具适合「少动手跟表 / 研究时间数据 / 辅助练习」。  
若目标是稳定全完美，需要更底层的游戏内钩子或重录表——**超出本项目范围，不再继续做**。欢迎社区 fork 改进。

---

## 目录结构

```text
click_assist/
  main.py                      # 入口
  requirements.txt
  LICENSE
  README.md
  dl_assist/
    gui.py                     # 主界面
    engine.py                  # 调度与点击
    data.py                    # 加载内置表 / 用户覆盖
    level_names.py             # 中英关卡名
    note_editor.py             # 表编辑器
    fail_tune.py / segments.py / tune.py
    clicker.py / input_backends.py / hotkeys.py
    ...
  tables_official/             # 软件内置点击表
  tables/                      # 旧版 txt 覆盖（可选）
  level_*.json                 # 运行缓存 / 用户数据（见 .gitignore）
```

用户本地生成、默认不提交：

- `level_overrides.json`
- `level_segment_latency.json`

---

## 注入后端（开发）

默认 `sendinput_scan`。游戏吃不到键时，可在 `AssistApp` 构造参数改 `backend` / `action`。  
可选：`pydirectinput` / `keybd_event` / `win32api` / `sendinput_vk`。

---

## 免责声明

- 仅供学习与研究；使用辅助功能可能违反游戏条款，风险自负。  
- 作者不对任何封号、存档损坏或通关结果负责。  
- 与 *Dancing Line* / 官方开发商无关联。

---

## 贡献

欢迎 PR / Issue：

- 修正 `level_names.py` 中文译名  
- 补全某关 overrides 时间表  
- 补充和校准内置点击表
- 文档与跨版本兼容

请勿提交个人 `level_overrides.json` / 段落延迟等本地调参文件。

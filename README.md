# ClipDraft — AI 自动剪辑 Agent 技能包

> 仓库代号 ClipDraft。把「一堆素材 + 一个想法」变成「一条达芬奇时间线」的 Agent 技能包。

![license](https://img.shields.io/badge/license-MIT-green)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![status](https://img.shields.io/badge/status-v0.1-orange)

**ClipDraft 是一套 AI 自动剪辑 Agent Skill，面向 Codex / Claude 等支持 skills 的 Agent 运行时。**
核心是一个原创的 `SKILL.md` 工作流：Agent 按阶段推进自动剪辑——每阶段先产出、经用户确认、再落盘，
而不是一口气黑箱剪完。素材分析、蓝图校验、时间线构建由配套的 Python 脚本完成，确定性强、可测试。

## 工作流概览

```
阶段 0 环境与素材确认 → 阶段 1 素材盘点与分析（脚本） → 阶段 2 审查结果确认
→ 阶段 3 文案创作（钩子/主体/收尾 + 分镜对应） → 阶段 4 剪辑蓝图 blueprint.json
→ 阶段 5 时间线构建（Resolve 脚本 API / MCP，失败降级只交蓝图）
→ 阶段 6 成片审计（空隙/重复/越界/文案对照） → 阶段 7 补拍建议清单
```

四条关键原则贯穿全程：**原素材只读；每阶段确认后才落盘；不把「测量成功」说成「写入成功」；
结构性修改用新时间线。**

## 安装

```bash
git clone <本仓库地址> clipdraft
cd clipdraft

# 把 skills/ 安装到 Agent 的 skills 目录（默认 Codex 与 Claude 两处都装）
python scripts/install_skills.py

# 只装一处，或装到自定义目录
python scripts/install_skills.py --only codex
python scripts/install_skills.py --target /path/to/skills
```

安装后，在 Agent 里给出素材目录和创作目标即可触发，例如：

```
调用 $autoedit-agent。素材在 D:\Media\launch-event。
做一条 3 分钟的活动纪录片，节奏克制，不要旁白。
```

## 环境要求

- Python 3.10+
- FFmpeg（含 ffprobe），需在 PATH 中 —— 素材分析依赖它
- Pillow（联系表生成）：`pip install Pillow`
- 可选：DaVinci Resolve **Studio** 18.5+ 并开启外部脚本 —— 没有它时，流程会降级为只交付剪辑蓝图与计划动作清单

先自检一遍环境：

```bash
python skills/autoedit-agent/scripts/check_setup.py
```

## 配套脚本（也可单独使用）

```bash
# 阶段 1：素材盘点分析 → inventory.csv / analysis.json / blueprint.json 骨架 / contact_sheet.jpg
python skills/autoedit-agent/scripts/analyze_media.py <素材目录> --out <输出目录>

# 阶段 5：先 dry-run 校验蓝图并打印计划动作，再实跑构建时间线
python skills/autoedit-agent/scripts/build_resolve_timeline.py <blueprint.json> --dry-run
python skills/autoedit-agent/scripts/build_resolve_timeline.py <blueprint.json>
```

蓝图字段规范见 `skills/autoedit-agent/references/blueprint-schema.md`，
完整示例见 `examples/blueprint.example.json`。

## 仓库结构

```
skills/autoedit-agent/
├── SKILL.md                  # 核心工作流（阶段 0–7 与关键原则）
├── references/
│   ├── blueprint-schema.md   # blueprint.json 字段规范
│   └── editing-heuristics.md # 剪辑经验规范（节奏/J-L cut/跳切/字幕/安全区）
└── scripts/
    ├── check_setup.py            # 环境检查
    ├── analyze_media.py          # 素材盘点与分析
    └── build_resolve_timeline.py # 时间线构建（含 --dry-run）
scripts/install_skills.py     # 一键安装技能到 Agent 的 skills 目录
tests/                        # pytest 单元测试（解析 / 蓝图校验 / dry-run）
examples/                     # 示例蓝图
```

## 开发与测试

```bash
python -m venv .venv
.venv/bin/pip install Pillow pytest
.venv/bin/python -m pytest -q
```

## 路线图

- **v0.1**（当前）：SKILL.md 八阶段工作流；素材盘点分析（元数据/黑帧/静音/联系表）；
  蓝图规范与校验；Resolve 脚本 API 建时间线（含 dry-run）；无 Resolve 时降级交付蓝图。
- **v0.2**：时间线构建增强——转场与字幕真正写入 Resolve、J/L-cut 的音频错峰、MCP 路径实装；
  审计阶段脚本化（自动比对时间线与蓝图/文案）。
- **v0.3**：素材打分与智能排序（清晰度/稳定性/构图评分辅助选段）、多平台画幅一键派生
  （16:9 → 9:16 安全区重构图）、补拍清单与素材库联动复检。

## English

ClipDraft is an **AI auto-editing agent skill pack** for skill-capable agents (Codex, Claude, etc.).
An original `SKILL.md` drives an eight-stage workflow — setup check, media inventory & analysis
(ffprobe metadata, black-frame / silence detection, contact sheets), review sign-off, scriptwriting,
an edit blueprint (`blueprint.json`), DaVinci Resolve timeline construction (script API or MCP,
gracefully degrading to blueprint-only delivery), a final audit, and a pickup-shot list.
Every stage is confirmed by the user before anything is written to disk; source media is always read-only.

Install: clone, then run `python scripts/install_skills.py` to copy `skills/` into your agent's
skills directory (`~/.codex/skills` and `~/.claude/skills` by default).

## License

MIT，见 [LICENSE](LICENSE)。Copyright (c) 2026 ClipDraft contributors.

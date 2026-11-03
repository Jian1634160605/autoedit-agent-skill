#!/usr/bin/env python3
"""把本仓库 skills/ 下的技能包安装到 Agent 的 skills 目录。

默认同时装到 Codex 与 Claude 两处默认目录：
    ~/.codex/skills
    ~/.claude/skills
也可以用 --target 指定任意目标目录（可重复传入多个）；
--only codex / --only claude 只装其中一处。
目标中已存在同名技能时默认覆盖更新（先删旧目录再拷贝，避免残留文件）。

用法：
    python scripts/install_skills.py
    python scripts/install_skills.py --only codex
    python scripts/install_skills.py --target /path/to/skills
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_SRC = REPO_ROOT / "skills"

DEFAULT_TARGETS = {
    "codex": Path.home() / ".codex" / "skills",
    "claude": Path.home() / ".claude" / "skills",
}


def install_to(target: Path) -> list[str]:
    """把 skills/ 下每个技能目录拷贝到 target，返回已安装的技能名列表。"""
    if not SKILLS_SRC.is_dir():
        raise FileNotFoundError(f"仓库 skills 目录不存在：{SKILLS_SRC}")
    target.mkdir(parents=True, exist_ok=True)
    installed = []
    for skill_dir in sorted(p for p in SKILLS_SRC.iterdir() if p.is_dir()):
        dest = target / skill_dir.name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(skill_dir, dest)
        installed.append(skill_dir.name)
        print(f"  ✓ {skill_dir.name} → {dest}")
    return installed


def main(argv: list[str] | None = None) -> int:
    """解析参数并逐个目标安装，最后打印汇总。"""
    parser = argparse.ArgumentParser(
        prog="install_skills.py", description="安装 autoedit-agent 技能包到 Agent 的 skills 目录"
    )
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="自定义目标 skills 目录（可重复传入）；给了就不再用默认目录",
    )
    parser.add_argument(
        "--only",
        choices=sorted(DEFAULT_TARGETS),
        default=None,
        help="只安装到某一个默认目录（codex 或 claude）",
    )
    args = parser.parse_args(argv)

    if args.target:
        targets = [Path(t).expanduser() for t in args.target]
    elif args.only:
        targets = [DEFAULT_TARGETS[args.only]]
    else:
        targets = list(DEFAULT_TARGETS.values())

    total = 0
    for target in targets:
        print(f"安装到：{target}")
        try:
            total += len(install_to(target))
        except FileNotFoundError as exc:
            print(f"错误：{exc}", file=sys.stderr)
            return 2
    print(f"完成：共安装 {total} 次技能拷贝（目标 {len(targets)} 处）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

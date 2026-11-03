#!/usr/bin/env python3
"""环境检查脚本（autoedit-agent 技能配套脚本，阶段 0 使用）。

逐项检查：Python 版本、ffmpeg、ffprobe、Pillow、DaVinci Resolve 脚本环境，
打印一份可读报告。核心项（Python / ffmpeg / ffprobe）缺失时退出码为 1；
Resolve 属于可选项，缺失只给警告（阶段 5 会降级为只交付蓝图）。

用法：
    python check_setup.py
"""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

RESOLVE_MODULE_DIRS = [
    "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules",  # macOS
    "/opt/resolve/Developer/Scripting/Modules",  # Linux
    os.path.expandvars(r"%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules"),  # Windows
]


def _tool_version(cmd: list[str]) -> str:
    """跑 `xxx -version` 取首行版本号，失败返回空串。"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        first = (result.stdout or result.stderr or "").splitlines()
        return first[0].strip() if first else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def check_python() -> tuple[bool, str]:
    """检查 Python 版本 ≥ 3.10。"""
    ok = sys.version_info >= (3, 10)
    return ok, f"Python {platform.python_version()}（{sys.executable}）"


def check_binary(name: str) -> tuple[bool, str]:
    """检查外部二进制是否存在并读取版本。"""
    path = shutil.which(name)
    if path is None:
        return False, f"{name} 未找到（不在 PATH 中）"
    version = _tool_version([name, "-version"])
    return True, f"{name}：{path}" + (f"｜{version}" if version else "")


def check_pillow() -> tuple[bool, str]:
    """检查 Pillow 是否可导入（联系表生成需要）。"""
    spec = importlib.util.find_spec("PIL")
    if spec is None:
        return False, "Pillow 未安装（pip install Pillow）"
    import PIL

    return True, f"Pillow {PIL.__version__}"


def check_resolve() -> tuple[bool, str]:
    """检查 DaVinci Resolve 脚本环境（可选）。

    依次看：DaVinciResolveScript 模块能否直接导入、RESOLVE_SCRIPT_API 环境变量、
    各平台默认的 Developer/Scripting/Modules 目录是否存在。
    注意：能找到模块文件不等于 Resolve 正在运行，阶段 5 连接失败时会另行报错。
    """
    if importlib.util.find_spec("DaVinciResolveScript") is not None:
        return True, "DaVinciResolveScript 模块可直接导入"
    api_dir = os.environ.get("RESOLVE_SCRIPT_API")
    if api_dir and Path(api_dir, "DaVinciResolveScript.py").exists():
        return True, f"在 RESOLVE_SCRIPT_API 找到脚本模块：{api_dir}"
    for directory in RESOLVE_MODULE_DIRS:
        if directory and Path(directory, "DaVinciResolveScript.py").exists():
            return True, f"在默认目录找到脚本模块：{directory}"
    return False, "未找到 Resolve 脚本模块（未安装 Resolve Studio 或未开启外部脚本）"


def main() -> int:
    """打印环境报告；核心项缺失返回 1，否则 0。"""
    print("=== autoedit-agent 环境检查 ===")
    core_checks = [
        ("Python ≥3.10", check_python()),
        ("ffmpeg", check_binary("ffmpeg")),
        ("ffprobe", check_binary("ffprobe")),
        ("Pillow", check_pillow()),
    ]
    optional_checks = [("DaVinci Resolve（可选）", check_resolve())]

    core_ok = True
    for label, (ok, detail) in core_checks:
        print(f"[{'✓' if ok else '✗'}] {label}：{detail}")
        core_ok = core_ok and ok
    for label, (ok, detail) in optional_checks:
        print(f"[{'✓' if ok else '△'}] {label}：{detail}")
        if not ok:
            print("    （缺失不影响素材分析与蓝图生成；阶段 5 将降级为只交付蓝图）")

    if core_ok:
        print("结论：核心环境就绪，可以开始素材盘点。")
        return 0
    print("结论：核心环境缺失，请先按上面提示补齐再开始。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

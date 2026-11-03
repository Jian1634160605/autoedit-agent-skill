"""把技能配套脚本目录加入 sys.path，让测试能直接 import 三个脚本模块。"""

import sys
from pathlib import Path

SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "autoedit-agent"
    / "scripts"
)
sys.path.insert(0, str(SCRIPTS_DIR))

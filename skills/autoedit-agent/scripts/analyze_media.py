#!/usr/bin/env python3
"""素材盘点与分析脚本（autoedit-agent 技能配套脚本，阶段 1 使用）。

功能：
  * 递归扫描素材目录中的常见视频文件；
  * 用 ffprobe 读取时长 / 分辨率 / 帧率 / 编码 / 大小；
  * 用 ffmpeg 的 blackdetect / silencedetect 找出黑帧段与静音段；
  * 每条素材在 10% / 50% / 90% 处抽帧，拼一张联系表（contact sheet）；
  * 输出 inventory.csv（清单）、analysis.json（完整分析）、
    blueprint.json（剪辑蓝图骨架，供阶段 4 在此之上细化）。

依赖：Python 3.10+、Pillow、外部二进制 ffmpeg / ffprobe。
工具缺失时会给出清晰报错并以非零码退出，不抛调用栈。

用法：
    python analyze_media.py <素材目录> --out <输出目录>
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
FRAME_RATIOS = (0.10, 0.50, 0.90)
THUMB_WIDTH = 320
LABEL_HEIGHT = 22
LONG_SILENCE_SECONDS = 3.0


class ToolMissingError(RuntimeError):
    """外部工具（ffmpeg / ffprobe）缺失时抛出，入口处转成友好提示。"""


# ---------------------------------------------------------------------------
# 工具与 ffprobe 元数据
# ---------------------------------------------------------------------------

def require_tools(*names: str) -> None:
    """确认给定外部工具都在 PATH 中，缺失则抛 ToolMissingError。"""
    missing = [n for n in names if shutil.which(n) is None]
    if missing:
        raise ToolMissingError(
            "未找到外部工具：{}。请先安装 ffmpeg（内含 ffprobe）并确保其在 PATH 中。".format(
                "、".join(missing)
            )
        )


def _parse_fps(rate: str | None) -> float:
    """把 ffprobe 的分数帧率（如 '30000/1001'）换算成浮点数。"""
    if not rate:
        return 0.0
    try:
        if "/" in rate:
            num, den = rate.split("/", 1)
            den_f = float(den)
            return round(float(num) / den_f, 2) if den_f else 0.0
        return round(float(rate), 2)
    except ValueError:
        return 0.0


def parse_probe_json(data: dict, file_size: int | None = None) -> dict:
    """把 ffprobe 的 JSON 输出解析成统一的元数据字典（纯函数，便于测试）。"""
    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    raw_duration = fmt.get("duration") or video.get("duration")
    try:
        duration = round(float(raw_duration), 3) if raw_duration is not None else 0.0
    except (TypeError, ValueError):
        duration = 0.0

    raw_size = fmt.get("size") if fmt.get("size") is not None else file_size
    try:
        size = int(raw_size) if raw_size is not None else 0
    except (TypeError, ValueError):
        size = 0

    return {
        "duration": duration,
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "fps": _parse_fps(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        "codec": video.get("codec_name") or "",
        "has_audio": audio is not None,
        "size_bytes": size,
    }


def probe_file(path: Path) -> dict:
    """对单个文件运行 ffprobe 并返回解析后的元数据。"""
    require_tools("ffprobe")
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe 读取失败：{path}（{(result.stderr or '').strip()[:200]}）"
        )
    return parse_probe_json(json.loads(result.stdout), file_size=path.stat().st_size)


# ---------------------------------------------------------------------------
# 黑帧 / 静音检测（解析 ffmpeg stderr）
# ---------------------------------------------------------------------------

_BLACK_RE = re.compile(
    r"black_start:(?P<start>[\d.]+)\s+black_end:(?P<end>[\d.]+)\s+black_duration:(?P<dur>[\d.]+)"
)
_SILENCE_START_RE = re.compile(r"silence_start:\s*(?P<start>[\d.]+)")
_SILENCE_END_RE = re.compile(
    r"silence_end:\s*(?P<end>[\d.]+)\s*\|\s*silence_duration:\s*(?P<dur>[\d.]+)"
)


def parse_blackdetect(text: str) -> list[dict]:
    """从 ffmpeg stderr 文本解析黑帧区间（纯函数，便于测试）。"""
    return [
        {
            "start": float(m.group("start")),
            "end": float(m.group("end")),
            "duration": float(m.group("dur")),
        }
        for m in _BLACK_RE.finditer(text or "")
    ]


def parse_silencedetect(text: str) -> list[dict]:
    """从 ffmpeg stderr 文本解析静音区间（纯函数，便于测试）。

    silencedetect 成对输出 silence_start / silence_end；
    末尾只有 start 没有 end 的未闭合段直接丢弃。
    """
    segments: list[dict] = []
    pending: float | None = None
    for line in (text or "").splitlines():
        m = _SILENCE_START_RE.search(line)
        if m:
            pending = float(m.group("start"))
            continue
        m = _SILENCE_END_RE.search(line)
        if m and pending is not None:
            segments.append(
                {
                    "start": pending,
                    "end": float(m.group("end")),
                    "duration": float(m.group("dur")),
                }
            )
            pending = None
    return segments


def _run_ffmpeg_filter(path: Path, extra_args: list[str]) -> str:
    """运行 ffmpeg 分析并返回 stderr 全文（检测信息都写在 stderr）。"""
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), *extra_args, "-f", "null", "-"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stderr or ""


def detect_black_frames(path: Path, min_duration: float = 0.5, pix_threshold: float = 0.10) -> list[dict]:
    """用 blackdetect 找黑帧段。"""
    vf = f"blackdetect=d={min_duration}:pix_th={pix_threshold}"
    return parse_blackdetect(_run_ffmpeg_filter(path, ["-vf", vf, "-an"]))


def detect_silence(path: Path, noise: str = "-50dB", min_duration: float = 1.0) -> list[dict]:
    """用 silencedetect 找静音段（无音轨素材返回空列表）。"""
    af = f"silencedetect=noise={noise}:d={min_duration}"
    return parse_silencedetect(_run_ffmpeg_filter(path, ["-af", af, "-vn"]))


# ---------------------------------------------------------------------------
# 抽帧与联系表
# ---------------------------------------------------------------------------

def frame_timestamps(duration: float) -> list[float]:
    """按时长算出 10% / 50% / 90% 三个抽帧时间点（秒）。"""
    if duration <= 0:
        return [0.0, 0.0, 0.0]
    return [round(duration * r, 2) for r in FRAME_RATIOS]


def extract_frame(video: Path, timestamp: float, out_path: Path) -> bool:
    """用 ffmpeg 在指定时间点抽一帧，成功返回 True。"""
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-ss", f"{timestamp:.2f}", "-i", str(video),
        "-frames:v", "1", "-q:v", "3", str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0 and out_path.exists()


def extract_frames(video: Path, duration: float, frames_dir: Path) -> list[Path | None]:
    """抽 3 帧到 frames_dir，返回与时间点一一对应的路径列表（失败为 None）。"""
    frames_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path | None] = []
    for idx, ts in enumerate(frame_timestamps(duration)):
        out = frames_dir / f"{video.stem}_f{idx}.jpg"
        results.append(out if extract_frame(video, ts, out) else None)
    return results


def make_contact_sheet(clips: list[dict], out_path: Path) -> Path:
    """把多条素材的抽帧拼成一张联系表：每行一条素材，行首标注文件名。

    clips: [{"name": 文件名, "frames": [Path | None, ...]}, ...]
    """
    from PIL import Image, ImageDraw  # 延迟导入：纯解析逻辑测试不需要 Pillow

    bg, fg, placeholder = (24, 24, 24), (235, 235, 235), (70, 70, 70)

    def load_thumb(frame_path: Path | None) -> "Image.Image":
        if frame_path is not None and Path(frame_path).exists():
            img = Image.open(frame_path).convert("RGB")
        else:
            img = Image.new("RGB", (THUMB_WIDTH, 180), placeholder)
        if img.width != THUMB_WIDTH:
            img = img.resize((THUMB_WIDTH, max(1, int(img.height * THUMB_WIDTH / img.width))))
        return img

    if not clips:
        sheet = Image.new("RGB", (THUMB_WIDTH * 3, LABEL_HEIGHT + 180), bg)
        ImageDraw.Draw(sheet).text((8, 4), "no clips", fill=fg)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(out_path, quality=88)
        return out_path

    rows = []
    row_height = 180
    for clip in clips:
        thumbs = [load_thumb(f) for f in clip.get("frames", [])]
        if thumbs:
            row_height = max(row_height, max(t.height for t in thumbs))
        rows.append((clip.get("name", ""), thumbs))

    sheet = Image.new("RGB", (THUMB_WIDTH * 3, (LABEL_HEIGHT + row_height) * len(rows)), bg)
    draw = ImageDraw.Draw(sheet)
    y = 0
    for label, thumbs in rows:
        draw.text((8, y + 4), str(label), fill=fg)
        for col, thumb in enumerate(thumbs):
            sheet.paste(thumb, (col * THUMB_WIDTH, y + LABEL_HEIGHT))
        y += LABEL_HEIGHT + row_height
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, quality=88)
    return out_path


# ---------------------------------------------------------------------------
# 结果组装与落盘
# ---------------------------------------------------------------------------

def clip_flags(clip: dict) -> list[str]:
    """根据检测结果给素材打建议标记。"""
    flags = []
    if clip.get("black_segments"):
        flags.append("has_black_frames")
    if any(
        seg.get("duration", 0) >= LONG_SILENCE_SECONDS
        for seg in clip.get("silence_segments", [])
    ):
        flags.append("long_silence")
    return flags


def build_analysis(clips: list[dict]) -> dict:
    """组装 analysis.json 的完整分析结构（纯函数，便于测试）。"""
    out = []
    for clip in clips:
        item = dict(clip)
        item["flags"] = clip_flags(clip)
        out.append(item)
    return {"tool": "analyze_media.py", "clip_count": len(out), "clips": out}


def build_skeleton(analysis: dict, project_name: str = "untitled") -> dict:
    """由分析结果生成剪辑蓝图骨架（字段规范见 references/blueprint-schema.md）。

    每条素材默认整段入选（source_in=0 到 source_out=时长），
    检测到的黑帧 / 静音区间写进 note，供 Agent 在阶段 4 裁剪时参考。
    """
    clips = []
    for idx, clip in enumerate(analysis["clips"], start=1):
        notes = []
        if clip.get("black_segments"):
            notes.append(f"含 {len(clip['black_segments'])} 段黑帧，裁剪时避开")
        if clip.get("silence_segments"):
            notes.append(f"含 {len(clip['silence_segments'])} 段静音，注意节奏")
        clips.append(
            {
                "id": f"c{idx:03d}",
                "media": clip["path"],
                "source_in": 0.0,
                "source_out": clip.get("duration", 0.0),
                "track": 1,
                "transition_in": "cut",
                "flags": clip.get("flags", []),
                "note": "；".join(notes),
            }
        )
    return {
        "version": "1.0",
        "project": {"name": project_name, "fps": 30, "width": 1920, "height": 1080},
        "target_duration": None,
        "clips": clips,
        "bgm": [],
    }


def write_inventory_csv(clips: list[dict], out_path: Path) -> None:
    """写 inventory.csv：每条素材一行。"""
    fields = [
        "path", "duration", "resolution", "fps", "codec",
        "size_bytes", "black_segments", "silence_segments", "flags",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for clip in clips:
            writer.writerow(
                {
                    "path": clip["path"],
                    "duration": clip.get("duration", 0.0),
                    "resolution": f"{clip.get('width', 0)}x{clip.get('height', 0)}",
                    "fps": clip.get("fps", 0.0),
                    "codec": clip.get("codec", ""),
                    "size_bytes": clip.get("size_bytes", 0),
                    "black_segments": len(clip.get("black_segments", [])),
                    "silence_segments": len(clip.get("silence_segments", [])),
                    "flags": "|".join(clip_flags(clip)),
                }
            )


def find_videos(source: Path) -> list[Path]:
    """递归找出目录下所有常见视频文件（按路径排序，结果稳定）。"""
    return sorted(
        p for p in source.rglob("*")
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
    )


def analyze_directory(source: Path, out_dir: Path, project_name: str = "untitled") -> dict:
    """执行一次完整盘点分析，落盘全部产物，返回 analysis 字典。"""
    videos = find_videos(source)
    frames_root = out_dir / "frames"
    clips: list[dict] = []
    sheet_clips: list[dict] = []
    for video in videos:
        meta = probe_file(video)
        black = detect_black_frames(video)
        silence = detect_silence(video)
        frames = extract_frames(video, meta["duration"], frames_root / video.stem)
        clips.append(
            {
                "path": str(video),
                **meta,
                "black_segments": black,
                "silence_segments": silence,
            }
        )
        sheet_clips.append({"name": video.name, "frames": frames})
        print(
            f"[analyze] {video.name}：{meta['duration']}s "
            f"{meta['width']}x{meta['height']}，黑帧 {len(black)} 段，静音 {len(silence)} 段"
        )

    analysis = build_analysis(clips)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_inventory_csv(clips, out_dir / "inventory.csv")
    (out_dir / "analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "blueprint.json").write_text(
        json.dumps(build_skeleton(analysis, project_name), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    make_contact_sheet(sheet_clips, out_dir / "contact_sheet.jpg")
    return analysis


def main(argv: list[str] | None = None) -> int:
    """脚本入口；工具缺失或目录不对时给出清晰报错，不抛调用栈。"""
    parser = argparse.ArgumentParser(
        prog="analyze_media.py", description="素材盘点与分析（autoedit-agent 阶段 1）"
    )
    parser.add_argument("source", help="素材目录路径")
    parser.add_argument("--out", required=True, help="输出目录")
    parser.add_argument("--project-name", default="untitled", help="蓝图骨架里的工程名")
    args = parser.parse_args(argv)

    source = Path(args.source)
    if not source.is_dir():
        print(f"错误：素材目录不存在：{source}", file=sys.stderr)
        return 2
    try:
        require_tools("ffmpeg", "ffprobe")
        analysis = analyze_directory(source, Path(args.out), args.project_name)
    except ToolMissingError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    print(f"完成：共 {analysis['clip_count']} 条素材，输出目录 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

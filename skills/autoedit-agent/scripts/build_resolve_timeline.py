#!/usr/bin/env python3
"""按剪辑蓝图构建 DaVinci Resolve 时间线（autoedit-agent 技能配套脚本，阶段 5 使用）。

两种运行模式：
  * --dry-run：不连接 Resolve，只校验 blueprint.json 并打印计划动作清单。
    蓝图有结构错误时逐条列出并以非零码退出。交付前必须先跑 dry-run。
  * 实际构建：通过 DaVinci Resolve Python 脚本 API（DaVinciResolveScript）
    创建工程、导入素材、建时间线、按源入出点逐段 append。
    需要本机装有 DaVinci Resolve Studio 并已开启外部脚本。
    连接不上时给出清晰报错，并提示可先用 --dry-run 校验蓝图。

蓝图字段规范见 ../references/blueprint-schema.md。

用法：
    python build_resolve_timeline.py <blueprint.json> [--dry-run] [--project-name 名称]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

VALID_TRANSITIONS = {"cut", "dissolve", "fade_in", "fade_out", "fade"}


# ---------------------------------------------------------------------------
# 蓝图校验（纯函数，便于测试）
# ---------------------------------------------------------------------------

def validate_blueprint(data: object, check_files: bool = True) -> list[str]:
    """校验蓝图结构，返回错误信息列表（空列表 = 通过）。"""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["蓝图根节点必须是 JSON 对象"]

    project = data.get("project")
    if project is not None:
        if not isinstance(project, dict):
            errors.append("project 必须是对象")
        else:
            fps = project.get("fps")
            if fps is not None and (not isinstance(fps, (int, float)) or fps <= 0):
                errors.append("project.fps 必须是正数")
            for key in ("width", "height"):
                v = project.get(key)
                if v is not None and (not isinstance(v, int) or v <= 0):
                    errors.append(f"project.{key} 必须是正整数")

    clips = data.get("clips")
    if not isinstance(clips, list) or not clips:
        errors.append("clips 必须是非空数组")
        return errors

    seen_ids: set[str] = set()
    for idx, clip in enumerate(clips):
        where = f"clips[{idx}]"
        if not isinstance(clip, dict):
            errors.append(f"{where} 必须是对象")
            continue
        cid = clip.get("id")
        if not cid:
            errors.append(f"{where}.id 缺失")
        elif cid in seen_ids:
            errors.append(f"{where}.id 重复：{cid}")
        else:
            seen_ids.add(cid)

        media = clip.get("media")
        if not media:
            errors.append(f"{where}.media 缺失")
        elif check_files and not Path(media).exists():
            errors.append(f"{where}.media 文件不存在：{media}")

        s_in, s_out = clip.get("source_in"), clip.get("source_out")
        if not isinstance(s_in, (int, float)) or not isinstance(s_out, (int, float)):
            errors.append(f"{where}.source_in / source_out 必须是数字（秒）")
        else:
            if s_in < 0:
                errors.append(f"{where}.source_in 不能为负：{s_in}")
            if s_out <= s_in:
                errors.append(f"{where} 源出点必须大于入点：{s_in} → {s_out}")

        track = clip.get("track", 1)
        if not isinstance(track, int) or track < 1:
            errors.append(f"{where}.track 必须是 ≥1 的整数")

        transition = clip.get("transition_in", "cut")
        if transition not in VALID_TRANSITIONS:
            errors.append(f"{where}.transition_in 不受支持：{transition}")

        subtitle = clip.get("subtitle")
        if subtitle is not None:
            if not isinstance(subtitle, dict) or not subtitle.get("text"):
                errors.append(f"{where}.subtitle 必须含非空 text")

    for idx, seg in enumerate(data.get("bgm") or []):
        if not isinstance(seg, dict) or not seg.get("media"):
            errors.append(f"bgm[{idx}] 必须含 media")
        elif check_files and not Path(seg["media"]).exists():
            errors.append(f"bgm[{idx}].media 文件不存在：{seg['media']}")

    target = data.get("target_duration")
    if target is not None and (not isinstance(target, (int, float)) or target <= 0):
        errors.append("target_duration 必须是正数或 null")

    return errors


def clip_duration(clip: dict) -> float:
    """单个片段在时间线上的时长（秒）。"""
    return float(clip["source_out"]) - float(clip["source_in"])


def total_duration(blueprint: dict) -> float:
    """按 track 1 顺序拼接估算的成片总时长（秒）。"""
    return round(sum(clip_duration(c) for c in blueprint.get("clips", [])), 3)


def plan_actions(blueprint: dict) -> list[str]:
    """把蓝图翻译成有序的计划动作清单（纯函数，dry-run 与实跑共用）。"""
    project = blueprint.get("project") or {}
    name = project.get("name", "untitled")
    fps = project.get("fps", 30)
    width, height = project.get("width", 1920), project.get("height", 1080)

    actions = [f"创建/打开工程：{name}（{width}x{height} @ {fps}fps）"]
    media_files = []
    for clip in blueprint["clips"]:
        if clip["media"] not in media_files:
            media_files.append(clip["media"])
    for media in media_files:
        actions.append(f"导入素材：{media}")
    actions.append(f"新建时间线：{name}_timeline")

    cursor = 0.0
    for clip in blueprint["clips"]:
        dur = clip_duration(clip)
        transition = clip.get("transition_in", "cut")
        actions.append(
            f"追加片段 {clip['id']}：{clip['media']} "
            f"[{float(clip['source_in']):.2f}s → {float(clip['source_out']):.2f}s] "
            f"到 V{clip.get('track', 1)}，时间线 {cursor:.2f}s–{cursor + dur:.2f}s，"
            f"入场转场：{transition}"
        )
        subtitle = clip.get("subtitle")
        if subtitle:
            actions.append(
                f"  └ 字幕（{clip['id']}）：「{subtitle['text']}」"
                f"偏移 {subtitle.get('start_offset', 0)}s–{subtitle.get('end_offset', dur)}s"
            )
        cursor += dur

    for idx, seg in enumerate(blueprint.get("bgm") or []):
        actions.append(
            f"铺设 BGM[{idx}]：{seg['media']}，起始 {seg.get('start', 0)}s，"
            f"时长 {seg.get('duration', '全程')}s，音量 {seg.get('volume_db', -18)}dB"
        )

    total = total_duration(blueprint)
    target = blueprint.get("target_duration")
    if target:
        actions.append(f"预计成片时长：{total:.2f}s（目标 {target}s，差值 {total - target:+.2f}s）")
    else:
        actions.append(f"预计成片时长：{total:.2f}s")
    return actions


# ---------------------------------------------------------------------------
# 实际构建（DaVinci Resolve Python API）
# ---------------------------------------------------------------------------

def _load_resolve():
    """尝试连接正在运行的 DaVinci Resolve，失败返回 None。"""
    try:
        import DaVinciResolveScript as dvr  # type: ignore
    except ImportError:
        api_dir = os.environ.get("RESOLVE_SCRIPT_API")
        if api_dir and os.path.isdir(api_dir):
            sys.path.append(api_dir)
            try:
                import DaVinciResolveScript as dvr  # type: ignore
            except ImportError:
                return None
        else:
            return None
    try:
        return dvr.scriptapp("Resolve")
    except Exception:
        return None


def build_in_resolve(blueprint: dict, project_name: str | None = None) -> int:
    """连接 Resolve 并按计划动作实际构建工程与时间线。

    每一步都检查 API 返回值；任何一步失败立即报错退出，
    不把「调用成功」冒充「写入成功」——构建完会回读时间线片段数核对。
    """
    resolve = _load_resolve()
    if resolve is None:
        print(
            "错误：无法连接 DaVinci Resolve。请确认已安装 Resolve Studio、"
            "已在偏好设置中开启「使用外部脚本」，并已启动 Resolve 后重试；"
            "或先用 --dry-run 只校验蓝图。",
            file=sys.stderr,
        )
        return 3

    project_cfg = blueprint.get("project") or {}
    fps = float(project_cfg.get("fps", 30))
    name = project_name or project_cfg.get("name", "untitled")

    pm = resolve.GetProjectManager()
    project = pm.CreateProject(name)
    if project is None:  # 同名工程已存在时退回打开它，但要用新时间线避免污染
        project = pm.LoadProject(name)
    if project is None:
        print(f"错误：创建/打开工程失败：{name}", file=sys.stderr)
        return 3
    project.SetSetting("timelineFrameRate", str(fps))
    project.SetSetting("timelineResolutionWidth", str(project_cfg.get("width", 1920)))
    project.SetSetting("timelineResolutionHeight", str(project_cfg.get("height", 1080)))

    media_pool = project.GetMediaPool()
    imported: dict[str, object] = {}
    for clip in blueprint["clips"]:
        media = clip["media"]
        if media not in imported:
            items = media_pool.ImportMedia([media])
            if not items:
                print(f"错误：导入素材失败：{media}", file=sys.stderr)
                return 3
            imported[media] = items[0]

    timeline = media_pool.CreateEmptyTimeline(f"{name}_timeline")
    if timeline is None:
        print("错误：新建时间线失败", file=sys.stderr)
        return 3
    project.SetCurrentTimeline(timeline)

    record_frame = 0
    appended = 0
    for clip in blueprint["clips"]:
        start_frame = int(round(float(clip["source_in"]) * fps))
        end_frame = int(round(float(clip["source_out"]) * fps))
        ok = media_pool.AppendToTimeline(
            [
                {
                    "mediaPoolItem": imported[clip["media"]],
                    "startFrame": start_frame,
                    "endFrame": end_frame,
                    "trackIndex": int(clip.get("track", 1)),
                    "recordFrame": record_frame,
                }
            ]
        )
        if not ok:
            print(f"错误：追加片段失败：{clip['id']}", file=sys.stderr)
            return 3
        appended += 1
        record_frame += end_frame - start_frame

    actual = timeline.GetItemListInTrack("video", 1)
    print(
        f"构建完成：工程 {name}，时间线 {name}_timeline，"
        f"计划片段 {appended} 段，时间线 V1 实际片段 {len(actual)} 段。"
    )
    if len(actual) != appended:
        print("警告：实际片段数与计划不一致，请在 Resolve 中人工核对。", file=sys.stderr)
        return 4
    pm.SaveProject()
    return 0


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def load_blueprint(path: Path) -> dict:
    """读取并解析 blueprint.json，文件不存在或 JSON 非法时抛 ValueError。"""
    if not path.exists():
        raise ValueError(f"蓝图文件不存在：{path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"蓝图 JSON 解析失败：{exc}") from exc


def main(argv: list[str] | None = None) -> int:
    """入口：先校验蓝图；--dry-run 只打印计划，实跑则连接 Resolve 构建。"""
    parser = argparse.ArgumentParser(
        prog="build_resolve_timeline.py", description="按剪辑蓝图构建 DaVinci Resolve 时间线"
    )
    parser.add_argument("blueprint", help="blueprint.json 路径")
    parser.add_argument("--dry-run", action="store_true", help="只校验并打印计划动作，不连接 Resolve")
    parser.add_argument("--project-name", default=None, help="覆盖蓝图中的工程名")
    parser.add_argument("--skip-file-check", action="store_true", help="校验时不检查素材文件是否存在")
    args = parser.parse_args(argv)

    try:
        blueprint = load_blueprint(Path(args.blueprint))
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    errors = validate_blueprint(blueprint, check_files=not args.skip_file_check)
    if errors:
        print("蓝图校验未通过：", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 2

    if args.project_name:
        blueprint.setdefault("project", {})["name"] = args.project_name

    actions = plan_actions(blueprint)
    if args.dry_run:
        print(f"[dry-run] 蓝图校验通过，共 {len(actions)} 项计划动作：")
        for i, action in enumerate(actions, start=1):
            print(f"{i:>2}. {action}")
        print("[dry-run] 未连接 Resolve，未做任何写入。")
        return 0

    print("计划动作：")
    for action in actions:
        print(f"  - {action}")
    return build_in_resolve(blueprint, args.project_name)


if __name__ == "__main__":
    raise SystemExit(main())

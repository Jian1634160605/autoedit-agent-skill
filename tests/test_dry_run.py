"""build_resolve_timeline 的 --dry-run 端到端单测（函数级调用，不连 Resolve）。"""

import json

from build_resolve_timeline import main


def write_blueprint(tmp_path, clips):
    media = tmp_path / "a.mp4"
    media.write_bytes(b"fake")
    bp = {
        "version": "1.0",
        "project": {"name": "dryrun_demo", "fps": 25, "width": 1280, "height": 720},
        "target_duration": None,
        "clips": clips(media),
        "bgm": [],
    }
    path = tmp_path / "blueprint.json"
    path.write_text(json.dumps(bp, ensure_ascii=False), encoding="utf-8")
    return path


def test_dry_run_ok(tmp_path, capsys):
    path = write_blueprint(
        tmp_path,
        lambda m: [
            {"id": "c001", "media": str(m), "source_in": 0.0, "source_out": 5.0},
            {"id": "c002", "media": str(m), "source_in": 8.0, "source_out": 11.5},
        ],
    )
    code = main([str(path), "--dry-run"])
    out = capsys.readouterr().out
    assert code == 0
    assert "[dry-run] 蓝图校验通过" in out
    assert "追加片段 c002" in out
    assert "预计成片时长：8.50s" in out
    assert "未连接 Resolve" in out


def test_dry_run_invalid_blueprint_fails(tmp_path, capsys):
    path = write_blueprint(
        tmp_path,
        lambda m: [{"id": "c001", "media": str(m), "source_in": 5.0, "source_out": 5.0}],
    )
    code = main([str(path), "--dry-run"])
    captured = capsys.readouterr()
    assert code == 2
    assert "校验未通过" in captured.err


def test_dry_run_missing_file_fails(tmp_path, capsys):
    code = main([str(tmp_path / "no_such.json"), "--dry-run"])
    captured = capsys.readouterr()
    assert code == 2
    assert "不存在" in captured.err


def test_dry_run_skip_file_check(tmp_path, capsys):
    media = tmp_path / "ghost.mp4"  # 故意不创建
    bp = {
        "version": "1.0",
        "project": {"name": "ghost", "fps": 30, "width": 1920, "height": 1080},
        "clips": [{"id": "c001", "media": str(media), "source_in": 0.0, "source_out": 3.0}],
        "bgm": [],
    }
    path = tmp_path / "blueprint.json"
    path.write_text(json.dumps(bp), encoding="utf-8")
    assert main([str(path), "--dry-run"]) == 2  # 默认校验文件存在 → 失败
    assert main([str(path), "--dry-run", "--skip-file-check"]) == 0

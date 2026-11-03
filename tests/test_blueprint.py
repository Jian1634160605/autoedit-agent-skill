"""蓝图校验（validate_blueprint）、计划动作（plan_actions）与分析骨架组装的单测。"""

import analyze_media
from build_resolve_timeline import plan_actions, total_duration, validate_blueprint


def make_blueprint(tmp_path, **overrides):
    """造一份最小合法蓝图；素材用 tmp_path 下的真实空文件，满足存在性校验。"""
    media = tmp_path / "a.mp4"
    media.write_bytes(b"fake")
    bp = {
        "version": "1.0",
        "project": {"name": "demo", "fps": 30, "width": 1920, "height": 1080},
        "target_duration": 10.0,
        "clips": [
            {
                "id": "c001",
                "media": str(media),
                "source_in": 0.0,
                "source_out": 6.0,
                "track": 1,
                "transition_in": "cut",
                "subtitle": {"text": "开场白", "start_offset": 0.0, "end_offset": 3.0},
            },
            {
                "id": "c002",
                "media": str(media),
                "source_in": 10.0,
                "source_out": 14.0,
            },
        ],
        "bgm": [],
    }
    bp.update(overrides)
    return bp


def test_valid_blueprint_passes(tmp_path):
    assert validate_blueprint(make_blueprint(tmp_path)) == []


def test_missing_media_file_is_error(tmp_path):
    bp = make_blueprint(tmp_path)
    bp["clips"][0]["media"] = str(tmp_path / "nope.mp4")
    errors = validate_blueprint(bp)
    assert any("不存在" in e for e in errors)
    # 关掉文件检查后应通过
    assert validate_blueprint(bp, check_files=False) == []


def test_bad_source_range_is_error(tmp_path):
    bp = make_blueprint(tmp_path)
    bp["clips"][0]["source_out"] = 0.0
    assert any("出点" in e for e in validate_blueprint(bp))


def test_duplicate_id_and_bad_transition(tmp_path):
    bp = make_blueprint(tmp_path)
    bp["clips"][1]["id"] = "c001"
    bp["clips"][0]["transition_in"] = "spin"
    errors = validate_blueprint(bp)
    assert any("重复" in e for e in errors)
    assert any("transition_in" in e for e in errors)


def test_empty_clips_is_error(tmp_path):
    bp = make_blueprint(tmp_path, clips=[])
    assert validate_blueprint(bp) != []


def test_total_duration_and_plan(tmp_path):
    bp = make_blueprint(tmp_path)
    assert total_duration(bp) == 10.0
    actions = plan_actions(bp)
    text = "\n".join(actions)
    assert "创建/打开工程：demo" in text
    assert "追加片段 c001" in text
    assert "字幕（c001）" in text
    assert "预计成片时长：10.00s（目标 10.0s" in text


def test_skeleton_from_analysis(tmp_path):
    media = tmp_path / "x.mp4"
    media.write_bytes(b"fake")
    clips = [
        {
            "path": str(media),
            "duration": 20.0,
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "codec": "h264",
            "size_bytes": 100,
            "black_segments": [{"start": 1.0, "end": 2.0, "duration": 1.0}],
            "silence_segments": [{"start": 5.0, "end": 9.0, "duration": 4.0}],
        }
    ]
    analysis = analyze_media.build_analysis(clips)
    assert analysis["clips"][0]["flags"] == ["has_black_frames", "long_silence"]
    skeleton = analyze_media.build_skeleton(analysis, project_name="demo")
    assert skeleton["project"]["name"] == "demo"
    first = skeleton["clips"][0]
    assert first["id"] == "c001"
    assert first["source_in"] == 0.0
    assert first["source_out"] == 20.0
    assert "黑帧" in first["note"]
    # 骨架应能直接通过蓝图校验
    assert validate_blueprint(skeleton) == []

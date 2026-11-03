"""analyze_media.parse_probe_json 的解析单测（假 ffprobe JSON，不依赖真实文件）。"""

from analyze_media import parse_probe_json

SAMPLE = {
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1920,
            "height": 1080,
            "avg_frame_rate": "30000/1001",
        },
        {"codec_type": "audio", "codec_name": "aac"},
    ],
    "format": {"duration": "12.500000", "size": "999999"},
}


def test_parse_basic_fields():
    meta = parse_probe_json(SAMPLE, file_size=12345)
    assert meta["duration"] == 12.5
    assert meta["width"] == 1920
    assert meta["height"] == 1080
    assert meta["fps"] == 29.97
    assert meta["codec"] == "h264"
    assert meta["has_audio"] is True
    assert meta["size_bytes"] == 999999  # 优先用 format.size


def test_parse_size_fallback_to_file_size():
    data = {"streams": SAMPLE["streams"], "format": {"duration": "3.0"}}
    meta = parse_probe_json(data, file_size=777)
    assert meta["size_bytes"] == 777


def test_parse_no_audio_and_int_fps():
    data = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "vp9",
                "width": 1280,
                "height": 720,
                "avg_frame_rate": "30/1",
            }
        ],
        "format": {"duration": "5.25", "size": "100"},
    }
    meta = parse_probe_json(data)
    assert meta["has_audio"] is False
    assert meta["fps"] == 30.0
    assert meta["codec"] == "vp9"


def test_parse_empty_input_is_safe():
    meta = parse_probe_json({})
    assert meta["duration"] == 0.0
    assert meta["width"] == 0
    assert meta["fps"] == 0.0
    assert meta["codec"] == ""
    assert meta["size_bytes"] == 0

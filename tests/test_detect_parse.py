"""blackdetect / silencedetect 的 stderr 文本解析单测（假日志）。"""

from analyze_media import parse_blackdetect, parse_silencedetect

BLACK_LOG = """\
Input #0, mov,mp4,m4a, from 'clip.mp4':
[blackdetect @ 0x55f0a1] black_start:1.5 black_end:3.25 black_duration:1.75
frame=  100 fps= 25 q=-0.0 size=N/A time=00:00:04.00
[blackdetect @ 0x55f0a1] black_start:8 black_end:8.64 black_duration:0.64
"""

SILENCE_LOG = """\
[silencedetect @ 0x1234] silence_start: 2.0
[silencedetect @ 0x1234] silence_end: 5.5 | silence_duration: 3.5
[silencedetect @ 0x1234] silence_start: 9.25
[silencedetect @ 0x1234] silence_end: 10.0 | silence_duration: 0.75
"""


def test_parse_blackdetect_segments():
    segs = parse_blackdetect(BLACK_LOG)
    assert len(segs) == 2
    assert segs[0] == {"start": 1.5, "end": 3.25, "duration": 1.75}
    assert segs[1]["start"] == 8.0
    assert segs[1]["end"] == 8.64


def test_parse_blackdetect_empty():
    assert parse_blackdetect("") == []
    assert parse_blackdetect("no detections here") == []


def test_parse_silencedetect_pairs():
    segs = parse_silencedetect(SILENCE_LOG)
    assert len(segs) == 2
    assert segs[0] == {"start": 2.0, "end": 5.5, "duration": 3.5}
    assert segs[1] == {"start": 9.25, "end": 10.0, "duration": 0.75}


def test_parse_silencedetect_dangling_start_dropped():
    log = SILENCE_LOG + "[silencedetect @ 0x1234] silence_start: 11.0\n"
    segs = parse_silencedetect(log)
    assert len(segs) == 2  # 末尾未闭合的 start 被丢弃


def test_parse_silencedetect_empty():
    assert parse_silencedetect("") == []

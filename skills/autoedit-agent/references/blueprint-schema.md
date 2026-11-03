# blueprint.json 字段规范

剪辑蓝图是阶段 4 的产物、阶段 5 的唯一输入。它描述「用哪些素材的哪一段、
按什么顺序、配什么字幕和音乐，拼成一条多长的片子」。
本文是字段的唯一权威定义；`build_resolve_timeline.py` 的校验规则与本文一致。

## 顶层结构

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `version` | string | 是 | 规范版本，当前固定 `"1.0"` |
| `project` | object | 是 | 工程设置，见下 |
| `target_duration` | number \| null | 否 | 目标成片时长（秒）；null 表示不设目标 |
| `clips` | array | 是 | 片段数组，按时间线先后顺序排列，不可为空 |
| `bgm` | array | 否 | BGM 段落数组，可为空 |

### project

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | string | 是 | 工程名；时间线名在此基础上加 `_timeline` 后缀 |
| `fps` | number | 是 | 时间线帧率，如 24 / 25 / 30 / 60 |
| `width` | int | 是 | 时间线宽度（像素） |
| `height` | int | 是 | 时间线高度（像素） |

### clips[]（片段）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | 是 | 片段唯一 id，建议 `c001` 递增编号，全蓝图内不可重复 |
| `media` | string | 是 | 素材文件路径（绝对路径，或相对蓝图文件的路径）；文件必须存在 |
| `source_in` | number | 是 | 源入点（秒），≥ 0 |
| `source_out` | number | 是 | 源出点（秒），必须 > `source_in`，且不应超过素材实际时长 |
| `track` | int | 否 | 目标视频轨道，默认 1 |
| `transition_in` | string | 否 | 入场转场：`cut`（硬切，默认）/ `dissolve` / `fade_in` / `fade_out` / `fade` |
| `subtitle` | object | 否 | 本段字幕，见下 |
| `flags` | array | 否 | 分析标记（如 `has_black_frames`），由 analyze_media.py 骨架带入，仅供参考 |
| `note` | string | 否 | 给人看的备注（如为什么选这段） |

片段在时间线上的时长 = `source_out - source_in`；片段按数组顺序在各自轨道上首尾相接，
不单独存时间线位置，位置由顺序推导，避免手写位置与时长打架。

### clips[].subtitle

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `text` | string | 是 | 字幕文本，非空；断句规则见 editing-heuristics.md |
| `start_offset` | number | 否 | 相对本片段起点的偏移（秒），默认 0 |
| `end_offset` | number | 否 | 相对本片段起点的结束偏移（秒），默认等于片段时长 |

### bgm[]（BGM 段落）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `media` | string | 是 | 音乐文件路径，文件必须存在 |
| `start` | number | 否 | 在时间线上的起始位置（秒），默认 0 |
| `duration` | number \| null | 否 | 使用时长（秒）；null 表示用到时间线结尾 |
| `volume_db` | number | 否 | 音量（dB），默认 -18；有人声的片段下方建议 ≤ -20 |

## 校验规则（与 build_resolve_timeline.py 一致）

1. 根节点必须是对象；`clips` 必须是非空数组。
2. 每个片段必须有不重复的 `id`、存在的 `media` 文件、合法的源入出点（`0 ≤ source_in < source_out`）。
3. `track` 必须是 ≥ 1 的整数；`transition_in` 必须在允许集合内。
4. 有 `subtitle` 时 `text` 不能为空。
5. `bgm[]` 的 `media` 必须存在。
6. `project.fps / width / height` 若出现，必须是正数。

## 完整示例

```json
{
  "version": "1.0",
  "project": { "name": "产品纪录片_活动幕后", "fps": 30, "width": 1920, "height": 1080 },
  "target_duration": 180.0,
  "clips": [
    {
      "id": "c001",
      "media": "/media/launch-event/a_cam_opening.mp4",
      "source_in": 2.5,
      "source_out": 9.0,
      "track": 1,
      "transition_in": "fade_in",
      "subtitle": { "text": "活动开始前两小时，后台已经忙成一团", "start_offset": 0.3, "end_offset": 6.2 },
      "note": "开场钩子：用最忙乱的镜头先抓住注意力"
    },
    {
      "id": "c002",
      "media": "/media/launch-event/b_cam_interview.mp4",
      "source_in": 41.0,
      "source_out": 58.5,
      "track": 1,
      "transition_in": "cut",
      "subtitle": { "text": "我们最怕的不是累，是观众看不到这些准备", "start_offset": 0.0, "end_offset": 17.5 },
      "note": "主体信息块 1：受访者自述，已避开 analysis 标记的 12.0–15.5s 黑帧段"
    },
    {
      "id": "c003",
      "media": "/media/launch-event/a_cam_closing.mp4",
      "source_in": 0.0,
      "source_out": 12.0,
      "track": 1,
      "transition_in": "dissolve",
      "note": "收尾空镜：散场后的空场，与开场形成对照"
    }
  ],
  "bgm": [
    { "media": "/media/music/ambient_main.mp3", "start": 0.0, "duration": null, "volume_db": -20 }
  ]
}
```

本例成片时长 = 6.5 + 17.5 + 12.0 = 36.0 秒；若 `target_duration` 为 180 秒，
阶段 4 就应发现偏差过大并回阶段 3 调整，而不是把示例这样直接交付。

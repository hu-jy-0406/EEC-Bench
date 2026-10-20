#!/usr/bin/env python3
"""Build a local three-model comparison gallery for selected episodes."""

from __future__ import annotations

import html
import json
from pathlib import Path

import locate_episode_outputs as locator


SELECTION = [
    {
        "priority": 1,
        "episode_id": "74Od5-Fmf60_s00006_n4_clean_v2",
        "reason": "必选首条；单场景、4-shot、多人办公室交互，适合观察人物身份与空间连续性。",
    },
    {
        "priority": 32,
        "episode_id": "DwiiGopbVNQ_s00017_n6_clean_v2",
        "reason": "6-shot、双场景，从厨房过渡到餐桌，并包含人与猫，适合比较跨场景主体保持。",
    },
    {
        "priority": 57,
        "episode_id": "q86dRIci1Uo_s00073_n6_clean_v2",
        "reason": "单场景动画、多只猫和逐步扩大的峡谷，适合观察非真人实体与大尺度空间变化。",
    },
    {
        "priority": 88,
        "episode_id": "eI9JkmulqkE_s00164_n8_clean_v3_alt8",
        "reason": "8-shot、四场景、蓝色照明与手机消息，覆盖最长序列和光照、特写、人物动作变化。",
    },
    {
        "priority": 98,
        "episode_id": "uHIbA86efRc_s00078_n6_clean_v2",
        "reason": "6-shot、六场景、坐姿反应与门口假人揭示，场景切换最密集。",
    },
]

OUTPUT_ROOT = (
    locator.WORKSPACE
    / "EECBench/data/generated/comparisons/top100_representative_5_20260924"
)


def link_video(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink():
        if link.resolve() != target.resolve():
            raise RuntimeError(f"existing link points elsewhere: {link}")
        return
    if link.exists():
        raise RuntimeError(f"refusing to replace existing path: {link}")
    link.symlink_to(target.resolve())


def main() -> None:
    episodes, shots = locator.load_indexes()
    wan_queue = locator.read_json(locator.WAN_ROOT / "queue.json")["tasks"]
    holo_queue = locator.read_json(locator.HOLO_ROOT / "queue.json")["tasks"]
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    rows = []
    for selected in SELECTION:
        episode_id = selected["episode_id"]
        record = locator.locate(episode_id, episodes, shots, wan_queue, holo_queue)
        if record["generation_priority"] != selected["priority"]:
            raise RuntimeError(f"priority mismatch for {episode_id}")
        if record["storymem"]["status"] != "complete":
            raise RuntimeError(f"StoryMem incomplete: {episode_id}")
        if record["wan22"]["status"] != "complete":
            raise RuntimeError(f"Wan2.2 incomplete: {episode_id}")
        if not (
            record["holocine"]["status"] == "done"
            and record["holocine"]["episode_video_exists"]
        ):
            raise RuntimeError(f"HoloCine incomplete: {episode_id}")
        if not (
            record["wan22"]["all_prompts_match_canonical_storymem"]
            and record["holocine"]["all_shot_prompts_match_canonical_storymem"]
        ):
            raise RuntimeError(f"per-shot prompt mismatch: {episode_id}")

        story = locator.read_json(Path(record["canonical"]["story_script_path"]))
        video_links = {}
        for model, filename in (
            ("storymem", "storymem.mp4"),
            ("wan22", "wan22.mp4"),
            ("holocine", "holocine.mp4"),
        ):
            target = Path(record[model]["episode_video_path"])
            if not target.is_file():
                raise RuntimeError(f"missing video: {target}")
            link = OUTPUT_ROOT / "videos" / episode_id / filename
            link_video(link, target)
            video_links[model] = str(link.relative_to(OUTPUT_ROOT))

        rows.append(
            {
                **selected,
                "story_name": story["story_name"],
                "story_overview": story["story_overview"],
                "shot_count": len(record["storymem"]["shots"]),
                "scene_count": len(story["scenes"]),
                "canonical": record["canonical"],
                "videos": {
                    model: {
                        "gallery_path": video_links[model],
                        "source_path": record[model]["episode_video_path"],
                    }
                    for model in ("storymem", "wan22", "holocine")
                },
                "per_shot_prompts_exactly_aligned": True,
                "holocine_additional_global_caption": record["holocine"][
                    "additional_global_caption"
                ],
            }
        )

    manifest = {
        "selection_scope": "generation priority 1-100",
        "selection_count": len(rows),
        "models": ["StoryMem", "Wan2.2", "HoloCine"],
        "selection_criteria": [
            "priority 1 is mandatory",
            "all three generated episode videos are complete",
            "cover 4/6/8-shot episodes and diverse scene counts",
            "cover live action, animation/non-human entities, lighting, and scene transitions",
        ],
        "prompt_note": (
            "All three use byte-identical per-shot prompts. HoloCine also receives an "
            "episode-level global caption and a combined multi-shot wrapper, so complete "
            "model inputs are not identical."
        ),
        "episodes": rows,
    }
    (OUTPUT_ROOT / "selection.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )

    cards = []
    labels = {"storymem": "StoryMem", "wan22": "Wan2.2", "holocine": "HoloCine"}
    for row in rows:
        videos = "\n".join(
            f'''<article class="model">
              <h3>{labels[model]}</h3>
              <video controls preload="metadata" src="{html.escape(row['videos'][model]['gallery_path'])}"></video>
              <a href="{html.escape(row['videos'][model]['gallery_path'])}">单独打开视频</a>
            </article>'''
            for model in ("storymem", "wan22", "holocine")
        )
        cards.append(
            f'''<section class="episode">
              <header>
                <span class="rank">优先级 {row['priority']}</span>
                <h2>{html.escape(row['story_name'])}</h2>
                <code>{html.escape(row['episode_id'])}</code>
                <p><b>{row['shot_count']}-shot · {row['scene_count']} scene(s)</b>　{html.escape(row['reason'])}</p>
                <p>{html.escape(row['story_overview'])}</p>
              </header>
              <div class="models">{videos}</div>
            </section>'''
        )

    page = f'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Top-100 代表 Episode：三模型对比</title>
  <style>
    :root {{ color-scheme: dark; font-family: system-ui, sans-serif; background: #0d1117; color: #e6edf3; }}
    body {{ max-width: 1800px; margin: auto; padding: 24px; }}
    h1 {{ margin-bottom: 8px; }}
    .note {{ color: #9da7b3; max-width: 1100px; }}
    .episode {{ margin: 34px 0; padding: 22px; border: 1px solid #30363d; border-radius: 14px; background: #161b22; }}
    .episode header p {{ max-width: 1200px; }}
    .rank {{ float: right; color: #7ee787; font-weight: 700; }}
    code {{ color: #79c0ff; }}
    .models {{ display: grid; grid-template-columns: repeat(3, minmax(260px, 1fr)); gap: 16px; margin-top: 18px; }}
    .model {{ min-width: 0; }}
    .model h3 {{ margin: 0 0 8px; }}
    video {{ width: 100%; background: #000; border-radius: 8px; }}
    a {{ color: #58a6ff; }}
    @media (max-width: 900px) {{ .models {{ grid-template-columns: 1fr; }} .rank {{ float: none; display: block; }} }}
  </style>
</head>
<body>
  <h1>优先级前 100：5 条代表 Episode 的三模型结果</h1>
  <p class="note">三列依次为 StoryMem、Wan2.2、HoloCine。三者逐-shot prompt 字节级一致；HoloCine 还接收 episode 级 global caption 和组合式 multi-shot wrapper，因此完整模型输入并非完全相同。</p>
  {''.join(cards)}
</body>
</html>
'''
    (OUTPUT_ROOT / "index.html").write_text(page)
    print(OUTPUT_ROOT / "index.html")
    print(OUTPUT_ROOT / "selection.json")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build an offline four-model gallery for fully completed Veo episodes."""

from __future__ import annotations

import html
import json
import subprocess
import sys
from pathlib import Path

import locate_episode_outputs as locator


WORKSPACE = locator.WORKSPACE
VEO_RUN = WORKSPACE / "EECBench/experiments/veo_generation_priority100_20260923/run02"
VEO_PROMPTS = (
    WORKSPACE
    / "EECBench/experiments/veo_prompt_adaptation_20260923/candidates_400_veo_6s.jsonl"
)
OUTPUT_ROOT = (
    WORKSPACE
    / "EECBench/data/generated/comparisons/four_model_veo_complete4_20260924"
)
EPISODE_IDS = [
    "52apMIyJVlc_s00176_n6_clean_v2",
    "Wl6COOA3V6Y_s00022_n4_clean_v2",
    "8iDEmCxXz-A_s00025_n6_clean_v2",
    "9ugYT3Xc59s_s00093_n4_clean_v2",
]


def link_file(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink():
        if link.resolve() != target.resolve():
            raise RuntimeError(f"existing link points elsewhere: {link}")
        return
    if link.exists():
        raise RuntimeError(f"refusing to replace existing path: {link}")
    link.symlink_to(target.resolve())


def probe_video(path: Path) -> dict:
    raw = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,width,height,pix_fmt:format=duration",
            "-of", "json", str(path),
        ],
        text=True,
    )
    data = json.loads(raw)
    stream = data["streams"][0]
    return {
        "codec": stream["codec_name"],
        "width": stream["width"],
        "height": stream["height"],
        "pixel_format": stream["pix_fmt"],
        "duration_seconds": float(data["format"]["duration"]),
    }


def concatenate_veo(episode_dir: Path, shot_count: int) -> tuple[Path, list[Path]]:
    source_dir = VEO_RUN / "videos" / episode_dir.name
    source_shots = [source_dir / f"Shot{i}.mp4" for i in range(1, shot_count + 1)]
    if not all(path.is_file() for path in source_shots):
        missing = [str(path) for path in source_shots if not path.is_file()]
        raise RuntimeError(f"missing Veo shots: {missing}")

    shot_dir = episode_dir / "veo_shots"
    for source in source_shots:
        link_file(shot_dir / source.name, source)

    concat_list = episode_dir / "veo_concat.txt"
    concat_list.write_text(
        "".join(f"file 'veo_shots/Shot{i}.mp4'\n" for i in range(1, shot_count + 1))
    )
    output = episode_dir / "veo31.mp4"
    temporary = episode_dir / "veo31.partial.mp4"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy", "-movflags", "+faststart", str(temporary),
        ],
        check=True,
    )
    temporary.replace(output)
    return output, source_shots


def main() -> None:
    sys.path.insert(0, str(WORKSPACE / "EECBench/scripts"))
    from prepare_veo_6s_prompts import convert

    episodes, shots = locator.load_indexes()
    wan_queue = locator.read_json(locator.WAN_ROOT / "queue.json")["tasks"]
    holo_queue = locator.read_json(locator.HOLO_ROOT / "queue.json")["tasks"]
    veo_rows = {
        row["episode_id"]: row
        for row in locator.read_jsonl(VEO_PROMPTS)
    }
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    rows = []
    for episode_id in EPISODE_IDS:
        located = locator.locate(episode_id, episodes, shots, wan_queue, holo_queue)
        if located["storymem"]["status"] != "complete":
            raise RuntimeError(f"StoryMem incomplete: {episode_id}")
        if located["wan22"]["status"] != "complete":
            raise RuntimeError(f"Wan2.2 incomplete: {episode_id}")
        if not (
            located["holocine"]["status"] == "done"
            and located["holocine"]["episode_video_exists"]
        ):
            raise RuntimeError(f"HoloCine incomplete: {episode_id}")

        canonical_shots = located["storymem"]["shots"]
        veo_episode = veo_rows[episode_id]
        if len(veo_episode["shots"]) != len(canonical_shots):
            raise RuntimeError(f"Veo shot count mismatch: {episode_id}")
        prompt_rows = []
        for canonical, veo_shot in zip(canonical_shots, veo_episode["shots"], strict=True):
            if canonical["shot_id"] != veo_shot["shot_id"]:
                raise RuntimeError(f"shot ID mismatch: {episode_id}")
            veo_source_prompt = veo_shot["generation_prompt_en"]
            exact_original_prompt = canonical["prompt"] == veo_source_prompt
            if not canonical["prompt"].startswith(veo_source_prompt):
                raise RuntimeError(
                    f"Veo source is not a prefix of the three-model prompt: "
                    f"{episode_id} {canonical['shot_id']}"
                )
            expected, replacements = convert(veo_source_prompt)
            if expected != veo_shot["generation_prompt_en_veo_6s"]:
                raise RuntimeError(f"Veo transform mismatch: {episode_id} {canonical['shot_id']}")
            prompt_rows.append(
                {
                    "shot_id": canonical["shot_id"],
                    "storymem_wan_holocine_prompt": canonical["prompt"],
                    "veo_source_prompt_before_duration_adaptation": veo_source_prompt,
                    "veo_6s_prompt": expected,
                    "duration_replacements": replacements,
                    "exact_original_prompt_match": exact_original_prompt,
                    "veo_source_is_prefix_of_three_model_prompt": True,
                    "three_model_appended_suffix": canonical["prompt"][len(veo_source_prompt):],
                }
            )

        episode_dir = OUTPUT_ROOT / "videos" / episode_id
        model_paths = {}
        for model, filename in (
            ("storymem", "storymem.mp4"),
            ("wan22", "wan22.mp4"),
            ("holocine", "holocine.mp4"),
        ):
            source = Path(located[model]["episode_video_path"])
            if not source.is_file():
                raise RuntimeError(f"missing {model} video: {source}")
            link = episode_dir / filename
            link_file(link, source)
            model_paths[model] = link

        veo_composite, veo_sources = concatenate_veo(episode_dir, len(canonical_shots))
        veo_probe = probe_video(veo_composite)
        if not (
            veo_probe["codec"] == "h264"
            and veo_probe["width"] == 1280
            and veo_probe["height"] == 720
            and abs(veo_probe["duration_seconds"] - 6 * len(canonical_shots)) < 0.1
        ):
            raise RuntimeError(f"unexpected Veo composite: {episode_id} {veo_probe}")

        story = locator.read_json(Path(located["canonical"]["story_script_path"]))
        rows.append(
            {
                "episode_id": episode_id,
                "generation_priority": located["generation_priority"],
                "story_name": story["story_name"],
                "story_overview": story["story_overview"],
                "shot_count": len(canonical_shots),
                "scene_count": len(story["scenes"]),
                "videos": {
                    "storymem": str(model_paths["storymem"].relative_to(OUTPUT_ROOT)),
                    "wan22": str(model_paths["wan22"].relative_to(OUTPUT_ROOT)),
                    "holocine": str(model_paths["holocine"].relative_to(OUTPUT_ROOT)),
                    "veo31": str(veo_composite.relative_to(OUTPUT_ROOT)),
                },
                "source_paths": {
                    "storymem": located["storymem"]["episode_video_path"],
                    "wan22": located["wan22"]["episode_video_path"],
                    "holocine": located["holocine"]["episode_video_path"],
                    "veo31_shots": [str(path.resolve()) for path in veo_sources],
                },
                "veo_composite": {
                    "method": "lossless concat in Shot1..ShotN order; no re-encoding",
                    **veo_probe,
                },
                "prompts": prompt_rows,
                "exact_original_prompt_shots": sum(
                    item["exact_original_prompt_match"] for item in prompt_rows
                ),
                "canonical": located["canonical"],
            }
        )

    manifest = {
        "episode_count": len(rows),
        "models": ["StoryMem", "Wan2.2", "HoloCine", "Veo 3.1 Fast"],
        "veo_generation": {
            "model": "veo-3.1-fast-generate-preview",
            "resolution": "1280x720",
            "duration_seconds_per_shot": 6,
            "aspect_ratio": "16:9",
            "run_events": str(VEO_RUN / "events.jsonl"),
        },
        "prompt_alignment": {
            "total_shots": sum(row["shot_count"] for row in rows),
            "exact_original_prompt_matches": sum(
                row["exact_original_prompt_shots"] for row in rows
            ),
            "veo_source_is_prefix_of_three_model_prompt": sum(
                item["veo_source_is_prefix_of_three_model_prompt"]
                for row in rows for item in row["prompts"]
            ),
            "note": (
                "The episode and shot mappings are exact. StoryMem, Wan2.2, and HoloCine "
                "use one shared prompt version. Veo uses an earlier shorter source version: "
                "6/20 shot prompts are byte-identical before duration adaptation; in the "
                "other 14, the Veo source is an exact prefix and the three-model version "
                "appends entity or scene constraint sentences. Veo then changes only "
                "five/5-second wording to six/six-second."
            ),
        },
        "episodes": rows,
    }
    (OUTPUT_ROOT / "selection.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )

    labels = {
        "storymem": "StoryMem",
        "wan22": "Wan2.2",
        "holocine": "HoloCine",
        "veo31": "Veo 3.1 Fast",
    }
    cards = []
    for row in rows:
        videos = "".join(
            f'''<article class="model"><h3>{labels[model]}</h3>
            <video controls preload="metadata" src="{html.escape(row['videos'][model])}"></video>
            <a href="{html.escape(row['videos'][model])}">单独打开视频</a></article>'''
            for model in ("storymem", "wan22", "holocine", "veo31")
        )
        cards.append(
            f'''<section class="episode"><header>
            <span class="rank">优先级 {row['generation_priority']}</span>
            <h2>{html.escape(row['story_name'])}</h2>
            <code>{html.escape(row['episode_id'])}</code>
            <p><b>{row['shot_count']}-shot · {row['scene_count']} scene(s)</b>　{html.escape(row['story_overview'])}</p>
            </header><div class="models">{videos}</div></section>'''
        )

    page = f'''<!doctype html><html lang="zh-CN"><head>
    <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>四模型 Veo 完整 Episode 对比</title><style>
    :root {{ color-scheme:dark;font-family:system-ui,sans-serif;background:#0d1117;color:#e6edf3 }}
    body {{ max-width:1900px;margin:auto;padding:24px }} .note {{ color:#9da7b3;max-width:1250px }}
    .episode {{ margin:34px 0;padding:22px;border:1px solid #30363d;border-radius:14px;background:#161b22 }}
    .rank {{ float:right;color:#7ee787;font-weight:700 }} code {{ color:#79c0ff }}
    .models {{ display:grid;grid-template-columns:repeat(4,minmax(240px,1fr));gap:16px;margin-top:18px }}
    .model {{ min-width:0 }} .model h3 {{ margin:0 0 8px }} video {{ width:100%;background:#000;border-radius:8px }}
    a {{ color:#58a6ff }} @media(max-width:1200px){{.models{{grid-template-columns:repeat(2,1fr)}}}}
    @media(max-width:700px){{.models{{grid-template-columns:1fr}}.rank{{float:none;display:block}}}}
    </style></head><body>
    <h1>Veo 3.1 已完整生成的 4 个 Episode：四模型对比</h1>
    <p class="note">Episode/shot 映射精确。前三列共享同一 prompt 版本；Veo 使用较短的早期版本：20 个 shot 中 6 个原始 prompt 字节级相同，另外 14 个 Veo prompt 是前三列 prompt 的完整前缀，前三列在末尾追加了实体或场景约束。Veo 随后仅将 5 秒措辞确定性改为 6 秒。Veo 原始结果是逐-shot MP4，此页播放按 Shot1→ShotN 无损拼接的完整 episode；ZIP 同时保留原始 Veo shot 文件。</p>
    {''.join(cards)}</body></html>'''
    (OUTPUT_ROOT / "index.html").write_text(page)
    (OUTPUT_ROOT / "README_本地预览.txt").write_text(
        "本地预览方法\n============\n\n"
        "1. 完整解压 ZIP，不要在压缩软件的临时预览中直接打开 HTML。\n"
        "2. 进入 four_model_veo_complete4_20260924 文件夹。\n"
        "3. 用 Chrome、Edge、Firefox 或 Safari 打开 index.html。\n\n"
        "页面通过相对路径读取 videos/ 下的视频，请保持解压后的目录结构不变。\n"
        "Veo 原始逐-shot文件位于每个 episode 的 veo_shots/ 子目录。\n"
    )
    print(OUTPUT_ROOT / "index.html")
    print(OUTPUT_ROOT / "selection.json")


if __name__ == "__main__":
    main()

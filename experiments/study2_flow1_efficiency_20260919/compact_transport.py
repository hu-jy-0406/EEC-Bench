"""Experimental compact transport; model/schema/isolation policy unchanged."""
import json,shutil,tempfile,time
from pathlib import Path
import run_wedetect_shot_entities as io
from partial_scene_contract import schema_validate
from compact_payload import pack,dump,GUIDE
PROMPTS=Path(__file__).resolve().parent/'prompts'
def call(stage, prompt_name, payload, images, schema, args):
    directory = args.out / stage
    directory.mkdir(parents=True, exist_ok=False)
    wire = pack(payload)
    prompt = (PROMPTS / prompt_name).read_text() + "\n" + GUIDE + "\nINPUT_JSON:\n" + dump(wire)
    (directory / "prompt.txt").write_text(prompt)
    io.dump(directory / "input.json", payload)
    io.dump(directory / "wire_input.json", wire)
    io.dump(directory / "output.schema.json", schema)
    start = time.time()
    state = dict(status="running", started=start, model=args.model, reasoning=args.reasoning)
    io.dump(directory / "status.json", state)
    try:
        with tempfile.TemporaryDirectory(prefix="eec-partial-scene-") as tmp:
            work = Path(tmp)
            command = [args.codex_bin, "--ask-for-approval", "never", "exec",
                "--ignore-user-config", "-c", args.disabled_skills, "--ephemeral",
                "--skip-git-repo-check", "--sandbox", "read-only", "--color", "never", "--json",
                "--model", args.model, "-c", 'model_reasoning_effort="' + args.reasoning + '"',
                "-c", "project_doc_max_bytes=0", "-c", 'web_search="disabled"',
                "--output-schema", str(directory / "output.schema.json"),
                "--output-last-message", str(directory / "response.json"), "--cd", str(work)]
            for feature in ("shell_tool", "unified_exec", "view_image", "apps", "plugins", "hooks",
                    "multi_agent", "memories", "skill_search", "browser_use", "computer_use",
                    "code_mode", "code_mode_only", "workspace_dependencies"):
                command += ["--disable", feature]
            for i, frame in enumerate(images, 1):
                image = work / ("image_" + str(i) + Path(frame["path"]).suffix)
                shutil.copy2(frame["path"], image)
                if io.sha(image) != frame["sha256"]:
                    raise ValueError("Image changed before request")
                command += ["--image", str(image)]
            command.append("-")
            io.dump(directory / "request.json", dict(command=command, prompt_sha256=io.sha(directory / "prompt.txt"),
                schema_sha256=io.sha(directory / "output.schema.json"),
                images=[dict(shot_id=f["shot_id"], frame_id=f["frame_id"], sha256=f["sha256"]) for f in images]))
            io.run_process(command, prompt, work, directory / "events.jsonl", directory / "stderr.log", args.timeout)
        usage = io.audit_events(directory / "events.jsonl")
        result = io.read(directory / "response.json")
        schema_validate(result, schema)
        state.update(status="success", usage=usage)
        return result
    except BaseException as exc:
        usage = []
        event_file = directory / "events.jsonl"
        if event_file.exists():
            for line in event_file.read_text().splitlines():
                try:
                    e = json.loads(line)
                    if e.get("usage"):
                        usage.append(e["usage"])
                except ValueError:
                    pass
        state.update(status="failed", error=type(exc).__name__ + ": " + str(exc), known_usage=usage)
        raise
    finally:
        state.update(ended=time.time(), seconds=time.time() - start)
        io.dump(directory / "status.json", state)

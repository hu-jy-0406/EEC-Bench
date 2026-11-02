"""List contract entities that fall near the owner's granularity boundaries (2026-10-27).

Reads the first-200 v1 contracts and writes granularity_candidates.json with, per category,
the entities (episode, name, description, shots, motion claims that involve them) found by
keyword matching. Keyword matching is approximate; the examples shown to the owner are picked
and checked by hand from this list.

Usage: python mine_granularity.py
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent
DELIV = ROOT.parent / "episode_contracts_20260921" / "deliverables"

WORN_HELD = r"\b(phone|smartphone|gun|pistol|rifle|knife|sword|bag|backpack|purse|handbag|briefcase|suitcase|hat|cap|helmet|glasses|sunglasses|goggles|watch|wristwatch|necklace|badge|ring|earring|scarf|tie|mask|glove|gloves|umbrella|cane|stick|staff|letter|envelope|card|book|notebook|camera|cup|mug|glass|bottle|flashlight|torch|microphone|guitar|violin|key|keys|wallet|map|photo|photograph|tablet|remote|cigarette|pipe|jacket|coat|shoe|shoes|boots|belt)\b"
STRUCTURE = r"\b(door|doors|doorway|window|windows|floor|ceiling|stairs|staircase|steps|railing|banister|column|columns|pillar|fence|gate|roof|wall|walls|curtain|curtains|blinds|sconce|lamp|lamps|light|lights|chandelier|rug|carpet|fireplace|mirror|shelf|shelves|bookshelf|counter|bar|archway|arch|balcony|corridor)\b"
FURNITURE = r"\b(chair|chairs|sofa|couch|table|desk|bed|bench|stool|cabinet|dresser|armchair|wardrobe|nightstand|cart|stand)\b"
COLLECTION = r"(collective|group of|crowd|guests|people|spectators|onlookers|pedestrians|papers|buildings|trees|books|bottles|boxes|cars|students|soldiers|dancers|audience)"


def load_ids():
    ids = []
    for line in (DELIV / "priority_200.jsonl").read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            ids.append(r.get("episode_id") or r.get("id"))
    return ids


def main():
    out = {"worn_held_objects": [], "worn_held_in_character_descriptions_with_action": [],
           "structure_objects": [], "furniture_objects": [], "collections": []}
    for eid in load_ids():
        c = json.loads((DELIV / "episodes" / eid / "contract.json").read_text())
        shots = {s["shot_id"]: s["text"] for s in c["prompt"]["shots"]}
        motion = [q for q in c["claims"] if q["dimension"] == "motion"]
        for key, e in c["entity_descriptions"].items():
            kind = key.split()[0]
            text = (e["name"] + " " + e["description"]).lower()
            sched = [k for k, s in c["entity_schedule"].items()
                     if e["name"] in s["characters"] + s["places"] + s["objects"]]
            acts = [q["expected"] for q in motion if key in q["entity_ids"]]
            row = {"episode": eid, "key": key, "name": e["name"], "description": e["description"],
                   "scheduled": sched, "motion_claims": acts}
            if kind == "Object" and re.search(WORN_HELD, text):
                out["worn_held_objects"].append(row)
            if kind == "Object" and re.search(STRUCTURE, text):
                out["structure_objects"].append(row)
            if kind == "Object" and re.search(FURNITURE, text):
                out["furniture_objects"].append(row)
            if re.search(COLLECTION, text):
                out["collections"].append(row)
            if kind == "Character":
                items = set(re.findall(WORN_HELD, e["description"].lower()))
                for q in motion:
                    if key in q["entity_ids"]:
                        hit = items & set(re.findall(WORN_HELD, q["expected"].lower()))
                        if hit:
                            out["worn_held_in_character_descriptions_with_action"].append(
                                {**row, "items": sorted(hit), "action": q["expected"],
                                 "shot": q["shot_ids"][0], "shot_text": shots.get(q["shot_ids"][0], "")})
    (ROOT / "granularity_candidates.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print({k: len(v) for k, v in out.items()})


if __name__ == "__main__":
    main()

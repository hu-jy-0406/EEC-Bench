#!/usr/bin/env python3
"""Old-run confirmed V-V issues counted as unspecified because the subject was an agent-added wall, floor, ground or
similar surface (n...), and the same videos' confirmed background issues in this rerun with their subjects' labels
and contract roles. Also counts the raw WeDetect candidates with wall/floor-type labels in the cited frames.
Writes wall_issue_audit.json; the matching of old to new issue is done by reading (see wall_issue_matches.json)."""
import json, re
from pathlib import Path
EXP = Path(__file__).resolve().parent
WALL = re.compile(r'墙|壁纸|瓷砖|砖|地面|地板|天花|wall|tile|floor|ground|ceiling|facade', re.I)
DET_WALL = re.compile(r'墙|壁纸|瓷砖|砖|地面|地板|天花板|天花|地砖')


def read(p):
    return json.loads(Path(p).read_text())


def states():
    out = {}
    for path in (EXP / 'runs').glob('*/progress.json'):
        for tid, st in read(path)['tasks'].items():
            if st.get('status') == 'success' and st.get('mode') == 'reuse_vv':
                out[tid] = st
    return out


def roles(case):
    c = read(case / 'contract.json')
    desc = c.get('entity_descriptions') or {}
    return {k: v.get('label') for k, v in desc.items()}


def main():
    st = states()
    rows = read(EXP / 'unspecified_issues.json')
    out = []
    for r in rows:
        if r['side'] != 'old':
            continue
        n_subj = [s for s in r['subjects'] if s['key'].startswith('n')]
        if not any(WALL.search(s['name']) for s in n_subj):
            continue
        s = st[r['task']]
        case = Path(s['case_dir'])
        role = roles(case)
        old_units = {u['unit_id']: u for u in read(Path(s['source_attempt']) / 'results/vv_review/result.json')['units']}
        ou = old_units[r['unit']]
        det_hits = []
        for ref in ou['frame_refs']:
            p = case / f'entities/detections/{ref["shot_id"]}/frame_{ref["frame_id"]:06d}/detections.json'
            if p.is_file():
                for d in read(p)['detections']:
                    if DET_WALL.search(d['label']):
                        det_hits.append((ref['shot_id'], ref['frame_id'], d['label'], round(d['score'], 2)))
        rv = read(Path(s['output_dir']) / 'vv_review/result.json')
        sc = read(Path(s['output_dir']) / 'episode_scoring/result.json')
        lab = {u['unit_id']: {x['entity_key']: x['label'] for x in u.get('subject_entities') or []} for u in sc['unit_scores']}
        ent = {e['entity_key']: e for e in rv.get('entities') or [] if isinstance(e, dict)}
        new = []
        for u in rv['units']:
            if u['verdict'] not in ('confirmed', 'uncertain', 'rejected'):
                continue
            if u['subcategory'] not in ('setting_background', 'background_drift', 'environment_lighting', 'object_identity'):
                continue
            subj = [x['entity_key'] for x in u.get('entity_refs') or [] if x.get('role') == 'subject']
            new.append(dict(unit=u['unit_id'], verdict=u['verdict'], scope=u['scope'], subcategory=u['subcategory'],
                            subjects=[dict(key=k, name=(ent.get(k) or {}).get('name'), label=lab.get(u['unit_id'], {}).get(k),
                                           contract_role=role.get(str((ent.get(k) or {}).get('prompt_entity_id'))))
                                      for k in subj],
                            frames=[(f['shot_id'], f['frame_id']) for f in u['frame_refs']], description=u['description']))
        out.append(dict(task=r['task'], old_unit=r['unit'], old_subjects=r['subjects'], old_description=r['description'],
                        old_frames=[(f['shot_id'], f['frame_id']) for f in ou['frame_refs']],
                        detector_wall_candidates=det_hits, new_units=new))
    (EXP / 'wall_issue_audit.json').write_text(json.dumps(out, indent=1, ensure_ascii=False) + '\n')
    for o in out:
        print('=' * 100)
        print(o['task'], o['old_unit'], [(s['key'], s['name'][:40]) for s in o['old_subjects']])
        print('  OLD:', o['old_description'][:200])
        print('  detector wall-type candidates in cited frames:', len(o['detector_wall_candidates']), sorted({h[2] for h in o['detector_wall_candidates']}))
        for n in o['new_units']:
            print('  NEW', n['unit'], n['verdict'], n['subcategory'], [(x['key'], (x['name'] or '')[:25], x['label'], x['contract_role']) for x in n['subjects']], '|', n['description'][:150])


if __name__ == '__main__':
    main()

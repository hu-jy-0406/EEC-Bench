"""Read-only evidence audit and final measured-run ledger; no inference."""
import csv
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
CASE = ROOT / 'run'
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p, x): p.write_text(json.dumps(x, indent=2, ensure_ascii=False) + '\n')


def main():
    s = read(CASE / 'summary.json'); runtime = read(CASE / 'pipeline_runtime.json')
    assert s['status'] == runtime['status'] == 'success'
    assert s['completed_through'] == 'full'
    assert s['appearance']['status'] == 'success'
    assert all(r['status'] == 'success' for r in runtime['stages'])
    manifest = read(CASE / 'raw_manifest.json')
    frames = [f for shot in manifest['shots'] for f in shot['frames']]
    assert len(frames) == 18
    for f in frames: assert sha(f['path']) == f['sha256']
    provenance = read(CASE / 'provenance.json')
    assert provenance['inference_reuse'] is False
    changed = [p for p, h in provenance['source_hashes'].items() if sha(p) != h]
    assert not changed, changed
    frontend = read(CASE / 'entities/run.json')
    assert frontend['status'] == 'success'
    assert all(r['reused_from'] is None for r in frontend['shots'])
    assert '--detections' not in next(r for r in runtime['stages'] if r['stage'] == 'detection_and_clustering')['command']
    sources = []; total = dict(input_tokens=0, cached_input_tokens=0, cache_write_input_tokens=0, output_tokens=0)
    dollars = 0; model_calls = 0
    for row in s['calls']:
        p = CASE / row['call'] / 'status.json'; state = read(p)
        assert state['status'] == 'success', (str(p), state['status'])
        usage = state.get('usage', state.get('known_usage', []))
        if isinstance(usage, dict): usage = [usage]
        for u in usage:
            if not u: continue
            model_calls += 1
            for key in total: total[key] += u.get(key, 0)
            i, c, w, o = (u.get(k, 0) for k in total)
            assert 0 <= c + w <= i
            dollars += ((i-c-w)*10+c+w*12.5)*(2 if i>272000 else 1)/1e6
            dollars += o*(75 if i>272000 else 50)/1e6
        sources.append(dict(path=str(p), sha256=sha(p)))
    assert total['input_tokens'] + total['output_tokens'] == s['total_tokens']
    assert abs(dollars - s['standard_api_equivalent_usd']) < 1e-8
    assert sum(r['total_tokens'] for r in s['stages']) == s['total_tokens']
    assert abs(sum(r['standard_api_equivalent_usd'] for r in s['stages'])-dollars) < 1e-8
    report = read(CASE / 'appearance/report/results.json')['studies'][0]
    pixel_audit = read(CASE / 'appearance/report/audit.json'); assert pixel_audit['passed']
    dino = read(CASE / 'appearance/canonical/dino_runtime.json')
    assert dino['appearance_count'] == pixel_audit['appearances_pixel_checked']
    lamp = [e for e in report['entities'] if 'lamp' in e['name'].lower() or '台灯' in e['name']]
    save(ROOT / 'audit.json', dict(passed=True, fresh_frontend_geometry_identity_dino_codex=True,
        original_frames=len(frames), source_hashes_unchanged=len(provenance['source_hashes']),
        appearance_audit=pixel_audit, model_calls=model_calls, usage=total,
        total_tokens=s['total_tokens'], standard_api_equivalent_usd=dollars,
        elapsed_seconds=s['elapsed_seconds'], appearance=s['appearance'], lamp_entities=lamp,
        within={k:v['spatial']['summary'] for k,v in s['within_shots'].items()},
        boundaries={k:dict(presence=v['presence']['summary'],spatial=v['spatial']['summary'])
                    for k,v in s['boundaries'].items()},call_sources=sources))
    dest = ROOT / 'source_snapshot'; dest.mkdir(exist_ok=True)
    for path in provenance['source_hashes']:
        p = Path(path); rel = p.relative_to(Path(__file__).resolve().parents[2])
        target=dest/rel; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,target)
    handle=read(ROOT/'active_run.json'); handle['status']='complete';save(ROOT/'active_run.json',handle)
    print(json.dumps(read(ROOT/'audit.json'),ensure_ascii=False,indent=2))


if __name__ == '__main__': main()

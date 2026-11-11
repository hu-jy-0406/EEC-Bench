#!/usr/bin/env python3
"""Content-addressed release of the current three geometry frontends and exact outputs."""
import argparse, ast, hashlib, json, shutil, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
CASE=ROOT/'EECBench/experiments/study_inconsistent_3'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def freeze(out):
    from run_isolated_shot_static_3d import owned_compute_job
    owned_compute_job()
    out.mkdir(parents=True,exist_ok=False)
    code=ROOT/'EECBench/scripts'
    names=['run_geocalib_boxer','evaluate_geocalib_boxer','audit_geocalib_boxer','guard_geocalib_boxer_gpu',
        'run_sparse_scene_3d','run_isolated_shot_static_3d','audit_isolated_shot_static_3d',
        'build_three_method_static_scenes','render_three_method_static_scenes','audit_three_method_static_scenes',
        'evaluate_static_global_reprojection','freeze_static_geometry_pipeline']
    paths=set();pending=[code/(n+'.py') for n in names]
    while pending:
        p=pending.pop()
        if p in paths:continue
        paths.add(p)
        for node in ast.walk(ast.parse(p.read_text())):
            mods=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) else []
            for mod in mods:
                q=code/((mod or '').split('.')[0]+'.py')
                if q.is_file() and q not in paths:pending.append(q)
    for pattern in ['sparse_scene_3d*','shot_motion_isolated*','partial_scene*','shot_spatial_relations*']:
        paths.update((ROOT/'EECBench/prompts').glob(pattern))
    for pattern in ['test_geocalib_boxer.py','test_isolated_shot_static_3d.py','test_three_method_static_scenes.py','test_static_global_reprojection.py']:
        paths.add(ROOT/'EECBench/tests'/pattern)
    for sid in ['shot1','shot3']:
        for name in ['source_shot.json','agent_review.json','review/input.json','review/prompt.txt','review/request.json','review/response.json','review/status.json']:
            paths.add(CASE/'shot_static_3d_isolated_20260914/run01'/sid/name)
        paths.add(CASE/'sparse_scene_3d_20260913/run01'/('scene_'+sid)/'scene.json')
        paths.add(CASE/'geocalib_boxer_20260913/calibration'/(sid+'.json'))
        paths.add(CASE/'wedetect_shot_entities_20260912/run01/shots'/sid/'entities.json')
        paths.update((CASE/'wedetect_shot_entities_20260912/frames'/sid).glob('*.jpg'))
        for method in ['codex','boxer_codex_camera','boxer_geocalib']:
            for name in ['Gs_global.json','Gs_frames.json']:
                paths.add(CASE/'three_method_static_3d_20260914/run01'/method/sid/name)
        for variant in ['geocalib','codex_camera']:
            paths.update((CASE/'geocalib_boxer_20260913/predictions'/variant/sid).glob('frame_*.json'))
    for name in ['provenance.json','README.md','audit.json']:
        paths.add(CASE/'geocalib_boxer_20260913'/name)
    for name in ['README.md','audit.json','summary.json','reprojection_evaluation/summary.json','reprojection_evaluation/observations.json','reprojection_evaluation/README.md','reprojection_evaluation/audit.json']:
        paths.add(CASE/'three_method_static_3d_20260914/run01'/name)
    records=[]
    for p in sorted(paths):
        rel=p.relative_to(ROOT);q=out/'payload'/rel;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
        records.append(dict(path=str(rel),sha256=sha(q),bytes=q.stat().st_size))
    pip=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True)
    (out/'cpu_requirements.txt').write_text(pip)
    env=CASE/'geocalib_boxer_20260913/venv/bin/python'
    (out/'geometry_requirements.txt').write_text(subprocess.check_output([str(env),'-m','pip','freeze'],text=True))
    manifest=dict(version='static-geometry-20260914-v1',preferred_method='boxer_geocalib',
        preferred_scope='best current paired in-sample 2D reprojection IoU; not 3D ground truth',
        files=records,environment_files={n:sha(out/n) for n in ['cpu_requirements.txt','geometry_requirements.txt']},
        model_provenance=json.loads((CASE/'geocalib_boxer_20260913/provenance.json').read_text()),
        caveat='Code, prompts, inputs and outputs are copied. Large model weights remain external, pinned by digest. Model-service reruns are not guaranteed bitwise deterministic. Absolute source paths are historical provenance; replay uses the pinned workspace inputs.')
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    (out/'manifest.sha256').write_text(sha(out/'manifest.json')+'  manifest.json\n')
    (out/'README.md').write_text('''# 固定版本 static-geometry-20260914-v1

三种方法及独立 shot 动静划分、质量融合、重投影评测的源码依赖闭包、提示词、输入、输出均在 payload 下；manifest.json 逐文件校验。大权重不复制，保存官方提交与权重 SHA256、当前环境包版本。特别固定 GeoCalib + Boxer 的共享内参/重力、无深度输入、960 输入、固定实体名单与融合规则。

验证：`python EECBench/scripts/freeze_static_geometry_pipeline.py --verify RELEASE_DIR`

此版本固定的是现有固定机位六帧实验。不要把相机平移全零的前端推广到移动相机；换前端/阈值必须创建新版本。不得覆盖此目录。原模型输出已保存，后续评分直接读取冻结 Gs；不重新抽样几何。代码快照是隔离存档，非对整个脏仓库的提交。
''')
    print(json.dumps(dict(release=str(out),files=len(records),manifest_sha256=sha(out/'manifest.json'))))
def verify(out):
    expected=(out/'manifest.sha256').read_text().split()[0]
    if sha(out/'manifest.json')!=expected:raise ValueError('Manifest modified')
    m=json.loads((out/'manifest.json').read_text());bad=[]
    for r in m['files']:
        p=out/'payload'/r['path']
        if not p.is_file() or sha(p)!=r['sha256']:bad.append(r['path'])
    for n,h in m['environment_files'].items():
        if sha(out/n)!=h:bad.append(n)
    if bad:raise ValueError(bad)
    print(json.dumps(dict(verified=True,files=len(m['files']),manifest_sha256=expected)))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path);p.add_argument('--verify',type=Path);a=p.parse_args()
    if a.verify:verify(a.verify)
    elif a.out:freeze(a.out)
    else:p.error('--out or --verify required')

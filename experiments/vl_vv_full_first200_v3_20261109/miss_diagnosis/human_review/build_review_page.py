#!/usr/bin/env python3
"""Build the human-review page for the 19 primary audit findings (owner request 2026-11-10: "给我做一个带图的网页").

Inputs (read only): ../audit20_summary.json (finding order, ledger/V-V outcome), ../audit20/<task>/{blind_findings.json,
trace.json, frames.json, prompt.txt, entities.txt}, markers.json (approximate regions placed by Claude after looking at
each cited frame; not detector output).
Outputs: img/<num>-<model>_<Shot>_f<k>.jpg (unchanged copies of every keyframe of each shot a finding involves) and
unspecified_audit_review.html (page_template.html with the data inlined). Chinese texts are Claude's translations of the
auditors' English findings; the English originals are kept in the page.
"""
import json, re, shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIAG = HERE.parent
MODEL = {'cinetrans': 'CineTrans-DiT', 'holocine': 'HoloCine', 'storymem': 'StoryMem', 'wan21': 'Wan2.1', 'wan22': 'Wan2.2'}
LEDGER_ZH = {
    'not_recorded': '账本里没有这个物体',
    'recorded_in_some_relevant_shots': '只在部分相关镜头里进了账本',
    'same_entity_in_all_relevant_shots': '所有相关镜头都记成同一个实体',
    'separate_entities_per_shot': '每个镜头各记成一个实体，没有连起来',
}
VV_ZH = {
    'no_candidate': 'V-V 检测没有提出这个问题',
    'rejected': 'V-V 提出了，但复核否掉了',
    'confirmed_specified_subjects_only': 'V-V 确认了，但问题主体只记了 specified 实体，不算涉及 unspecified',
}
NIGHT_ZH = {
    'priority_036__holocine/A2': 'C、D 两组确认了这个问题，主体是 unspecified 的窗台绿植（C：ge0010；D：检测新增的 n1）。',
    'priority_055__wan21/A1': 'C、C2 两组确认了女子身后陈设不一致，主体含 unspecified 实体（C：吊柜 ge0002；C2：检测新增的“背景搁架”）。',
    'priority_078__wan22/A1': 'E2 组（逐物体检查，推理 medium）提出了电视柜的变化，复核判为“不确定”。',
}
NIGHT_DEFAULT = '昨晚 9 组试验都没有把这一条确认为涉及 unspecified 实体的问题。'
# Full videos the owner asked for in the review notes (2026-11-10). Unchanged copies; start/end = the shot inside the
# file; keyframe times from the case's raw_manifest.json (timestamp_sec), 16 fps.
RUNS = Path('/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/vl_vv_full_first200_20261107/runs')
VIDEOS = {
    'priority_036__holocine/A1': dict(case='cpu_b/holocine/priority_036_Dc2ULKEj0tw_s00012_n4_clean_v2', shot='Shot1',
                                      name='036-holocine_episode.mp4',
                                      label='HoloCine 生成的完整 episode（20 秒，4 个镜头）。Shot1 = 0–5.06 秒，第 0–80 帧。'),
    'priority_096__holocine/A1': dict(case='cpu_c/holocine/priority_096_KDFdX20yFP0_s00118_n4_clean_v2', shot='Shot3',
                                      name='096-holocine_episode.mp4',
                                      label='HoloCine 生成的完整 episode（20 秒，4 个镜头）。Shot3 = 10.06–15.06 秒，第 161–240 帧；打开时从 Shot3 开头播放。'),
    'priority_127__wan21/A1': dict(case='cpu_c/wan21/priority_127_A-Ckh0slywY_s00026_n8_clean_v2', shot='Shot5',
                                   name='127-wan21_Shot5.mp4',
                                   label='Wan2.1 的 Shot5 完整片段（5.06 秒，81 帧）。这个模型每个镜头单独生成一段视频。'),
}


def video_for(key):
    v = VIDEOS.get(key)
    if not v: return None, None
    m = read(RUNS / v['case'] / 'attempt_01/work/case/raw_manifest.json')
    s = [x for x in m['shots'] if x['shot_id'] == v['shot']][0]
    start = s.get('segment_start_sec') or 0.0
    rel = f"video/{v['name']}"
    return dict(src=rel, start=start, end=start + s['segment_duration_sec'], fps=16, shot=v['shot'], label=v['label'],
                keyframes=[f['timestamp_sec'] for f in s['frames']]), (rel, s['video_path'])
ZH = {
    'priority_013__cinetrans/A1': (
        '男子右侧站着的女子（Shot1、Shot3 没戴帽子；这两个镜头的文本没写她，可能是合同里戴帽子的女子没画出帽子）',
        '同一位置、男子身旁的女子在两个镜头里像两个人：Shot1 年纪较大，及肩发带刘海，围深蓝围巾；Shot3 更年轻，短发波波头，白衬衫配深色领带。两人也都不像 Shot2、Shot4 里戴帽子的女子。'),
    'priority_013__cinetrans/A2': (
        '红椅上方的绿色玻璃瓶状物（可能是合同里的绿色玻璃灯或棕榈叶）',
        'Shot1 是一个实心绿色圆柱，Shot3 同一位置只剩半透明的淡影；Shot2 这个位置换成了绿色皮椅，Shot4 换成支架上的亮绿色玻璃灯罩。'),
    'priority_013__cinetrans/A3': (
        'Shot2 桌上的黑色圆形编织物（Shot2 文本没写；可能是合同里带提手的黑包）',
        '桌上同一位置，Shot2 是没有提手的圆顶黑色编织物，Shot4 是带金属扣和提手的光面黑包。'),
    'priority_025__storymem/A1': (
        '墙上的电灯开关',
        'Shot2 里年轻男子左侧的平墙上一直有一个白色电灯开关。prompt 说 Shot4 回到同一个反向视角，但 Shot4 这一侧是拱形壁龛，没有开关。'),
    'priority_025__storymem/A2': (
        '雕花玻璃茶壶、蓝色摆件、红框植物画，以及一排放瓶子的拱形壁龛',
        'Shot4 回到的反向视角里，左侧壁龛放着雕花玻璃茶壶和蓝色摆件，上方挂红框植物画，右侧是一排放瓶子的拱形壁龛。Shot2 拍同一处时都没有这些，只有平墙、一幅深色框的画和一个放三个小摆件的壁龛。'),
    'priority_036__holocine/A1': (
        '右下角的第二架小无人机',
        'f5 时画面右下边缘突然出现第二个像无人机的物体（白顶、细黑竖杆、红色底部），f0–f4 都没有；这时 prompt 里的无人机正在凸窗旁。'),
    'priority_036__holocine/A2': (
        '凸窗窗台上的绿植',
        'Shot4 每一帧凸窗底部都有一排小绿植，Shot1 里同一扇窗的窗台是空的。'),
    'priority_036__holocine/A3': (
        '车库门上方的深色雨棚',
        'Shot4 里车库门和砖柱上方伸出一个深灰色门廊雨棚，遮住凸窗左上角；Shot1 这里没有雨棚，只有白色车库门卷帘盒和一盏壁灯。'),
    'priority_036__holocine/A4': (
        '车库里的绿色机器（割草机）',
        '男子左侧车库里的绿色机器，在 Shot1 是装在灰色带轮支架上的深绿色方形割草机，在 Shot3 变成一个亮黄绿色的光滑圆顶。'),
    'priority_047__storymem/A1': (
        '海报墙上的白色告示纸',
        'Shot2 f0–f1 和 Shot6 f5 中，开关面板左下方挂着一张白色告示（顶部有小照片），两处与开关的相对位置一致；Shot1 f1–f5 同一位置在画面内，却是空墙。'),
    'priority_047__storymem/A2': (
        '后墙的置物架、两条白色竖幅和红色徽标',
        'Shot5 两人身后，房间后部有放东西的墙架、两条白色竖幅（中间是红色徽标）和海报；Shot4 越过年长男子的背朝同一方向看，后墙却是空的，只有一架梯子和一面旗。'),
    'priority_055__wan21/A1': (
        '女子身后的背景陈设（木质吊柜、台面杂物、深色盒子、放金色物件的架子）',
        '女子两个反打镜头里，身后的陈设没有延续：Shot2 右侧台面上方有木质吊柜，台面上放着瓶罐；Shot4 同一室内、台面仍在她右后方，却没有吊柜，换成一排放金色物件的开放式架子，台面上一个深色盒子里有发光的金色物件。'),
    'priority_078__wan22/A1': (
        '电视下方的电视柜',
        '同一个客厅角落（挂钟下方的电视，右侧是走廊），Shot2 电视放在带抽屉的白色矮柜上，Shot5 变成深色木质或黑色的电视架，两边有黑色机顶盒。'),
    'priority_096__holocine/A1': (
        '部分电视屏幕上 prompt 没写的画面（戴头盔或兜帽的人像、白色圆形物）',
        '从 f4 起，十块屏幕中的四块（右上、中排左边两块、右下）从淡蓝色人像网格突然换成深色画面（戴头盔或兜帽的人像、圆形物体），右下那块在 f5 又变了一次；其余屏幕保持网格。'),
    'priority_120__storymem/A1': (
        '西装男子手里的指挥棒或细棍',
        'f0 西装男子的右手在画面右边缘拿着一根细木棍（黑头指挥棒或铅笔）；f1–f2（以及 f4）他已经转身、放下手臂，棍子还悬在原处，没有手或支撑物拿着它。'),
    'priority_126__cinetrans/A1': (
        '画面左侧的木质躺椅（Shot1）',
        '左侧的躺椅在 f0 像蒙着青色和红色布面的椅子，f1–f5 变成光秃的浅色木架，上面搭着一块白布，木架的形状在帧间也不断变化。'),
    'priority_126__cinetrans/A2': (
        '条纹椅旁的小圆边桌',
        'Shot2 条纹椅旁是一张实心的棕色木质圆桌；Shot4 从同一方向看同一把椅子和遮阳伞，桌面变成灰色、半透明，像幻影。'),
    'priority_126__cinetrans/A3': (
        '条纹椅座上的蓝白色毛巾或包',
        'Shot2 每一帧条纹椅座上都有一件蓝白图案的东西；Shot4 同一把椅子在画面里，没人碰过，东西却不见了。'),
    'priority_127__wan21/A1': (
        '怪物爪中的深蓝小布',
        'f0 怪物的右爪（画面右侧）攥着一块深蓝色小布或丝带；从 f1 起爪子空了，地上也看不到掉落的同色布。'),
}


def read(p):
    return json.loads(Path(p).read_text())


def parse_prompt(text):
    out = {}
    for block in re.split(r'\n\s*\n', text.strip()):
        m = re.match(r'^(GLOBAL|Shot\d+):\s*(.*)$', block.strip(), re.S)
        if m: out[m.group(1)] = ' '.join(m.group(2).split())
    return out


def main():
    summary = read(DIAG / 'audit20_summary.json')
    markers = read(HERE / 'markers.json')
    img = HERE / 'img'; img.mkdir(exist_ok=True)
    videos, findings, files = {}, [], {}
    for f in summary['primary']:
        task, fid = f['task'], f['id']; key = f'{task}/{fid}'
        num, mkey = task.split('_')[1], task.split('__')[1]
        a = DIAG / 'audit20' / task
        blind = [x for x in read(a / 'blind_findings.json')['primary'] if x['id'] == fid][0]
        trace = [x for x in read(a / 'trace.json')['primary'] if x['id'] == fid][0]
        frames = read(a / 'frames.json')
        prompt = parse_prompt((a / 'prompt.txt').read_text())
        shots = sorted(blind['shots'], key=lambda s: int(s[4:]))
        for shot in shots:
            for k, src in enumerate(frames[shot]):
                name = f'img/{num}-{mkey}_{shot}_f{k}.jpg'
                if name not in files:
                    shutil.copyfile(src, HERE / name); files[name] = str(HERE / name)
        if task not in videos:
            ents = [ln[2:].strip() for ln in (a / 'entities.txt').read_text().splitlines() if ln.startswith('- [')]
            videos[task] = dict(task=task, num=num, model=MODEL[mkey], mkey=mkey, shots=len(frames), entities=ents,
                                global_prompt=prompt.get('GLOBAL', ''), findings=[])
        videos[task]['findings'].append(f'{num}-{fid}')
        obj_zh, what_zh = ZH[key]
        video, copy = video_for(key)
        if copy:
            (HERE / 'video').mkdir(exist_ok=True)
            shutil.copyfile(copy[1], HERE / copy[0]); files[copy[0]] = str(HERE / copy[0])
        findings.append(dict(fid=f'{num}-{fid}', task=task, id=fid, num=num, model=MODEL[mkey], mkey=mkey,
                             scope=f['scope'], sure=f['sure'], obj_zh=obj_zh, what_zh=what_zh, obj_en=f['entity'],
                             what_en=f['what'], shots=shots, cited=blind['frames'], markers=markers[key],
                             prompt={s: prompt.get(s, '') for s in shots},
                             ledger_zh=LEDGER_ZH[trace['ledger_status']],
                             # trace.json holds a string, a list or null here; the page expects a list
                             ledger_ids=[x for x in ([trace.get('ledger_entity')] if isinstance(trace.get('ledger_entity'), str)
                                                     else trace.get('ledger_entity') or [])],
                             vv_zh=VV_ZH[trace['vv_outcome']], trace_note=trace.get('note', ''),
                             night_zh=NIGHT_ZH.get(key, NIGHT_DEFAULT), video=video))
    data = dict(generated='2026-11-10', videos=list(videos.values()), findings=findings)
    blob = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    page = (HERE / 'page_template.html').read_text().replace('__DATA_JSON__', blob)
    (HERE / 'unspecified_audit_review.html').write_text(page)
    (HERE / 'files_map.json').write_text(json.dumps(files, indent=1) + '\n')
    print(len(findings), 'findings,', len(videos), 'videos,', len(files), 'images,', len(page), 'page bytes')


if __name__ == '__main__':
    main()

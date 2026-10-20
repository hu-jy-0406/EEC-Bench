"""Assistant's matching for the five videos first run with the current pipeline here, plus R1 English summaries.

Same rules as the comparison page: an issue matches an artifact when it reports the same physical
discrepancy; a control is a thing that should not be flagged.
"""
import json
from pathlib import Path

A = {}

def run(key, rid, matches, notes=None):
    A.setdefault(key, dict(runs={}))['runs'][rid] = dict(matches=matches, notes=notes or {})

def n(en, assessment):
    return dict(en=en, assessment=assessment)

run('p014_holocine', 'v2/run_a', {'A1': ['I1'], 'C1': ['I2']}, {
    'I1': n('The older man wears a black beret in both of his shots instead of the requested earflap hat; in Shot2 the woman also clasps her hands instead of letting her arms hang.', 'Matches A1'),
    'I2': n('Shot3 frame 0 still shows Shot2\'s two-person wide view; the close-up of the woman appears about a second later.', 'Debatable: a sub-second late cut, which the rules treat as a timing offset (control C1)'),
})
run('p014_holocine', 'v2/run_b', {'A1': ['I4'], 'C1': ['I2', 'I3']})
run('p014_holocine', 'v2/run_c', {'A1': ['I5'], 'C1': ['I1', 'I3', 'I4']})

run('p032_wan22', 'v2/run_a', {}, {
    'I1': n('In Shot6 the man\'s hair looks tidier and swept back compared with the shorter cut of Shots 1-5; beard and shirt check differ too.', 'Debatable: small difference seen at a much wider framing'),
    'I2': n('Shot6: the cat walks off to the right behind the lamp instead of lowering itself over the table edge and disappearing below.', 'Real, not one of the key artifacts'),
    'I3': n('Proposed: the kitchen\'s layout and colors differ across Shots 1-5.', 'Debatable; review rejected it (A2 concerns the oven itself)'),
})
run('p032_wan22', 'v2/run_b', {'A1': ['I1'], 'A2': ['I2'], 'A4': ['I3']})
run('p032_wan22', 'v2/run_c', {'A2': ['I3']})

run('p047_storymem', 'v2/run_a', {'A1': ['I1'], 'A2': ['I2'], 'A3': ['I3']}, {
    'I1': n('Shot6 frame 0 is covered by red-orange blur and dark areas; scene and person are unreadable; later frames are normal.', 'Matches A1'),
    'I2': n('The older man\'s beard and mustache are dark, although the text asks for white.', 'Matches A2'),
    'I3': n('The Sleeveless man\'s bare arm appears at the upper-right edge instead of the upper-left.', 'Matches A3'),
})
run('p047_storymem', 'v2/run_b', {'A1': ['I2']})
run('p047_storymem', 'v2/run_c', {'A1': ['I2']})

run('p069_wan21', 'v2/run_a', {'A2': ['I1'], 'A3': ['I1'], 'A5': ['I2']}, {
    'I1': n('The protagonist\'s jacket changes from red-black diamond quilting (Shot1) to fine red-black stripes (Shot3); his gun\'s shape and yellow strap differ too.', 'Matches A2 and A3'),
    'I2': n('The short figure is a short-haired woman in a brown coat in Shot2 but a man in a dark long coat in Shot4.', 'Matches A5'),
    'I3': n('The long-coat adult changes from straight hair, gray coat and dark-red trousers (Shot2) to curly hair and an olive coat (Shot4).', 'Real, not one of the key artifacts'),
    'I4': n('Shot3\'s stairwell has pale-green regular block walls, unlike the weathered green paint and bare brick of Shot1.', 'Debatable: the prompt itself describes a green-brick stairwell'),
})
run('p069_wan21', 'v2/run_b', {'A2': ['I2'], 'A3': ['I2'], 'A5': ['I4']})
run('p069_wan21', 'v2/run_c', {'A2': ['I1'], 'A3': ['I2']})

run('p165_cinetrans', 'v2/run_a', {'A1': ['I1'], 'A2': ['I2', 'I3']}, {
    'I1': n('Proposed: Shot2 is not the specified single-person view; the counter and a woman behind it stay in frame.', 'Matches A1 in part (content only, no transition label); review rejected it'),
    'I2': n('Shot1: the visitor behind the counter looks like a woman with tied blond hair in a red striped top, not the described blond man.', 'Matches A2 (identity confusion)'),
    'I3': n('The receptionist behind the counter in Shot4 is a long-haired blonde in a dark top, unlike the brown-haired receptionist in a lilac top in Shots 1 and 3.', 'Matches A2'),
})
run('p165_cinetrans', 'v2/run_b', {'A1': ['I2', 'I3']})
run('p165_cinetrans', 'v2/run_c', {'A2': ['I2', 'I3'], 'A5': ['I1']})

Path('results_annotations.json').write_text(json.dumps(A, ensure_ascii=False, indent=2) + '\n')
print('ok', list(A))

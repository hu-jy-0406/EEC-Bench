"""Assistant's matching of each run's issues to reference artifacts, plus English summaries for the displayed runs.

Matching rule: an issue matches an artifact when it reports the same physical discrepancy,
even if it names the wrong shot (noted). Assessments start with Matches / Real / Debatable / Wrong.
"""
import json
from pathlib import Path

A = {}

def case(key, headline, takeaway=''):
    A[key] = dict(headline=headline, takeaway=takeaway, runs={})

def run(key, rid, matches, notes=None):
    A[key]['runs'][rid] = dict(matches=matches, notes=notes or {})

def n(en, assessment):
    return dict(en=en, assessment=assessment)

# ---------------- #002 Wan2.1 ----------------
case('p002_wan21', 'Cross-shot changes now carry both labels, and the changing face is found')
run('p002_wan21', 'v1/historical', {'A1': ['vl1'], 'A2': ['vl2']}, {
    'vl1': n('The same man switches to a dark collared shirt in Shot4, unlike the blue-gray T-shirt of the other shots.', 'Matches A1, but names Shot4 (the collared shirt is in Shot3) and is filed only as V-L'),
    'vl2': n('The sofa in Shot4 has a tall rounded back, unlike the low sofa of the earlier shots.', 'Matches A2, filed only as V-L'),
})
run('p002_wan21', 'v2/run_a', {'A1': ['I1'], 'A2': ['I2'], 'A3': ['I1'], 'A4': ['I3']}, {
    'I1': n('The man in Shot4 looks like someone else: shorter, flatter hair, lighter skin, a different face, and (it says) a collared shirt instead of the T-shirt.', 'Matches A3; also covers A1 but places the shirt in Shot4 (it is in Shot3)'),
    'I2': n('Shot4\'s seat is a tall wrap-around single chair, not the low sofa of Shots 1-3.', 'Matches A2, with both labels'),
    'I3': n('Shot1: arms stretched along the sofa back instead of resting low.', 'Matches A4'),
    'I4': n('Proposed: Shot4\'s all-dark-wood background does not fit the door and pale wall seen in Shots 1 and 3.', 'Debatable; review rejected it'),
})
run('p002_wan21', 'v2/run_b', {'A1': ['I1'], 'A2': ['I4'], 'A3': ['I2'], 'A4': []})
run('p002_wan21', 'v2/run_c', {'A1': ['I1'], 'A2': ['I3'], 'A3': ['I1'], 'A4': []})

# ---------------- #014 Wan2.1 ----------------
case('p014_wan21', 'The courtyard change is found in every new run; the hat finding is lost')
run('p014_wan21', 'v1/historical', {'A3': ['vl1'], 'A4': ['vl2']}, {
    'vl1': n('The older man wears a black wide-brim hat with no earflaps.', 'Matches A3'),
    'vl2': n('Shot4 starts with his back to the camera instead of a lowered screen-left profile.', 'Matches A4'),
})
run('p014_wan21', 'v2/run_a', {'A1': ['I1'], 'A2': ['I2']}, {
    'I1': n('The courtyard\'s buildings differ in type, material and layout: old brown-gray stone (Shot1), cream arched facade (Shot2), low beige house (Shot3). Camera angle cannot explain it.', 'Matches A1, with both labels'),
    'I2': n('The woman\'s gray coat changes: belted with no visible double buttons in Shot1, big double-breasted buttons in Shot3, open in Shot2.', 'Matches A2'),
})
run('p014_wan21', 'v2/run_b', {'A1': ['I2'], 'A2': ['I1'], 'A4': ['I3']})
run('p014_wan21', 'v2/run_c', {'A1': ['I2'], 'A2': ['I1'], 'A4': ['I3']})

# ---------------- #014 StoryMem (control) ----------------
case('p014_storymem', 'Control: the consistent courtyard is left alone')
run('p014_storymem', 'v1/historical', {})
run('p014_storymem', 'v2/run_a', {'C1': ['I2']}, {
    'I1': n('The older man\'s long scarf is plaid in Shot2 but shows wide horizontal bands in Shot4.', 'Debatable: the same broad check can read as bands at a different size'),
    'I2': n('Proposed: the buildings behind the courtyard look different from shot to shot.', 'Matches the control C1; review correctly rejected it'),
})
run('p014_storymem', 'v2/run_b', {'C1': ['I1']})
run('p014_storymem', 'v2/run_c', {'C1': ['I1']})

# ---------------- #028 Wan2.2 ----------------
case('p028_wan22', 'The turquoise woman\'s changing look and the blue chair are found')
run('p028_wan22', 'v1/historical', {}, {
    'vl1': n('Shot2: she does not support the incoming hand\'s wrist with her own hand.', 'Real, not one of the key artifacts'),
    'vl2': n('Shot1 opens with her eyes open, not nearly closed.', 'Real, not one of the key artifacts'),
})
run('p028_wan22', 'v2/run_a', {'A1': ['I2'], 'A2': ['I2'], 'A4': ['I4']}, {
    'I1': n('Shot1: the hand drifts from beside the ear toward the chin instead of holding the ear-side pose.', 'Debatable, minor'),
    'I2': n('The turquoise woman\'s look changes across her shots: shoulder-length waves in Shots 2/8, longer fuller curls in 4/6; the palm print in Shot8 differs from the scattered marks in 4/6.', 'Matches A1 and A2 (hair; faces not compared)'),
    'I3': n('Shot3: framing jumps between frame 0 and frame 1, like an unrequested cut.', 'Wrong: a smooth reframing against the same background, not a cut'),
    'I4': n('The returning blue chair is a small upright chair in Shots 1/5 but a wide lounger in Shots 3/7.', 'Matches A4, with both labels'),
})
run('p028_wan22', 'v2/run_b', {'A1': ['I4'], 'A2': ['I4'], 'A4': ['I3']})
run('p028_wan22', 'v2/run_c', {'A1': ['I2'], 'A2': ['I2'], 'A4': ['I1']})

# ---------------- #028 CineTrans ----------------
case('p028_cinetrans', 'One continuous take instead of eight shots is finally reported')
run('p028_cinetrans', 'v1/historical', {'A2': ['vl01', 'vl02']}, {
    'vl01': n('Throughout the long take the woman wears turquoise; the Robe woman\'s white bathrobe never appears.', 'Matches A2 in part: wrong look, filed only as V-L; the merge and the missing cuts go unmentioned'),
    'vl02': n('The shore shots show a lighter-haired, older-looking woman instead of the young brown-haired Turquoise woman.', 'Matches A2 in part, filed only as V-L'),
    'vl03': n('The shore shots show only her own hand at the ear; no incoming hand from the right.', 'Real, not one of the key artifacts'),
})
run('p028_cinetrans', 'v2/run_a', {'A1': ['I3'], 'A2': ['I1']}, {
    'I1': n('All eight shots show the same light-haired woman in turquoise; the two characters never alternate, and the robe and palm beach are missing.', 'Matches A2, with both labels'),
    'I2': n('The incoming hand never appears as a separate hand touching her cheek.', 'Real, not one of the key artifacts'),
    'I3': n('All seven required cuts are missing: neighbouring shots keep the same horizon, position and framing.', 'Matches A1, with both labels'),
})
run('p028_cinetrans', 'v2/run_b', {'A2': ['I1', 'I2'], 'A3': ['I3']})
run('p028_cinetrans', 'v2/run_c', {'A1': ['I4'], 'A2': ['I1', 'I2']})

# ---------------- #180 CineTrans ----------------
case('p180_cinetrans', 'Missing cuts and a first-frame flash are reported')
run('p180_cinetrans', 'v1/historical', {'A2': ['vl1', 'vl2']}, {
    'vl1': n('Shots 2 and 4 show the person in close-up instead of the hallway.', 'Matches A2'),
    'vl2': n('The hallway shots are filled by the person; Shot4 shows them too.', 'Matches A2 (second report of the same failure)'),
})
run('p180_cinetrans', 'v2/run_a', {'A1': ['I3'], 'A2': ['I1'], 'A3': ['I2']}, {
    'I1': n('Shots 2 and 4 should show the hallway and the open far door but keep showing the person.', 'Matches A2'),
    'I2': n('Shot1 frame 0 is much darker; brightness jumps back at frame 1.', 'Matches A3'),
    'I3': n('Shots that should cut to the hallway or a close-up keep the same frontal portrait; no cut happens.', 'Matches A1, with both labels'),
})
run('p180_cinetrans', 'v2/run_b', {'A1': ['I3'], 'A2': ['I1', 'I2']})
run('p180_cinetrans', 'v2/run_c', {'A1': ['I1'], 'A2': ['I1'], 'A3': ['I2']})

# ---------------- #047 Wan2.1 ----------------
case('p047_wan21', 'Swapped and duplicated characters are reported; changing faces still slip through')
run('p047_wan21', 'v1/historical', {'A5': ['vl_1']}, {
    'vl_1': n('The white-clad man flips into the doorway instead of dropping out of the bottom of the frame.', 'Matches A5'),
})
run('p047_wan21', 'v2/run_a', {'A1': ['I2'], 'A2': ['I3'], 'A5': ['I1']}, {
    'I1': n('Shot1: instead of dropping out of view he turns into the doorway and flips inside the frame.', 'Matches A5'),
    'I2': n('Shot4: the person in the Ponytailed man\'s place is shirtless in black trousers, unlike his black uniform in Shots 3/5.', 'Matches A1, with both labels'),
    'I3': n('Proposed: Shot6 has an extra shirtless, gray-haired, white-bearded man in the foreground.', 'Matches A2; review rejected it'),
    'I4': n('Shots of the same training room show unrelated surroundings (orange wood wall, gray-green wall with burgundy floor, blue-gray lower wall, mirrors).', 'Debatable: these may be different walls of one room'),
})
run('p047_wan21', 'v2/run_b', {'A1': ['I2'], 'A2': ['I4'], 'A5': ['I1']})
run('p047_wan21', 'v2/run_c', {'A1': ['I3'], 'A2': ['I4'], 'A3': ['I5'], 'A5': ['I1']})

# ---------------- #015 CineTrans ----------------
case('p015_cinetrans', 'Missing cuts are reported; within-shot defects are only partly caught')
run('p015_cinetrans', 'v1/historical', {'A2': ['vv1']}, {
    'vl1': n('The bob-haired woman wears a strapless black dress, not a thin-strapped one.', 'Real, not one of the key artifacts'),
    'vl2': n('The floral-dress woman\'s hair falls loose to the shoulders instead of being swept up.', 'Real, not one of the key artifacts'),
    'vl3': n('In Shot3 the ear adjustment is made by the bob-haired woman, not the floral-dress woman.', 'Real, not one of the key artifacts'),
    'vl4': n('The floral-dress woman sits beside the other woman at the window, not at the rear vanity.', 'Real, not one of the key artifacts'),
    'vl5': n('Shot1 lacks the required rear vanity, bed and white rug.', 'Real, not one of the key artifacts'),
    'vv1': n('The floral-dress woman\'s dress turns plain black in Shot4.', 'Matches A2 (filed as cross-shot)'),
})
run('p015_cinetrans', 'v2/run_a', {'A1': ['I1']}, {
    'I1': n('All four shots reuse one fixed two-person window view; the wide intro, the single-person shots and the vanity shot never appear, and no boundary shows a new setup.', 'Matches A1, with both labels'),
    'I2': n('Proposed: the floral-dress woman stays in shots that should show only one person.', 'Real in substance; review rejected it'),
    'I3': n('The floral-dress woman\'s hair is loose and straight in Shots 1 and 3, not swept up.', 'Real, not one of the key artifacts'),
})
run('p015_cinetrans', 'v2/run_b', {'A1': ['I7'], 'A2': ['I2', 'I3']})
run('p015_cinetrans', 'v2/run_c', {'A1': ['I5', 'I6', 'I7'], 'A2': ['I4']})

# ---------------- #068 HoloCine ----------------
case('p068_holocine', 'Hard case: the static take is partly reported; within-shot vanishing and morphing are mostly missed')
run('p068_holocine', 'v1/historical', {'A4': ['vl02']}, {
    'vl01': n('The woman wears brown trousers instead of a black knee-length skirt.', 'Real, not one of the key artifacts'),
    'vl02': n('The blue-shirted man wears a green shirt.', 'Matches A4 in part: the required man is replaced'),
})
run('p068_holocine', 'v2/run_b', {'A4': ['I2', 'I3'], 'A5': ['I1']})

# ---------------- later additions: v1 reruns and remaining v2 runs ----------------
run('p002_wan21', 'v1/rerun_a', {'A1': ['vl01', 'vv01']})
run('p002_wan21', 'v1/rerun_b', {'A1': ['vl1'], 'A2': ['vv1']})
run('p014_wan21', 'v1/rerun_a', {'A2': ['VL-1'], 'A4': ['VL-2']})
run('p014_wan21', 'v1/rerun_b', {'A2': ['vv1', 'vv2'], 'A3': ['vl1'], 'A4': ['vl2']})
run('p014_storymem', 'v1/rerun_a', {})
run('p014_storymem', 'v1/rerun_b', {})
run('p028_wan22', 'v1/rerun_a', {'A4': ['vv1']})
run('p028_wan22', 'v1/rerun_b', {'A1': ['vv01'], 'A5': ['vl01']})
run('p068_holocine', 'v2/run_a', {'A2': ['I5'], 'A4': ['I1', 'I3', 'I6'], 'A5': ['I7']}, {
    'I1': n('Shot1: the blue-shirted man is absent; the vested man appears instead.', 'Matches A4'),
    'I2': n('The woman wears brown trousers in most shots and a gray-green top in Shot5, neither matching the green shirt and black knee-length skirt.', 'Debatable: frames are very dark'),
    'I3': n('The recurring man labelled as the blue-shirted man wears a green shirt and brown trousers in Shots 6 and 8.', 'Matches A4 (the required man is replaced)'),
    'I4': n('The woman has dark curly hair tied up, not shoulder-length light-brown waves.', 'Real, not one of the key artifacts'),
    'I5': n('Proposed: in Shot6 the people vanish, the empty elevator shows for several frames, then the woman returns with no visible exit or entrance.', 'Matches A2; review rejected it'),
    'I6': n('Shot7 stays inside the elevator; the atrium landing, glass balustrades and columns never appear.', 'Matches A4'),
    'I7': n('Shot1 frame 0 is almost black; people and elevator are unreadable.', 'Matches A5'),
})
run('p068_holocine', 'v2/run_c', {'A4': ['I1', 'I2']})

run('p028_cinetrans', 'v1/rerun_a', {'A2': ['vl01'], 'A3': ['vl03']})
run('p028_cinetrans', 'v1/rerun_b', {'A2': ['vl01']})
run('p180_cinetrans', 'v1/rerun_a', {'A2': ['vl1', 'vl2', 'vl3']})
run('p180_cinetrans', 'v1/rerun_b', {'A2': ['vl1', 'vl2']})
run('p047_wan21', 'v1/rerun_a', {'A1': ['vl2'], 'A5': ['vl1']})
run('p047_wan21', 'v1/rerun_b', {'A1': ['vl2'], 'A2': ['vl3'], 'A5': ['vl1']})
run('p015_cinetrans', 'v1/rerun_a', {})
run('p015_cinetrans', 'v1/rerun_b', {'A2': ['vv-cross-1']})
run('p068_holocine', 'v1/rerun_a', {'A4': ['vl01', 'vl03']})
run('p068_holocine', 'v1/rerun_b', {'A4': ['vl01', 'vl04', 'vv01']})

TAKE = {
 'p002_wan21': ('Cross-shot changes get both labels; the changing face is found',
   'Old: the shirt and sofa changes were caught in some runs but filed inconsistently: V-L only, V-V only, or the same change twice in both lists (R2). The man\'s changing face was never reported. New: all three runs report the shirt, sofa and face changes, each with both labels, and V-V cross drops from a median of 81 to 30.'),
 'p014_wan21': ('The courtyard change is found in every new run; the hat finding is lost',
   'Old: all three runs missed the courtyard change behind the woman. New: all three runs confirm it with both labels, along with her coat change, and V-V cross drops from 100 to 37.5. Regression: no new run confirmed the wide-brim hat, which two of three old runs caught.'),
 'p014_storymem': ('Control: the consistent courtyard is left alone by both',
   'Both pipelines leave the consistent courtyard alone; the new runs proposed it every time and review rejected it. Neither caught the small neckline change or the near-duplicate Shot3. New R1 and old R3 both confirmed a debatable scarf-pattern difference.'),
 'p028_wan22': ('The turquoise woman\'s changing look and the blue chair are found',
   'Old: the turquoise woman\'s changing top was found in one of three runs, her hair never, the blue chair once. New: all three runs report her top, her hair and the chair (the chair with both labels); V-V cross drops from 75 to 37.5. Both miss the robe woman\'s loose hair in Shot7 and the lost cheek contact in Shot8. New R1 also confirmed a false within-shot cut.'),
 'p028_cinetrans': ('The merged characters and missing cuts are finally reported',
   'Old: every run reported the women\'s wrong looks as V-L only and nothing about the single continuous take or the merged characters, so V-V stayed at 100. New: all three runs report the merge with both labels and two of three report the seven missing cuts; V-V cross median 25. Neither catches the first-frame flash.'),
 'p180_cinetrans': ('Missing cuts and a first-frame flash are reported',
   'Old: only the missing hallway content, as V-L, in every run. New: all three runs report that no cut happens (both labels) and two of three catch the first-frame flash; V-V cross median 25 instead of 100.'),
 'p047_wan21': ('Swapped characters get both labels; faces still slip through',
   'Old: the fighters\' swapped looks were found in two of three runs as V-L only, the duplicate old man once. New: the swap is found in all runs with both labels, the duplicate old man is proposed in all three (confirmed once), and one run catches the older man\'s shirt change. Both miss the Sleeveless man\'s face change.'),
 'p015_cinetrans': ('Missing cuts are reported; within-shot defects are not improved',
   'Old: never mentions that the 20-second video has no cuts. New: all three runs report it with both labels. The dress flicker is found equally often by both (two of three runs each), and neither catches the plant popping in or the first-frame flash.'),
 'p068_holocine': ('Hard case: within-shot vanishing and morphing are still missed',
   'Both pipelines report the missing required people and places. New runs add the first-frame flash (two of three). Neither reports the static take, the characters vanishing for several frames (proposed once, rejected) or the woman turning into a man. This case shows the remaining within-shot weakness.'),
}
for key, (head, take) in TAKE.items():
    A[key]['headline'] = head
    A[key]['takeaway'] = take

Path('annotations.json').write_text(json.dumps(A, ensure_ascii=False, indent=2) + '\n')
print('ok', len(A))

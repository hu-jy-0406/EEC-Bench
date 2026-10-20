"""English text for the partly-true verdict page (translations of the reviewers' Chinese text are the assistant's)."""

CASE_NAMES = {'p002_wan21': '#002 Wan2.1', 'p014_wan21': '#014 Wan2.1', 'p028_wan22': '#028 Wan2.2', 'p069_wan21': '#069 Wan2.1'}

# Issue descriptions, keyed by (case, run, issue).
DESCRIPTIONS = {
    ('p002_wan21', 'run_a', 'I1'): 'In Shot4 the man looks different from Shots 1–3: shorter, flatter hair, lighter skin, a different face, and a collared shirt instead of the crew-neck T-shirt.',
    ('p002_wan21', 'run_a', 'I2'): "Shot4's seat looks like a tall, wrap-around single chair; in Shots 1–3 it is a low, wide sofa. Shape and size clearly differ.",
    ('p002_wan21', 'run_b', 'I2'): "In Shot4 the man's face shape and curls clearly differ from Shots 1–3; he looks like a different man.",
    ('p002_wan21', 'run_b', 'I4'): "Shot4's seat is a tall, curved-back, armchair-like piece around the man, unlike the earlier low, wide sofa.",
    ('p014_wan21', 'run_a', 'I1'): 'All four shots are the same courtyard, but the background buildings differ in type, material and layout: an old brown-gray stone building in Shot1, a cream building with arched windows and a porch in Shot2, low beige houses in Shot3. Camera angle does not explain it.',
    ('p014_wan21', 'run_b', 'I1'): "The woman's gray coat changes style: belted and closed in Shot1, open in Shot2, black double-breasted buttons in Shot3. In Shot3 the light-brown scarf also hides the peach neckline that should be clearly visible.",
    ('p014_wan21', 'run_c', 'I1'): 'In Shot3 the woman switches to a double-breasted gray coat with black buttons and a thick light-brown scarf; in Shots 1–2 she wears a belted gray coat with a peach high collar showing and no scarf. A clothing discontinuity of a recurring character.',
    ('p028_wan22', 'run_b', 'I2'): 'In Shot2 frame 0 the hand hovers beside her face without touching; contact only comes later, so the required hand contact is not kept throughout.',
    ('p028_wan22', 'run_b', 'I3'): 'The same blue beach chair is a small upright chair in Shots 1 and 5 but a large lounger with a wooden frame in Shots 3 and 7.',
    ('p028_wan22', 'run_b', 'I4'): "The scheduled turquoise-top woman's hair and top change: shoulder-length highlighted waves and a plain strap top in Shot2; a dark palm-print top in Shots 4/8; a black shoulder mark and a white long-sleeve layer in Shot6.",
    ('p028_wan22', 'run_c', 'I1'): 'The recurring blue beach chair becomes a large low lounger in Shots 3 and 7, unlike the small upright chair of Shots 1 and 5; Shot7 also shows an extra similar lounger.',
    ('p028_wan22', 'run_c', 'I2'): "The turquoise-top woman's look changes across Shots 2, 4, 6 and 8: hair length and texture, and the top's pattern. Shot8's palm print differs from Shot4's scattered marks and Shot6's shoulder logo.",
    ('p069_wan21', 'run_a', 'I2'): 'In Shot2 the short figure is a short-haired woman in a brown coat and brown trousers; in Shot4 the same scheduled character appears as a man in a dark long coat against the brick wall. Identity and appearance do not continue.',
    ('p069_wan21', 'run_a', 'I3'): "Shot2's long-coat adult is a straight-haired woman in a gray coat and dark-red trousers; in Shot4 the corresponding character has curly hair, a loose olive-green coat and dark trousers.",
    ('p069_wan21', 'run_b', 'I3'): "The long-coat adult doesn't look the same in Shot2 and Shot4: gray coat, burgundy trousers and straight hair in Shot2; olive-green coat, dark trousers and curly hair in Shot4.",
    ('p069_wan21', 'run_b', 'I4'): "Shot4's short, dark-clothed figure appears as an adult man in black; in Shot2 the figure looks like a shorter woman in brown trousers. Identity and appearance don't match.",
    ('p069_wan21', 'run_b', 'I6'): 'In Shots 1 and 3 the jacket man stands in a narrow passage of bare brick with peeling green paint, stairs behind him; Shot3 shows green block walls and green stairs more clearly. Compared with the same corridor in Shots 2 and 4 (lattice windows, green wainscot, curtains), it hardly reads as one continuous place.',
    ('p069_wan21', 'run_c', 'I2'): "Shot1's large gray-black angular gun clearly differs in Shot3: a conventional rifle shape with a prominent yellow strap.",
    ('p069_wan21', 'run_c', 'I4'): "Shot2's long-coat adult has straight hair, a gray coat and dark-red trousers; Shot4's corresponding fighter has curly dark hair and an olive coat. A clear identity and appearance mismatch.",
}

# Review v3 parts of every partly-true label, keyed by (case, run, issue, label): (true part, cut part).
PARTS = {
    ('p002_wan21', 'run_a', 'I1', 'v_l'): ('Shot4 collared shirt versus the blue-gray crew-neck T-shirt the text fixes for the same man.',
                                           "Lighter skin and a different-looking face can't be confirmed as a text conflict (could be lighting). The hair differs, but the text doesn't fix the hairstyle shot by shot."),
    ('p002_wan21', 'run_a', 'I1', 'v_v'): ('The same man changes from the blue-gray T-shirt to a collared shirt in Shot4, and his hair looks shorter and tighter.',
                                           "Skin tone and a change of face can't be determined from these keyframes; skin tone may be lighting."),
    ('p002_wan21', 'run_a', 'I2', 'v_l'): ("Shot4's beige backrest is tall and curved; Shots 1 and 3 show a low, wide backrest. This breaks the 'same sofa' continuity.",
                                           "Can't establish that Shot4 is a single chair rather than another part or angle of the same sofa; the text doesn't fix size or back shape."),
    ('p002_wan21', 'run_a', 'I2', 'v_v'): ('Tall curved backrest in Shot4 versus the low, wide backrest of Shots 1 and 3: an unexplained difference.',
                                           "The frames can't prove it is a single chair, or rule out a different view of the same sofa."),
    ('p002_wan21', 'run_b', 'I2', 'v_v'): ("The man's hair in Shot4 becomes shorter and tighter, with curls at the front.",
                                           "'Different face', and so 'a different man', can't be established: the beard and overall features are similar, and angle, framing and light differ."),
    ('p002_wan21', 'run_b', 'I4', 'v_v'): ('The backrest shapes in Shot1 and Shot4 clearly differ: tall and curved in Shot4, low and wide in Shot1.',
                                           "Can't establish that it is an armchair: Shot4 is a close oblique view, and the prompt itself mentions a curved sofa back."),
    ('p014_wan21', 'run_a', 'I1', 'v_l'): ("Shot1's brown-gray stone building versus Shot2's cream façade with arches conflicts with 'retain the courtyard continuity'.",
                                           "Not all four shots are incompatible: the light buildings of Shots 2 and 4 fit together; Shot3's background differs, but these frames can't show it is not part of the same courtyard."),
    ('p014_wan21', 'run_a', 'I1', 'v_v'): ("Shot1's brown-gray stone building versus Shot2's light façade: a large unexplained difference.",
                                           "Shots 2 and 4 are compatible; Shot3's low light building isn't shown to be a different place."),
    ('p014_wan21', 'run_b', 'I1', 'v_l'): ("Shot1's coat isn't fastened the way the text describes; in Shot3 the scarf hides the peach neckline that must be clearly visible.",
                                           "The open coat in Shot2 isn't a text violation (that shot only requires the gray coat); the buttons in Shot3 actually fit a buttoned coat."),
    ('p014_wan21', 'run_c', 'I1', 'v_l'): ('In Shot3 the light-brown scarf hides the peach neckline the prompt requires to be clearly visible.',
                                           "The coat is still gray, so the gray-coat requirement holds; belted → double-breasted and the added scarf don't by themselves break clothing details the text never specified."),
    ('p028_wan22', 'run_b', 'I2', 'v_l'): ("Shot2 frame 0: a visible gap between the little finger and her cheek, so the contact isn't there at that moment.",
                                           "'Not kept throughout' doesn't hold: from frame 1 on, the hand touches her cheek."),
    ('p028_wan22', 'run_b', 'I3', 'v_l'): ("The blue loungers of Shots 3 and 7 clearly differ from the small chair of Shots 1 and 5, contradicting 'the familiar blue chair is still there'.",
                                           "'Small' is only stated for Shot1, so not every shot violates the size."),
    ('p028_wan22', 'run_b', 'I4', 'v_v'): ('Her hair is shoulder-length and wavy in Shot2 but clearly longer and curlier in Shots 4, 6 and 8; the wind mentioned in the text does not explain it.',
                                           "Not every top difference is unexplained: from Shot4 on, the text asks for dark markings on the top, and the white inner sleeve isn't ruled out."),
    ('p028_wan22', 'run_c', 'I1', 'v_l'): ('The blue chairs in Shots 3 and 7 are large loungers, not the small beach chair Shot1 requires.',
                                           "The extra lounger in Shot7 can't be confirmed."),
    ('p028_wan22', 'run_c', 'I1', 'v_v'): ('Large blue lounger in Shots 3 and 7 versus the small upright chair at the same spot in Shots 1 and 5.',
                                           'The extra lounger in Shot7 is not confirmed.'),
    ('p028_wan22', 'run_c', 'I2', 'v_v'): ("Her hair changes across Shots 2, 4, 6 and 8, and the top's pattern changes between Shots 4/6 and Shot8.",
                                           "'Shot6 shoulder logo' and 'Shot8 palm print' are pattern details, not shown to be mutually exclusive."),
    ('p069_wan21', 'run_a', 'I2', 'v_l'): ('The figure against the left wall in Shot4 wears dark trousers, while the same short figure in Shot2 wears brown ones; the trouser colour is not kept in Shot4.',
                                           "The prompt doesn't require the figure to be a woman or to wear a brown coat; it only specifies short, dark clothing and brownish trousers, and the Shot4 figure does wear a dark coat."),
    ('p069_wan21', 'run_a', 'I2', 'v_v'): ("The Shot2 short figure and the Shot4 figure by the wall don't match in face and short hair.",
                                           "The coat claim is wrong: in Shot2 the figure actually wears a dark-brown long coat, so the coat change isn't confirmed."),
    ('p069_wan21', 'run_a', 'I3', 'v_l'): ("Shot4's coat is olive green; Shot2 requires a gray-brown coat for this character.",
                                           "No clear trouser conflict (dark in both shots); curly hair isn't specified by the text."),
    ('p069_wan21', 'run_a', 'I3', 'v_v'): ('The hair clearly differs between Shot2 and Shot4, and the coat changes from gray-brown to olive.',
                                           "Calling Shot2's coat 'gray' is inaccurate (it is gray-brown); the trousers are dark in both shots, so no trouser change."),
    ('p069_wan21', 'run_b', 'I3', 'v_l'): ("In Shot2 frame 5 the long-coat adult's trousers are burgundy, contradicting this shot's required dark trousers.",
                                           "The gray-brown versus olive coat and straight versus curly hair don't by themselves violate Shot4's prompt, which doesn't specify them."),
    ('p069_wan21', 'run_b', 'I3', 'v_v'): ('The same adult has straight hair in Shot2 frame 5 and clearly curly hair in Shot4 frame 0.',
                                           'The coat change from gray-brown to olive may be lighting; the trouser contrast is not enough to confirm.'),
    ('p069_wan21', 'run_b', 'I4', 'v_l'): ("The short figure on the left of Shot4 frame 0 wears dark trousers, contradicting the contract's brownish trousers.",
                                           "Woman versus adult man is not a requirement the text states, so it can't be a V-L conflict."),
    ('p069_wan21', 'run_b', 'I6', 'v_l'): ('The walls and stairs behind the man clearly differ between Shot1 and Shot3, although Shot3 returns to the same man in the same corridor.',
                                           "Shot2's windows and curtains and Shot4's stairwell needn't face the same way as Shots 1/3; different backgrounds alone don't violate 'the same corridor'."),
    ('p069_wan21', 'run_b', 'I6', 'v_v'): ("Behind the same man, Shot1 and Shot3 show clearly different wall and stair construction that the camera angle can't explain.",
                                           "Windows, curtains and stair partitions in Shots 2 and 4 don't by themselves show a discontinuity; camera direction and moving along the corridor explain them."),
    ('p069_wan21', 'run_c', 'I2', 'v_l'): ("Shot3's gray-black gun is a slim conventional rifle with a prominent yellow strap, not the required large, angular gun with a bulky textured casing.",
                                           "The gun is still gray-black, so the colour requirement isn't violated."),
    ('p069_wan21', 'run_c', 'I4', 'v_l'): ("Shot4's fighter, the counterpart of Shot2's long-coat adult, wears an olive coat; Shot2 requires a gray-brown coat.",
                                           "Straight versus curly hair is visible, but the prompt doesn't specify this character's hairstyle; the trouser colour isn't enough to confirm a violation of 'dark trousers'."),
}

# Cause of each partly-true label (assistant classification), and a note where real content was cut.
GROUPS = [
    ('vl_bundle', 'Several visual changes in one issue, only some contradict the prompt',
     'The visual change is real; the V-L label is narrowed to the change the text actually forbids.'),
    ('comparisons', 'Several shot or place comparisons in one issue',
     'One comparison holds and another does not.'),
    ('attributes', 'Several attribute changes of one character or object',
     'One detail is wrong, an extra claim cannot be checked, or the reviewer hedges.'),
    ('single', 'One problem',
     'The "cut part" is a hedge on the same change, a nitpick, or something the issue never claimed.'),
]
CAUSE = {
    ('p002_wan21', 'run_a', 'I1', 'v_l'): 'vl_bundle', ('p014_wan21', 'run_b', 'I1', 'v_l'): 'vl_bundle',
    ('p014_wan21', 'run_c', 'I1', 'v_l'): 'vl_bundle', ('p069_wan21', 'run_a', 'I2', 'v_l'): 'vl_bundle',
    ('p069_wan21', 'run_a', 'I3', 'v_l'): 'vl_bundle', ('p069_wan21', 'run_b', 'I3', 'v_l'): 'vl_bundle',
    ('p069_wan21', 'run_b', 'I4', 'v_l'): 'vl_bundle', ('p069_wan21', 'run_c', 'I4', 'v_l'): 'vl_bundle',
    ('p014_wan21', 'run_a', 'I1', 'v_l'): 'comparisons', ('p014_wan21', 'run_a', 'I1', 'v_v'): 'comparisons',
    ('p069_wan21', 'run_b', 'I6', 'v_l'): 'comparisons', ('p069_wan21', 'run_b', 'I6', 'v_v'): 'comparisons',
    ('p002_wan21', 'run_a', 'I1', 'v_v'): 'attributes', ('p028_wan22', 'run_b', 'I4', 'v_v'): 'attributes',
    ('p028_wan22', 'run_c', 'I1', 'v_l'): 'attributes', ('p028_wan22', 'run_c', 'I1', 'v_v'): 'attributes',
    ('p028_wan22', 'run_c', 'I2', 'v_v'): 'attributes', ('p069_wan21', 'run_a', 'I2', 'v_v'): 'attributes',
    ('p069_wan21', 'run_a', 'I3', 'v_v'): 'attributes', ('p069_wan21', 'run_b', 'I3', 'v_v'): 'attributes',
    ('p002_wan21', 'run_a', 'I2', 'v_l'): 'single', ('p002_wan21', 'run_a', 'I2', 'v_v'): 'single',
    ('p002_wan21', 'run_b', 'I2', 'v_v'): 'single', ('p002_wan21', 'run_b', 'I4', 'v_v'): 'single',
    ('p028_wan22', 'run_b', 'I2', 'v_l'): 'single', ('p028_wan22', 'run_b', 'I3', 'v_l'): 'single',
    ('p069_wan21', 'run_c', 'I2', 'v_l'): 'single',
}
REAL_CUT = {
    ('p002_wan21', 'run_a', 'I1', 'v_v'): "The dropped face change is a verified artifact (A3: the man's face and hair change).",
    ('p002_wan21', 'run_b', 'I2', 'v_v'): "The dropped face change is a verified artifact (A3: the man's face and hair change).",
    ('p014_wan21', 'run_a', 'I1', 'v_l'): 'The dropped Shot3 comparison is the verified artifact (A1: courtyard changes between Shot1 and Shot3).',
    ('p014_wan21', 'run_a', 'I1', 'v_v'): 'The dropped Shot3 comparison is the verified artifact (A1: courtyard changes between Shot1 and Shot3).',
}
KIND_NOTE = {
    ('p002_wan21', 'run_a', 'I2', 'v_l'): 'Hedge', ('p002_wan21', 'run_a', 'I2', 'v_v'): 'Hedge',
    ('p002_wan21', 'run_b', 'I2', 'v_v'): 'Hedge', ('p002_wan21', 'run_b', 'I4', 'v_v'): 'Hedge',
    ('p028_wan22', 'run_b', 'I2', 'v_l'): 'Nitpick: the issue already said contact comes later',
    ('p028_wan22', 'run_b', 'I3', 'v_l'): 'Nitpick on which shots state "small"',
    ('p069_wan21', 'run_c', 'I2', 'v_l'): 'Invented: the issue never claimed a colour change',
}

# Old-review reasons and the new review's assessment for the five showcased examples (translated).
OLD_REASONS = {
    'E1': ("The prompt requires the white beanie, straight hair and peach neckline in Shot3, but doesn't require a belted coat or forbid black buttons or a scarf. The gray coat and peach neckline are still visible, so no V-L violation.",
           'Shot3 explicitly requires the peach neckline to be clearly visible, but the light-brown scarf wraps her neck and hides it. The coat still being gray is not a conflict.'),
    'E2': ("The text requires a short, dark-clothed figure in brownish trousers; it doesn't fix gender, hair or coat colour. Shot2's trousers are brown and Shot4's look darker, but these frames aren't enough to confirm a violation of 'brownish'.",
           "The text only requires short, dark clothing and brownish trousers, not gender, hair or coat colour. The Shot4 figure's trousers look darker, but that isn't a text contradiction."),
    'E3': ('Shot2 states that the long-coat adult wears a loose gray-brown coat and dark trousers; in Shot4 the coat is clearly olive, contradicting the description established for this character.',
           "Shot4 only requires the long-coat adult to fight; it states no coat colour, trouser colour or hair. Shot2's gray-brown coat can't be applied directly as a Shot4 requirement."),
    'E4': ("Shots 1 and 3 share stairs and the green industrial look; Shots 2 and 4 share windows, wainscot and curtains. Different view directions may explain some differences, but the keyframes aren't enough to confirm that all views are one space.",
           'Shots 1 and 3 both show the wall and stairs behind the jacket man, but Shot1 has bare brick with peeling green paint while Shot3 has green block walls and different stairs. A large comparable background difference with no visible cause.'),
    'E5': ("The text requires a large, gray-black, angular gun but doesn't exclude a rifle shape or a yellow strap. Shot3's gun still shows a gray-black body and angular parts, so no clear violation.",
           "Shot1 sets a large gray-black angular gun with a bulky casing; Shot3 shows a conventional rifle with a prominent yellow strap, which doesn't match."),
}
OTHER_LABEL_NOTE = {
    'E1': 'The V-V label (cross-shot appearance) was true in all three reviews.',
    'E2': 'The V-V label (identity) was true in both old reviews; the new review calls it partly true: face and short hair differ, but the coat claim is wrong.',
    'E3': 'The V-V label (appearance) was true in both old reviews; the new review calls it partly true: hair changes, while the coat may be lighting.',
    'E4': 'The V-L label ("the same industrial corridor") was true in both old reviews; the new review splits it the same way.',
    'E5': 'The V-V label (object identity) was true in all three reviews.',
}
EXAMPLES = [
    dict(id='E1', key=('p014_wan21', 'run_c', 'I1', 'v_l'), cause='vl_bundle',
         heading='The scarf hides the required peach neckline',
         read=("Correct. Shot3 frame 0 shows the scarf covering the collar. The issue listed what changed visually instead of naming the "
               "requirement it breaks, which is the imprecise description this change was meant to catch. The visual change itself (V-V) was never in doubt."),
         frames=[('014', 'Shot1', 0, None), ('014', 'Shot2', 0, None), ('014', 'Shot3', 0, None)]),
    dict(id='E2', key=('p069_wan21', 'run_a', 'I2', 'v_l'), cause='vl_bundle',
         heading="The short figure's trousers turn dark",
         read=("The headline problem, a woman replaced by a man, is a visual inconsistency, and the V-V label carries it. The V-L true part is a side "
               "detail, trouser colour, that the issue mentions in passing. Both old reviews saw the same dark trousers and decided they were not a "
               "clear violation of 'brownish'; the new review decided they were. A moderate penalty for trouser colour seems heavy."),
         frames=[('069', 'Shot2', 5, 'zoom'), ('069', 'Shot4', 0, None), ('069', 'Shot4', 5, None)]),
    dict(id='E3', key=('p069_wan21', 'run_b', 'I3', 'v_l'), cause='vl_bundle',
         heading='Burgundy trousers in Shot2, not the claimed cross-shot change',
         read=("The true part is a different problem from the one the issue describes: a mismatch inside Shot2 alone (burgundy trousers where the "
               "text says dark), not a change between shots. The review found it only because the issue happened to mention Shot2's trousers. "
               "It is visually correct."),
         frames=[('069', 'Shot2', 5, 'zoom'), ('069', 'Shot4', 0, None)]),
    dict(id='E4', key=('p069_wan21', 'run_b', 'I6', 'v_v'), cause='comparisons',
         heading='Corridor: Shot1 versus Shot3 holds, Shot2/Shot4 does not',
         read=("Two comparisons were bundled into one issue. The split is right: brick behind the man in Shot1, green blocks in Shot3, while "
               "Shots 2 and 4 plausibly show other parts of the corridor."),
         frames=[('069', 'Shot1', 1, None), ('069', 'Shot3', 0, None), ('069', 'Shot2', 5, None), ('069', 'Shot4', 0, None)]),
    dict(id='E5', key=('p069_wan21', 'run_c', 'I2', 'v_l'), cause='single',
         heading='The gun changes; the "false part" was never claimed',
         read=("One well-defined problem. The issue never said the colour was wrong, so the cut part is invented and this should simply be true. "
               "The penalty is the same either way."),
         frames=[('069', 'Shot1', 5, None), ('069', 'Shot3', 5, None)]),
]
WEAKENED = [
    dict(id='W1', heading="#002 Wan2.1: the man's face change was cut as \"can't be established\"",
         keys=[('p002_wan21', 'run_a', 'I1', 'v_v'), ('p002_wan21', 'run_b', 'I2', 'v_v')],
         reference=("Verified artifact A3, the man's face and hair change: \"Maintain the same man\"; hair volume, hairline and face "
                    'differ across Shots 1–4. Known weak spot of the evaluator: face identity.'),
         frames=[('002', 'Shot1', 2, None), ('002', 'Shot2', 2, None), ('002', 'Shot3', 2, None), ('002', 'Shot4', 2, None)]),
    dict(id='W2', heading='#014 Wan2.1: the Shot1 versus Shot3 courtyard change was left out of the true part',
         keys=[('p014_wan21', 'run_a', 'I1', 'v_v'), ('p014_wan21', 'run_a', 'I1', 'v_l')],
         reference=('Verified artifact A1, your own example: "retain the courtyard continuity". A tall dark stone building with balustraded '
                    'stairs behind the woman in Shot1; a low beige single-storey building and bench behind her in Shot3, from a comparable frontal view.'),
         frames=[('014', 'Shot1', 2, None), ('014', 'Shot2', 2, None), ('014', 'Shot3', 2, None), ('014', 'Shot4', 2, None)]),
]
PROMPTS = {
    'E1': ['her white beanie, straight dark hair and muted peach neckline clear', 'The woman retains her white beanie, peach neckline and gray coat'],
    'E2': ['the Short dark-clothed figure, wearing brownish trousers'],
    'E3': ['wearing a loose gray-brown coat over dark trousers'],
    'E4': ['the same industrial corridor', 'Farther down the same corridor'],
    'E5': ['Large gray-and-black angular firearm with bulky textured casing.', 'holds the Angular firearm diagonally across his torso with one hand'],
}

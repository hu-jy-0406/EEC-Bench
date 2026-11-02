#!/usr/bin/env python3
"""Style decisions, confirmed by reading every keyword candidate (style_candidates.jsonl).

Key: 0-based position in the generation queue. Shot values come from that shot's prompt; '*' comes from the
global prompt and applies to every shot without a value of its own. An entry is a quote (the value is the
quote), or (value, quote), or (value, [quotes]). The value uses the prompt's own words.

Counted as style: a statement about the video or the rendered scene (a shot, view, room, world, image).
Not counted: one entity or prop (a "cartoon man", "stylized skin"), a picture inside the scene (a television,
an arcade screen), expressions ("animated face"), clothing, and plain colour grades or lighting ("muted colors").
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
E = HERE.parents[1]
sys.path.insert(0, str(E / 'scripts'))
import episode_contract as contract_io  # noqa: E402

ANIMATED = ('animated', 'animated shots')
BW = 'black-and-white'
S3A = 'stylized 3D animated'
STYLES = {
    8: {'Shot1': ('painterly animated', 'painterly animated bedroom scene'), 'Shot2': ('painterly', 'same painterly bedroom'),
        'Shot3': ('painterly', 'painterly wall texture'), 'Shot4': 'saturated painterly animation'},
    10: {'Shot1': ('live-action', 'live-action scene')},
    11: {'Shot1': ('miniature puppet', 'miniature puppet shot')},
    21: {'Shot1': 'colorful stylized 3D animation'},
    41: {'Shot1': ('stylized 3D', 'stylized 3D outdoor scene')},
    56: {'Shot1': (S3A, 'stylized 3D animated shot'), 'Shot3': ('animated', 'animated landscape')},
    61: {'Shot1': 'painterly 3D animation', 'Shot2': ('painterly', 'same painterly woodland'),
         'Shot4': ('painterly', 'same painterly woodland clearing')},
    64: {'Shot1': 'hand-drawn cel-animation', 'Shot2': 'hand-drawn animation', 'Shot3': 'hand-drawn animation', 'Shot4': 'hand-drawn animation'},
    81: {'Shot1': ('dim, nearly monochrome 3D-rendered', 'dim, nearly monochrome 3D-rendered rocky plain'),
         'Shot2': 'muted gray rendered style', 'Shot3': 'subdued monochrome 3D rendering', 'Shot4': 'dim, nearly monochrome rendered appearance'},
    83: {'*': ANIMATED, 'Shot1': 'vivid, rounded 3D animation', 'Shot2': 'glossy, rounded 3D animation', 'Shot3': 'saturated 3D cartoon look'},
    87: {'*': ANIMATED, 'Shot1': ('stylized animated', 'stylized animated close-up')},
    95: {'Shot1': 'stylized 3D animation'},
    98: {'*': ANIMATED, 'Shot1': 'detailed, rounded 3D animation', 'Shot2': ('sepia-toned animated', 'sepia-toned animated street'),
         'Shot3': ('animated, sepia-toned', ['animated shots', 'sepia-toned street exchange']), 'Shot4': 'warm full-color 3D animation'},
    110: {'Shot1': 'cool, grainy monochrome'},
    126: {'Shot1': 'stylized 3D animation', 'Shot7': ('animated', 'animated shot')},
    137: {'Shot1': (S3A, 'stylized 3D animated detail'), 'Shot2': 'stylized 3D animation'},
    139: {'Shot1': ('dim, nearly monochrome CG', 'dim, nearly monochrome CG mountain ridge'), 'Shot2': 'dim, desaturated CG appearance',
          'Shot3': ('subdued monochrome CG', 'subdued monochrome CG lighting'),
          'Shot4': ('subdued, nearly monochrome CG', 'subdued, nearly monochrome CG shading')},
    140: {'*': ANIMATED, 'Shot1': ('hand-drawn animated', 'hand-drawn animated scene')},
    158: {'Shot1': 'subdued vintage color-film texture'},
    160: {'Shot1': (S3A, 'stylized 3D animated rooftop')},
    163: {'Shot1': ('monochrome, letterboxed', 'monochrome, letterboxed close view'), 'Shot2': ('monochrome, letterboxed', 'monochrome, letterboxed living room'),
          'Shot3': ('monochrome, letterboxed', 'monochrome, letterboxed close view'), 'Shot4': ('monochrome, letterboxed', 'monochrome, letterboxed medium close view'),
          'Shot5': ('monochrome, letterboxed', 'monochrome, letterboxed living-room view'), 'Shot6': 'monochrome with letterboxing'},
    169: {'Shot1': 'softly textured animation'},
    173: {'*': 'golden illustrated style', 'Shot1': ('grainy ochre and brown washes', 'rendered in grainy ochre and brown washes'),
          'Shot2': 'warm, grainy ochre illustration', 'Shot4': ('warm, grainy painted', 'warm, grainy painted close-up')},
    178: {'Shot1': ('black-and-white film', 'black-and-white film shot'), 'Shot2': (BW, 'same black-and-white landing'),
          'Shot3': (BW, 'same black-and-white wood-paneled landing'), 'Shot4': 'black and white'},
    196: {'Shot1': 'stylized 3D animation', 'Shot2': 'stylized 3D animation', 'Shot3': ('stylized 3D', 'stylized 3D shot'),
          'Shot4': ('stylized 3D', 'same stylized 3D world'), 'Shot5': ('stylized 3D', 'sunny stylized 3D exterior'), 'Shot6': 'stylized 3D animation'},
    197: {'Shot1': ('animated fantasy', 'animated fantasy shot')},
    198: {'*': ANIMATED, 'Shot1': (S3A, 'stylized 3D animated turquoise ice passage')},
    199: {'*': ANIMATED, 'Shot1': 'painterly 2D animation', 'Shot2': 'painterly animated style', 'Shot3': 'painterly 2D animation', 'Shot4': 'painterly animation'},
    252: {'*': ANIMATED, 'Shot1': 'Hand-drawn animation'},
    255: {'Shot1': (S3A, 'stylized 3D animated forest'), 'Shot2': ('animated', 'dark animated woodland')},
    261: {'Shot1': ('cinematic CGI', 'cinematic CGI view')},
    263: {'*': ('illustrated', 'illustrated shots'), 'Shot1': 'softly textured watercolor animation', 'Shot2': 'yellow-ochre watercolor style',
          'Shot3': ('grainy yellow watercolor', 'grainy yellow watercolor sky'), 'Shot4': ('yellow-ochre watercolor', 'yellow-ochre watercolor room'),
          'Shot5': ('warm watercolor', 'warm watercolor dining room'), 'Shot6': ('blue-green watercolor', 'blue-green watercolor view')},
    267: {'*': ('monochrome', 'monochrome appearance'), 'Shot1': ('letterboxed black-and-white', 'letterboxed black-and-white interior shot'),
          'Shot2': (BW, 'black-and-white room'), 'Shot3': ('letterboxed monochrome', 'letterboxed monochrome close-up'), 'Shot4': 'black and white',
          'Shot5': ('letterboxed black-and-white', 'letterboxed black-and-white wide view'), 'Shot7': (BW, 'black-and-white view'),
          'Shot8': ('letterboxed black-and-white', 'letterboxed black-and-white urban pavement')},
    271: {'Shot4': 'subdued letterboxed visual style'},
    277: {'Shot1': ('polished 3D animated', 'polished 3D animated seaside scene')},
    280: {'Shot1': (S3A, 'stylized 3D animated rooftop shot')},
    295: {'Shot1': ('stylized 3D', 'stylized 3D close-up'), 'Shot2': 'stylized 3D rendering', 'Shot3': ('stylized 3D', 'same stylized 3D appearance'),
          'Shot4': 'stylized 3D rendering'},
    301: {'Shot1': (S3A, 'stylized 3D animated forest camp')},
    313: {'*': ('animated, with muted woodland colors and painted backgrounds', ['animated shots', 'muted woodland colors and painted backgrounds']),
          'Shot1': ('painted 2D', 'painted 2D woodland shot'),
          'Shot3': ('hand-drawn, with soft painted forest textures and muted colors', ['hand-drawn woodland shot', 'soft painted forest textures and muted colors']),
          'Shot4': ('softly painted', 'softly painted forest clearing')},
    316: {'Shot1': (BW, 'Black-and-white daylight'), 'Shot2': (BW, 'black-and-white close-up'), 'Shot3': (BW, 'black-and-white wide view'),
          'Shot4': 'black and white', 'Shot5': (BW, 'black-and-white vehicle interior'), 'Shot6': (BW, 'black-and-white exterior')},
    319: {'Shot1': (S3A, 'stylized 3D animated shot')},
    331: {'Shot1': ('CGI', 'sunlit CGI desert')},
    333: {'Shot1': ('pastel 3D animated', 'pastel 3D animated room'), 'Shot2': 'rounded, tactile 3D animation style', 'Shot3': 'soft, rounded 3D style',
          'Shot4': ('rounded 3D animated', 'rounded 3D animated finish')},
    338: {'*': ANIMATED, 'Shot1': 'hand-drawn 2D animation with textured painted backgrounds', 'Shot2': ('hand-drawn animated', 'hand-drawn animated view'),
          'Shot3': 'hand-drawn animation', 'Shot4': 'hand-drawn animation'},
    339: {'Shot1': ('cinematic animated', 'cinematic animated desert wreckage scene')},
    342: {'*': ANIMATED, 'Shot1': (S3A, 'stylized 3D animated cyan ice chute'), 'Shot4': ('stylized animated', 'stylized animated cavern')},
    349: {'*': 'textured, hand-drawn animation', 'Shot1': 'grainy hand-painted animation', 'Shot2': ('rough painted-paper animation', 'rough painted-paper animation texture'),
          'Shot3': 'textured hand-drawn animation', 'Shot4': 'rough painted-paper animation'},
    350: {'*': ANIMATED, 'Shot1': ('shaded 2D animated', 'shaded 2D animated side-profile shot'), 'Shot2': 'shaded 2D animation', 'Shot3': 'shaded 2D animation',
          'Shot4': ('shaded 2D animated', 'shaded 2D animated medium view'), 'Shot5': 'shaded 2D animation', 'Shot6': 'shaded 2D animation'},
    355: {'Shot1': ('letterboxed black-and-white', 'letterboxed black-and-white interior shot'), 'Shot2': 'letterboxed black and white',
          'Shot3': ('letterboxed monochrome', 'letterboxed monochrome appearance'), 'Shot4': 'letterboxed black and white'},
    358: {'*': ANIMATED, 'Shot1': ('hand-drawn cel-animation', 'hand-drawn cel-animation scene'), 'Shot3': ('hand-drawn animation', 'hand-drawn animation style'),
          'Shot4': ('hand-drawn', 'hand-drawn nighttime group scene')},
    386: {'*': ('monochrome sculptural', 'monochrome sculptural landscape'), 'Shot1': ('dim monochrome, sculptural 3D', 'dim monochrome, sculptural 3D landscape'),
          'Shot8': ('stark monochrome sculptural', 'stark monochrome sculptural appearance')},
    390: {'Shot1': ('painterly animated', 'painterly animated interior'), 'Shot2': ('softly painted', 'softly painted room'), 'Shot4': ('painterly', 'painterly interior'),
          'Shot6': ('painterly', 'bright painterly interior')},
    391: {'Shot1': (S3A, 'stylized 3D animated waterfront')},
    392: {'*': ANIMATED, 'Shot1': 'painted backgrounds and outlined animation', 'Shot2': 'outlined animation'},
}
NOT_FILLED = [
    dict(index=118, shot='Shot1', text='A letterboxed nighttime exterior with cool, muted colors.', reason='letterbox and colour grade only'),
    dict(index=259, shot='Shot1', text='the image cool, dim, and slightly grainy', reason='image grade, not a stated style'),
    dict(index=41, shot='Shot2', text='detailed stylized skin and gray hair', reason='one entity'),
    dict(index=21, shot='Shot2', text='a brown-skinned cartoon man', reason='one entity'),
    dict(index=277, shot='Shot2', text='an older, light-skinned animated man', reason='one entity'),
    dict(index=127, shot='Shot1', text='a colorful pixel-art graveyard', reason='a game seen on an arcade screen inside the scene'),
    dict(index=200, shot='Shot1', text="curved-screen television's cool monochrome picture", reason='a television picture inside the scene'),
    dict(index=112, shot='global', text='the miniature setting', reason='a set, not a stated render style'),
    dict(index=189, shot='Shot1', text='muted teal-green cinematic palette', reason='colour grade'),
    dict(index=385, shot='Shot1', text='Use cold, desaturated light', reason='lighting'),
]


def normal(text):
    return ' '.join(text.split()).casefold()


def main():
    ids = [x.strip() for x in (E / 'experiments/source_video_priority_20260921/generation_queue_400.ids.txt').read_text().splitlines() if x.strip()]
    errors, episodes = [], {}
    for index, rows in sorted(STYLES.items()):
        eid = ids[index]
        prompt = contract_io.read(contract_io.resolve_v2_contract(eid))['prompt']
        texts = {'global': prompt['global_prompt'], **{s['shot_id']: s['text'] for s in prompt['shots']}}
        out = {}
        for shot in [s['shot_id'] for s in prompt['shots']]:
            entry, own = rows.get(shot), True
            if entry is None:
                entry, own = rows.get('*'), False
            if entry is None:
                continue
            value, quotes = entry if isinstance(entry, tuple) else (entry, entry)
            quotes = quotes if isinstance(quotes, list) else [quotes]
            found = []
            for quote in quotes:
                places = ([shot, 'global'] if own else ['global'])
                source = next((p for p in places if normal(quote) in normal(texts[p])), None)
                if source is None:
                    errors.append(f'{index} {eid} {shot}: quote not found: {quote!r}')
                found.append(dict(fact_id=source, quote=quote))
            out[shot] = dict(value=value, quotes=found)
        unknown = set(rows) - set(texts) - {'*'}
        if unknown:
            errors.append(f'{index} {eid}: unknown shots {sorted(unknown)}')
        episodes[eid] = out
    if errors:
        print('\n'.join(errors))
        sys.exit(1)
    shots = sum(len(v) for v in episodes.values())
    (HERE / 'style_decisions.json').write_text(json.dumps(dict(
        rule=__doc__.strip(), episodes=episodes, not_filled=[dict(row, episode_id=ids[row['index']]) for row in NOT_FILLED]),
        ensure_ascii=False, indent=1) + '\n')
    first = sum(index < 200 for index in STYLES)
    print(json.dumps(dict(episodes=len(episodes), first_200=first, shots=shots)))


if __name__ == '__main__':
    main()

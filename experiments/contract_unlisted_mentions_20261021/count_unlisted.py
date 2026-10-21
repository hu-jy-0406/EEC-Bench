#!/usr/bin/env python3
"""Which kinds of things do the Full400 prompts mention without an own entity entry in contract.json?

For each episode, every keyword hit in the global prompt or a shot prompt is classified as:
  listed   - the word occurs in some entity NAME (it has its own entry, approximately);
  nested   - not in a name, but in an entity description or a claim's expected text (attribute of an entity);
  unscored - only in the coverage "unscored" quotes (the compiler decided not to evaluate it);
  missing  - in the prompt only.
Counted once per (episode, keyword). English keyword matching, approximate. -> unlisted_counts.json
"""
import collections, glob, json, re
from pathlib import Path
HERE = Path(__file__).resolve().parent
EPISODES = HERE.parent / 'episode_contracts_20260921/deliverables/episodes'
CATEGORIES = {
    'worn accessories': ['wristwatch', 'watch', 'sunglasses', 'glasses', 'earring', 'ear stud', 'necklace', 'bracelet', 'ring',
                         'hat', 'cap', 'beanie', 'helmet', 'scarf', 'tie', 'bow tie', 'belt', 'gloves', 'headband', 'headphones',
                         'mask', 'badge', 'lanyard', 'apron', 'veil', 'crown', 'hood'],
    'garments': ['shirt', 't-shirt', 'jacket', 'coat', 'dress', 'gown', 'sweater', 'hoodie', 'trousers', 'pants', 'jeans', 'skirt',
                 'shorts', 'blouse', 'vest', 'suit', 'robe', 'uniform', 'boots', 'shoes', 'sneakers', 'cardigan', 'top', 'sleeves'],
    'held or carried props': ['phone', 'smartphone', 'cup', 'mug', 'bottle', 'book', 'bag', 'backpack', 'purse', 'briefcase',
                              'umbrella', 'cigarette', 'pen', 'paper', 'papers', 'letter', 'gun', 'pistol', 'rifle', 'knife', 'sword',
                              'microphone', 'camera', 'laptop', 'tray', 'plate', 'guitar', 'ball', 'flashlight', 'stick', 'tablet'],
    'furniture and fixtures': ['table', 'chair', 'desk', 'sofa', 'couch', 'bed', 'bench', 'counter', 'shelf', 'shelves', 'cabinet',
                               'lamp', 'door', 'doorway', 'window', 'curtain', 'curtains', 'wall', 'walls', 'floor', 'ceiling', 'stairs',
                               'staircase', 'railing', 'fence', 'sign', 'poster', 'painting', 'mirror', 'pillar', 'column'],
    'background people and crowds': ['crowd', 'people', 'spectators', 'audience', 'pedestrians', 'passersby', 'bystanders', 'guests',
                                     'onlookers', 'extras', 'figure', 'figures', 'dancers', 'soldiers', 'students', 'customers', 'patrons'],
    'vehicles': ['car', 'cars', 'truck', 'bus', 'bike', 'bicycle', 'motorcycle', 'boat', 'train', 'taxi', 'van', 'traffic'],
    'nature and scenery': ['tree', 'trees', 'sky', 'clouds', 'sun', 'moon', 'sea', 'ocean', 'waves', 'mountain', 'mountains', 'grass',
                           'flowers', 'plants', 'snow', 'river', 'beach', 'field', 'forest', 'hills', 'water', 'rocks'],
    'light and atmosphere': ['light', 'lights', 'glow', 'smoke', 'fog', 'mist', 'shadow', 'shadows', 'reflection', 'fire', 'flames', 'sparks'],
    'animals': ['dog', 'cat', 'bird', 'birds', 'horse', 'fish'],
}

def found(word, text):
    return re.search(r'(?<![a-z-])' + re.escape(word) + r'(?![a-z])', text) is not None

counts = {cat: collections.Counter() for cat in CATEGORIES}
words = {cat: {s: collections.Counter() for s in ('listed', 'nested', 'unscored', 'missing')} for cat in CATEGORIES}
examples = collections.defaultdict(list)
episodes = sorted(EPISODES.glob('*/contract.json'))
for path in episodes:
    c = json.load(open(path))
    ents = c['entity_descriptions'].values()
    names = ' | '.join(e['name'] for e in ents).lower()
    descriptions = ' | '.join(e.get('description', '') for e in ents).lower()
    claims = ' | '.join(str(cl.get('expected', '')) + ' ' + str(cl.get('predicate', '')) for cl in c['claims']).lower()
    unscored = ' | '.join(u['quote'] for row in c['coverage'] for u in row.get('unscored', [])).lower()
    prompt = c['prompt']
    text = ' '.join([prompt.get('global_prompt') or ''] + [s['text'] for s in prompt['shots']]).lower()
    for cat, kws in CATEGORIES.items():
        seen = set()
        for w in sorted(kws, key=len, reverse=True):
            if not found(w, text) or any(w in s for s in seen):
                continue
            seen.add(w)
            if found(w, names): status = 'listed'
            elif found(w, descriptions) or found(w, claims): status = 'nested'
            elif found(w, unscored): status = 'unscored'
            else: status = 'missing'
            counts[cat][status] += 1; words[cat][status][w] += 1
            if status in ('unscored', 'missing') and len(examples[(cat, status)]) < 4:
                m = re.search(r'.{0,60}(?<![a-z-])' + re.escape(w) + r'(?![a-z]).{0,40}', text)
                examples[(cat, status)].append(f'{path.parent.name[:22]}: …{m.group(0)}…')
out = dict(episodes=len(episodes), categories={})
for cat in CATEGORIES:
    total = sum(counts[cat].values())
    out['categories'][cat] = dict(mentions=total, **{s: counts[cat][s] for s in ('listed', 'nested', 'unscored', 'missing')},
                                  not_listed=total - counts[cat]['listed'],
                                  top_not_listed=(words[cat]['nested'] + words[cat]['unscored'] + words[cat]['missing']).most_common(8),
                                  examples_unscored=examples[(cat, 'unscored')], examples_missing=examples[(cat, 'missing')])
json.dump(out, open(HERE / 'unlisted_counts.json', 'w'), indent=1)
print(f"{'category':30s} {'mentions':>8s} {'listed':>7s} {'nested':>7s} {'unscored':>8s} {'missing':>8s}")
for cat, r in sorted(out['categories'].items(), key=lambda kv: -kv[1]['not_listed']):
    print(f"{cat:30s} {r['mentions']:8d} {r['listed']:7d} {r['nested']:7d} {r['unscored']:8d} {r['missing']:8d}   top not listed: {r['top_not_listed'][:6]}")

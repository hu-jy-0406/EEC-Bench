import json, sys
ref = {c['key']: c for c in json.load(open('reference.json'))['cases']}
runs = json.load(open('runs.json'))
for key in sys.argv[1:]:
    c = ref[key]
    print('#' * 10, key)
    for a in c['artifacts']:
        print(f"  {a['id']} {a['title']} [{a['expected_labels']}]")
    for r in runs[key]:
        if r['status'] != 'success':
            print(f"  -- {r['protocol']}/{r['run_id']}: {r['status']}")
            continue
        print(f"  -- {r['protocol']}/{r['run_id']} scores={r['scores']}")
        for i in r['issues']:
            lab = ' + '.join(f"{l['label']}:{l['subcategory']}={l['verdict'][:4]}/{l['severity']}" for l in i['labels'])
            print(f"     {i['issue_id']} {i['scope']} {lab} | {i['description']}")

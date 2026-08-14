import json, glob, sys, collections

sys.stdout.reconfigure(encoding='utf-8')

DATA_DIR = r'c:\Users\twink\4MATION\crawler\data'
RESULTS_DIR = r'C:\Users\twink\AppData\Local\Temp\claude\c--Users-twink-4MATION\c8fc7181-93c5-4994-811a-efe7af928da6\scratchpad\gt_audit_v3\results'

# --- load base GT (round-1 output = round-2 input) ---
base = []
with open(f'{DATA_DIR}\\gt_final_v2.jsonl', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line:
            base.append(json.loads(line))
base_by_id = {o['id']: o for o in base}
assert len(base) == 1651, f'expected 1651, got {len(base)}'

# --- load corpus for span verification ---
chunks = {}
with open(f'{DATA_DIR}\\chunks.jsonl', encoding='utf-8') as f:
    for line in f:
        c = json.loads(line)
        chunks[c['chunk_id']] = c

def norm(s):
    return ''.join(s.split())

# --- load all round-2 review results (one JSON array per batch file) ---
review = {}
dup = []
status_count = collections.Counter()
files = sorted(glob.glob(f'{RESULTS_DIR}\\*.json'))
print(f'{len(files)} result files found')
for fp in files:
    with open(fp, encoding='utf-8') as f:
        items = json.load(f)
    for it in items:
        rid = it['id']
        if rid in review:
            dup.append(rid)
        review[rid] = it
        status_count[it['status']] += 1

print('status counts (raw, may include dup overwrites):', dict(status_count))
if dup:
    print('WARNING duplicate ids across batches:', dup)

reviewed_ids = set(review)
print(f'reviewed items: {len(reviewed_ids)}')

# --- apply changes: only items that were sent for round-2 review can change;
# everything else in gt_final_v2.jsonl passes through untouched ---
v3 = []
change_log = []
span_errors = []

for o in base:
    rid = o['id']
    r = review.get(rid)
    new = dict(o)  # copy
    if r is None:
        v3.append(new)
        continue

    status = r['status']

    if status == 'OK':
        v3.append(new)
        continue

    changed_fields = {}
    for field in ('gt_chunk_id', 'gt_anchor_span', 'answerable'):
        if new.get(field) != r.get(field):
            changed_fields[field] = (new.get(field), r.get(field))
        new[field] = r.get(field)

    new_alt = r.get('gt_alt_evidence') or []
    if (new.get('gt_alt_evidence') or []) != new_alt:
        changed_fields['gt_alt_evidence'] = (new.get('gt_alt_evidence') or [], new_alt)
    new['gt_alt_evidence'] = new_alt
    new['review_status_v3'] = status
    new['review_reason_v3'] = r.get('reason', '')
    new['review_confidence_v3'] = r.get('confidence')

    # span verbatim check
    if new.get('gt_anchor_span') and new.get('gt_chunk_id'):
        c = chunks.get(new['gt_chunk_id'])
        if c is None:
            span_errors.append((rid, 'chunk_id not found', new['gt_chunk_id']))
        elif norm(new['gt_anchor_span']) not in norm(c['text']):
            span_errors.append((rid, 'span not verbatim in chunk', new['gt_chunk_id']))

    for alt in new.get('gt_alt_evidence', []) or []:
        c = chunks.get(alt.get('chunk_id'))
        if c is None:
            span_errors.append((rid, 'alt chunk_id not found', alt.get('chunk_id')))
        elif alt.get('span') and norm(alt['span']) not in norm(c['text']):
            span_errors.append((rid, 'alt span not verbatim', alt.get('chunk_id')))

    if changed_fields:
        change_log.append({'id': rid, 'status': status, 'changed': changed_fields, 'reason': r.get('reason', '')})

    v3.append(new)

# --- refresh derived QA fields against the CURRENT (gt_chunk_id, gt_anchor_span) pairing.
# span_verbatim_ok/cross_domain/answer_bf were computed once by judge_label.py at round-0 and
# never recomputed by build_gt_v2.py either, so any item whose chunk/span was corrected in
# round-1 or round-2 carries a stale flag from before the fix. eval_anchor.py filters on
# span_verbatim_ok/cross_domain, so a stale False/True here silently drops or leaks items.
for item in v3:
    cid = item.get('gt_chunk_id')
    span = item.get('gt_anchor_span')
    c = chunks.get(cid) if cid else None
    if c is not None:
        item['span_verbatim_ok'] = (not span) or (norm(span) in norm(c['text']))
        actual_bf = c.get('business_function')
        item['answer_bf'] = actual_bf
        item['cross_domain'] = bool(actual_bf and item.get('business_function') and actual_bf != item.get('business_function'))

print()
print('=== round-2 status counts (reviewed items only) ===')
final_status_count = collections.Counter(review[rid]['status'] for rid in reviewed_ids)
for k, v in final_status_count.most_common():
    print(k, v)

print()
print(f'actual field changes: {len(change_log)}')
print(f'span verification errors: {len(span_errors)}')
for e in span_errors[:30]:
    print(' ', e)

with open(f'{DATA_DIR}\\gt_final_v3.jsonl', 'w', encoding='utf-8') as f:
    for item in v3:
        f.write(json.dumps(item, ensure_ascii=False) + '\n')

with open(f'{DATA_DIR}\\gt_final_v3_changelog.json', 'w', encoding='utf-8') as f:
    json.dump(change_log, f, ensure_ascii=False, indent=2)

print()
print(f'wrote {len(v3)} lines to gt_final_v3.jsonl')
print(f'wrote {len(change_log)} change records to gt_final_v3_changelog.json')

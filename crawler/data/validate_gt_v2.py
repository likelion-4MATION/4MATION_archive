import json, sys, collections

sys.stdout.reconfigure(encoding='utf-8')

DATA_DIR = r'c:\Users\mungn\4MATION\crawler\data'

errors = []

def check(cond, msg):
    if not cond:
        errors.append(msg)

# --- load files ---
with open(f'{DATA_DIR}\\gt_final.jsonl', encoding='utf-8') as f:
    orig_lines = [l for l in f if l.strip()]
    orig = [json.loads(l) for l in orig_lines]

with open(f'{DATA_DIR}\\gt_final_v2.jsonl', encoding='utf-8') as f:
    v2_lines = [l for l in f if l.strip()]
    v2 = [json.loads(l) for l in v2_lines]

with open(f'{DATA_DIR}\\chunks.jsonl', encoding='utf-8') as f:
    chunks = {}
    for l in f:
        c = json.loads(l)
        chunks[c['chunk_id']] = c

# 1. basic structure
check(len(v2) == 1651, f'total count != 1651 (got {len(v2)})')
ids = [x['id'] for x in v2]
check(len(ids) == len(set(ids)), f'duplicate ids found: {len(ids)-len(set(ids))}')
check(all('id' in x and x['id'] for x in v2), 'missing id field in some entries')

orig_ids = set(x['id'] for x in orig)
v2_ids = set(ids)
check(orig_ids == v2_ids, f'id set mismatch: missing={orig_ids-v2_ids}, extra={v2_ids-orig_ids}')

# 2. span checks (project convention from judge_label.py: whitespace-insensitive containment)
def norm(s):
    return ''.join(s.split())

for x in v2:
    span = x.get('gt_anchor_span')
    cid = x.get('gt_chunk_id')
    if span is not None:
        check(span != '', f'{x["id"]}: empty string span (should be null)')
        c = chunks.get(cid)
        check(c is not None, f'{x["id"]}: gt_chunk_id {cid} not found in chunks.jsonl')
        if c is not None:
            check(norm(span) in norm(c['text']), f'{x["id"]}: gt_anchor_span not verbatim in chunk {cid}')
    # alt evidence
    for alt in x.get('gt_alt_evidence', []) or []:
        ac = chunks.get(alt.get('chunk_id'))
        check(ac is not None, f'{x["id"]}: alt_evidence chunk_id {alt.get("chunk_id")} not found')
        if ac is not None and alt.get('span'):
            check(norm(alt['span']) in norm(ac['text']), f'{x["id"]}: alt_evidence span not verbatim in chunk {alt.get("chunk_id")}')

# 3. answerable consistency
for x in v2:
    if x['answerable'] is False:
        check(x.get('gt_chunk_id') is None, f'{x["id"]}: answerable=false but gt_chunk_id is set ({x.get("gt_chunk_id")})')
        check(x.get('gt_anchor_span') is None, f'{x["id"]}: answerable=false but gt_anchor_span is set')
    else:
        # answerable=true: chunk should generally exist unless NO_SPAN-without-chunk is impossible per spec (NO_SPAN keeps chunk, only span null)
        check(x.get('gt_chunk_id') is not None, f'{x["id"]}: answerable=true but gt_chunk_id is null')

# 4. MULTI schema
for x in v2:
    alt = x.get('gt_alt_evidence')
    check(isinstance(alt, list), f'{x["id"]}: gt_alt_evidence is not a list')
    if x.get('review_status') == 'MULTI':
        check(len(alt) >= 1, f'{x["id"]}: MULTI status but empty gt_alt_evidence')
        for a in alt:
            check('chunk_id' in a and 'span' in a, f'{x["id"]}: alt_evidence entry missing chunk_id/span')

# 5. original file untouched
import hashlib
with open(f'{DATA_DIR}\\gt_final.jsonl', 'rb') as f:
    orig_bytes = f.read()
# we didn't touch gt_final.jsonl in this script, but let's confirm line count still 1651
check(len(orig) == 1651, f'gt_final.jsonl line count changed?! now {len(orig)}')

# --- report ---
print(f'total checked: {len(v2)}')
status_count = collections.Counter(x.get('review_status', 'OK') for x in v2)
for k, v in status_count.most_common():
    print(f'  {k}: {v}')

print()
if errors:
    print(f'VALIDATION FAILED: {len(errors)} errors')
    for e in errors[:50]:
        print(' -', e)
    sys.exit(1)
else:
    print('VALIDATION PASSED: all checks OK')

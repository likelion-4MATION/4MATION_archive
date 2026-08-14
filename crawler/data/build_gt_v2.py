import json, glob, sys, io, collections

sys.stdout.reconfigure(encoding='utf-8')

DATA_DIR = r'c:\Users\mungn\4MATION\crawler\data'
RESULTS_DIR = r'C:\Users\mungn\AppData\Local\Temp\claude\c--Users-mungn-4MATION\c2df49fb-3ccf-45be-9624-b92df19bdf84\scratchpad\gt_review\results'

# --- load original GT ---
orig = []
with open(f'{DATA_DIR}\\gt_final.jsonl', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line:
            orig.append(json.loads(line))
orig_by_id = {o['id']: o for o in orig}
assert len(orig) == 1651, f'expected 1651, got {len(orig)}'

# --- load corpus for span verification ---
chunks = {}
with open(f'{DATA_DIR}\\chunks.jsonl', encoding='utf-8') as f:
    for line in f:
        c = json.loads(line)
        chunks[c['chunk_id']] = c

# --- load all review results ---
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

# --- manual span corrections: some agents collapsed the source's internal
# newlines into spaces when quoting a span. These are verbatim fixes only
# (same intended evidence), restoring the corpus's actual '\n' breaks.
SPAN_OVERRIDES = {
    'train4-HIDE-042': '실명인증\n(간편인증 또는 휴대폰인증)',
    'train4-HIDE-051': '실명인증\n(간편인증 또는 휴대폰인증)\n신고하기\n비밀번호 입력 후 신고 완료\n접수번호 기록\n(접수번호 자동부여)',
    'train4-HIDE-065': '은닉재산신고 상담신청\n은닉재산신고 전 담당자와 미리 상담이 필요하신 경우 신청하십시오.',
    'train4-HIDE-070': '은닉재산신고 상담신청\n은닉재산신고 전 담당자와 미리 상담이 필요하신 경우 신청하십시오.',
    'train4-HIDE-072': '은닉재산이란 금융부실관련자의 재산으로서 국내 또는 해외에 은닉한 동산 · 부동산 등 일체의 재산을 말합니다.\n- 다만, 공부상 부실관련자 본인 명의로 되어 있는 국내 소재 부동산은 은닉재산으로 보지 않습니다.',
    'train5-HIDE-013': '은닉재산신고 및 신고내역 조회\n은닉재산신고 절차\n예금보험공사 홈페이지에서는 단계를 거쳐 금융부실관련자의 은닉재산신고 및 이미 신고하신 내역을 조회할 수 있습니다.',
    'train5-HIDE-031': '제보건수(건) | 발견재산\n회수액(억원) | 포상금(억원)\n511 | 918 | 67.6',
    'train5-HIDE-034': '제보건수(건) | 발견재산\n회수액(억원) | 포상금(억원)\n511 | 918 | 67.6',
    'train5-HIDE-035': '□ 포상제외\n- 공사 또는 채권기관이 이미 인지하고 있는 재산을 신고한 경우\n(다만, 신고가 없었더라면 부실관련자의 은닉재산 회수가 곤란한 경우에는 포상금 지급)\n- 등기부 또는 지적공부상 부실관련자 본인의 명의로 등기 또는 등록되어 있는 국내 소재 부동산을 신고한 경우\n(다만, 신고 이전에 실시한 재산조사에서 발견되지 않은 경우에는 포상금 지급)\n- 공사 또는 채권기관의 전 · 현직 임 · 직원이 자기 직무와 관련하여 신고한 경우 및 이에 준하는 경우\n- 포상금 지급 전까지 신고자가 현행 법령을 위반하여 신고한 것으로 확인된 경우\n- 신고자가 익명으로 신고하는 등으로 신고자 확인이나 신고자와 연락이 불가능한 경우',
    'train5-HIDE-046': '인터넷은 예금보험공사 홈페이지(\nhttp://www.kdic.or.kr\n)의 금융부실관련자 은닉재산 신고센터 창을 이용',
}
for rid, span in SPAN_OVERRIDES.items():
    if rid in review:
        review[rid]['gt_anchor_span'] = span

# --- manual consistency fixes for 3 records the review agents left in a
# self-contradictory state (found by validate_gt_v2.py, resolved by
# re-checking the actual corpus) ---
# train-PROT-048: FIX status but no gt_chunk_id was given even though the
# original gt_chunk_id was already null. Located the chunk that actually
# contains the proposed span.
review['train-PROT-048']['gt_chunk_id'] = 'kdic-www-sp-dpstrprot-selectProtSystProtSumr#02'
# train-UNCL-032: WRONG_CHUNK supplied a real chunk/span showing no
# nationality restriction exists, but left answerable=false (contradiction).
review['train-UNCL-032']['answerable'] = True
# train5-DEBT-001: NO_SPAN correctly nulled the (irrelevant) span but also
# nulled gt_chunk_id while answerable stayed true. Point chunk_id at the
# KDIC 재기지원 overview page (the other side of the comparison the
# question asks about); span stays null per NO_SPAN semantics.
review['train5-DEBT-001']['gt_chunk_id'] = 'kdic-www-rb-lbltajmt-LbltAjmtSprtLbltAjmtSyst-selectScrn#00'

print('status counts (raw, may include dup overwrites):', dict(status_count))
if dup:
    print('WARNING duplicate ids across batches:', dup)

missing = set(orig_by_id) - set(review)
extra = set(review) - set(orig_by_id)
print(f'missing from review: {len(missing)}')
print(f'extra ids not in orig: {len(extra)}')
if missing:
    print('sample missing:', list(missing)[:10])
if extra:
    print('sample extra:', list(extra)[:10])

# --- apply changes ---
v2 = []
change_log = []
final_status_count = collections.Counter()
span_errors = []

for o in orig:
    rid = o['id']
    r = review.get(rid)
    new = dict(o)  # copy
    if r is None:
        # not reviewed somehow -- keep as-is, flag
        final_status_count['MISSING_REVIEW'] += 1
        v2.append(new)
        continue

    status = r['status']
    final_status_count[status] += 1

    if status == 'OK':
        new.setdefault('gt_alt_evidence', [])
        v2.append(new)
        continue

    # apply field-level changes
    changed_fields = {}
    for field in ('gt_chunk_id', 'gt_anchor_span', 'answerable'):
        if field in r:
            if new.get(field) != r[field]:
                changed_fields[field] = (new.get(field), r[field])
            new[field] = r[field]

    if 'gt_alt_evidence' in r:
        new['gt_alt_evidence'] = r['gt_alt_evidence']
    else:
        new.setdefault('gt_alt_evidence', [])

    new['review_status'] = status
    new['review_reason'] = r.get('reason', '')
    new['review_confidence'] = r.get('confidence')

    # span verbatim check (project convention from judge_label.py: whitespace-insensitive containment)
    def norm(s):
        return ''.join(s.split())

    if new.get('gt_anchor_span') and new.get('gt_chunk_id'):
        c = chunks.get(new['gt_chunk_id'])
        if c is None:
            span_errors.append((rid, 'chunk_id not found', new['gt_chunk_id']))
        elif norm(new['gt_anchor_span']) not in norm(c['text']):
            span_errors.append((rid, 'span not verbatim in chunk', new['gt_chunk_id']))

    # alt evidence span verbatim check
    for alt in new.get('gt_alt_evidence', []) or []:
        c = chunks.get(alt.get('chunk_id'))
        if c is None:
            span_errors.append((rid, 'alt chunk_id not found', alt.get('chunk_id')))
        elif alt.get('span') and norm(alt['span']) not in norm(c['text']):
            span_errors.append((rid, 'alt span not verbatim', alt.get('chunk_id')))

    if changed_fields:
        change_log.append({'id': rid, 'status': status, 'changed': changed_fields, 'reason': r.get('reason', '')})

    v2.append(new)

print()
print('=== final status counts ===')
for k, v in final_status_count.most_common():
    print(k, v)

print()
print(f'actual field changes: {len(change_log)}')
print(f'span verification errors: {len(span_errors)}')
for e in span_errors[:30]:
    print(' ', e)

# write gt_final_v2.jsonl
with open(f'{DATA_DIR}\\gt_final_v2.jsonl', 'w', encoding='utf-8') as f:
    for item in v2:
        f.write(json.dumps(item, ensure_ascii=False) + '\n')

with open(f'{DATA_DIR}\\gt_final_v2_changelog.json', 'w', encoding='utf-8') as f:
    json.dump(change_log, f, ensure_ascii=False, indent=2)

print()
print(f'wrote {len(v2)} lines to gt_final_v2.jsonl')
print(f'wrote {len(change_log)} change records to gt_final_v2_changelog.json')

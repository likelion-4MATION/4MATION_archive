"""gt_final_v3_q2.jsonl -> gt_schema_v6.jsonl (eval_anchor_v3.py 입력 스키마).

eval_anchor_v3.py는 gt_chunk_ids(list) + chunk_relation(single/or/and)을 요구하지만
gt_final_v3_q2.jsonl은 gt_chunk_id(단수) + gt_alt_evidence(멀티골드 보조근거)로 저장돼
있다. 원본(gt_final_v3_q2.jsonl)은 건드리지 않고 이 변환만 별도 산출물로 만든다.

gt_alt_evidence가 있는 11건은 전부 "두 청크를 함께 봐야 판단 가능"한 조합형이라
chunk_relation="and"로 매핑한다(OR로 판단된 사례는 지금까지 없었음).
"""
import json

DATA_DIR = r'c:\Users\twink\4MATION\crawler\data'

src = [json.loads(l) for l in open(f'{DATA_DIR}\\gt_final_v3_q2.jsonl', encoding='utf-8') if l.strip()]

out = []
n_and = 0
for x in src:
    gt_chunk_ids = []
    if x.get('gt_chunk_id'):
        gt_chunk_ids.append(x['gt_chunk_id'])
    alt = x.get('gt_alt_evidence') or []
    for a in alt:
        if a.get('chunk_id') and a['chunk_id'] not in gt_chunk_ids:
            gt_chunk_ids.append(a['chunk_id'])

    relation = 'and' if alt else 'single'
    if alt:
        n_and += 1

    out.append({
        'id': x['id'],
        'business_function': x['business_function'],
        'question': x['question'],
        'answerable': x['answerable'],
        'gt_chunk_ids': gt_chunk_ids,
        'chunk_relation': relation,
    })

with open(f'{DATA_DIR}\\gt_schema_v6.jsonl', 'w', encoding='utf-8') as f:
    for item in out:
        f.write(json.dumps(item, ensure_ascii=False) + '\n')

print(f'wrote {len(out)} records to gt_schema_v6.jsonl ({n_and} with chunk_relation=and)')

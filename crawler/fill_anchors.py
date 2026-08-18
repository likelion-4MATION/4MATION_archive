"""수기 앵커 채우기 — 미앵커 gold 청크에 근거 스팬을 부여한다.

배경: 표 원자성 수정으로 재청킹하면 `chunk_id`가 바뀌어, 앵커가 없는 gold는
`chunk_id` 폴백이 죽는다(HOLES H30). `and`는 ALL 판정이라 죽은 id 하나가 문항
전체를 불가능하게 만들어 정본 수치를 누른다(TEST id 의존도 16.7% → 23.7%).

**이것은 GT 조작이 아니다.** gold 청크 집합을 바꾸지 않고, 이미 gold인 청크의
근거를 id 대신 텍스트로 표현할 뿐이다. 스팬은 **옛 gold 청크 원문에서 고른 것**이며
(생성 아님) 두 단계로 검증한다 — ① 옛 gold 청크에 verbatim 존재 ② 새 코퍼스에
verbatim 존재. 검색되기 쉬운 문장을 고르는 게 아니라 그 청크의 근거를 고른다.

한계: 표 청크(구비서류·보호대상)의 스팬은 '최소 근거 문장'이 아니라 해당 행을
특정하는 locator에 가깝다 — 표에는 근거 문장이라 할 단위가 없다. 자동화
파이프라인에 넣지 않고 수기 산출물로 관리한다(사람 결정).

사용:
  cd crawler && python fill_anchors.py --map /tmp/anchor_fill.json
"""
from __future__ import annotations
import argparse, json, pathlib, sys
import eval_anchor_v3 as ev3

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default="data/anchor_fill_430.json")
    ap.add_argument("--chunks", default="data/chunks.jsonl")
    ap.add_argument("--old-chunks", default=None, help="재청킹 전 코퍼스(원문 검증용)")
    ap.add_argument("--sets", nargs="+", default=["430", "355"])
    ap.add_argument("--suffix", default="_anchored")
    args = ap.parse_args()

    fill = {k: v for k, v in json.load(open(args.map, encoding="utf-8")).items()
            if not k.startswith("_")}
    new = {c["chunk_id"]: ev3._norm_text(c.get("text", ""))
           for c in ev3._load_jsonl(pathlib.Path(args.chunks))}
    # ② 새 코퍼스 verbatim 검증 — 하나라도 실패하면 중단(조용히 틀리면 판정이 오염된다)
    miss = [k for k, v in fill.items() if not any(ev3._norm_text(v) in t for t in new.values())]
    if miss:
        sys.exit(f"[중단] 새 코퍼스에 없는 앵커 {len(miss)}개: {miss[:3]}")
    if args.old_chunks:
        old = {c["chunk_id"]: ev3._norm_text(c.get("text", ""))
               for c in ev3._load_jsonl(pathlib.Path(args.old_chunks))}
        bad = [k for k, v in fill.items()
               if k in old and ev3._norm_text(v) not in old[k]]
        if bad:
            sys.exit(f"[중단] 옛 gold 청크 원문에 없는 앵커 {len(bad)}개: {bad[:3]}")
        print(f"[검증] 옛 gold 청크 원문 verbatim {len(fill)}/{len(fill)}")
    print(f"[검증] 새 코퍼스 verbatim {len(fill)}/{len(fill)}")

    for name in args.sets:
        src = pathlib.Path(f"../final_testset/gt_natural{name}.jsonl")
        rows = ev3._load_jsonl(src)
        added = touched = 0
        for r in rows:
            anchors = list(r.get("gt_anchors") or ([r["gt_anchor_span"]] if r.get("gt_anchor_span") else []))
            before = len(anchors)
            for c in ev3._get_gt_chunk_ids(r):
                a = fill.get(c)
                # 이미 어떤 앵커가 그 gold를 덮으면 추가하지 않는다
                if not a or a in anchors:
                    continue
                if c in new and any(ev3._norm_text(x) in new[c] for x in anchors):
                    continue
                anchors.append(a)
            if len(anchors) != before:
                touched += 1
                added += len(anchors) - before
            r["gt_anchors"] = anchors
        out = src.parent / f"gt_natural{name}{args.suffix}.jsonl"
        out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                       encoding="utf-8")
        print(f"[out] {out} · {len(rows)}행 · 앵커 추가 {added}개 ({touched}문항)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

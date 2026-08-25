"""앵커 라벨 점검 + 미앵커 gold 청크의 후보 앵커 추출.

배경: `and` 문항은 gold가 2~4개인데 앵커는 1개뿐인 경우가 대부분이라, 나머지 gold는
`chunk_id` 폴백으로 판정된다(eval.py chunk 판정의 하이브리드). 그 폴백분이 얼마나 되고
어느 청크에 몰려 있는지, 그리고 결정론적으로 후보 앵커를 뽑을 수 있는지 본다.

**앵커를 생성하지 않는다.** 후보는 청크 원문에서 '고른' 줄이며, 그 줄이 이 질문의
근거인지는 사람이 확인해야 한다. 특히 표 청크에서 뽑힌 후보는 근거 문장이 아니라
청크 식별자(locator)에 가깝다 — 재청킹에는 견디지만 '최소 근거 스팬'은 아니다.

후보 선정 규칙(결정론):
  청크 본문의 줄 중 MIN_LINE자 이상이면서 **코퍼스에서 그 청크에만 존재하는** 줄.
  그런 줄이 여럿이면 가장 짧은 것(최소 스팬 원칙). 없으면 후보 없음으로 남긴다.

사용:
  cd crawler && python audit_anchors.py --gt ../final_testset/gt_natural430.jsonl
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib

import eval as ev3

MIN_LINE = 12          # 후보 줄 최소 길이(정규화 전 원문 기준)
MAX_CANDIDATES = 3     # 청크당 제시할 후보 수


def unique_lines(chunk: dict, norm_text: dict[str, str]) -> list[str]:
    """그 청크에만 존재하는 줄들을 짧은 순으로. 없으면 빈 리스트."""
    out = []
    for line in {l.strip() for l in chunk["text"].split("\n") if len(l.strip()) >= MIN_LINE}:
        nl = ev3._norm_text(line)
        owners = [cid for cid, t in norm_text.items() if nl in t]
        if len(owners) == 1 and owners[0] == chunk["chunk_id"]:
            out.append(line)
    return sorted(out, key=len)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", required=True)
    ap.add_argument("--chunks", default="data/chunks.jsonl")
    ap.add_argument("--report", default=None)
    ap.add_argument("--out", default=None, help="후보 앵커 JSONL")
    args = ap.parse_args()

    chunks = {c["chunk_id"]: c for c in ev3._load_jsonl(pathlib.Path(args.chunks))}
    nt = {k: ev3._norm_text(v.get("text", "")) for k, v in chunks.items()}
    rows = ev3._load_jsonl(pathlib.Path(args.gt))
    items = [r for r in rows if r.get("answerable") is True and ev3._get_gt_chunk_ids(r)]
    stem = pathlib.Path(args.gt).stem
    report_path = args.report or f"data/anchor_audit_{stem}.md"
    out_path = args.out or f"data/anchor_candidates_{stem}.jsonl"

    # ── 커버리지 집계 ──
    per_rel = collections.defaultdict(lambda: {"n": 0, "gold": 0, "cov": 0, "full": 0})
    gaps: list[tuple[dict, str]] = []          # (문항, 미앵커 gold chunk_id)
    for it in items:
        rel = ev3._get_relation_label(it)
        gold = ev3._get_gt_chunk_ids(it)
        anchors = ev3._get_gt_anchors(it)
        una, _stale = ev3._split_gold_by_anchor(gold, anchors, nt)
        s = per_rel[rel]
        s["n"] += 1
        s["gold"] += len(gold)
        s["cov"] += len(gold) - len(una)
        s["full"] += (not una)
        gaps += [(it, c) for c in una if c in chunks]

    gap_chunks = collections.Counter(c for _, c in gaps)
    tot_gold = sum(s["gold"] for s in per_rel.values())
    tot_cov = sum(s["cov"] for s in per_rel.values())

    L = []
    a = L.append
    a(f"# 앵커 라벨 점검 — `{args.gt}`\n")
    a(f"- 평가 대상 {len(items)}문항 · gold 청크 {tot_gold}개 중 앵커가 덮는 것 "
      f"**{tot_cov}개({tot_cov / tot_gold:.1%})** · 미앵커 {tot_gold - tot_cov}개")
    a(f"- 미앵커가 걸린 고유 청크 **{len(gap_chunks)}개** (문항×청크 쌍 {len(gaps)}건)\n")
    a("## relation별 커버리지\n")
    a("| relation | 문항 | gold 청크 | 앵커 커버 | 전부 덮인 문항 |")
    a("|---|---:|---:|---:|---:|")
    for rel, s in sorted(per_rel.items(), key=lambda t: -t[1]["n"]):
        a(f"| `{rel}` | {s['n']} | {s['gold']} | {s['cov']} ({s['cov'] / s['gold']:.0%}) | "
          f"{s['full']} ({s['full'] / s['n']:.0%}) |")

    # ── 미앵커 청크별 후보 ──
    a("\n## 미앵커 gold 청크와 후보 앵커\n")
    a("후보는 **청크 원문에서 고른 줄**이다(창작 아님). 코퍼스 전체에서 그 청크에만 존재하는")
    a("줄 중 가장 짧은 것을 우선한다. **표 청크에서 뽑힌 후보는 근거 문장이 아니라 청크")
    a("식별자에 가깝다** — 재청킹에는 견디지만 '최소 근거 스팬'은 아니므로 사람 확인이 필요하다.\n")
    a("| 청크 | 걸린 문항 | 길이 | 문서 | 후보 앵커 |")
    a("|---|---:|---:|---|---|")
    records = []
    n_uniq = n_none = 0
    for cid, cnt in gap_chunks.most_common():
        ch = chunks[cid]
        cands = unique_lines(ch, nt)[:MAX_CANDIDATES]
        n_uniq += bool(cands)
        n_none += (not cands)
        shown = "<br>".join(f"`{c}`" for c in cands) or "**후보 없음**"
        a(f"| `{cid}` | {cnt} | {len(ch['text'])}자 | {ch['parent_doc_id'].split('-')[-1]} | {shown} |")
        records.append({"chunk_id": cid, "parent_doc_id": ch["parent_doc_id"],
                        "n_items": cnt, "text_len": len(ch["text"]),
                        "page_title": ch.get("page_title", ""),
                        "sub_category": ch.get("sub_category", ""),
                        "candidates": cands,
                        "status": "candidate" if cands else "no_unique_line",
                        "text": ch["text"]})
    a(f"\n- 유일한 줄로 후보를 뽑은 청크 **{n_uniq}/{len(gap_chunks)}** · 후보 없음 {n_none}개")

    # ── 미앵커가 몰린 문서 ──
    a("\n## 미앵커가 몰린 문서\n")
    a("| 문서 | 미앵커 청크 | 걸린 문항(중복 포함) |")
    a("|---|---:|---:|")
    bydoc = collections.Counter()
    bydoc_items = collections.Counter()
    for cid, cnt in gap_chunks.items():
        bydoc[chunks[cid]["parent_doc_id"]] += 1
        bydoc_items[chunks[cid]["parent_doc_id"]] += cnt
    for d, k in bydoc.most_common():
        a(f"| `{d}` | {k} | {bydoc_items[d]} |")

    pathlib.Path(report_path).write_text("\n".join(L) + "\n", encoding="utf-8")
    pathlib.Path(out_path).write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")

    print(f"평가 {len(items)}문항 · gold {tot_gold} · 앵커 커버 {tot_cov} ({tot_cov / tot_gold:.1%})")
    print(f"미앵커 고유 청크 {len(gap_chunks)}개 · 후보 추출 {n_uniq} · 후보 없음 {n_none}")
    for rel, s in sorted(per_rel.items(), key=lambda t: -t[1]["n"]):
        print(f"  {rel:<10} {s['n']:>3}문항 · gold {s['gold']:>3} · 커버 {s['cov']:>3}"
              f" ({s['cov'] / s['gold']:.0%}) · 전부 덮인 문항 {s['full']}")
    print(f"[out] {report_path}\n[out] {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

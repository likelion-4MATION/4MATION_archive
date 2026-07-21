"""착오송금 반환 대표질의의 실제 검색 top-3를 발표 슬라이드(HTML)로 출력.

현재 시스템은 '검색(retrieval)'까지 — 질의를 임베딩해 코사인/RRF로 top-k 청크를
반환한다(생성 단계 없음). 이 스크립트는 그 실제 반환 결과를 그대로 슬라이드로 만든다.

로컬(모델 캐시 있는 곳)에서 crawler/ 기준 실행:
    python slide_kmrs_top3.py
결과: slide_kmrs_top3.html  (브라우저로 열어 캡처)
"""
from __future__ import annotations

import html
import json
import pathlib

import rag

QUERY = "착오송금 반환은 어떤 경우에 신청할 수 있나요?"
TESTSET = "data/testset_merged.jsonl"
MODE = "hybrid"
TOPK = 3
OUT = "slide_kmrs_top3.html"


def gold_for(query: str) -> set[str]:
    for l in open(TESTSET, encoding="utf-8"):
        x = json.loads(l)
        if x["question"] == query:
            return set(x["gt_docs"])
    return set()


def snippet(text: str, n: int = 160) -> str:
    t = " ".join(text.split())
    return t[:n] + ("…" if len(t) > n else "")


def main() -> None:
    gold = gold_for(QUERY)
    hits = rag.Searcher().search(QUERY, k=TOPK, mode=MODE)

    cards = []
    for i, c in enumerate(hits, 1):
        is_gold = c["parent_doc_id"] in gold
        badge = ('<span class="b hit">정답 근거 ✓</span>' if is_gold
                 else '<span class="b oth">관련 청크</span>')
        cards.append(f"""
    <div class="card {'g' if is_gold else ''}">
      <div class="row">
        <span class="rank">#{i}</span>
        <span class="tag">{html.escape(c.get('business_function',''))}</span>
        {badge}
        <span class="score">score {c.get('_score','')}</span>
      </div>
      <div class="title">{html.escape(c.get('page_title',''))}</div>
      <div class="snip">{html.escape(snippet(c['text']))}</div>
      <div class="src">{html.escape(c['parent_doc_id'])}</div>
    </div>""")

    doc = f"""<!doctype html><html lang="ko"><meta charset="utf-8">
<title>착오송금 검색 top-3</title>
<style>
  body{{font-family:'Pretendard','Apple SD Gothic Neo','Malgun Gothic',sans-serif;
       background:#fff;color:#1c1917;margin:0;padding:40px}}
  .wrap{{max-width:900px;margin:0 auto}}
  h1{{font-size:22px;margin:0 0 4px}}
  .q{{font-size:15px;color:#57534e;margin:0 0 4px}}
  .meta{{font-size:12.5px;color:#78716c;margin:0 0 20px}}
  .card{{border:1px solid #e7e5e4;border-radius:14px;padding:16px 18px;margin-bottom:14px}}
  .card.g{{border-color:#16a34a;background:#f0fdf4}}
  .row{{display:flex;align-items:center;gap:10px;margin-bottom:8px;flex-wrap:wrap}}
  .rank{{font-weight:800;font-size:15px;color:#b45309}}
  .tag{{font-size:11.5px;font-weight:700;background:#f5f5f4;color:#57534e;padding:3px 10px;border-radius:999px}}
  .b{{font-size:11.5px;font-weight:800;padding:3px 10px;border-radius:999px}}
  .b.hit{{background:#dcfce7;color:#166534}} .b.oth{{background:#f5f5f4;color:#78716c}}
  .score{{margin-left:auto;font-size:11.5px;color:#a8a29e;font-family:ui-monospace,monospace}}
  .title{{font-size:15px;font-weight:700;margin-bottom:6px}}
  .snip{{font-size:13px;line-height:1.6;color:#292524}}
  .src{{font-size:11px;color:#a8a29e;font-family:ui-monospace,monospace;margin-top:10px;
        border-top:1px dashed #e7e5e4;padding-top:8px}}
</style>
<div class="wrap">
  <h1>RAG 검색 결과 — 착오송금 반환 신청</h1>
  <p class="q">Q. {html.escape(QUERY)}</p>
  <p class="meta">ko-sroberta-multitask · {MODE} (RRF) · top-{TOPK} 청크 · 초록 테두리 = 정답 근거 페이지</p>
  {''.join(cards)}
</div></html>"""
    pathlib.Path(OUT).write_text(doc, encoding="utf-8")

    print(f"Q: {QUERY}\n정답 gt: {sorted(gold)}\n")
    for i, c in enumerate(hits, 1):
        g = "✓GOLD" if c["parent_doc_id"] in gold else "     "
        print(f"[{i}] {g} score={c.get('_score')} | {c.get('business_function')}/{c.get('page_title')}")
        print(f"      {snippet(c['text'])}")
        print(f"      {c['parent_doc_id']}\n")
    print(f"슬라이드 → {OUT} (브라우저로 열어 캡처)")


if __name__ == "__main__":
    main()

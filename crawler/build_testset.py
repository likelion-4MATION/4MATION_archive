"""평가셋 v0 생성 — 질문-정답문서 쌍 (실전1 스펙 30~50건).

원천 (fins FAQ 게시판은 robots 차단이라 제외):
  1) www FAQ 페이지(예금자보호제도 FAQ · 은닉재산신고 FAQ)의 질문-답변 쌍
  2) 질문형 헤딩(본문 h4 "~인가요?/~나요?/~란?") 페이지
  3) 6대 업무 대표질문 6건(curated) — 자연어 질의, representative=True

정답은 문서(parent_doc_id) 단위. gt_docs 리스트 = 정답으로 인정하는 문서들.
산출: data/testset.jsonl {question · gt_docs · business_function · source · representative}
"""

from __future__ import annotations

import json
import re

CHUNKS = "data/chunks.jsonl"
OUT = "data/testset.jsonl"

# 6대 업무 대표질문 (자연어) — 정답 인정 문서 집합
REPRESENTATIVE = [
    ("예금자 보호 한도는 얼마인가요?", "예금자보호제도",
     ["kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn",
      "kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn"]),
    ("예금보험금은 어떻게 신청하나요?", "예금보험금 안내",
     ["kdic-www-sp-dpstrprot-DpsmIbamtAplyProc-selectScrn",
      "kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn",
      "kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn"]),
    ("고객 미수령금은 어떻게 조회하고 신청하나요?", "고객 미수령금 신청",
     ["kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn",
      "kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn"]),
    ("착오송금 반환은 어떤 경우에 신청할 수 있나요?", "착오송금 반환 신청",
     ["kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn",
      "kdic-www-sp-kmrs-kmrsItrd-selectScrn"]),
    ("신용회복 지원은 어떻게 받나요?", "채무조정 안내",
     ["kdic-www-rb-lbltajmt-LbltAjmtSprtCredRcvrySprt-selectScrn"]),
    ("은닉재산 신고 포상금은 얼마인가요?", "은닉재산 신고",
     ["kdic-www-sp-sprtfund-SprtFndCncmDclrGudn-selectScrn",
      "kdic-www-sp-sprtfund-SprtFndCncmDclrFaq-selectScrn"]),
]

HEADING_RE = re.compile(r"(\?|란|인가요|나요|되나요|습니까|무엇|어떻게)$")
BAD = re.compile(r"^(시겠|신청비용|영상|글자|열기)|^.{0,3}$")


def load_chunks() -> list[dict]:
    return [json.loads(l) for l in open(CHUNKS, encoding="utf-8")]


def faq_questions(chunks: list[dict]) -> list[dict]:
    out = []
    for c in chunks:
        lines = [l.strip() for l in c["text"].split("\n") if l.strip()]
        if len(lines) >= 2 and lines[0] == "질문":
            q = lines[1]
            if 6 <= len(q) <= 60:
                out.append({"question": q, "gt_docs": [c["parent_doc_id"]],
                            "business_function": c["business_function"],
                            "source": "faq", "representative": False})
    return out


def heading_questions(chunks: list[dict]) -> list[dict]:
    seen, out = set(), []
    for c in chunks:
        if c["text"].split("\n")[0].strip() == "질문":
            continue
        for ln in c["text"].split("\n"):
            ln = ln.strip()
            if not (6 <= len(ln) <= 40):
                continue
            if HEADING_RE.search(ln) and not BAD.search(ln):
                key = ln
                if key in seen:
                    continue
                seen.add(key)
                out.append({"question": ln, "gt_docs": [c["parent_doc_id"]],
                            "business_function": c["business_function"],
                            "source": "heading", "representative": False})
    return out


def main() -> None:
    chunks = load_chunks()
    items = [{"question": q, "gt_docs": docs, "business_function": bf,
              "source": "representative", "representative": True}
             for q, bf, docs in REPRESENTATIVE]
    items += faq_questions(chunks)
    items += heading_questions(chunks)

    # 질문 텍스트 기준 dedup (대표질문 우선 유지)
    seen, uniq = set(), []
    for it in items:
        k = it["question"]
        if k in seen:
            continue
        seen.add(k)
        uniq.append(it)

    with open(OUT, "w", encoding="utf-8") as f:
        for it in uniq:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    from collections import Counter
    print(f"평가셋 {len(uniq)}건 → {OUT}")
    print("  출처별:", dict(Counter(i["source"] for i in uniq)))
    print("  업무별:", dict(Counter(i["business_function"] for i in uniq)))
    print("  대표질문:", sum(1 for i in uniq if i["representative"]))
    if len(uniq) < 30:
        print("  ※ 30건 미만 — 헤딩 규칙 완화 필요")


if __name__ == "__main__":
    main()

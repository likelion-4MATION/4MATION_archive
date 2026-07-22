"""청킹 + 스키마 부착 → data/chunks.jsonl

설정(고정, 03 문서 노션 권고 준용):
- CHUNK_SIZE=800자, OVERLAP=100자 (문단/섹션 경계 우선)
- 표(연속 "cell | cell" 라인)는 절대 중간분할 금지 → 단독 청크
- FAQ 페이지(page_type/title에 'FAQ')는 질문-답변 1쌍 = 1청크 (크기 무시), '열기' 토글 제거
- FAQ/게시판 청크는 청크별 business_function 재태깅 (결정론적 키워드 규칙, 게이트 보호)

청크 스키마(11필드): chunk_id · parent_doc_id · business_function · sub_category ·
  page_type · coverage · variant · source_url · page_title · breadcrumb · text
"""

from __future__ import annotations

import glob
import json
import pathlib
import sys

PARSED_DIR = "data/parsed"
OUT_PATH = "data/chunks.jsonl"

CHUNK_SIZE = 800
OVERLAP = 100
MIN_CHUNK = 60   # 표 사이 낀 짧은 헤딩/라인 파편 병합 임계

SCHEMA_FIELDS = ["chunk_id", "parent_doc_id", "business_function", "sub_category",
                 "page_type", "coverage", "variant", "source_url",
                 "page_title", "breadcrumb", "text"]


def is_faq(rec: dict) -> bool:
    tag = (rec.get("page_type", "") or "") + (rec.get("page_title", "") or "")
    return "FAQ" in tag or "faq" in tag


def is_board(rec: dict) -> bool:
    """FAQ/게시판형 문서(청크별 업무 재태깅 대상). fins 통합 게시판(-cm-bbs-) 포함."""
    return is_faq(rec) or "-cm-bbs-" in rec.get("doc_id", "")


# ── 청크별 business_function 재태깅 (결정론적 키워드 규칙) ───────────────────
# 배경: fins 통합 게시판 FAQ(예: selectFaqNramtAply)는 여러 업무의 Q&A를 한 페이지에
# 담는데 URL 규칙상 문서 전체가 업무 1개로 태깅 → 청크 메타 오염 → 검색 혼입.
# 대책: FAQ/게시판 청크에 한해 청크별로 실제 업무를 재분류. 단 오분류를 막기 위해
#   (1) 다른 업무가 '원 태그보다' FAQ_MARGIN 이상 우세할 때만 재태깅
#   (2) 문서의 재태깅 비율이 FAQ_RETAG_GATE 미만이면(=대체로 맞는 문서) 통째로 원 태그 유지
# LLM 미개입·결정론 원칙 준수. 키워드는 변별력 높은 도메인 어휘.
FAQ_MARGIN = 2
FAQ_RETAG_GATE = 0.5

BF_KEYWORDS = {
    "예금자보호제도": [("예금보호", 2), ("보호한도", 3), ("보호대상", 2), ("후순위채권", 2),
                  ("부보금융", 2), ("원리금", 1), ("합병등기", 2), ("세전", 2),
                  ("예금자보호법", 2), ("비보호", 2), ("1인당", 1), ("명의", 1),
                  ("중도해지", 2), ("이자포함", 1)],
    "예금보험금 안내": [("예금보험금", 2), ("가지급금", 3), ("개산지급금", 2), ("보험사고", 2),
                  ("지급대행", 2), ("지급보류", 2), ("계약이전", 2), ("지급시기", 2),
                  ("지급기한", 1), ("청구", 1), ("위임장", 1)],
    "고객 미수령금 신청": [("미수령금", 3), ("파산배당금", 3), ("정산금", 2), ("찾아가지", 2),
                   ("통합신청", 1), ("상속인 금융거래", 3), ("휴면", 2)],
    "착오송금 반환 신청": [("착오송금", 3), ("잘못 보낸", 2), ("잘못 송금", 2), ("잘못 이체", 2),
                   ("반환지원", 3), ("수취인", 2), ("반환 신청", 1), ("송금확인", 1)],
    "채무조정 안내": [("채무조정", 3), ("채무정보", 2), ("개인회생", 3), ("파산면책", 3),
                 ("신용회복", 3), ("연체대출", 2), ("채무자", 1), ("부채증명", 2)],
    "은닉재산 신고": [("은닉재산", 3), ("부실관련자", 3), ("신고센터", 2), ("포상금", 3),
                 ("제보", 2), ("신고자", 2)],
}


def _classify_bf(text: str, orig: str) -> str:
    """청크 1개의 업무 추정. 원 태그보다 FAQ_MARGIN 이상 우세한 업무만 채택, 아니면 원 태그."""
    sc = {bf: sum(w * text.count(k) for k, w in kws) for bf, kws in BF_KEYWORDS.items()}
    top = max(sc, key=sc.get)
    if sc[top] == 0 or top == orig:
        return orig
    if sc[top] - sc.get(orig, 0) >= FAQ_MARGIN:
        return top
    return orig


def faq_bf_list(parts: list[str], orig: str) -> list[str]:
    """FAQ/게시판 문서의 청크별 업무 리스트. 재태깅 비율이 게이트 미만이면 통째로 원 태그."""
    prelim = [_classify_bf(p, orig) for p in parts]
    if not parts:
        return prelim
    retag_frac = sum(1 for b in prelim if b != orig) / len(parts)
    return prelim if retag_frac >= FAQ_RETAG_GATE else [orig] * len(parts)


# 수동 검증 오버라이드 — 팀 원문 대조로 확정된 청크별 업무(키워드 규칙 오분류 교정).
# selectFaqNramtAply(미수령금통합신청 FAQ): 본문이 예금보험금 지급/영업정지 Q&A로 채워져
#   키워드 규칙이 미수령금·예금자보호로 오태깅 → 인덱스 기준 수동 매핑으로 고정.
#   #00~01 공통(시스템 안내) · #02~05 예금자보호제도 · #06~ 예금보험금 안내.
def _nramtaply_bf(i: int) -> str:
    if i <= 1:
        return "공통"
    if i <= 5:
        return "예금자보호제도"
    return "예금보험금 안내"


FAQ_BF_OVERRIDE = {"kdic-fins-cm-bbs-selectFaqNramtAply": _nramtaply_bf}


def split_faq(text: str) -> list[str]:
    """'질문' 라인마다 새 Q&A 청크 시작. '열기' 토글 라인 제거."""
    lines = [l for l in text.split("\n") if l.strip() and l.strip() != "열기"]
    chunks, cur = [], []
    for l in lines:
        if l.strip() == "질문" and cur:
            chunks.append("\n".join(cur))
            cur = [l]
        else:
            cur.append(l)
    if cur:
        chunks.append("\n".join(cur))
    return [c.strip() for c in chunks if c.strip()]


def _blocks(text: str) -> list[tuple[str, str]]:
    """표(연속 |라인)는 ('table', ...) 원자 블록, 그 외는 ('text', 라인)."""
    lines = [l for l in text.split("\n") if l.strip()]
    out, i = [], 0
    while i < len(lines):
        if "|" in lines[i]:
            j = i
            while j < len(lines) and "|" in lines[j]:
                j += 1
            out.append(("table", "\n".join(lines[i:j])))
            i = j
        else:
            out.append(("text", lines[i]))
            i += 1
    return out


def split_generic(text: str) -> list[str]:
    chunks, cur = [], ""
    for kind, blk in _blocks(text):
        if kind == "table":
            if cur.strip():
                chunks.append(cur.strip())
            chunks.append(blk)          # 표 단독 청크 (중간분할 금지)
            cur = ""
            continue
        cand = (cur + "\n" + blk).strip() if cur else blk
        if len(cand) <= CHUNK_SIZE:
            cur = cand
        else:
            if cur.strip():
                chunks.append(cur.strip())
                cur = (cur[-OVERLAP:] + "\n" + blk).strip()   # 오버랩
            else:
                cur = blk
            while len(cur) > CHUNK_SIZE + OVERLAP:             # 긴 단일 문단 하드분할
                chunks.append(cur[:CHUNK_SIZE])
                cur = cur[CHUNK_SIZE - OVERLAP:]
    if cur.strip():
        chunks.append(cur.strip())
    return _merge_small(chunks)


def _merge_small(chunks: list[str], min_len: int = MIN_CHUNK) -> list[str]:
    """표 사이에 낀 짧은 헤딩/파편 청크를 인접 청크에 병합 (검색 노이즈 제거)."""
    out: list[str] = []
    for c in chunks:
        if out and (len(c) < min_len or len(out[-1]) < min_len):
            out[-1] = (out[-1] + "\n" + c).strip()
        else:
            out.append(c)
    return out


def make_chunks(rec: dict) -> list[dict]:
    text = rec.get("text", "")
    if not text.strip():
        return []
    faq = is_faq(rec)
    parts = split_faq(text) if faq else split_generic(text)
    orig_bf = rec.get("business_function", "")
    # FAQ/게시판 문서는 청크별 업무 재태깅(게이트 보호), 그 외는 문서 태그 상속
    bf_list = faq_bf_list(parts, orig_bf) if is_board(rec) else [orig_bf] * len(parts)
    doc_id = rec["doc_id"]
    ov = FAQ_BF_OVERRIDE.get(doc_id)
    if ov:
        bf_list = [ov(i) for i in range(len(parts))]
    out = []
    for i, part in enumerate(parts):
        out.append({
            "chunk_id": f"{doc_id}#{i:02d}",
            "parent_doc_id": doc_id,
            "business_function": bf_list[i],
            "sub_category": rec.get("sub_category", ""),
            "page_type": rec.get("page_type", ""),
            "coverage": rec.get("coverage", ""),
            "variant": rec.get("variant", ""),
            "source_url": rec.get("source_url", ""),
            "page_title": rec.get("page_title", ""),
            "breadcrumb": rec.get("breadcrumb", []),
            "text": part,
        })
    return out


def main() -> None:
    parsed = sorted(glob.glob(f"{PARSED_DIR}/*.json"))
    if not parsed:
        sys.exit(f"파싱 결과 없음: {PARSED_DIR}")
    all_chunks, skipped = [], []
    for p in parsed:
        rec = json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
        cs = make_chunks(rec)
        if not cs:
            skipped.append(rec["doc_id"])
        all_chunks.extend(cs)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    # 스키마 검증
    bad = []
    for c in all_chunks:
        miss = [k for k in SCHEMA_FIELDS if k not in c]
        empty = [k for k in ("chunk_id", "parent_doc_id", "business_function",
                             "source_url", "text") if not c.get(k)]
        if miss or empty:
            bad.append((c.get("chunk_id"), miss, empty))

    print(f"청크 {len(all_chunks)}건 (문서 {len(parsed)}건) → {OUT_PATH}")
    if skipped:
        print(f"  본문 비어 스킵: {skipped}")
    faqn = sum(1 for c in all_chunks if is_faq(c))
    print(f"  FAQ 청크: {faqn} · 일반 청크: {len(all_chunks)-faqn}")
    # 재태깅 요약 (parent 문서 태그와 청크 태그가 다른 청크 수)
    import collections
    doc_orig = {}
    for p in parsed:
        r = json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
        doc_orig[r["doc_id"]] = r.get("business_function", "")
    retagged = [c for c in all_chunks
                if c["business_function"] != doc_orig.get(c["parent_doc_id"], "")]
    print(f"  청크별 재태깅: {len(retagged)}건")
    for d, cnt in collections.Counter(c["parent_doc_id"] for c in retagged).most_common():
        print(f"    {cnt:2d}  {d} ({doc_orig[d]} → 청크별)")
    lens = [len(c["text"]) for c in all_chunks]
    print(f"  청크 길이 min/avg/max: {min(lens)}/{sum(lens)//len(lens)}/{max(lens)}")
    print("  스키마 검증:", "전건 유효" if not bad else f"위반 {len(bad)}건: {bad[:5]}")
    if bad:
        sys.exit(1)


if __name__ == "__main__":
    main()

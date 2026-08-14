"""FAQ 청크 BF 태깅 — 라우터 조인 레이어 (faq_routing_bf.md 구현)

부모 문서 태그 상속(P1) · 게이트 롤백(P2) · 순번 조인 오버라이드(P3)를 대체한다.
FAQ 청크의 질문 문장을 라우터에 태워 BF를 재산출하고, 결과를 chunks.jsonl이 아닌
별도 레이어(data/bf_map.jsonl)에 qhash 조인 키로 기록한다.

원칙 (문서 0절):
- 개별 청크의 bf 값을 손으로 고치지 않는다. 규칙만 고치고 전체 재실행한다.
- source: manual 값은 이 단계에서 생성하지 않는다.
- chunks.jsonl을 수정하지 않는다.
- 질문 문장만 라우터에 입력한다(청크 전문 금지 — 학습 분포 유지).
- 추출 실패 청크는 추측으로 채우지 않고 목록으로 남긴다.

조인 키 (I2):
  qhash = sha256(normalize(질문문장))[:16]
  순번(P3)이 아니라 질문 텍스트에 조인 → FAQ 항목 증감에 무관, 질문 수정 시 미매핑으로 드러남.

사용:
  python faq_bf_map.py --dry-run                     # 추출·qhash·검증만 (라우터 불필요)
  python faq_bf_map.py --router <ckpt_dir>           # 전체 실행 → data/bf_map.jsonl
  python faq_bf_map.py --router <ckpt_dir> --msp 0.7 # MSP 임계 지정 (θ 확정은 후속 단계)
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import sys
import unicodedata
from datetime import datetime, timezone

CHUNKS_PATH = "data/chunks.jsonl"
OUT_PATH = "data/bf_map.jsonl"
REPORT_PATH = "data/bf_map_report.md"

# 6대 업무 — 라우터 id2label이 이 집합과 일치해야 한다(V1). 불일치 시 중단(문서 7절).
CANONICAL_BF = [
    "예금자보호제도",
    "예금보험금 안내",
    "고객 미수령금 신청",
    "착오송금 반환 신청",
    "채무조정 안내",
    "은닉재산 신고",
]

# 잠정값. θ 확정은 후속 단계(문서 3절 '후속')이며 이 단계에서 튜닝하지 않는다.
MSP_THRESHOLD_DEFAULT = 0.70

QUESTION_MARKER = "질문"
ANSWER_MARKER = "답변"


# ── 대상 청크 필터 (문서 5절 1) ──────────────────────────────
# chunk.py의 is_faq/is_board와 동일 판정. 단 chunks.jsonl에는 doc_id가 아니라
# parent_doc_id로 들어오므로 필드명만 맞춘다.
def is_faq(c: dict) -> bool:
    tag = (c.get("page_type") or "") + (c.get("page_title") or "")
    return "FAQ" in tag or "faq" in tag


def is_board(c: dict) -> bool:
    return is_faq(c) or "-cm-bbs-" in (c.get("parent_doc_id") or "")


# ── 질문 추출 (문서 5절 2 / Q1) ──────────────────────────────
# split_faq()는 '질문' 라인마다 청크를 끊으므로 청크 구조는
#   질문 / <질문문장> / 답변 / <답변...>
# 이다. 실패 시 None을 반환하며 추측 폴백을 두지 않는다(문서 5절 말미).
def extract_question(text: str) -> str | None:
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if QUESTION_MARKER not in lines:
        return None
    qi = lines.index(QUESTION_MARKER)
    try:
        ai = lines.index(ANSWER_MARKER, qi + 1)
    except ValueError:
        ai = len(lines)
    q = " ".join(lines[qi + 1:ai]).strip()
    return q or None


# ── 정규화 · qhash (문서 I2) ─────────────────────────────────
# 보수적으로만 정규화한다. 과도한 정규화는 서로 다른 질문을 같은 hash로 접어
# V4(충돌)를 유발하므로 문장부호·조사는 건드리지 않는다.
def normalize_q(q: str) -> str:
    q = unicodedata.normalize("NFKC", q)
    return " ".join(q.split())


def qhash(q_norm: str) -> str:
    return hashlib.sha256(q_norm.encode("utf-8")).hexdigest()[:16]


# ── 라우터 어댑터 ────────────────────────────────────────────
class Router:
    """로컬 시퀀스 분류 체크포인트 래퍼. id2label 검증 후에만 추론한다."""

    def __init__(self, ckpt: str, batch_size: int = 16):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch = torch
        self.name = ckpt
        self.batch_size = batch_size
        self.tok = AutoTokenizer.from_pretrained(ckpt)
        self.model = AutoModelForSequenceClassification.from_pretrained(ckpt)
        self.model.eval()

        # decoder 계열(Qwen 등) 시퀀스 분류는 마지막 non-pad 토큰의 은닉표현을 쓴다.
        # 좌측 패딩이면 그 위치 계산이 어긋나므로 우측 패딩을 강제한다.
        self.tok.padding_side = "right"
        if self.tok.pad_token_id is None:
            self.tok.pad_token = self.tok.eos_token
        if self.model.config.pad_token_id is None:
            self.model.config.pad_token_id = self.tok.pad_token_id

        self.device = ("mps" if torch.backends.mps.is_available()
                       else "cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        print(f"[router] {ckpt} · device={self.device}")

        # V1 — 라벨 매핑. 조용히 틀리는 유형이므로 불일치 시 중단(문서 7절).
        id2label = self.model.config.id2label
        labels = [id2label[i] for i in sorted(id2label)]
        unknown = [l for l in labels if l not in CANONICAL_BF]
        missing = [b for b in CANONICAL_BF if b not in labels]
        if unknown or missing:
            raise SystemExit(
                "[V1 실패] 라우터 id2label이 6대 업무와 일치하지 않습니다 — 중단합니다.\n"
                f"  체크포인트 라벨: {labels}\n"
                f"  정본 6업무    : {CANONICAL_BF}\n"
                f"  미인식 라벨   : {unknown}\n"
                f"  누락 업무     : {missing}\n"
                "  → 라벨 매핑 테이블을 확인한 뒤 재실행하세요(문서 6절 V1)."
            )
        self.labels = labels
        print(f"[V1] 라벨 매핑 확인 — {len(labels)}개 업무 문자열 일치")

    def predict(self, questions: list[str]) -> list[tuple[str, float]]:
        """질문 문장 리스트 → [(예측 BF, MSP)]. 질문만 입력한다(문서 7절)."""
        out: list[tuple[str, float]] = []
        for i in range(0, len(questions), self.batch_size):
            batch = questions[i:i + self.batch_size]
            enc = self.tok(batch, padding=True, truncation=True,
                           max_length=128, return_tensors="pt").to(self.device)
            with self.torch.no_grad():
                logits = self.model(**enc).logits
            probs = self.torch.softmax(logits.float().cpu(), dim=-1)
            msp, idx = probs.max(dim=-1)
            out += [(self.labels[j], float(p))
                    for j, p in zip(idx.tolist(), msp.tolist())]
        return out


# ── 기존 산출물 재사용 (문서 I5) ─────────────────────────────
def load_existing(path: str) -> dict[str, dict]:
    """qhash → 기존 레코드. 같은 모델·같은 질문이면 재추론하지 않는다."""
    p = pathlib.Path(path)
    if not p.exists():
        return {}
    return {r["qhash"]: r for r in
            (json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip())}


# ── 검증 리포트 (문서 6절) ───────────────────────────────────
def build_report(chunks, board, extracted, failed, collisions, records, msp_th, model_name):
    L = []
    a = L.append
    a("# bf_map 파이프라인 검증 리포트\n")
    a(f"- 생성: {datetime.now(timezone.utc).isoformat()}")
    a(f"- 라우터: `{model_name}`")
    a(f"- MSP 임계: {msp_th} (잠정 — θ 확정은 후속 단계)\n")
    a("## 검증 항목 (문서 6절)\n")
    a("| # | 확인 | 결과 |")
    a("|---|---|---|")
    a(f"| V1 | 라벨 매핑이 6개 BF 명칭과 일치 | {'확인' if model_name != '(dry-run)' else '미실행'} |")
    a(f"| V2 | 질문 문장 추출 | {len(extracted)}건 성공 |")
    a(f"| V3 | 추출 실패 청크 | {len(failed)}건 |")
    a(f"| V4 | qhash 충돌 (다른 질문 → 같은 hash) | {len(collisions)}건 |")
    a(f"| V5 | 대상 청크 수 (is_board) | {len(board)} / 전체 {len(chunks)} |")
    # 같은 질문이 여러 FAQ 페이지에 중복 게재되는 것은 충돌이 아니다(같은 BF로 수렴).
    # 레코드 수(청크 단위)와 고유 qhash 수가 갈리는 이유를 리포트에 남겨 혼동을 막는다.
    uniq = len({e["qhash"] for e in extracted})
    a(f"| — | 고유 질문 수 | {uniq} (레코드 {len(extracted)} · 중복 게재 {len(extracted) - uniq}) |")

    if records:
        by_doc = collections.defaultdict(set)
        for r in records:
            by_doc[r["chunk_id"].split("#")[0]].add(r["bf"])
        multi = {d: sorted(v - {None}) for d, v in by_doc.items() if len(v - {None}) > 1}
        nulls = sum(1 for r in records if r["bf"] is None)
        a(f"| V6 | 문서 내 BF가 갈리는 문서 | {len(multi)}건 (**정상 동작**) |")
        a(f"| V7 | null 비율 | {nulls}/{len(records)} = {nulls / len(records):.1%} |")
    else:
        a("| V6 | 문서 내 BF가 갈리는 문서 | 미실행 (라우터 없음) |")
        a("| V7 | null 비율 | 미실행 (라우터 없음) |")

    a("\n## V5 — 대상 청크 내역\n")
    per_doc = collections.Counter(c["parent_doc_id"] for c in board)
    a("| doc_id | 청크 | page_type |")
    a("|---|---:|---|")
    pt = {c["parent_doc_id"]: c["page_type"] for c in board}
    for d, n in per_doc.most_common():
        a(f"| `{d}` | {n} | {pt[d]} |")

    if collisions:
        a("\n## V4 — qhash 충돌\n")
        for h, ids in collisions.items():
            a(f"- `{h}` ← {ids}")

    if failed:
        a("\n## V3 — 질문 추출 실패 (bf_map 미기록, 추측으로 채우지 않음)\n")
        for cid in failed:
            a(f"- `{cid}`")

    if records:
        a("\n## V6 — 문서별 BF 분포 (라우터 산출)\n")
        a("| doc_id | 청크 | BF 분포 |")
        a("|---|---:|---|")
        dist = collections.defaultdict(collections.Counter)
        for r in records:
            dist[r["chunk_id"].split("#")[0]][r["bf"] or "null"] += 1
        for d, c in dist.items():
            body = " · ".join(f"{k} {v}" for k, v in c.most_common())
            a(f"| `{d}` | {sum(c.values())} | {body} |")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--router", help="라우터 체크포인트 경로(로컬 디렉터리 또는 HF id)")
    ap.add_argument("--dry-run", action="store_true",
                    help="추출·qhash·V2~V5 검증만 수행(라우터 불필요)")
    ap.add_argument("--msp", type=float, default=MSP_THRESHOLD_DEFAULT)
    ap.add_argument("--chunks", default=CHUNKS_PATH)
    ap.add_argument("--out", default=OUT_PATH)
    args = ap.parse_args()

    if not args.router and not args.dry_run:
        print("--router 또는 --dry-run 중 하나가 필요합니다.", file=sys.stderr)
        return 2

    chunks = [json.loads(l) for l in
              pathlib.Path(args.chunks).read_text(encoding="utf-8").splitlines() if l.strip()]

    # 1) is_board 필터
    board = [c for c in chunks if is_board(c)]

    # 2) 질문 추출 → qhash
    extracted: list[dict] = []
    failed: list[str] = []
    for c in board:
        q = extract_question(c["text"])
        if q is None:
            failed.append(c["chunk_id"])
            continue
        qn = normalize_q(q)
        extracted.append({"chunk_id": c["chunk_id"], "question": qn, "qhash": qhash(qn)})

    # V4 — 서로 다른 질문이 같은 hash로 접히는지
    by_hash = collections.defaultdict(set)
    for e in extracted:
        by_hash[e["qhash"]].add(e["question"])
    collisions = {h: sorted(qs) for h, qs in by_hash.items() if len(qs) > 1}

    print(f"[V5] is_board 청크 {len(board)} / 전체 {len(chunks)}")
    print(f"[V2] 질문 추출 성공 {len(extracted)} · [V3] 실패 {len(failed)}")
    print(f"[V4] qhash 충돌 {len(collisions)}")
    if collisions:
        print("     ! 서로 다른 질문이 같은 hash → 정규화 규칙을 고칠 것(문서 6절 V4)")

    records: list[dict] = []
    model_name = "(dry-run)"

    if args.router:
        router = Router(args.router)
        model_name = args.router
        prev = load_existing(args.out)
        now = datetime.now(timezone.utc).isoformat()

        # I5 — 같은 모델·같은 질문이면 재추론하지 않고 기존 값 재사용
        todo = [e for e in extracted
                if not (prev.get(e["qhash"], {}).get("model") == model_name)]
        reused = len(extracted) - len(todo)
        preds = dict(zip([e["qhash"] for e in todo],
                         router.predict([e["question"] for e in todo]))) if todo else {}
        print(f"[I5] 재추론 {len(todo)} · 기존 재사용 {reused}")

        for e in extracted:
            if e["qhash"] in preds:
                bf, msp = preds[e["qhash"]]
                # 4) MSP 미달은 null. 부모 태그로 롤백하지 않는다(문서 I4).
                records.append({
                    "qhash": e["qhash"], "chunk_id": e["chunk_id"], "question": e["question"],
                    "bf": bf if msp >= args.msp else None, "msp": round(msp, 4),
                    "model": model_name, "source": "router", "labeled_at": now,
                })
            else:
                old = dict(prev[e["qhash"]])
                old["chunk_id"] = e["chunk_id"]   # 순번이 밀려도 질문 기준으로 따라옴
                records.append(old)

        pathlib.Path(args.out).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
        nulls = sum(1 for r in records if r["bf"] is None)
        print(f"[out] {args.out} · {len(records)}건 · [V7] null {nulls} ({nulls / len(records):.1%})")
    else:
        # dry-run 산출: 추출 결과만 남겨 질문 추출 규칙을 눈으로 검증할 수 있게 한다.
        dry = args.out.replace(".jsonl", "_questions.jsonl")
        pathlib.Path(dry).write_text(
            "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in extracted), encoding="utf-8")
        print(f"[out] {dry} · {len(extracted)}건 (질문 추출만 — BF 미산출)")

    pathlib.Path(REPORT_PATH).write_text(
        build_report(chunks, board, extracted, failed, collisions, records, args.msp, model_name),
        encoding="utf-8")
    print(f"[out] {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

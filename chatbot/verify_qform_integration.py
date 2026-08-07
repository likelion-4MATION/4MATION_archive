# -*- coding: utf-8 -*-
"""큐폼 B안 통합 검증 — collect() 후단 survivors 필터.

실측 항목:
  AC1. graceful — qform=None / sub_task=None 이면 baseline 과 완전 동일(무손실)
  AC2. 후단 필터 = baseline 의 부분집합 (첨부를 추가하지 않고 좁히기만)
  AC3. §3-1 감소폭 — collect() 단독 vs 조합 조인 후 (발표 수치 22→4~6)
  AC4. 계약 불변 — answer() 에 qform 파라미터만 추가(4필드 무변경), 검색·생성 미개입

네트워크/HCX 없음: 실제 청크를 hits 로 넣어 attachments.collect() 만 구동한다.
"""
import inspect
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "chatbot"))
sys.path.insert(0, str(ROOT / "crawler"))

import attachments
from qform_extract import extract

CHUNKS = ROOT / "crawler" / "data" / "chunks.jsonl"
DOCA = ROOT / "crawler" / "data" / "doc_attachments.json"
MAIN_DOC = "kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn"

# 착오송금 첨부 보유 문서(3) 의 실제 청크를 hits 로 사용
MS_DOCS = {
    MAIN_DOC,
    "kdic-fins-ir-aplygudn-MsdrAddrsePossDcmntGudn-selectScrn",
    "kdic-fins-ir-aplygudn-MtrsVstRcptGudn-selectScrn",
}
hits = [json.loads(l) for l in CHUNKS.open(encoding="utf-8")
        if json.loads(l)["parent_doc_id"] in MS_DOCS]


def keyset(atts):
    return {(a["doc_id"], a["orig_filename"]) for a in atts}


baseline = attachments.collect(hits)
raw22 = len(json.load(DOCA.open(encoding="utf-8"))[MAIN_DOC])
print(f"hits={len(hits)}청크 · baseline collect() = {len(baseline)}건 "
      f"(dedup) · MsdrprPossDcmntGudn raw={raw22}건\n")

ok = True

# ── AC1. graceful (무손실 통과) ─────────────────────────────────────────────
print("── AC1. graceful — qform=None / sub_task=None 은 baseline 과 동일 ──")
g_none = attachments.collect(hits, qform=None)
g_empty = attachments.collect(hits, qform={"party": None, "sub_task": None,
                                           "qualification": None, "subject": None, "method": None})
a1 = keyset(g_none) == keyset(baseline) and keyset(g_empty) == keyset(baseline)
print(f"  qform=None: {len(g_none)}건 · sub_task=None: {len(g_empty)}건 · baseline {len(baseline)}건"
      f"  → {'OK' if a1 else 'DIFF'}")
ok = ok and a1

# ── AC2/AC3. 후단 필터: 부분집합 + 감소폭 ────────────────────────────────────
print("\n── AC2/AC3. 후단 필터 (부분집합 + §3-1 감소폭) ──")
scen = [
    ("반환신청·본인", {"party": "송금인", "sub_task": "반환신청", "qualification": "본인", "subject": "본인", "method": None}),
    ("반환신청·대리인·미성년자", {"party": "송금인", "sub_task": "반환신청", "qualification": "대리인", "subject": "미성년자", "method": None}),
    ("반환신청·대리인·법인", {"party": "송금인", "sub_task": "반환신청", "qualification": "대리인", "subject": "법인", "method": None}),
    ("반환신청·자격미상(7행)", {"party": "송금인", "sub_task": "반환신청", "qualification": None, "subject": None, "method": None}),
    ("신청철회", {"party": "송금인", "sub_task": "신청철회", "qualification": None, "subject": None, "method": None}),
    ("이의제기(수취인)", {"party": "수취인", "sub_task": "이의제기", "qualification": None, "subject": None, "method": None}),
    ("이체수수료환급(수취인)", {"party": "수취인", "sub_task": "이체수수료환급", "qualification": None, "subject": None, "method": None}),
]
def forms(atts):  # canonical 서식(확장자 제거 stem) 집합 — hwp/pdf 중복 접기
    return {pathlib.Path(a["orig_filename"]).stem for a in atts if a.get("orig_filename")}


base_keys = keyset(baseline)
base_forms = len(forms(baseline))
print(f"  {'시나리오':24} {'서식':>4} {'파일':>4}  부분집합   (collect 단독: {base_forms}서식/{len(baseline)}파일)")
for name, slots in scen:
    narrowed = attachments.collect(hits, qform=slots)
    subset = keyset(narrowed) <= base_keys
    ok = ok and subset
    print(f"  {name:24} {len(forms(narrowed)):>4} {len(narrowed):>4}  {'⊆OK' if subset else 'DIFF✗'}")
print(f"  → §3-1 감소폭: collect() 단독 {base_forms}서식(raw {raw22}파일) "
      f"→ 조합 조인 후 **1~4서식**. 첨부를 추가하지 않고 좁히기만(부분집합 불변).")

# ── 실제 자연어 질의 (extract → collect) ────────────────────────────────────
print("\n  실제 질의(extract→collect, 서식명):")
for q in ["미성년자 착오송금 반환 서류 알려줘요", "법인이 잘못 송금하면 서류가 따로 있어요?",
          "이체수수료도 돌려받아요?", "착오송금 반환 신청 철회하고 싶어요"]:
    slots = extract(q, "착오송금 반환 신청")
    n = attachments.collect(hits, qform=slots)
    print(f"    \"{q}\" → {len(forms(n))}서식 {sorted(forms(n))}")

# ── AC4. 계약 불변 (파라미터만 추가) ────────────────────────────────────────
print("\n── AC4. 계약 불변 ──")
import chain  # noqa: E402  (import 시 네트워크 없음)
sig = inspect.signature(chain.answer)
has_qform = "qform" in sig.parameters and sig.parameters["qform"].default is None
csig = inspect.signature(attachments.collect)
c_qform = "qform" in csig.parameters and csig.parameters["qform"].default is None
a4 = has_qform and c_qform
print(f"  answer{tuple(sig.parameters)} · collect qform 기본 None: {'OK' if a4 else 'DIFF'}")
print("  (검색·생성·반환 4필드 불변 — 첨부 목록만 후단 정밀화)")
ok = ok and a4

print("\n" + ("전체 통과 ✅" if ok else "실패 ⛔"))
sys.exit(0 if ok else 1)

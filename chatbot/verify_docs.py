# -*- coding: utf-8 -*-
"""문서 정합 검증 — T7 AC 실측.

문서가 코드와 어긋나는 것은 조용히 일어난다. 셋을 기계로 잡는다:
  AC1  `ARCH_통합_v0.md` §1 다이어그램의 층 = `qform_trace.LAYER_ORDER` (패널 카드와 1:1)
  AC2  §3 실배선표에 적힌 파일·함수·상수가 **실제 코드에 있는가**
  AC4  기존 문서(`QFORM_ARCH_설계스펙.md`·`DECISIONS.md`) **본문 무수정 — 추기만**

AC3(갭 누락 없음)·AC5(팀원이 §1만 읽고 흐름을 말할 수 있는가)는 사람이 판정한다.

실행: python3 chatbot/verify_docs.py
"""
from __future__ import annotations

import ast
import hashlib
import pathlib
import re
import sys

_BASE = pathlib.Path(__file__).resolve().parent.parent
for _p in (_BASE / "chatbot", _BASE / "crawler"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from qform_trace import LAYER_LABEL, LAYER_ORDER  # noqa: E402

ARCH = _BASE / "docs" / "records" / "ARCH_통합_v0.md"
fails: list[tuple[str, str, str]] = []

# 문서 최상단 상태 배지는 **메타데이터라 본문이 아니다.** 비교 전에 벗긴다 —
# 안 벗기면 배지를 붙이는 순간 모든 append-only 검사가 깨진다(2026-08-25 문서 재편).
BADGE_RE = re.compile(r"^<!-- 상태:[^>]*-->\n(?:>.*\n)*\n---\n\n", re.M)


def _body(text: str) -> str:
    """상태 배지를 제거한 본문."""
    return BADGE_RE.sub("", text, count=1)


# 추기 **직전**의 원본 지문. 본문을 한 글자라도 고치면 prefix 비교가 깨진다.
# 지문은 `_body()`(배지 제거) 기준이다.
APPEND_ONLY = {
    "docs/current/QFORM_ARCH_설계스펙.md": (
        14514, "e1c16a01c49b40ecf539ea2edcf979b0ad45854c4c694e55c251bb8f2124e870"),
    # 2026-08-25 재기준 — 헤딩 표기를 `Dn (MM-DD)` 로 통일하며 D0~D6 7개 제목을 고쳤다
    # (`D0 (금)` → `D0 (07-11)` 등). 본문 내용은 무변경이고 제목 표기만 바뀐 것이라
    # 재기준을 남긴다. 직전 지문: 26916B / 9c4d4fdf1e05…
    "DECISIONS.md": (
        26919, "7b87bf914364943957386174c46684de589b3aa3232ee4063c6cdfa5986f1c93"),
}

text = ARCH.read_text(encoding="utf-8")
print(f"ARCH_통합_v0.md {len(text)}자 · 층 {len(LAYER_ORDER)}종\n")

# ── AC1. §1 다이어그램 층 == LAYER_ORDER ────────────────────────────────────
print("── AC1. §1 다이어그램 = 패널 층 구성 (1:1) ──")
sec1 = text.split("## §1.")[1].split("## §2.")[0]
doc_layers = re.findall(r"\[(\d)\]\s+(\S+(?:\s\S+)?)\s{2,}", sec1)
seen, ordered = set(), []
for num, label in doc_layers:
    if num not in seen:
        seen.add(num)
        ordered.append((int(num), label.strip()))
ordered.sort()
want = [LAYER_LABEL[k] for k in LAYER_ORDER]
got = [lab for _, lab in ordered]
ac1 = got == want
print(f"  문서 §1: {' → '.join(got)}")
print(f"  코드    : {' → '.join(want)}")
print(f"  {len(got)}층 · 순서·이름 {'일치' if ac1 else '불일치'}  → {'OK' if ac1 else 'DIFF ⛔'}")
if not ac1:
    fails.append(("AC1", "LAYER_ORDER 와 1:1", f"{got}"))

# ── AC2. §3 실배선표의 이름이 실제 코드에 있는가 ────────────────────────────
print("\n── AC2. §3 실배선표 ↔ 실제 코드 ──")
sec3 = text.split("## §3.")[1].split("## §4.")[0]

# 파일 경로: `chatbot/foo.py` 형태
paths = sorted(set(re.findall(r"`([\w/]+\.(?:py|csv|json|jsonl))`", sec3)))
missing_paths = [p for p in paths if not (_BASE / p).exists()]

# 심볼: `func()` · `CONST=값` · `CONST` (대문자)
syms = set()
for m in re.findall(r"`([A-Za-z_][\w.]*)\(", sec3):
    syms.add(m.split(".")[-1])
for m in re.findall(r"`([A-Z][A-Z0-9_]{2,})(?:=[^`]*)?`", sec3):
    syms.add(m)

defined: set[str] = set()
for p in paths:
    if not p.endswith(".py"):
        continue
    tree = ast.parse((_BASE / p).read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(n.name)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    defined.add(t.id)
        # 타입 주석이 붙은 대입(`SPEC: dict = {...}`)도 대입이다. 08-11 이전에는
        # 이걸 놓쳐서, 주석만 붙이면 문서에 적힌 실재 상수가 "코드에 없다"고 나왔다.
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            defined.add(n.target.id)
        elif isinstance(n, ast.arg):
            defined.add(n.arg)
missing_syms = sorted(s for s in syms if s not in defined)

ac2 = not missing_paths and not missing_syms
print(f"  파일 {len(paths)}개 · 미실재 {len(missing_paths)}건")
for p in missing_paths:
    print(f"    ✗ 없는 파일 {p}")
print(f"  심볼 {len(syms)}개 · 미실재 {len(missing_syms)}건  → {'OK' if ac2 else 'DIFF ⛔'}")
for s in missing_syms:
    print(f"    ✗ 코드에 없는 이름 {s}")
if not ac2:
    fails.append(("AC2", "이름 전건 실재", f"파일 {len(missing_paths)} · 심볼 {len(missing_syms)}"))

# 상수는 값까지 대조한다 — 문서의 `QBF_MIN_SCORE=3` 이 코드와 다르면 거짓말이 된다
print("\n  [상수 값 대조]")
import qform_ask  # noqa: E402
import qform_flow  # noqa: E402
import qform_panel  # noqa: E402
import qform_trace  # noqa: E402

LIVE = {"QBF_MIN_SCORE": qform_trace.QBF_MIN_SCORE, "QBF_MARGIN": qform_trace.QBF_MARGIN,
        "MAX_ASK_TURNS": qform_flow.MAX_ASK_TURNS, "MAX_EXAMPLES": qform_ask.MAX_EXAMPLES,
        "MAX_LEN": qform_ask.MAX_LEN, "PANEL_HEIGHT": qform_panel.PANEL_HEIGHT}
bad_val = []
for name, val in LIVE.items():
    m = re.search(rf"`{name}=(\S+?)`", sec3)
    doc_v = m.group(1) if m else None
    ok = doc_v is not None and doc_v == str(val)
    if not ok:
        bad_val.append((name, doc_v, val))
    print(f"    {name:16} 문서 {str(doc_v):>6} · 코드 {str(val):>6}  {'OK' if ok else 'DIFF ✗'}")
if bad_val:
    fails.append(("AC2b", "상수 값 일치", str(bad_val)))

# ── AC4. 기존 문서 본문 무수정 (추기만) ─────────────────────────────────────
print("\n── AC4. 기존 문서 본문 무수정 — 추기만 ──")
ac4 = True
for rel, (orig_len, orig_sha) in APPEND_ONLY.items():
    b = _body((_BASE / rel).read_text(encoding="utf-8")).encode("utf-8")
    head = b[:orig_len]
    same = hashlib.sha256(head).hexdigest() == orig_sha
    grew = len(b) > orig_len
    ac4 &= same and grew
    print(f"  {rel:28} 원본 {orig_len}B 보존 {'✅' if same else '✗ 수정됨'} · "
          f"추기 +{len(b) - orig_len}B")
if not ac4:
    fails.append(("AC4", "본문 무수정", "prefix 불일치"))
print(f"  → {'OK' if ac4 else 'DIFF ⛔'}  (추기 직전 sha256 대비 prefix 비교)")

# ── AC3·AC5 는 사람 판정 ────────────────────────────────────────────────────
gaps = re.findall(r"\|\s*(G\d+)\s*\|", text)
print(f"\n── AC3·AC5 (사람 판정) ──")
print(f"  §4 갭 표 {len(set(gaps))}건: {', '.join(sorted(set(gaps), key=lambda g: int(g[1:])))}")
print("  AC3 — '문서엔 있고 코드엔 없는 것'이 빠짐없는지는 사람이 확인")
print("  AC5 — 팀원 한 명에게 §1만 읽히고 흐름을 말하게 해볼 것")

print()
if fails:
    print("어긋난 AC ⛔")
    print(f"  {'AC':6} {'기대':22} 실측")
    for ac, want_, got_ in fails:
        print(f"  {ac:6} {want_:22} {got_}")
    sys.exit(1)
print("전체 통과 ✅  (AC1·AC2·AC4 기계 검증 · AC3·AC5 사람 판정)")
sys.exit(0)

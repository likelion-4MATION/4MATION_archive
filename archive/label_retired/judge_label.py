"""LLM judge 라벨링 (HyperCLOVA X / CLOVA Studio) — router_trainset 질문에 gt_chunk_id + 정답 스팬 부여.

전송 규격은 프로젝트 chain.py._hcx 와 동일하게 맞춤:
  · .env 로드: python-dotenv (키/URL/모델 모두 .env에서)
  · API_KEY = CLOVA_API_KEY, API_URL = CLOVA_API_URL, MODEL = CLOVA_MODEL
      (엔드포인트는 하드코딩하지 않는다 — .env의 CLOVA_API_URL을 그대로 쓴다)
  · requests.post(API_URL, json={"messages":..., **params}, headers={Authorization Bearer, ...})
  · 응답 파싱: result.message.content
  · params: temperature/topP/maxTokens (chain.py CLS_PARAMS 계열, 결정성 우선)

라벨링 설계(대화 정리 md):
  · 앵커는 검색기(임베딩)와 독립된 LLM '판단'으로 '추출(extractive)'.
  · 실제 청크에서 정답 스팬 선택 + chunk_id 기록(생성 금지).
  · "답 없음(answerable=false)" 출구 허용 → fallback을 GT에서 재생산하지 않음.

후보 범위(HCX엔 prompt caching 없음 → 비용 고려):
  --candidates all  : 코퍼스 전수(편향0, 콜당 ~43k토큰)  [기본]
  --candidates bm25 : 질문별 BM25 top-k(비용↓, 약한 어휘편향; under-test는 dense라 독립적)

출력(JSONL): {id, business_function, question, answerable, gt_chunk_id, gt_anchor_span,
              answer_bf, cross_domain, span_verbatim_ok, confidence, reason}
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import sys
import time
import uuid
from collections import Counter

import requests

try:
    from dotenv import load_dotenv, find_dotenv
    _HAS_DOTENV = True
except ImportError:
    _HAS_DOTENV = False


# ── .env 로딩 (chain.py와 동일하게 python-dotenv 사용, label/ 배치까지 robust) ──
def _parse_env_fallback(path: pathlib.Path) -> None:
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        os.environ.setdefault(k, v)


def load_env(explicit: str | None = None) -> str | None:
    """현재/상위/스크립트 위치에서 .env를 찾아 로드. judge_label.py가 label/ 안에 있고
    .env가 바로 바깥(상위)에 있는 배치를 우선 커버한다. 로드한 경로 반환."""
    here = pathlib.Path(__file__).resolve().parent
    cwd = pathlib.Path.cwd()
    cands = ([pathlib.Path(explicit)] if explicit else []) + [
        here / ".env", here.parent / ".env", here.parent.parent / ".env",
        cwd / ".env", cwd.parent / ".env",
    ]
    seen: set[pathlib.Path] = set()
    for p in cands:
        try:
            p = p.resolve()
        except OSError:
            continue
        if p in seen:
            continue
        seen.add(p)
        if p.is_file():
            (load_dotenv(p) if _HAS_DOTENV else _parse_env_fallback(p))
            return str(p)
    if _HAS_DOTENV:                       # 최후: dotenv 자체 상향 탐색
        found = find_dotenv(usecwd=True)
        if found:
            load_dotenv(found)
            return found
    return None


# 판정 파라미터는 call_hcx 내부에서 구성(maxTokens는 CLI로 조절). chain.py CLS 계열, 저온도.

JUDGE_SYS = """너는 KDIC 검색 평가용 정답 라벨러다. 주어진 '코퍼스'(실제 크롤링된 청크 목록) 안에서만 판단한다.

규칙:
1) 오직 코퍼스 청크의 실제 내용으로만 판단한다. 사전지식으로 답을 지어내지 마라(추출 only).
2) 답을 담은 청크(들)의 chunk_id를 gt_chunk_ids 배열로, 대표 청크의 정답 스팬을 gt_anchor_span에 원문 그대로 넣는다.
3) '골드 업무'는 힌트일 뿐. 정답 청크는 다른 업무 태그일 수 있다(크로스도메인 허용).

[부정형 질문 ↔ 긍정형 답 (반드시 적용)]
 "없나요/안 되나요/못 하나요/불가능한가요/방법이 없나요" 처럼 부정으로 묻는 질문은,
 코퍼스의 '긍정형 사실'이 그대로 답이 된다. 부정형이라고 "없다는 정보가 없으니 none"으로 좁게 보지 마라.
 - "온라인으로 안 되나요?" ← "온라인으로 신청 가능합니다" = direct (되니까 부정에 대한 답).
 - "대리인은 못 하나요?" ← "대리인은 위임장으로 가능합니다" = direct.
 - "기한 지나면 방법이 없나요?" ← "1년 이내 신청 가능"(가능 범위) + "기한 후엔 압류·소송 등으로 회수"(대안)
   를 조합 → inferable + and. (가능 조건이 곧 '언제 안 되는지'의 답이고, 대안이 '방법 있음'의 답이다.)
 즉 "가능/방법 있음"을 서술한 청크는 그 반대(불가/방법 없음)를 묻는 부정형 질문의 정답 근거다.

[근거 강도 evidence_type — A/B/C 중 하나]
 - "direct"(A): 질문에 답하는 문장이 청크에 그대로 있음. → gt_anchor_span에 그 문장 그대로.
 - "inferable"(B): 문장 그대로는 없지만, 코퍼스의 명시적 사실들을 조합하면 답을 안전하게 도출 가능.
     예: "신청 후 계좌 변경 가능?" ← "등록계좌로 지급"+"변경은 방문으로" 조합. 이때 gt_anchor_span은 null 가능.
     ★ direct가 아니라고 false로 버리지 마라. 조합으로 답되면 answerable=true + evidence_type="inferable".
 - "none"(C): 조합해도 코퍼스로 답 결정 불가 → answerable=false, evidence_type="none".

[복수정답 관계 chunk_relation — AND/OR/single]
 - "single": 정답 청크 1개.
 - "and"(멀티청크): 답이 여러 청크에 나뉘어 다 모아야 완성(절차 단계·조합 근거 등). gt_chunk_ids에 전부.
 - "or"(복수정답): 같은 답이 여러 청크에 각각 독립 존재(안내+FAQ 중복 등). 아무거나 하나면 답. gt_chunk_ids에 모두.

[false는 두 경우만]
 (a) 소관밖(외국예금·타기관: 세금=국세청, 개인회생/파산=법원, 피해구제=금감원 등, 금융무관)
 (b) 소관내지만 코퍼스에 direct도 inferable도 전혀 없는 순수 정보(통계·처리기간·내부명단 등)
 위가 아니면 direct/inferable로 반드시 포함. "용어가 그대로 없다"만으로 false 금지.

출력은 아래 JSON 하나만. 백틱·설명 금지.
{"answerable": true/false, "evidence_type": "direct"|"inferable"|"none",
 "chunk_relation": "single"|"and"|"or", "gt_chunk_ids": ["chunk_id", ...] 또는 [],
 "gt_anchor_span": "스팬 또는 null", "confidence": 0.0~1.0, "reason": "한 문장"}"""

# ── 선택적 BM25 후보 축소 (kiwi) ───────────────────────────────────────────
_kiwi = None
_KEEP = {"NNG", "NNP", "NNB", "NR", "NP", "VV", "VA", "SL", "SN", "SH", "MAG", "XR"}


def _tok(s: str) -> list[str]:
    global _kiwi
    if _kiwi is None:
        from kiwipiepy import Kiwi
        _kiwi = Kiwi()
    return [t.form.lower() for t in _kiwi.tokenize(s) if t.tag in _KEEP and len(t.form) >= 1]


class _BM25:
    def __init__(self, docs_tokens: list[list[str]]):
        self.docs = docs_tokens
        self.N = len(docs_tokens)
        self.avgdl = sum(len(d) for d in docs_tokens) / max(1, self.N)
        self.df = Counter()
        for d in docs_tokens:
            for w in set(d):
                self.df[w] += 1

    def top_k(self, q_tokens: list[str], k: int, k1=1.5, b=0.75) -> list[int]:
        out = []
        for i, d in enumerate(self.docs):
            tf = Counter(d)
            s = 0.0
            for w in q_tokens:
                if w not in tf:
                    continue
                idf = math.log(1 + (self.N - self.df[w] + 0.5) / (self.df[w] + 0.5))
                s += idf * tf[w] * (k1 + 1) / (tf[w] + k1 * (1 - b + b * len(d) / self.avgdl))
            out.append((s, i))
        out.sort(reverse=True)
        return [i for _, i in out[:k]]


def build_corpus_block(chunks: list[dict]) -> str:
    lines = ["# 코퍼스 (총 %d청크) — 각 항목: [chunk_id | 업무 | page_title] 본문" % len(chunks)]
    for c in chunks:
        body = " ".join(c["text"].split())
        lines.append(f'\n[{c["chunk_id"]} | {c["business_function"]} | {c.get("page_title","")}]\n{body}')
    return "\n".join(lines)


def build_messages(corpus_block: str, question: str, gold_bf: str) -> list[dict]:
    user_msg = (
        f"{corpus_block}\n\n"
        f"---\n골드 업무(힌트): {gold_bf}\n질문: {question}\n\n"
        "위 코퍼스에서 이 질문의 정답을 담은 청크를 규칙대로 판정해 JSON으로만 답하라."
    )
    return [{"role": "system", "content": JUDGE_SYS},
            {"role": "user", "content": user_msg}]


def call_hcx(messages: list[dict], api_url: str, api_key: str,
             max_tokens: int, retries: int = 4) -> str:
    """chain.py._hcx 구조: requests.post → result.message.content.
    400(컨텍스트초과 등 클라이언트 오류)은 재시도해도 소용없으므로 즉시 실패.
    429/5xx/네트워크만 백오프 재시도(429는 Retry-After 존중)."""
    params = {"temperature": 0.1, "topP": 0.8, "maxTokens": max_tokens}
    for attempt in range(retries):
        try:
            r = requests.post(
                api_url, json={"messages": messages, **params}, timeout=60,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "X-NCP-CLOVASTUDIO-REQUEST-ID": uuid.uuid4().hex,
                },
            )
            if r.status_code == 200:
                return r.json()["result"]["message"]["content"]
            body = r.text[:200].replace(chr(10), " ")
            if r.status_code == 400:                 # 결정적 오류 → 재시도 무의미
                raise ValueError(f"http_400 (재시도무의미): {body}")
            if r.status_code == 429:                 # 레이트리밋 → Retry-After 존중 후 대기
                wait = int(r.headers.get("Retry-After", 0)) or min(60, 5 * (2 ** attempt))
                print(f"    ! http_429 rate-limit → {wait}s 대기", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"    ! http_{r.status_code}: {body}", file=sys.stderr)
        except ValueError:
            raise
        except Exception as e:                       # noqa: BLE001
            print(f"    ! exception:{type(e).__name__}", file=sys.stderr)
        time.sleep(min(30, 2 * (2 ** attempt)))
    raise RuntimeError("HCX 재시도 모두 실패")


def _salvage_json(t: str) -> dict:
    """깨진 JSON에서 필드를 정규식으로 직접 건진다(span의 미이스케이프 따옴표·개행·역슬래시 대응)."""
    import re
    out: dict = {}
    m = re.search(r'"answerable"\s*:\s*(true|false)', t)
    if m:
        out["answerable"] = (m.group(1) == "true")
    m = re.search(r'"evidence_type"\s*:\s*"([^"]*)"', t)
    if m:
        out["evidence_type"] = m.group(1)
    m = re.search(r'"chunk_relation"\s*:\s*(?:"([^"]*)"|null)', t)
    if m:
        out["chunk_relation"] = m.group(1)
    # gt_chunk_ids: [ ... ] 안의 "..." 토큰만 추출
    m = re.search(r'"gt_chunk_ids"\s*:\s*\[(.*?)\]', t, re.S)
    if m:
        out["gt_chunk_ids"] = re.findall(r'"([^"]+)"', m.group(1))
    m = re.search(r'"gt_chunk_id"\s*:\s*"([^"]*)"', t)
    if m and not out.get("gt_chunk_ids"):
        out["gt_chunk_ids"] = [m.group(1)]
    m = re.search(r'"confidence"\s*:\s*([0-9.]+)', t)
    if m:
        try:
            out["confidence"] = float(m.group(1))
        except ValueError:
            pass
    # span은 깨짐의 주범 → 살리지 않고 null(검증에서 어차피 걸러짐)
    out.setdefault("gt_anchor_span", None)
    out.setdefault("reason", "salvaged")
    return out


def parse_judge(text: str) -> dict:
    t = (text or "").strip()
    for fence in ("```json", "```"):
        if t.startswith(fence):
            t = t[len(fence):]
    t = t.strip().removesuffix("```").strip()
    if not t.startswith("{"):
        i, j = t.find("{"), t.rfind("}")
        if i != -1 and j != -1:
            t = t[i:j + 1]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        salvaged = _salvage_json(t)      # 깨진 JSON → 필드 직접 추출
        if "answerable" in salvaged:
            return salvaged
        raise


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trainset", default="router_trainset_v2.jsonl")
    ap.add_argument("--chunks", default="chunks.jsonl")
    ap.add_argument("--out", default="gt_labeled.jsonl")
    ap.add_argument("--candidates", choices=["all", "bm25"], default="bm25")
    ap.add_argument("--cand-k", type=int, default=12, help="bm25 후보 청크 수(HCX-003은 ~10 권장)")
    ap.add_argument("--max-tokens", type=int, default=512, help="출력 토큰(JSON 짧음, 작아도 됨)")
    ap.add_argument("--ctx-limit", type=int, default=0,
                    help="모델 총 컨텍스트 토큰(초과 예상 시 사전 경고·자동 축소). 0=HCX-003(4096) 가정")
    ap.add_argument("--limit", type=int, default=0, help="처음 N건만(스모크)")
    ap.add_argument("--stratified", type=int, default=0,
                    help="업무별 N건씩 샘플(6개 도메인 골고루 — 크로스도메인·gap 검증용)")
    ap.add_argument("--sleep", type=float, default=0.5, help="콜 간 대기초(429 방지, 기본 0.5)")
    ap.add_argument("--resume", action="store_true",
                    help="--out에 이미 있는 id는 건너뛰고 이어서(중단 복구). 파일에 append")
    ap.add_argument("--only-ids", default=None,
                    help="이 파일(id 한 줄씩)에 있는 id만 라벨링(false 재점검용). --out에 append 권장")
    ap.add_argument("--env", default=None, help=".env 경로 명시(미지정 시 현재/상위 자동 탐색)")
    args = ap.parse_args()

    env_path = load_env(args.env)
    print(f".env 로드: {env_path or '(못 찾음 — 셸 환경변수만 사용)'} · dotenv={_HAS_DOTENV}")

    api_key = os.environ.get("CLOVA_API_KEY")
    api_url = os.environ.get("CLOVA_API_URL")
    model = os.environ.get("CLOVA_MODEL", "(미설정)")
    missing = [n for n, v in [("CLOVA_API_KEY", api_key), ("CLOVA_API_URL", api_url)] if not v]
    if missing:
        sys.exit(
            f"필수 환경변수 없음: {', '.join(missing)}\n"
            f"탐색한 .env: {env_path or '없음'}\n"
            "→ .env에 CLOVA_API_KEY / CLOVA_API_URL (선택 CLOVA_MODEL)가 있어야 함. "
            "다른 경로면 --env 로 지정."
        )

    # URL/모델 정합성 경고: HCX-005/007은 v3 경로에서만 동작(v1이면 40084)
    url_l = (api_url or "").lower()
    mdl = (model if model != "(미설정)" else "") or url_l
    if ("hcx-005" in mdl.lower() or "hcx-007" in mdl.lower() or "dash-002" in mdl.lower()) \
            and "/v1/" in url_l:
        print("⚠️ CLOVA_API_URL이 /v1/ 인데 모델은 HCX-005/007 계열 → 40084(Unsupported) 발생. "
              "URL을 /v3/ 로 바꾸세요: .../v3/chat-completions/HCX-005", file=sys.stderr)

    # 모델명으로 컨텍스트 자동 판단(--ctx-limit 0이면). HCX-003=4k, HCX-005/007/DASH-002=128k
    if not args.ctx_limit:
        m = mdl.lower()
        if any(t in m for t in ("hcx-005", "hcx-007", "dash-002")):
            args.ctx_limit = 128000
        else:                                        # HCX-003/DASH-001 등
            args.ctx_limit = 4096
        print(f"[ctx 자동판단] model≈{model} → ctx-limit {args.ctx_limit} "
              f"(다르면 --ctx-limit로 덮어쓰기)")

    for label, path in [("chunks", args.chunks), ("trainset", args.trainset)]:
        if not pathlib.Path(path).is_file():
            sys.exit(f"입력 파일 없음({label}): {path}\n"
                     f"현재 위치: {pathlib.Path.cwd()}\n"
                     f"→ 파일명이 다르면 --{label} 로 지정하세요.")
    chunks = [json.loads(l) for l in open(args.chunks, encoding="utf-8")]
    chunk_by_id = {c["chunk_id"]: c for c in chunks}
    recs = [json.loads(l) for l in open(args.trainset, encoding="utf-8")]
    if args.only_ids:
        keep = {l.strip() for l in open(args.only_ids, encoding="utf-8") if l.strip()}
        recs = [r for r in recs if r["id"] in keep]
        print(f"[only-ids] {len(keep)}개 id 지정 → 매칭 {len(recs)}건만 라벨링")
    if args.stratified:
        from collections import defaultdict as _dd
        by = _dd(list)
        for r in recs:
            by[r["business_function"]].append(r)
        recs = [x for bf in by for x in by[bf][: args.stratified]]
        print(f"[층화 샘플] 업무 {len(by)}개 × {args.stratified}건 = {len(recs)}건")
    elif args.limit:
        recs = recs[: args.limit]

    # 출력 폴더 자동 생성 (data/... 같은 경로도 알아서 만듦)
    out_dir = pathlib.Path(args.out).parent
    if str(out_dir) not in ("", "."):
        out_dir.mkdir(parents=True, exist_ok=True)

    # resume: --out에 이미 '성공'으로 기록된 id만 건너뜀(error 레코드는 재시도 대상)
    done_ids: set[str] = set()
    if args.resume and pathlib.Path(args.out).is_file():
        for l in open(args.out, encoding="utf-8"):
            try:
                rec = json.loads(l)
            except Exception:                        # noqa: BLE001
                continue
            if str(rec.get("reason", "")).startswith("error"):
                continue                             # 실패건은 완료로 치지 않음 → 재시도
            done_ids.add(rec["id"])
        before = len(recs)
        recs = [r for r in recs if r["id"] not in done_ids]
        print(f"[resume] 성공 {len(done_ids)}건 건너뜀 → 남은 {len(recs)}/{before}건 (실패건 포함 재시도)")
    open_mode = "a" if (args.resume and pathlib.Path(args.out).is_file()) else "w"

    full_block = build_corpus_block(chunks) if args.candidates == "all" else None
    bm25 = _BM25([_tok(c["text"]) for c in chunks]) if args.candidates == "bm25" else None

    # 토큰 추정(한국어 HCX 보수적으로 1토큰≈1.5자) — 실제 블록 문자수 기반
    CHARS_PER_TOK = 1.5
    ctx_limit = int((args.ctx_limit or 4096) * 0.9)   # 10% 안전마진 (0이면 HCX-003)
    sys_tok = int(len(JUDGE_SYS) / CHARS_PER_TOK)

    def est_tokens(block: str) -> int:
        return sys_tok + int(len(block) / CHARS_PER_TOK) + 60   # +질문/지시 여유

    # bm25면 cand-k를 컨텍스트에 맞게 자동 축소(첫 질문 기준 대표 추정)
    if bm25 is not None:
        budget_chars = int((ctx_limit - args.max_tokens - sys_tok - 60) * CHARS_PER_TOK)
        sample_idx = bm25.top_k(_tok(recs[0]["question"]), args.cand_k)
        # 청크 하나 평균 크기로 들어갈 수 있는 개수 추정
        avg_chars = sum(len(chunks[j]["text"]) for j in sample_idx) / max(1, len(sample_idx)) + 40
        fit_k = max(3, int(budget_chars / avg_chars))
        if fit_k < args.cand_k:
            print(f"⚠️ 컨텍스트({ctx_limit}tok) 초과 예상 → cand-k {args.cand_k} → {fit_k}로 자동 축소 "
                  f"(model={model}). 더 큰 컨텍스트 원하면 .env를 HCX-005로.")
            args.cand_k = fit_k
    else:
        e = est_tokens(full_block)
        if e + args.max_tokens > ctx_limit:
            sys.exit(f"⚠️ 전수(all) 입력 ≈{e}tok + 출력 {args.max_tokens} > 컨텍스트 {ctx_limit}. "
                     f"model={model}. → .env를 HCX-005(128k)로 바꾸거나 --candidates bm25 사용.")

    approx = est_tokens(build_corpus_block(
        [chunks[j] for j in bm25.top_k(_tok(recs[0]["question"]), args.cand_k)]) if bm25 else full_block)
    print(f"[HCX 라벨링] model={model} · 후보={args.candidates}"
          f"{'(k=%d)' % args.cand_k if bm25 else ''} · 대상 {len(recs)}건 · "
          f"콜당 입력 ≈ {approx:,} 토큰 (ctx≤{ctx_limit}, 출력 {args.max_tokens})")

    n_ans = n_gap = n_cross = 0
    with open(args.out, open_mode, encoding="utf-8") as fout:
        for i, r in enumerate(recs, 1):
            gold_bf = r["business_function"]
            if bm25 is not None:
                cand = [chunks[j] for j in bm25.top_k(_tok(r["question"]), args.cand_k)]
                block = build_corpus_block(cand)
            else:
                block = full_block
            try:
                text = call_hcx(build_messages(block, r["question"], gold_bf),
                                api_url, api_key, args.max_tokens)
                j = parse_judge(text)
            except Exception as e:                   # noqa: BLE001
                msg = str(e)[:300]
                print(f"[{i}/{len(recs)}] {r['id']} 실패: {type(e).__name__}: {msg}", file=sys.stderr)
                j = {"answerable": False, "gt_chunk_id": None, "gt_anchor_span": None,
                     "confidence": 0.0, "reason": f"error:{msg}"}

            # gt_chunk_ids(배열) 우선, 없으면 단일 gt_chunk_id 호환
            cids = j.get("gt_chunk_ids")
            if not cids:
                one = j.get("gt_chunk_id")
                cids = [one] if one else []
            cids = [c for c in cids if c in chunk_by_id]   # 실존 검증
            valid_id = len(cids) > 0
            primary = cids[0] if valid_id else None
            answer_bf = chunk_by_id[primary]["business_function"] if valid_id else None
            span = j.get("gt_anchor_span")
            span_ok = bool(valid_id and span and
                           "".join(str(span).split()) in "".join(chunk_by_id[primary]["text"].split()))
            cross = bool(valid_id and answer_bf != gold_bf)

            out = {
                "id": r["id"], "business_function": gold_bf, "question": r["question"],
                "answerable": bool(j.get("answerable")) if valid_id else False,
                "evidence_type": j.get("evidence_type") if valid_id else "none",
                "chunk_relation": j.get("chunk_relation") if valid_id else None,
                "gt_chunk_ids": cids,
                "gt_chunk_id": primary,                    # 대표(하위호환)
                "multi_chunk": len(cids) > 1,
                "gt_anchor_span": span if span_ok else None,
                "answer_bf": answer_bf, "cross_domain": cross,
                "span_verbatim_ok": span_ok,
                "confidence": j.get("confidence", 0.0), "reason": j.get("reason", ""),
            }
            fout.write(json.dumps(out, ensure_ascii=False) + "\n")
            fout.flush()

            if out["answerable"]:
                n_ans += 1
                n_cross += cross
            else:
                n_gap += 1
            print(f"[{i}/{len(recs)}] {r['id']} ans={out['answerable']} "
                  f"cids={cids} multi={out['multi_chunk']} cross={cross} conf={out['confidence']}")
            if args.sleep:
                time.sleep(args.sleep)

    print(f"\n완료 {len(recs)}건 → {args.out}")
    print(f"  답가능(gt_chunk_id 有): {n_ans} · 그중 크로스도메인 {n_cross}")
    print(f"  답없음(거절 eval行): {n_gap}")


if __name__ == "__main__":
    main()

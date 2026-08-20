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
1) 오직 코퍼스 청크의 실제 내용으로만 판단한다. 너의 사전지식으로 답을 지어내지 마라(추출 only, 생성 금지).
2) 질문에 답하는 내용을 담은 청크가 코퍼스에 있으면: 가장 정확히 답하는 청크 하나를 골라 그 chunk_id와,
   그 청크 text에서 정답을 담은 최소 스팬을 '원문 그대로(verbatim)' 뽑는다.
3) '골드 업무'는 참고 힌트일 뿐이다. 정답 청크는 다른 업무 태그일 수 있다(크로스도메인 허용).
   내용이 맞으면 업무 태그가 달라도 그 청크를 골라라.
4) 질문에 답하는 청크가 코퍼스에 없으면(통계·국회·감사·재기지원 매뉴얼·조직도 등 크롤링 안 된 주제):
   answerable=false, gt_chunk_id=null, gt_anchor_span=null 로 정직하게 답한다. 억지로 고르지 마라.
5) 부분적으로만 관련되고 실제 답은 없으면 answerable=false 로 간다. 애매하면 confidence를 낮게(<0.5) 준다.

출력은 아래 JSON 하나만. 백틱·코드블록·설명·머리말 금지.
{"answerable": true/false, "gt_chunk_id": "chunk_id 또는 null", "gt_anchor_span": "스팬 또는 null",
 "confidence": 0.0~1.0, "reason": "한 문장"}"""

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
    return json.loads(t)


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

    for label, path in [("chunks", args.chunks), ("trainset", args.trainset)]:
        if not pathlib.Path(path).is_file():
            sys.exit(f"입력 파일 없음({label}): {path}\n"
                     f"현재 위치: {pathlib.Path.cwd()}\n"
                     f"→ 파일명이 다르면 --{label} 로 지정하세요.")
    chunks = [json.loads(l) for l in open(args.chunks, encoding="utf-8")]
    chunk_by_id = {c["chunk_id"]: c for c in chunks}
    recs = [json.loads(l) for l in open(args.trainset, encoding="utf-8")]
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

            cid = j.get("gt_chunk_id")
            valid_id = bool(cid) and cid in chunk_by_id
            answer_bf = chunk_by_id[cid]["business_function"] if valid_id else None
            span = j.get("gt_anchor_span")
            span_ok = bool(valid_id and span and
                           "".join(str(span).split()) in "".join(chunk_by_id[cid]["text"].split()))
            cross = bool(valid_id and answer_bf != gold_bf)

            out = {
                "id": r["id"], "business_function": gold_bf, "question": r["question"],
                "answerable": bool(j.get("answerable")) if valid_id else False,
                "gt_chunk_id": cid if valid_id else None,
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
            print(f"[{i}/{len(recs)}] {r['id']} ans={out['answerable']} cid={cid} "
                  f"cross={cross} conf={out['confidence']}")
            if args.sleep:
                time.sleep(args.sleep)

    print(f"\n완료 {len(recs)}건 → {args.out}")
    print(f"  답가능(gt_chunk_id 有): {n_ans} · 그중 크로스도메인 {n_cross}")
    print(f"  답없음(거절 eval行): {n_gap}")


if __name__ == "__main__":
    main()

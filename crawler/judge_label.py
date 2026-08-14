"""LLM judge 라벨링 — router_trainset 질문에 gt_chunk_id + 정답 스팬을 부여한다.

목적: 라우터 학습셋을 '앵커(청크) 단위' 검색 eval GT로 재활용하기 위한 GT 생성.
설계 합의(대화 6턴):
  - 앵커는 임베딩이 아니라 LLM '판단'으로 만든다(검색기와 독립 → 순환성 차단).
  - LLM은 '생성'이 아니라 '추출'한다: 실제 청크에서 정답 스팬을 고르고 chunk_id를 남긴다.
  - 후보는 도메인 스코프가 아니라 코퍼스 전수(215개)를 준다.
      · 이유: 미수령금 질문의 정답이 예금보험금 태그 청크(그 미수령금통합신청 FAQ)에
        앉아 있는 등 크로스도메인이 실재. 도메인으로 자르면 GT가 답을 놓친다.
      · 전수라 후보 선택에 dense/bm25 어떤 검색기 편향도 안 들어간다.
  - "답 없음(answerable=false)" 출구를 반드시 허용 → least-bad 청크 강제선택으로
    fallback 문제를 GT에서 재생산하지 않는다. 답없음(재기지원·통계·국회 등 ~84건)은
    검색 eval에서 빠지고 거절/에스컬레이션 eval로 격리된다.

비용: CLOVA Studio(HCX)는 Anthropic 같은 prompt caching이 없다 → 코퍼스 블록을 매콜 그대로
      재전송한다(콜당 토큰비용 ↑, 캐시 전제였던 이전 비용 추정은 더 이상 유효하지 않음).
      급하면 --limit으로 스모크 테스트 후 본실행 규모를 가늠할 것.

출력(JSONL, 1레코드/질문):
  {id, business_function(gold), question,
   answerable(bool), gt_chunk_id(str|null), gt_anchor_span(str|null),
   answer_bf(str|null),        # 정답 청크의 업무(크로스도메인 탐지용)
   cross_domain(bool),         # answer_bf != gold business_function
   confidence(0~1), reason}
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

try:
    from dotenv import load_dotenv
    load_dotenv()  # 프로젝트 루트의 .env를 읽는다(.env.example은 템플릿일 뿐, 실키 넣지 말 것)
except ImportError:
    pass  # python-dotenv 미설치면 그냥 os.environ(터미널에서 직접 export한 값)만 씀

# ── 설정 (.env.example과 이름 통일: CLOVA_API_KEY / CLOVA_API_URL / CLOVA_MODEL) ──────────

# .env.example의 값이 빈 문자열("")로만 잡혀 있어도(키는 있지만 미기입) 기본값으로
# 폴백하도록 or 사용 — os.environ.get(key, default)는 키가 "존재"하면 빈 문자열도 그대로 반환해버림.
API_URL = os.environ.get("CLOVA_API_URL") or "https://clovastudio.stream.ntruss.com/v1/openai/chat/completions"
MODEL = os.environ.get("CLOVA_MODEL") or "HCX-005"   # 판정용: 비용/품질 균형
MAX_TOKENS = 700
API_KEY_ENV = "CLOVA_API_KEY"

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

출력은 아래 JSON 하나만. 다른 텍스트·마크다운·설명 금지.
{"answerable": bool, "gt_chunk_id": str|null, "gt_anchor_span": str|null,
 "confidence": 0.0~1.0, "reason": "한 문장"}"""


def build_corpus_block(chunks: list[dict]) -> str:
    """전수 코퍼스를 판정 프롬프트용 텍스트로. chunk_id로 참조. (캐시 대상)"""
    lines = ["# 코퍼스 (총 %d청크) — 각 항목: [chunk_id | 업무 | page_title] 본문" % len(chunks)]
    for c in chunks:
        body = " ".join(c["text"].split())          # 공백 정규화(토큰 절약)
        lines.append(
            f'\n[{c["chunk_id"]} | {c["business_function"]} | {c.get("page_title","")}]\n{body}'
        )
    return "\n".join(lines)


def make_payload(corpus_block: str, question: str, gold_bf: str) -> dict:
    user_msg = (
        f"골드 업무(힌트): {gold_bf}\n"
        f"질문: {question}\n\n"
        "위 코퍼스에서 이 질문의 정답을 담은 청크를 규칙대로 판정해 JSON으로만 답하라."
    )
    return {
        "model": MODEL,
        # CLOVA Studio OpenAI-호환 엔드포인트: system 블록/캐시 개념이 없어 하나의
        # system 메시지로 합친다(JUDGE_SYS + 코퍼스). 매 콜 전체 재전송됨(위 비용 메모 참고).
        "messages": [
            {"role": "system", "content": JUDGE_SYS + "\n\n" + corpus_block},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0,     # 재현 가능한 GT가 목적 — 결정적으로 고정
        "max_tokens": MAX_TOKENS,
        "seed": 42,
    }


def call_api(payload: dict, api_key: str, retries: int = 4) -> dict:
    data = json.dumps(payload).encode("utf-8")
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                API_URL, data=data, method="POST",
                headers={
                    "content-type": "application/json",
                    "authorization": f"Bearer {api_key}",
                },
            )
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())
        except Exception as e:                       # noqa: BLE001
            wait = 2 ** attempt
            print(f"    ! API 오류({e}) {wait}s 후 재시도", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError("API 재시도 모두 실패")


def parse_judge(resp: dict) -> dict:
    # OpenAI 호환 응답 형식: choices[0].message.content
    txt = resp["choices"][0]["message"]["content"]
    txt = txt.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(txt)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trainset", default="data/router_trainset_v2_anchor_831-1665.jsonl")
    ap.add_argument("--chunks", default="data/chunks.jsonl")
    ap.add_argument("--out", default="data/gt_labeled.jsonl")
    ap.add_argument("--limit", type=int, default=0, help="처음 N건만(스모크 테스트용)")
    ap.add_argument("--sleep", type=float, default=0.0, help="콜 간 대기(레이트리밋)")
    args = ap.parse_args()

    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        sys.exit(f"환경변수 {API_KEY_ENV} 없음. 프로젝트 루트 .env 파일에 {API_KEY_ENV}=실키 를 채우거나, "
                  f"터미널에서 직접 지정 후 실행.")

    chunks = [json.loads(l) for l in open(args.chunks, encoding="utf-8")]
    chunk_by_id = {c["chunk_id"]: c for c in chunks}
    recs = [json.loads(l) for l in open(args.trainset, encoding="utf-8")]
    if args.limit:
        recs = recs[: args.limit]
    corpus_block = build_corpus_block(chunks)

    n_ok = n_ans = n_gap = n_cross = 0
    with open(args.out, "w", encoding="utf-8") as fout:
        for i, r in enumerate(recs, 1):
            gold_bf = r["business_function"]
            payload = make_payload(corpus_block, r["question"], gold_bf)
            resp = call_api(payload, api_key)
            try:
                j = parse_judge(resp)
            except Exception as e:                   # noqa: BLE001
                print(f"[{i}/{len(recs)}] {r['id']} 파싱실패: {e}", file=sys.stderr)
                j = {"answerable": None, "gt_chunk_id": None, "gt_anchor_span": None,
                     "confidence": 0.0, "reason": "parse_error"}

            cid = j.get("gt_chunk_id")
            # 검증: judge가 실제 존재하는 chunk_id를 골랐는가 + 스팬이 그 청크에 verbatim 있는가
            valid_id = cid in chunk_by_id if cid else False
            answer_bf = chunk_by_id[cid]["business_function"] if valid_id else None
            span = j.get("gt_anchor_span")
            span_ok = bool(valid_id and span and
                           "".join(span.split()) in "".join(chunk_by_id[cid]["text"].split()))
            cross = bool(valid_id and answer_bf != gold_bf)

            out = {
                "id": r["id"], "business_function": gold_bf, "question": r["question"],
                "answerable": bool(j.get("answerable")) if valid_id else False,
                "gt_chunk_id": cid if valid_id else None,
                "gt_anchor_span": span if span_ok else None,
                "answer_bf": answer_bf,
                "cross_domain": cross,
                "span_verbatim_ok": span_ok,
                "confidence": j.get("confidence", 0.0),
                "reason": j.get("reason", ""),
            }
            fout.write(json.dumps(out, ensure_ascii=False) + "\n")
            fout.flush()

            n_ok += 1
            if out["answerable"]:
                n_ans += 1
                n_cross += cross
            else:
                n_gap += 1
            usage = resp.get("usage", {})
            print(f"[{i}/{len(recs)}] {r['id']} ans={out['answerable']} "
                  f"cid={cid} cross={cross} conf={out['confidence']} "
                  f"tokens={usage.get('total_tokens','?')}")
            if args.sleep:
                time.sleep(args.sleep)

    print(f"\n완료 {n_ok}건 → {args.out}")
    print(f"  답가능(gt_chunk_id 有): {n_ans}  · 그중 크로스도메인: {n_cross}")
    print(f"  답없음(거절 eval行): {n_gap}")


if __name__ == "__main__":
    main()

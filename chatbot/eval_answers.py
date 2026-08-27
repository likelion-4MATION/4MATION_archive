"""같은 검색 컨텍스트로 HCX와 DeepSeek 답변을 생성하는 비교 실험 러너.

검색은 문항당 한 번만 수행하고 저장된 같은 context를 두 provider에 전달한다.
OpenCode는 이 스크립트가 만든 답변을 직접 생성하지 않고, 후속 블라인드 심사만 맡는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import random
import subprocess
import sys
import time


ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "chatbot"))
sys.path.insert(0, str(ROOT / "crawler"))

import chain  # noqa: E402


TESTSET = ROOT / "crawler" / "gt_testset_retrieval_450.jsonl"
ANCHORS = ROOT / "final_testset" / "gt_natural430_anchored.jsonl"
CHUNKS = ROOT / "crawler" / "data" / "chunks.jsonl"
DEFAULT_OUT = ROOT / "chatbot" / "data" / "llm_compare"
PROVIDERS = ("hcx", "deepseek")
GEN_PARAMS = {"temperature": 0.2, "top_p": 0.8, "max_tokens": 512}


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _sample(rows: list[dict], n: int, seed: int) -> list[dict]:
    """업무 균형을 먼저 맞추고 P1(150)이면 희소 층 최소 수를 채운다."""
    if not 1 <= n <= len(rows):
        raise ValueError(f"n은 1~{len(rows)} 범위여야 합니다: {n}")
    rng = random.Random(seed)
    by_bf: dict[str, list[dict]] = {}
    for row in rows:
        by_bf.setdefault(str(row.get("business_function") or ""), []).append(row)
    for group in by_bf.values():
        rng.shuffle(group)

    chosen: dict[str, dict] = {}
    per_bf = min(20 if n >= 150 else n // max(1, len(by_bf)), n)
    for bf in sorted(by_bf):
        for row in by_bf[bf][:per_bf]:
            chosen[row["id"]] = row

    if n >= 150:
        constraints = [
            (lambda r: r.get("chunk_relation") == "and", 25),
            (lambda r: r.get("cross_domain") is True, 10),
            (lambda r: r.get("evidence_type") == "inferable", 10),
            (lambda r: r.get("answerable") is False, 2),
        ]
        pool = list(rows)
        rng.shuffle(pool)
        for predicate, target in constraints:
            have = sum(1 for row in chosen.values() if predicate(row))
            for row in pool:
                if have >= target or len(chosen) >= n:
                    break
                if predicate(row) and row["id"] not in chosen:
                    chosen[row["id"]] = row
                    have += 1

    remainder = [row for row in rows if row["id"] not in chosen]
    rng.shuffle(remainder)
    for row in remainder:
        if len(chosen) >= n:
            break
        chosen[row["id"]] = row
    return sorted(chosen.values(), key=lambda row: row["id"])


def build_context(hits: list[dict]) -> str:
    return "\n\n".join(
        f"[출처{i}] {hit['page_title']}\n{hit['text']}" for i, hit in enumerate(hits, 1)
    )


def _manifest(rows: list[dict], args, providers: list[str]) -> dict:
    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    return {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "head": head,
        "seed": args.seed,
        "n": len(rows),
        "repeat": args.repeat,
        "k": args.k,
        "search_mode": "hybrid",
        "providers": providers,
        "models": {"hcx": chain.HCX_MODEL, "deepseek": chain.DEEPSEEK_MODEL},
        "generation_params": GEN_PARAMS,
        "sha256": {
            "testset_450": _sha(TESTSET),
            "anchored_430": _sha(ANCHORS),
            "chunks": _sha(CHUNKS),
        },
        "item_ids": [row["id"] for row in rows],
    }


def run(args) -> tuple[pathlib.Path, pathlib.Path]:
    providers = list(PROVIDERS if args.provider == "both" else (args.provider,))
    rows = _sample(_jsonl(TESTSET), args.n, args.seed)
    out_dir = pathlib.Path(args.out_dir).resolve()
    contexts_path = out_dir / "contexts.jsonl"
    answers_path = out_dir / "answers.jsonl"
    manifest_path = out_dir / "run_manifest.json"
    if not args.overwrite and any(path.exists() for path in (contexts_path, answers_path, manifest_path)):
        raise SystemExit(f"기존 산출물이 있습니다: {out_dir} (--overwrite로 새 실험 시작)")
    out_dir.mkdir(parents=True, exist_ok=True)

    searcher = chain.get_searcher()
    contexts = []
    for index, row in enumerate(rows, 1):
        hits = searcher.search(row["question"], k=args.k, mode="hybrid")
        context = build_context(hits)
        contexts.append({
            "item_id": row["id"], "question": row["question"],
            "business_function": row.get("business_function"),
            "answerable": row.get("answerable"), "evidence_type": row.get("evidence_type"),
            "chunk_relation": row.get("chunk_relation"), "cross_domain": row.get("cross_domain"),
            "span_verbatim_ok": row.get("span_verbatim_ok"),
            "gt_anchor_span": row.get("gt_anchor_span"), "gt_anchors": row.get("gt_anchors"),
            "context_chunk_ids": [hit.get("chunk_id") for hit in hits],
            "context_sha": hashlib.sha256(context.encode("utf-8")).hexdigest(),
            "context": context,
        })
        print(f"[context {index:>3}/{len(rows)}] {row['id']}")

    with contexts_path.open("w", encoding="utf-8") as fh:
        for row in contexts:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    manifest_path.write_text(
        json.dumps(_manifest(rows, args, providers), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.dry_run:
        answers_path.write_text("", encoding="utf-8")
        return contexts_path, answers_path

    for provider in providers:
        key, url, _model = chain._provider_settings(provider)
        if not key or not url:
            raise SystemExit(f"{provider} API 설정이 비어 있습니다. .env를 확인하세요.")
    chain.CALL_BUDGET = max(chain.CALL_BUDGET, len(contexts) * len(providers) * args.repeat * 2 + 10)
    chain._calls = 0
    with answers_path.open("w", encoding="utf-8") as fh:
        total = len(contexts) * len(providers) * args.repeat
        done = 0
        for row in contexts:
            messages = [
                {"role": "system", "content": chain.SYS_PROMPT_V2},
                {"role": "user", "content":
                 f"[참고문서]\n{row['context']}\n\n[질문]\n{row['question']}"},
            ]
            for provider in providers:
                params = dict(GEN_PARAMS)
                if provider == "deepseek":
                    params["thinking"] = {"type": "disabled"}
                for repeat_idx in range(args.repeat):
                    text, meta = chain._llm(
                        messages, req_id=f"eval-{row['item_id']}-{provider}-r{repeat_idx}",
                        params=params, provider=provider,
                    )
                    answer = {
                        "item_id": row["item_id"], "repeat_idx": repeat_idx,
                        "provider": provider, "model": meta.get("model"),
                        "question": row["question"],
                        "context_chunk_ids": row["context_chunk_ids"],
                        "context_sha": row["context_sha"], "answer": text,
                        "latency_ms": meta.get("latency_ms"),
                        "api_status": meta.get("model_status"), "error": meta.get("error"),
                    }
                    fh.write(json.dumps(answer, ensure_ascii=False) + "\n")
                    fh.flush()
                    done += 1
                    print(f"[answer {done:>4}/{total}] {row['item_id']} {provider} r{repeat_idx} "
                          f"status={answer['api_status']} error={answer['error']}")
                    if args.delay:
                        time.sleep(args.delay)
    return contexts_path, answers_path


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=40)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--provider", choices=("both", *PROVIDERS), default="both")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT))
    parser.add_argument("--delay", type=float, default=0.2)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    cpath, apath = run(parse_args())
    print(f"완료: {cpath}\n      {apath}")

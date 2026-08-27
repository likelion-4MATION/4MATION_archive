"""HCX/DeepSeek 생성 결과를 모델명을 숨긴 OpenCode 심사 배치로 조립한다."""
from __future__ import annotations

import argparse
import json
import pathlib
import random


ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "chatbot" / "data" / "llm_compare"
RUBRIC = ROOT / "chatbot" / "judge_rubric.md"


def _jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _item_block(context: dict, answer_a: str, answer_b: str, number: int) -> str:
    anchor = ""
    if context.get("span_verbatim_ok") and context.get("gt_anchor_span"):
        anchor = f"\n<정답구절> {context['gt_anchor_span']}"
    return (
        f"\n\n=== 문항 {number} ===\n"
        f"<id> {context['item_id']}\n"
        f"<질문> {context['question']}\n"
        f"<답변가능> {str(bool(context.get('answerable'))).lower()}"
        f"{anchor}\n"
        f"<근거문서>\n{context['context']}\n"
        f"<답변 A>\n{answer_a}\n"
        f"<답변 B>\n{answer_b}\n"
    )


def build(args) -> list[pathlib.Path]:
    if args.batch_size != 1:
        raise SystemExit("심사 객체 생략을 막기 위해 --batch-size는 1만 허용합니다")
    data_dir = pathlib.Path(args.data_dir).resolve()
    contexts = {row["item_id"]: row for row in _jsonl(data_dir / "contexts.jsonl")}
    answers = [row for row in _jsonl(data_dir / "answers.jsonl")
               if row.get("repeat_idx") == args.repeat_idx]
    grouped: dict[str, dict[str, dict]] = {}
    for row in answers:
        grouped.setdefault(row["item_id"], {})[row["provider"]] = row

    pairs = []
    for item_id in sorted(contexts):
        models = grouped.get(item_id) or {}
        if set(models) != {"hcx", "deepseek"}:
            raise SystemExit(f"{item_id}: repeat {args.repeat_idx}의 두 모델 답변이 모두 필요합니다")
        if models["hcx"].get("error") or models["deepseek"].get("error"):
            raise SystemExit(f"{item_id}: 생성 오류가 있어 심사 배치를 만들 수 없습니다")
        expected_sha = contexts[item_id]["context_sha"]
        if any(row.get("context_sha") != expected_sha for row in models.values()):
            raise SystemExit(f"{item_id}: HCX/DeepSeek context_sha 불일치")
        pairs.append((contexts[item_id], models))

    out_dir = pathlib.Path(args.out_dir or (data_dir / "judge")).resolve()
    existing = list(out_dir.glob("batch_*.md")) + list(out_dir.glob("key.json"))
    if existing and not args.overwrite:
        raise SystemExit(f"기존 심사 배치가 있습니다: {out_dir} (--overwrite로 재생성)")
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.overwrite:
        for path in existing:
            path.unlink()

    rng = random.Random(args.seed)
    rubric = RUBRIC.read_text(encoding="utf-8").strip()
    key = {"seed": args.seed, "repeat_idx": args.repeat_idx, "items": {}}
    blocks = []
    for number, (context, models) in enumerate(pairs, 1):
        order = ["hcx", "deepseek"]
        rng.shuffle(order)
        key["items"][context["item_id"]] = {"A": order[0], "B": order[1]}
        blocks.append(_item_block(
            context, models[order[0]]["answer"], models[order[1]]["answer"], number
        ))

    paths = []
    for start in range(0, len(blocks), args.batch_size):
        batch_no = start // args.batch_size + 1
        path = out_dir / f"batch_{batch_no:02d}.md"
        path.write_text(rubric + "\n" + "".join(blocks[start:start + args.batch_size]),
                        encoding="utf-8")
        paths.append(path)
    (out_dir / "key.json").write_text(
        json.dumps(key, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return paths


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA))
    parser.add_argument("--out-dir")
    parser.add_argument("--batch-size", type=int, choices=(1,), default=1)
    parser.add_argument("--repeat-idx", type=int, default=0)
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    created = build(parse_args())
    print("생성된 OpenCode 심사 배치:")
    for path in created:
        print(f"  {path}")

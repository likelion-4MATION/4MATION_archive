"""fetch_attachments.py가 받은 실파일을 parser.py 산출물(attachments)에 연결.

data/files/manifest.json(실다운로드 결과)과 data/parsed/*.json(페이지 단위 첨부
메타)을 (doc_id, enc_real, enc_temp) — 다운로드 토큰 그 자체 — 로 조인해서, 각
첨부 항목에 로컬 파일 정보(local_path·orig_filename·file_size·sha256)를 붙여
data/parsed/*.json에 되써넣는다. 토큰은 파일의 실제 신원이라(같은 문서명이
페이지 내 여러 곳에 노출돼도 토큰이 다르면 다른 파일) name/anchor_text 같은
표시 텍스트 기반 매칭과 달리 오매칭 여지가 없다.

chunk.py는 attachments를 그대로 복사해 청크에 실으므로, 이 스크립트 이후
chunk.py를 다시 돌리면 청크 단위 attachments에도 local_path가 자동으로
따라간다 — chunk.py 자체는 수정할 필요 없음.

실행 순서: parser.py → fetch_attachments.py → link_files.py → chunk.py
"""
from __future__ import annotations

import json
import pathlib
import sys

PARSED_DIR = pathlib.Path("data/parsed")
MANIFEST_PATH = pathlib.Path("data/files/manifest.json")


def main() -> None:
    if not MANIFEST_PATH.exists():
        # [doc-agg] build_dataset --no-fetch 등 첨부 다운로드를 건너뛴 경우 —
        # 파이프라인을 깨지 않고 첨부 링크만 스킵(첨부 없이 진행).
        print(f"[link_files] manifest 없음({MANIFEST_PATH}) — 첨부 링크 스킵(첨부 없이 진행)")
        return

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    by_token: dict[tuple, dict] = {}
    dup_tokens = []
    for m in manifest:
        if m["status"] != "ok":
            continue
        key = (m["doc_id"], m["enc_real"], m["enc_temp"])
        if key in by_token:
            dup_tokens.append(key)
        by_token[key] = m

    linked = 0
    unmatched_atts = []  # parsed 첨부인데 manifest에 매칭 실패(다운로드 실패/누락)
    used_keys: set[tuple] = set()

    for p in sorted(PARSED_DIR.glob("*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        atts = rec.get("attachments", [])
        if not atts:
            continue
        changed = False
        for att in atts:
            if att.get("link_type") != "onclick_dynamic":
                continue  # direct는 이미 실파일 절대 URL을 url에 갖고 있음
            key = (rec["doc_id"], att.get("enc_real"), att.get("enc_temp"))
            m = by_token.get(key)
            if m is None:
                unmatched_atts.append((rec["doc_id"], att.get("name"), att.get("anchor_text")))
                continue
            used_keys.add(key)
            att["local_path"] = m["stored_path"]
            att["orig_filename"] = m["orig_filename"]
            att["file_size"] = m["size_bytes"]
            att["sha256"] = m["sha256"]
            linked += 1
            changed = True
        if changed:
            p.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")

    unused_manifest = [(m["doc_id"], m["orig_filename"]) for m in manifest
                        if m["status"] == "ok"
                        and (m["doc_id"], m["enc_real"], m["enc_temp"]) not in used_keys]

    print(f"연결됨: {linked}건")
    if unmatched_atts:
        print(f"매칭 실패(첨부 → 로컬파일 못 찾음, 다운로드 실패/누락 가능성) {len(unmatched_atts)}건:")
        for doc_id, name, anchor in unmatched_atts:
            print(f"   - {doc_id}: name={name!r} anchor_text={anchor!r}")
    if unused_manifest:
        print(f"미사용(다운로드는 됐는데 매칭되는 첨부 항목 없음) {len(unused_manifest)}건:")
        for doc_id, fname in unused_manifest:
            print(f"   - {doc_id}: {fname}")
    if dup_tokens:
        print(f"경고: manifest 내 토큰 중복 {len(dup_tokens)}건 (같은 파일 재다운로드?) {dup_tokens[:5]}")


if __name__ == "__main__":
    main()

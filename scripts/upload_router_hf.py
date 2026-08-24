"""라우터 체크포인트를 HF 프라이빗 repo에 올린다 — 체크포인트를 가진 사람이 1회 실행.

git에 넣을 수 없는 `pytorch_model.bin`(2.38GB)을 팀에 공유하는 경로다. 설정파일 8개는
레포에도 커밋돼 있지만, `from_pretrained(repo_id)`가 repo만 보고 동작해야 하므로
**9개 전부** 올린다.

멱등이다 — 이미 올라간 파일은 크기를 비교해 건너뛴다. 중간에 끊겨도 다시 돌리면 된다
(huggingface_hub가 청크 업로드를 재개한다).

사전 준비:
    pip install "huggingface-hub>=0.23"
    export HF_TOKEN=hf_...        # write 권한 토큰. https://huggingface.co/settings/tokens
    # 또는: huggingface-cli login

사용:
    python scripts/upload_router_hf.py                 # 매니페스트 기준 업로드
    python scripts/upload_router_hf.py --dry-run       # 올릴 목록만 출력
    python scripts/upload_router_hf.py --repo other/id # repo 덮어쓰기

주의: 이 스크립트는 **로컬 파일을 읽기만** 한다. 삭제·수정하지 않는다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "crawler" / "data" / "router_manifest.json"


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=None, help="HF repo id (기본: 매니페스트의 hf_repo)")
    ap.add_argument("--src", default=None, help="체크포인트 디렉토리 (기본: 매니페스트의 local_dir)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify-sha", action="store_true",
                    help="업로드 전 sha256 전수 검증(2.38GB 읽음, 느림)")
    a = ap.parse_args()

    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    repo = a.repo or m["hf_repo"]
    src = pathlib.Path(a.src) if a.src else ROOT / m["local_dir"]

    if not src.is_dir():
        sys.exit(f"[중단] 체크포인트 디렉토리가 없습니다: {src}")

    # ── 로컬 무결성 먼저. 깨진 걸 올리면 팀 전체가 깨진 걸 받는다 ──────────────
    missing, bad = [], []
    for name, meta in m["files"].items():
        f = src / name
        if not f.exists():
            missing.append(name)
        elif f.stat().st_size != meta["size"]:
            bad.append(f"{name}: 크기 {f.stat().st_size} != {meta['size']}")
        elif a.verify_sha and sha256(f) != meta["sha256"]:
            bad.append(f"{name}: sha256 불일치")
    if missing or bad:
        for x in missing:
            print(f"  없음     : {x}")
        for x in bad:
            print(f"  불일치   : {x}")
        sys.exit("[중단] 로컬 체크포인트가 매니페스트와 다릅니다. 올리지 않습니다.")
    print(f"[검증] 로컬 {len(m['files'])}개 파일 확인"
          f"{' (sha256 전수)' if a.verify_sha else ' (크기)'} — 이상 없음")

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if not token and not a.dry_run:
        print("[안내] HF_TOKEN 환경변수가 없습니다. huggingface-cli login 세션을 씁니다.")

    try:
        from huggingface_hub import HfApi
    except ImportError:
        if not a.dry_run:
            sys.exit('[중단] pip install "huggingface-hub>=0.23" 후 다시 실행하세요.')
        print('[안내] huggingface-hub 미설치 — 원격 대조 없이 계획만 출력합니다.')
        HfApi = None

    api = HfApi(token=token) if HfApi else None

    # 원격에 이미 있는 것 — 크기가 같으면 건너뛴다
    remote: dict[str, int] = {}
    try:
        if api is None:
            raise RuntimeError("huggingface-hub 미설치")
        for info in api.list_repo_files(repo_id=repo, repo_type="model"):
            remote[info] = -1
        for f in api.list_repo_tree(repo_id=repo, repo_type="model", recursive=True):
            size = getattr(f, "size", None)
            if size is not None:
                remote[f.path] = size
    except Exception as e:                      # repo 미생성 · 권한 없음 · 오프라인
        print(f"[안내] 원격 목록을 못 읽었습니다({type(e).__name__}) — 전량 업로드로 진행합니다.")

    todo = [n for n, meta in m["files"].items() if remote.get(n, None) != meta["size"]]
    skip = [n for n in m["files"] if n not in todo]
    for n in skip:
        print(f"  건너뜀   : {n} (원격 크기 일치)")
    total = sum(m["files"][n]["size"] for n in todo)
    print(f"\n올릴 파일 {len(todo)}개 · {total / 1048576:.1f} MB → {repo} (private)")
    for n in todo:
        print(f"  올림     : {n}  ({m['files'][n]['size'] / 1048576:.1f} MB)")

    if a.dry_run:
        print("\n--dry-run — 아무것도 올리지 않았습니다.")
        return 0
    if not todo:
        print("\n원격이 이미 최신입니다.")
        return 0

    api.create_repo(repo_id=repo, repo_type="model", private=True, exist_ok=True)
    for n in todo:
        print(f"\n업로드 중: {n} …")
        api.upload_file(path_or_fileobj=str(src / n), path_in_repo=n,
                        repo_id=repo, repo_type="model")
    print(f"\n완료 — https://huggingface.co/{repo}/tree/main")
    print("팀원은 HF_TOKEN(read)만 있으면 crawler/router_source.py가 알아서 받아옵니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

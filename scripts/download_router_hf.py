"""라우터 체크포인트를 HF 프라이빗 repo에서 **로컬 디렉토리로** 내려받는다.

`scripts/upload_router_hf.py` 의 반대 방향이다. 클론 직후 1회 실행하면 그 뒤로는
네트워크를 타지 않는다 — `crawler/router_source.resolve()` 가 로컬 디렉토리를
먼저 보고, 매니페스트의 파일이 전부 있고 크기가 맞으면 로컬 경로를 돌려주기
때문이다(HF repo id 는 로컬이 불완전할 때만 쓰는 폴백이다).

왜 별도 스크립트인가
  · `from_pretrained(repo_id)` 로 매번 받게 두면 실행마다 HF 허브를 재검증하고,
    `HF_HUB_OFFLINE=1` 로 막아둔 경로(`chatbot/*`)에서는 아예 못 받는다.
  · 받아 놓은 위치가 `~/.cache/huggingface` 안이면 무결성을 매니페스트로 못 잰다.
    레포 안 `router_moai_embedding_model/` 로 받아야 `router_source --verify` 가
    sha256 까지 대조할 수 있다.

멱등이다 — 크기가 이미 맞는 파일은 건너뛴다. 중간에 끊겨도 다시 돌리면 된다.

사전 준비:
    pip install "huggingface-hub>=0.23"
    export HF_TOKEN=hf_...        # read 권한이면 충분. https://huggingface.co/settings/tokens
    # 또는: huggingface-cli login

사용:
    python scripts/download_router_hf.py                  # 매니페스트 기준 내려받기
    python scripts/download_router_hf.py --dry-run        # 받을 목록만 출력
    python scripts/download_router_hf.py --verify-sha     # 받은 뒤 sha256 전수 검증(느림)
    python scripts/download_router_hf.py --repo other/id  # repo 덮어쓰기
    python scripts/download_router_hf.py --dst /path/ckpt # 저장 위치 덮어쓰기

주의: 이 스크립트는 **매니페스트에 적힌 9개 파일만** 쓴다. 그 밖의 파일은 건드리지 않는다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
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
    ap = argparse.ArgumentParser(description="라우터 체크포인트를 로컬로 내려받는다")
    ap.add_argument("--repo", default=None, help="HF repo id (기본: 매니페스트의 hf_repo)")
    ap.add_argument("--dst", default=None, help="저장 디렉토리 (기본: 매니페스트의 local_dir)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify-sha", action="store_true",
                    help="내려받은 뒤 sha256 전수 검증(2.38GB 읽음, 느림)")
    a = ap.parse_args()

    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    repo = a.repo or os.environ.get("ROUTER_HF_REPO") or m["hf_repo"]
    dst = pathlib.Path(a.dst) if a.dst else ROOT / m["local_dir"]

    # ── 이미 맞는 파일은 건너뛴다 ────────────────────────────────────────
    todo, skip = [], []
    for name, meta in m["files"].items():
        f = dst / name
        (skip if f.exists() and f.stat().st_size == meta["size"] else todo).append(name)
    for n in skip:
        print(f"  건너뜀   : {n} (로컬 크기 일치)")
    total = sum(m["files"][n]["size"] for n in todo)
    print(f"\n받을 파일 {len(todo)}개 · {total / 1048576:.1f} MB  {repo} → {dst}")
    for n in todo:
        print(f"  받음     : {n}  ({m['files'][n]['size'] / 1048576:.1f} MB)")

    if a.dry_run:
        print("\n--dry-run — 아무것도 내려받지 않았습니다.")
        return 0
    if not todo:
        print("\n로컬이 이미 완전합니다 — 네트워크를 타지 않습니다.")
    else:
        try:
            from huggingface_hub import hf_hub_download
        except ImportError:
            sys.exit('[중단] pip install "huggingface-hub>=0.23" 후 다시 실행하세요.')

        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        if not token:
            print("[안내] HF_TOKEN 환경변수가 없습니다. huggingface-cli login 세션을 씁니다.")

        dst.mkdir(parents=True, exist_ok=True)
        for n in todo:
            print(f"\n내려받는 중: {n} …", flush=True)
            try:
                cached = hf_hub_download(repo_id=repo, filename=n, repo_type="model",
                                         token=token)
            except Exception as e:                 # 권한 없음 · 오프라인 · repo 미존재
                sys.exit(f"[중단] {n} 을 받지 못했습니다({type(e).__name__}: {e}).\n"
                         f"       프라이빗 repo 입니다 — HF_TOKEN(read) 또는 "
                         f"huggingface-cli login 이 필요합니다.")
            # 캐시 심볼릭 링크가 아니라 실파일을 레포 안에 둔다 — 매니페스트 무결성
            # 검사와 오프라인 실행이 캐시 상태에 의존하지 않게 하기 위해서다.
            shutil.copyfile(cached, dst / n)

    # ── 받은 결과를 매니페스트로 대조한다 ────────────────────────────────
    sys.path.insert(0, str(ROOT / "crawler"))
    import router_source

    ok, problems = router_source.check_local(m, strict=a.verify_sha)
    print(f"\n[검증] 로컬 상태: {'사용 가능' if ok else '사용 불가'}"
          f"{' (sha256 전수 검사 통과)' if ok and a.verify_sha else ' (크기)'}")
    for p in problems[:10]:
        print(f"   - {p}")
    if not ok:
        return 1

    chosen = router_source.resolve(m)
    print(f"router_source.resolve() -> {chosen}")
    if chosen != str(router_source.local_dir(m)):
        print("[경고] resolve() 가 로컬 경로를 고르지 않았습니다 — "
              "ROUTER_PATH 환경변수가 설정돼 있는지 확인하세요.")
    else:
        print("이제 rag.get_router() 가 로컬에서 로드합니다 — HF 접속 없음.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""라우터 체크포인트 위치 해석 — 로컬 디렉토리 또는 HF 프라이빗 repo.

배경: 가중치 `pytorch_model.bin`이 2.38GB라 git에 넣을 수 없다(GitHub 단일 파일
100MB 상한, Release 에셋도 2GB 상한). 임베딩 모델 `dragonkue/BGE-m3-ko`가
sentence-transformers를 통해 런타임에 HF에서 받아 캐시하는 것과 **같은 패턴**으로,
라우터도 HF 프라이빗 repo에서 받는다.

`transformers.AutoModel*.from_pretrained()`는 로컬 경로와 HF repo id를 모두 받으므로,
이 모듈은 "무엇을 넘길지"만 정한다. 다운로드·캐시는 huggingface_hub가 한다
(기본 캐시: ~/.cache/huggingface/hub).

해석 순서 — 먼저 맞는 것에서 멈춘다:

  1. 환경변수 `ROUTER_PATH`      명시 지정. A/B나 실험 체크포인트용. 검증 없이 그대로 반환
  2. 로컬 디렉토리(완전할 때)     매니페스트의 파일이 전부 있고 크기가 맞으면 로컬 사용.
                                이미 체크포인트를 가진 사람은 네트워크를 타지 않는다
  3. HF repo id                  `ROUTER_HF_REPO` 또는 매니페스트의 `hf_repo`
  4. None                        위가 전부 실패. 호출부(rag.get_router)가 키워드 분류로 폴백

**여기서 예외를 던지지 않는다.** 라우터는 있으면 좋고 없으면 폴백하는 계층이고,
체크포인트가 없는 환경(클론 직후·CI)에서 검색 자체가 죽으면 안 된다.

무결성 검사는 기본이 **크기만** 본다. sha256 전수는 2.38GB를 매번 읽어야 해서
평상시엔 과하다 — `verify(strict=True)` 또는 `python router_source.py --verify`로
명시적으로 돌린다.

사용:
    from router_source import resolve
    ROUTER_PATH = resolve()          # str | None

    python router_source.py          # 현재 무엇이 선택되는지 출력
    python router_source.py --verify # sha256 전수 검사(느림)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib

MANIFEST_PATH = pathlib.Path(__file__).resolve().parent / "data" / "router_manifest.json"
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_manifest(path: pathlib.Path = MANIFEST_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def local_dir(manifest: dict | None = None) -> pathlib.Path:
    m = manifest or load_manifest()
    return REPO_ROOT / m.get("local_dir", "router_moai_embedding_model")


def check_local(manifest: dict | None = None, strict: bool = False) -> tuple[bool, list[str]]:
    """로컬 디렉토리가 쓸 수 있는 상태인지. (사용가능, 문제목록)을 돌려준다.

    strict=False (기본) — 존재 + 크기 일치만 본다. 부분 다운로드·빈 파일을 잡는다.
    strict=True        — sha256까지 본다. 2.38GB를 읽으므로 느리다.
    """
    m = manifest or load_manifest()
    d = local_dir(m)
    problems: list[str] = []
    if not d.is_dir():
        return False, [f"디렉토리 없음: {d}"]
    for name, meta in m["files"].items():
        f = d / name
        if not f.exists():
            problems.append(f"없음: {name}")
            continue
        size = f.stat().st_size
        if size != meta["size"]:
            problems.append(f"크기 불일치: {name} ({size} != {meta['size']})")
            continue
        if strict:
            h = hashlib.sha256()
            with f.open("rb") as fh:
                for blk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(blk)
            if h.hexdigest() != meta["sha256"]:
                problems.append(f"sha256 불일치: {name}")
    return (not problems), problems


def resolve(manifest: dict | None = None, quiet: bool = False) -> str | None:
    """from_pretrained에 넘길 값. 로컬 경로(str) | HF repo id(str) | None."""
    m = manifest or load_manifest()

    env = os.environ.get("ROUTER_PATH")
    if env:
        return env

    ok, problems = check_local(m)
    if ok:
        return str(local_dir(m))
    if problems and not quiet and local_dir(m).is_dir():
        # 디렉토리는 있는데 불완전하다 — 조용히 HF로 넘어가면 원인을 못 찾는다
        print(f"[router] 로컬 체크포인트 불완전({len(problems)}건) — HF에서 받습니다. "
              f"첫 문제: {problems[0]}")

    repo = os.environ.get("ROUTER_HF_REPO") or m.get("hf_repo")
    if repo:
        return repo
    return None


def _main() -> int:
    ap = argparse.ArgumentParser(description="라우터 체크포인트 위치 확인")
    ap.add_argument("--verify", action="store_true", help="sha256 전수 검사(2.38GB 읽음, 느림)")
    a = ap.parse_args()

    m = load_manifest()
    d = local_dir(m)
    print(f"매니페스트 : {MANIFEST_PATH}")
    print(f"로컬 경로  : {d}  ({'있음' if d.is_dir() else '없음'})")
    print(f"HF repo    : {os.environ.get('ROUTER_HF_REPO') or m.get('hf_repo')}"
          f"{' (프라이빗 — HF_TOKEN 필요)'}")
    if os.environ.get("ROUTER_PATH"):
        print(f"ROUTER_PATH: {os.environ['ROUTER_PATH']}  ← 환경변수가 최우선")

    ok, problems = check_local(m, strict=a.verify)
    print(f"\n로컬 상태  : {'사용 가능' if ok else '사용 불가'}"
          f"{' (sha256 전수 검사 통과)' if ok and a.verify else ''}")
    for p in problems[:10]:
        print(f"   - {p}")
    if len(problems) > 10:
        print(f"   ... 외 {len(problems) - 10}건")

    chosen = resolve(m)
    print(f"\nresolve() -> {chosen}")
    if a.verify and not ok and chosen == str(d):
        print("  ⚠ sha256는 틀렸지만 크기는 맞아 resolve()가 로컬을 고릅니다.\n"
              "    (평상시 검사는 크기만 본다 — 위 --verify 결과를 신뢰할 것.)\n"
              "    조치: 손상된 파일을 지우고 다시 받거나, 재학습본이면 매니페스트를 갱신하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

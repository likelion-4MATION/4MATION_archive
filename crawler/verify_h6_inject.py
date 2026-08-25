#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H-6 주입 검사 — 하네스가 실제로 잡는가 (수정 마일스톤 전용).

M9-3b 2-3 에서 원복 경로를 안전하게 고쳤다. 이전의 인라인 방식은
    open(path, "wb").write(open(path, "rb").read().replace(...))
로, `wb` 오픈이 인자를 평가하기 **전에** 파일을 0바이트로 비워
이어지는 `rb` 읽기가 빈 파일을 읽었다 → 대상 CSV 파괴(H46 — combos_dpin 0바이트 사고).

이 스크립트의 안전 규칙:
  1) 주입 **전**에 원본을 별도 경로로 복사해 둔다.
  2) 주입은 신규 컬럼(evidence_spans) 안 스니펫 1글자만. 원본 문자열 컬럼은 안 건드린다.
  3) 원복은 그 복사본을 되돌려놓는다.
  4) 원복 후 sha256 을 스스로 대조하고 불일치면 rc=1.

실행: python3 crawler/verify_h6_inject.py
기대: 주입 후 verify_combos rc=1 · 원복 후 sha 일치 · 전체 통과 ✅ · exit 0
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

BASE = pathlib.Path(__file__).resolve().parent
TARGET = BASE / "data" / "qform_combos_dpin.csv"
VERIFY = BASE / "verify_combos.py"

# 주입 대상 — evidence_spans 안 스니펫 1글자. one_line/discriminator/phrase 등 원본 컬럼은 건드리지 않는다.
FROM = "가지급금이란?"
TO = "가지급금이람?"


def sha256(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    orig = sha256(TARGET)
    print(f"주입 전 sha {orig}")

    fd, backup_path = tempfile.mkstemp(prefix="h6_backup_", suffix=".csv")
    os.close(fd)
    backup = pathlib.Path(backup_path)
    try:
        shutil.copyfile(TARGET, backup)              # 1) 원본 백업 (주입 전)

        data = TARGET.read_bytes()
        inj = data.replace(FROM.encode("utf-8"), TO.encode("utf-8"))
        if inj == data:
            print(f"⛔ 주입 실패: {FROM!r} 를 {TARGET.name} 에서 찾지 못함")
            return 1
        TARGET.write_bytes(inj)                      # 2) 주입

        r = subprocess.run([sys.executable, str(VERIFY)], capture_output=True, text=True)
        print(f"주입 후 verify_combos rc={r.returncode} (기대 1)")
        if r.returncode != 1:
            print("⛔ 검사가 주입을 못 잡았다 — 하네스 무효")
            return 1

        shutil.copyfile(backup, TARGET)              # 3) 복사본으로 원복
        final = sha256(TARGET)                       # 4) 자가검사
        print(f"원복 후 sha {final}")
        print(f"원복 일치   {'OK' if final == orig else 'DIFF ⛔'}")
        if final != orig:
            return 1
    finally:
        backup.unlink(missing_ok=True)

    print("전체 통과 ✅  (주입 검출 rc=1 · 원복 sha 일치)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# ASSIGNMENT_D0 — 수집 파이프 관통 (금)

**목표**: 매니페스트 전량 raw HTML + 메타 JSON 확보, 재실행 재현성 통과, link_registry.json 완성.
시작 전 `CLAUDE.md` 절대 규칙을 읽는다.

## 입력 (전제 조건)

| 파일 | 상태 | 용도 |
|---|---|---|
| `분석필요태깅_포함여부분석.xlsx` | ~/Downloads 존재 확인됨 | 포함 판정분 병합 + 링크만 5건 판정 근거 |
| `분석필요_예비판정.csv` | ~/Downloads 존재 확인됨 | 판정 교차 확인 |
| 범위정의서 (필수 URL 원본, 55 URL: 필수 37/분석필요 18) | **사용자가 폴더에 넣어줘야 함** | 필수 리스트의 원천 |

범위정의서가 없으면 **T1에서 중단하고 사용자에게 요청**한다. 임의 재구성 금지.

## 태스크 (순서 고정)

**T1. 입력 확보 확인** — 세 파일을 프로젝트 폴더로 복사(glob으로 탐색, NFD 주의). 없는 파일은 사용자에게 요청 후 대기.

**T2. 매니페스트 병합** — `python build_manifest.py <필수원본> <xlsx> -o crawl_manifest.csv`
- 실행 시 출력되는 **컬럼 매핑을 반드시 검수**하고 미리보기 5행을 눈으로 확인
- 병합 결과 건수를 세고, 필수분이 데일리 로그 기준(30)과 다르면 델타 목록을 `HOLES.md`에 기록 (멘토 확인 대기 4건 중 "F4 건수 불일치"와 연결)
- 링크만/제외/보류 판정 항목이 매니페스트에 **들어가지 않았는지** 확인

**T3. link_registry.json 작성** — 아래 스키마로 6건. URL과 판정은 xlsx·범위정의서에서 추출하고, **문서에 없는 URL을 지어내지 않는다** (못 찾으면 HOLES에 기록).

```json
{
  "entries": [
    {
      "intent_id": "personal_rehabilitation",
      "keywords": ["개인회생", "회생절차", "..."],
      "message": "개인회생은 예금보험공사 소관 업무가 아닙니다. 아래 담당 기관에서 안내받으실 수 있습니다.",
      "org": "담당 기관명",
      "url": "https://...",
      "source_judgment": "링크만"
    }
  ]
}
```

- 대상 6건: 예금자보호한도(해외) · 지급대상 검색 · 신용회복 · 파산면책 · 개인회생 · 불법행위신고
- keywords는 함정 테스트를 염두에 두고 동의어 3개 이상 (예: 개인회생/회생절차/법원회생)
- 안내 문구는 "소관 아님을 밝히고 → 담당 기관 안내" 구조 유지

**T4. `config.py` USER_AGENT의 contact 이메일 채우기** (팀 대표 메일).

**T5. 스모크** — `python run_crawl.py --manifest crawl_manifest.csv --limit 3`
- 3건 모두 ok인지, raw/meta 파일이 실제 생성됐는지, 메타의 breadcrumb·title이 채워졌는지 확인.

**T6. 전량 수집 2회** — `--out run1` → `--out run2` (각 30여 건 × ~2초 ≈ 2분 내외).

**T7. 재현성 검증** — `python verify_rerun.py run1 run2` 통과 확인. 불일치 건은 원인(동적 요소 등)을 HOLES에 기록.

**T8. 마감** — `data/crawl_report.json` 요약을 진행 로그로 정리, `HOLES.md`/`DECISIONS.md` 갱신. 커밋 대상 파일 목록(경로 + 한 줄 설명)을 정리해 사용자에게 보고한다. **git 명령은 실행하지 않는다** — 커밋은 사용자 직접.

## 통과 기준 (전부 예/아니오)

- [ ] crawl_manifest.csv의 모든 URL에 대해 raw HTML + 메타 JSON 존재 (오류 페이지·robots 차단 건 제외, 해당 건은 report에 사유 기록)
- [ ] verify_rerun 통과 — 재실행 동일 결과
- [ ] robots disallow 페이지 수집 0건
- [ ] link_registry.json 6건 · 각각 안내 문구 + URL 보유
- [ ] HOLES.md에 필수 건수 델타(있다면) 기록됨

## 범위 밖 (오늘 하지 않는다)

파싱 · 표 미화 · 청킹 · 임베딩 · 첨부(PDF/HWP) · robots 차단 건 수집 · 측정후결정(불법행위신고 A/B).

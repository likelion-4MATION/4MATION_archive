# -*- coding: utf-8 -*-
"""예솜24 챗봇 버튼트리 → 평가셋 확장 + Q-A 데이터셋 (버튼 도달 답변만).

이번 단계 범위: 자유질문/텍스트 제안은 따라가지 않고, **버튼 클릭(value 재전송)으로
도달하는 답변만** 수집한다. 챗봇 응답이 간헐적으로 fallback('의도가 명확하지 않아요')을
반환하므로 각 노드를 여러 번 재조회해 버튼 합집합으로 누락을 없앤다.

  API: POST https://pubkbot.kdic.or.kr/chat/message  body {user, text}
       user = source (homepage/kmrs/iris/portal 중 하나)
       응답 {elements:[{type:text|buttons|export|...}]}  버튼 value 를 다시 보내면 하위로.

  gt_docs 매핑: 답변의 '바로가기' 링크 url → crawler 슬러그. 코퍼스(수집분)에 있으면 그 doc_id,
                없으면 업무 대표문서(BIZDEF). fallback-only 노드(=채무조정 루트)는 제외.

산출: testset_yesom.jsonl (5필드, eval.py 드롭인) · yesom_qa.jsonl (질문+답변 전문) ·
      testset_merged.jsonl (원본 + 예솜, 질문 dedup)
주의: KDIC 컨테이너 밖(로컬)에서 실행. 예의상 요청 간격 유지.
"""
from __future__ import annotations
import json, re, time, urllib.request
from collections import Counter

from config import USER_AGENT

BASE = "https://pubkbot.kdic.or.kr"
USER = "homepage"
DELAY = 0.15
RETRY = 4                       # fallback 대응 재조회 횟수
ORIG_TS = "data/testset.jsonl"  # 병합 대상 (레포 경로에 맞춰 조정)
OUT_TS, OUT_QA, OUT_MERGED = "data/testset_yesom.jsonl", "data/yesom_qa.jsonl", "data/testset_merged.jsonl"

# 카테고리 seed = 챗봇 푸터 버튼의 실제 onclick value(#intent 키). 라벨 텍스트를 보내면
# '채무조정 안내'처럼 intent 매칭 실패로 fallback → 서브트리 누락. 반드시 # 값으로 seed.
SEEDS = [("#예금자보호제도", "예금자보호제도"), ("#예금보험금", "예금보험금 안내"),
         ("#미수령금신청", "고객 미수령금 신청"), ("#착오송금반환지원제도", "착오송금 반환 신청"),
         ("#채무조정제도", "채무조정 안내"), ("#은닉재산신고", "은닉재산 신고")]
SEED_LABELS = {v: l for v, l in SEEDS}
FB = re.compile(r"의도가 명확하지 않아요|상담원 연결이 필요")

# 코퍼스(D1 수집 ok) — gt 유효성. 필요시 crawl_report.json 에서 자동 생성 권장.
CORPUS = {
 "kdic-www-sp-dpstrprot-ProtSyst-selectScrn","kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn",
 "kdic-www-sp-dpstrprot-selectProtSystProtSumr","kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr",
 "kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn","kdic-www-sp-dpstrprot-ProtSystProtGudn-selectScrn",
 "kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn","kdic-www-sp-dpstrprot-DpsmIbamtAplyProc-selectScrn",
 "kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn","kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn",
 "kdic-www-sp-dpstrprot-ProtSystHrpeHistInq-selectScrn","kdic-www-sp-kmrs-kmrsItrd-selectScrn",
 "kdic-www-sp-kmrs-kmrsItrdProc-selectScrn","kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn",
 "kdic-www-sp-kmrs-kmrsItrdAplyMthd-selectScrn","kdic-www-sp-sprtfund-SprtFndCncmDclrGudn-selectScrn",
 "kdic-www-sp-sprtfund-SprtCncmDclrInqGudn-selectScrn","kdic-www-sp-sprtfund-SprtFndCncmDclrFaq-selectScrn",
 "kdic-www-rb-lbltajmt-LbltAjmtSprtLbltAjmtSyst-selectScrn","kdic-www-rb-lbltajmt-LbltAjmtSprtLbltInfoInqDscsnAply-selectScrn",
 "kdic-www-rb-lbltajmt-LbltAjmtSprtCredRcvrySprt-selectScrn","kdic-www-rb-lbltajmt-LbltAjmtSprtPsnRg-selectScrn",
 "kdic-www-rb-lbltajmt-LbltAjmtSprtPsnBr-selectScrn",
}
BIZDEF = {
 "예금자보호제도": ["kdic-www-sp-dpstrprot-ProtSyst-selectScrn"],
 "예금보험금 안내": ["kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn"],
 "고객 미수령금 신청": ["kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn"],
 "착오송금 반환 신청": ["kdic-www-sp-kmrs-kmrsItrdAplyMthd-selectScrn"],
 "채무조정 안내": ["kdic-www-rb-lbltajmt-LbltAjmtSprtLbltAjmtSyst-selectScrn"],
 "은닉재산 신고": ["kdic-www-sp-sprtfund-SprtFndCncmDclrGudn-selectScrn"],
}
# 노드 라벨이 원시 intent 키(#...)로 잡히는 경우의 사람이 읽을 질문
HASHQ = {
 "#인터넷미수령금신청": "미수령금 인터넷 신청 방법은?",
 "#은닉재산신고이메일": "은닉재산 이메일 신고 방법은?", "#은닉재산신고인터넷": "은닉재산 인터넷 신고 방법은?",
 "#은닉재산신고우편": "은닉재산 우편 신고 방법은?", "#은닉재산신고방문": "은닉재산 방문 신고 방법은?",
}
GENERIC = {"은행", "보험회사", "종합금융회사", "투자매매업자 / 투자중개업자", "상호저축은행 및 상호저축은행 중앙회"}


def ask(text: str) -> dict:
    req = urllib.request.Request(BASE + "/chat/message",
        data=json.dumps({"user": USER, "text": text}).encode(),
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Referer": BASE + "/chatbot.html?source=homepage",
        }, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def slug(url: str) -> str:
    m = re.match(r"https?://(www|fins)\.kdic\.or\.kr(/[^?#]*)", url or "")
    if not m:
        return ""
    p = re.sub(r"\.do$", "", m.group(2)).strip("/")
    return "kdic-" + m.group(1) + "-" + p.replace("/", "-") if p else ""


def crawl() -> dict:
    """버튼트리 BFS. 노드별 버튼/텍스트/링크를 재조회로 누적."""
    G: dict = {}
    def rec(k, label):
        G.setdefault(k, {"label": label, "texts": [], "btn": {}, "links": {}, "files": [], "fb": 0})
        return G[k]
    def query(k, label):
        n = rec(k, label)
        for _ in range(RETRY):
            try:
                j = ask(k)
            except Exception:
                time.sleep(DELAY); continue
            saw_btn = False
            for el in j.get("elements", []):
                t = el.get("type")
                if t in ("text", "title", "subtitle"):
                    tx = el.get("text", "")
                    if tx and tx not in n["texts"]:
                        n["texts"].append(tx)
                    if FB.search(tx or ""):
                        n["fb"] += 1
                elif t == "buttons":
                    for b in el.get("buttons", []):
                        if re.match(r"^https?://", b["value"]):
                            n["links"][b["value"]] = b["text"]
                        else:
                            n["btn"][b["value"]] = b["text"]; saw_btn = True
                elif t == "export":
                    f = el.get("orgfilename") or el.get("src")
                    if f and f not in n["files"]:
                        n["files"].append(f)
            if saw_btn:
                break
            time.sleep(DELAY)
        return n
    # 여러 패스: 간헐 fallback으로 놓친 분기를 합집합으로 흡수.
    # 단, 버튼을 이미 확보한 노드는 다음 패스에서 재조회하지 않는다(H21) — 예전 코드는
    # 매 패스마다 queued 전체를 다시 훑어 이미 끝난 노드까지 반복 조회, 노드 수가 늘수록
    # 패스당 요청 수가 계속 커져 실행 시간이 크게 불어났다(수백 건 이상 왕복 가능).
    # 재조회 대상은 (a) 이번 패스에 새로 발견된 노드, (b) 버튼을 못 얻고 fallback만
    # 봤던 노드(최대 3패스)로 한정한다.
    queued = {v for v, _ in SEEDS}
    labels = dict(SEEDS)
    to_visit = set(queued)
    fb_retries: dict = {}
    pass_no = 0
    while to_visit:
        pass_no += 1
        print(f"  [예솜 크롤 pass {pass_no}] 조회 {len(to_visit)}개 · 누적 발견 {len(queued)}개")
        next_visit = set()
        for i, k in enumerate(sorted(to_visit), 1):
            n = query(k, labels.get(k, k))
            for val, txt in n["btn"].items():
                labels.setdefault(val, txt)
                if val not in queued:
                    queued.add(val); next_visit.add(val)
            if not n["btn"] and n["fb"] > 0 and fb_retries.get(k, 0) < 3:
                fb_retries[k] = fb_retries.get(k, 0) + 1
                next_visit.add(k)
            time.sleep(DELAY)
        to_visit = next_visit
    print(f"  [예솜 크롤] 완료 — 총 {len(queued)}개 노드, {pass_no}패스")
    return G


def build(G: dict):
    # biz·path는 seed에서 **정방향 BFS**로 부여한다. 같은 라벨의 서류 노드가
    # '미수령금 신청서류' 밑과 '예금보험금 신청>보험금신청서류' 밑에 각각(다른 키로)
    # 존재하므로, 부모 역추적(첫 부모)은 오배정된다. 진입 경로의 seed 업무가 정답.
    from collections import deque
    biz_map, path_map = {}, {}
    dq = deque((v, l, [l]) for v, l in SEEDS)
    seen_f = set()
    while dq:
        k, biz, path = dq.popleft()
        if k in seen_f:
            continue
        seen_f.add(k); biz_map[k] = biz; path_map[k] = path
        for val, txt in G.get(k, {}).get("btn", {}).items():
            if val not in seen_f:
                dq.append((val, biz, path + [txt]))
    def clean_q(label, path):
        if label in HASHQ:
            return HASHQ[label]
        if label in GENERIC:
            return ("비보호 금융상품" if "보호 되지 않는" in path else "보호 금융상품") + " - " + label
        if label.startswith("#"):       # 원시 intent 키 → 경로에서 # 제거해 사람이 읽게
            return " ".join(s for s in path.split(">") if not s.startswith("#")) or label
        return label

    ts, qa, seen = [], [], set()
    for k, n in G.items():
        ans = " ".join(t for t in n["texts"] if not FB.search(t)).strip()
        ans = re.sub(r"\s+", " ", ans)
        if not ans:                      # fallback-only 제외
            continue
        path = path_map.get(k, [n["label"]]); biz = biz_map.get(k); url = next(iter(n["links"]), "")
        d = slug(url)
        if d in CORPUS:                  # 답변의 '바로가기' 링크 우선
            gt = [d]
        elif "보험금신청서류" in ">".join(path):   # 예금보험금 구비서류 세부
            gt = ["kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn"]
        else:                            # 업무 대표문서 (근사)
            gt = BIZDEF.get(biz, [])
        q = clean_q(n["label"], ">".join(path))
        while q in seen:                 # 질문 유일화
            q = q + " (" + (path[-2] if len(path) > 1 else biz) + ")"
        seen.add(q)
        ts.append({"question": q, "gt_docs": gt, "business_function": biz,
                   "source": "yesom", "representative": False})
        qa.append({"question": q, "answer": ans, "business_function": biz,
                   "yesom_path": " > ".join(path), "is_leaf": not n["btn"],
                   "ref_url": url, "files": n["files"], "gt_docs": gt})
    return ts, qa


def main():
    G = crawl()
    ts, qa = build(G)
    with open(OUT_TS, "w", encoding="utf-8") as f:
        for it in ts:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    with open(OUT_QA, "w", encoding="utf-8") as f:
        for it in qa:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    # 병합 (원본 + 예솜, 질문 dedup)
    orig = [json.loads(l) for l in open(ORIG_TS, encoding="utf-8") if l.strip()]
    seen = {r["question"] for r in orig}; merged = list(orig)
    for it in ts:
        if it["question"] not in seen:
            seen.add(it["question"]); merged.append(it)
    with open(OUT_MERGED, "w", encoding="utf-8") as f:
        for it in merged:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    print(f"예솜 답변노드 {len(ts)} → {OUT_TS} / {OUT_QA}")
    print("  업무별:", dict(Counter(i["business_function"] for i in ts)))
    print("  gt_docs 코퍼스밖:", [d for i in ts for d in i["gt_docs"] if d not in CORPUS])
    print(f"  병합 {len(orig)} → {len(merged)}  ({OUT_MERGED})")
    if any(i["gt_docs"] == [] for i in ts):
        print("  ※ gt_docs 빈 항목 존재 — BIZDEF 확인")


if __name__ == "__main__":
    main()

"""앵커 미보유 18건에 검색 기준 앵커(= 검색기가 반드시 회수해야 할 스팬)를 부여한다.

기존 span_verbatim_ok=False는 '단일 verbatim 정답 문장이 없다'는 generator 기준 판정이었다.
검색 평가에서는 '어느 스팬을 회수해야 하는가'가 기준이므로 18건 모두 평가 가능하다.
"""
import json, io, sys
sys.stdout.reconfigure(encoding="utf-8")
D = "data/"
norm = lambda s: "".join((s or "").split())

ANCHORS = {
 # 착오송금 구비서류 표(c091) — 법인/비법인 · 온라인/방문 4분면
 "nat450-0139": "법인을 대리하는 경우 사업자등록증 사본",
 "nat450-0141": "비법인단체를 대리하는 경우 고유번호증 사본",
 "nat450-0147": "법인을 대리하는 경우 사업자등록증 파일업로드",
 "nat450-0149": "비법인단체를 대리하는 경우 고유번호증 파일업로드",
 # 미수령금
 "nat450-0207": "개산지급금 파산절차 장기화에 따른 예금자의 불편을 해소하기 위해",
 "nat450-0348": "공사는 상속인이 피상속인(사망자, 실종자, 금치산자 또는 피성년후견인, 피산정후견인)의 금융재산 및 채무를 여러 금융회사를 일일이 방문하여야 하는 시간적·경제적 어려움을 덜어주기 위하여",
 "nat450-0350": "파산 금융회사 정보 검색 예금보험공사가 관리하고 있는 파산금융회사의 상세정보를 확인할 수 있습니다.",
 "nat450-0351": "여러분이 현재 받으실 미수령금이 있는지 금융안심포털에서 통합 확인 및 통합신청이 가능합니다.",
 "nat450-0359": "미수령금 종류별 · 부실금융회사별 구분없이 '16.10월부터 전국 지급대행점 어디에서든 미수령금을 통합신청할 수 있도록 하였습니다.",
 # 채무조정 / 회생 / 파산
 "nat450-0260": "예금보험공사는 예금보호대상 금융회사(은행, 보험회사, 투자매매업자·투자중개업자, 종합금융회사, 상호저축은행 등)가 파산한 경우 채무자의 연체대출금에 대한 채무조정을 지원",
 "nat450-0261": "개인신용회복지원제도란 개인 및 개인사업자 중 협약 등에서 구성하는 일정요건을 갖춘 채무자를 대상으로",
 "nat450-0269": "소유하고 있는 재산을 처분할 필요가 없음 | 재산을 처분하여 빚을 갚음",
 "nat450-0275": "개인회생제도란 지급불능 상태에 있는 사람이 일정한 소득을 얻고 있을 경우에 3~5년간 일정한 금액을 갚으면 채무를 면제받는 제도입니다.",
 "nat450-0279": "개인인 채무자가 자신의 재산으로 모든 채무를 변제할 수 없는 상태에 빠진 경우에 그 채무의 정리를 위하여 채무자 또는 채권자가 파산신청을 하는 경우 이를 개인파산이라고 합니다.",
 "nat450-0442": "청산가치가 보장되는 것 이상의 일정한 수입이 있어야 함 | 일정한 수입이 없어도 됨",
 # 예금보험금 / 은닉재산
 "nat450-0319": "부모 중 한 분만 지급대행지점에 방문하시는 경우에는 부모 중 방문하는 분의 주민등록증 등 본인증명 서류, 친권자합의서",
 "nat450-0387": "이 채권을 은닉하기 위해 자신의 장모에게 허위로 채권을 양도하였다",
 "nat450-0399": "파산된 저축은행 등의 주채무자 또는 보증채무자로서",
}

chunks = [json.loads(l) for l in io.open(D + "chunks.jsonl", encoding="utf-8")]
tag = {c["chunk_id"]: "c%03d" % i for i, c in enumerate(chunks)}
text = {c["chunk_id"]: norm(c["text"]) for c in chunks}

ok, bad = 0, []
for qid, span in ANCHORS.items():
    hosts = [tag[cid] for cid, t in text.items() if norm(span) in t]
    if hosts: ok += 1
    else: bad.append(qid)
    print(f"  {qid}: host={hosts or 'NONE'}")
print(f"\n검증: {ok}/{len(ANCHORS)} 매칭. 실패 {bad}")
if bad: sys.exit(1)

gt = [json.loads(l) for l in io.open(D + "gt_natural450_v9_dupfix2.jsonl", encoding="utf-8")]
n = 0
for g in gt:
    if g["id"] in ANCHORS:
        g["gt_anchor_span"] = ANCHORS[g["id"]]
        g["span_verbatim_ok"] = True
        g["anchor_basis"] = "retrieval"   # generator 기준 verbatim 정답문이 아니라 회수대상 스팬
        n += 1
io.open(D + "gt_natural450_v10_anchor.jsonl", "w", encoding="utf-8").writelines(
    json.dumps(g, ensure_ascii=False) + "\n" for g in gt)
tot = sum(1 for g in gt if g.get("answerable") is True and norm(g.get("gt_anchor_span")))
print(f"\n{n}건 앵커 부여 -> data/gt_natural450_v10_anchor.jsonl")
print(f"앵커 보유 answerable 문항: {tot} / answerable {sum(1 for g in gt if g.get('answerable') is True)}")

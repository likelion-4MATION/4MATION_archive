# -*- coding: utf-8 -*-
"""gt_natural430.jsonl(필터 후) 의 and/or 문항 중 앵커가 부족한 gold 청크에 대해,
Claude가 직접 원문을 읽고 실제 근거 문장을 고른 결과를 주입한다.

데이터셋_평가셋_수정내역_20260818.md §5(라벨 보강)의 방법론을 그대로 따르되,
사람이 아니라 Claude가 직접 청크 원문과 질문을 대조해 근거를 골랐다:
  1) 미앵커 gold 청크를 chunk_id 단위로 모은다(문항이 아니라 청크 단위 — 같은 청크가
     여러 문항에 재사용되므로, 팀의 38개 수기 앵커가 131개 슬롯으로 펼쳐진 것과 같은 구조).
  2) 재청킹으로 사라진 chunk_id는 재청킹 이전 218청크 스냅샷에서 원문을 조회한다.
  3) 그 청크 원문과, 그 청크를 필요로 하는 모든 문항의 질문을 함께 놓고 실제 근거
     문장을 골랐다(아래 CURATED 딕셔너리). 청크 전체를 쓰거나 임의로 자르지 않고,
     질문에 실제로 답이 되는 문장/행을 원문에서 그대로 발췌했다.
  4) 검증: 골라낸 스팬이 (a) 원 출처(현재청크 또는 구버전청크) 원문에 verbatim으로
     있는지, (b) 현재 181청크 코퍼스 어딘가에 verbatim으로 있는지(재청킹에서 살아
     남았는지) 둘 다 확인한다. 실패하면 즉시 에러를 낸다 — 조용히 넘어가지 않는다.

원본(gt_natural450.jsonl)은 무수정. 출력은 새 파일로 나간다.
"""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent
SRC = DATA / "gt_natural430_fresh.jsonl"   # filter_anchored.py 산출물(450->430, has-anchor)
DST = DATA / "gt_natural430_curated.jsonl"
CUR_CHUNKS = DATA / "chunks.jsonl"
OLD_CHUNKS = Path(r"C:\Users\twink\AppData\Local\Temp\claude\c--Users-twink-4MATION\2284c094-d825-4f15-8fac-2df4398da006\scratchpad\chunks_old218.jsonl")


def norm(s: str) -> str:
    return "".join(s.split())


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def anchors(item: dict) -> list[str]:
    a = item.get("gt_anchors")
    if a:
        return [x for x in a if x]
    s = item.get("gt_anchor_span")
    return [s] if s else []


def gold_ids(item: dict) -> list[str]:
    ids = item.get("gt_chunk_ids")
    if ids:
        return list(dict.fromkeys(ids))
    cid = item.get("gt_chunk_id")
    return [cid] if cid else []


# Claude가 각 chunk_id의 원문(현재 또는 구버전)과 해당 질문들을 직접 대조해서 고른
# 근거 문장. 전부 그 청크 원문에서 그대로 발췌했다(창작 없음).
CURATED: dict[str, str] = {
    "kdic-www-rb-lbltajmt-LbltAjmtSprtCredRcvrySprt-selectScrn#01":
        "신청인이 채권금융회사 빚 독촉 및 회수 중지를 신용회복위원회에 신청을 하면 상환기간 연장, 분할상환, 이자율 조정, 변제기유예, 채무감면 등 심사채무과정을 거치게 됩니다.",
    "kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#00":
        "예금보험공사는 예금보험 가입 금융회사가 취급하는 '예금' 등 만을 보호합니다. 그런데 여기서 꼭 알아두어야 할 점은 모든 금융상품이 보호대상 '예금' 등에 해당하지 않는다는 것입니다.",
    "kdic-www-rb-lbltajmt-LbltAjmtSprtPsnBr-selectScrn#03":
        "채무자가 허위의 채권자목록 그 밖의 신청서류를 제출하거나 법원에 대하여 그 재산 상태에 관하여 허위의 진술을 하는 행위",
    "kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#01":
        "은행 | 보통예금, 기업자유예금, 별단예금, 당좌예금 등 요구불예금",
    "kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn#02":
        "보험금/개산지급금/가지급금 신청은 본인명의 공인인증서, 금융인증서나 간편인증 등을 통해 하단의 「예금보험금/개산지급금/가지급금 신청 바로가기」에 접속하여 신청하시거나,",
    "kdic-www-rb-lbltajmt-LbltAjmtSprtLbltAjmtSyst-selectScrn#00":
        "예금보험공사는 예금보호대상 금융회사(은행, 보험회사, 투자매매업자·투자중개업자, 종합금융회사, 상호저축은행 등)가 파산한 경우 채무자의 연체대출금에 대한 채무조정을 지원( 동 제도는 2001년부터 운영)하고 있습니다.",
    "kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn#01":
        "친권자를 확인할 수 있는 증명서(가족관계증명서 및 미성년자 기준의 기본증명서)",
    "kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn#00":
        "예금보험공사는 미수령금 종류별·부실금융회사별로 독립되어 있던 지급대행점 운영 체계를 개선하여 미수령금 종류별·부실금융회사별 구분없이 ‘16.10월부터 전국 지급대행점 어디에서든 미수령금을 통합 신청할 수 있도록 하였습니다.",
    "kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn#02":
        "소액 상속 간편 지급 안내\n상속 예금등이 3백만 원 이하인 경우, 상속인 1인이 간편 지급을 신청할 수 있습니다.",
    "kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#04":
        "랩어카운트, 주가지수연계증권(ELS), 주가연계 파생결합사채(ELB), 주식워런트증권(ELW)",
    "kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#07":
        "상호저축은행 및 상호저축 은행중앙회 | 보통예금, 저축예금, 정기예금, 정기적금, 신용부금, 표지어음",
    "kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn#03":
        "현지 대사관의 공증을 받거나 해당국이 발급한 아포스티유를 첨부한 예금자 본인 명의의 위임장이어야 함",
    "kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn#10":
        "인감증명서제출이 불가능한경우 현지 공관장의 공증이 포함된 위임장 파일 업로드 | 해외거주자를 대리하는 경우",
    "kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn#09":
        "인감증명서제출이 불가능한경우 군복무 확인서(소속부대장발금) 파일업로드 | 군복무자를 대리하는 경우",
    "kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn#11":
        "(영주권자) 대사관\n착오송금 반환지원 신청 철회",
    "kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn#02":
        "대리인 | 공통 서류 | 대리인 확인용 신분증\n(주민등록증, 운전면허증, 여권 등) ※ 미성년자는 대리인이 될 수 없음",
    "kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn#08":
        "친권자 혹은 후견인임을 증명하는 서류 (가족관계증명서 및 미성년자 기준 기본증명서(상세)등) ※ 미성년자의 대리는 친권자 또는 후견인만가능",
    "kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn#00":
        "예금자가 미성년자인 경우 : 본인이 아닌 친권자 혹은 후견인이 예금보험금 수령",
    "kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn#07":
        "친권자 합의서 파일 업로드",
    "kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn#06":
        "고유번호증 사본 | 부가가치세법에 의하여 고유번호를 부여 받은 단체",
    "kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn#03":
        "착오송금인의 인감 날인된 금융 거래정보제공요구(동의)서",
    "kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn#04":
        "착오송금인의 인감 날인된 착오송금 반환지원 신청 등 위임장 스캔파일",
    "kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn#05":
        "사업자등록증 파일업로드 | 법인을 대리하는 경우",
    "kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#08":
        "상호저축은행중앙회 발행 자기앞수표 등 | 저축은행 발행채권(후순위채권 등) 등",
    "kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#02":
        "확정기여형, 개인형 퇴직연금제도 및 중소기업퇴직연금기금 편입 금융상품 중 예금보호대상으로 운용되는 금융상품은 합산하여 1억원까지 별도 보호하며, 사고보험금과 연금저축(신탁·보험)은 각각 1억원 한도로 별도보호",
    "kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#03":
        "자기신용대주담보금, 신용거래계좌 설정보증금, 신용공여담보금 등의 현금 잔액",
    "kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#05":
        "변액보험계약 최저사망보험금·최저연금적립금·최저중도인출금·최저종신중도인출금 등 최저보증",
    "kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#06":
        "보증보험계약, 재보험계약",
    "kdic-fins-ir-addrse-AddrseAttnMttr-selectScrn#00":
        "이의제기는 온라인 [착오송금 수취인 - 이의제기] 메뉴 또한 직접 방문하여 할 수 있습니다.",
    "kdic-www-sp-kmrs-kmrsItrd-selectScrn#00":
        "잘못 보낸 돈 되찾기 서비스란 착오송금인이 실수로 잘못 보낸 돈을 최소한의 비용으로 빠르게 되찾을 수 있도록 도와드리는 제도입니다.",
    "kdic-fins-ir-msdrpr-MsdrprAttnMttr-selectScrn#01":
        "착오송금 이후 사망한 자",
    "kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn#00":
        "착오송금인은 예금보험공사에게 반환지원신청(채권매입)",
    "kdic-www-rb-lbltajmt-LbltAjmtSprtCredRcvrySprt-selectScrn#00":
        "신청을 원하시는 분들은 아래의 신청자격, 절차 등을 참고하시어 신용회복위원회(개별 금융회사에 신청하는 것이 아닙니다.)에 구비서류를 지참하여 신청하여 주시기 바랍니다.",
    "kdic-www-rb-lbltajmt-LbltAjmtSprtCredRcvrySprt-selectScrn#02":
        "신청 및 접수 | 신청인이 사무국에 직접 방문하거나 우편 등으로 접수",
    "kdic-fins-lb-lbltinfo-LbltInfoInqItrdMthdGudn-selectScrn#00":
        "예금보험공사는 예금보호대상 금융회사(은행, 보험회사, 투자매매업자·투자중개업자, 종합금융회사, 상호저축은행 등)가 파산한 경우\n채무자의 연체대출금에 대한 채무조정을 지원(동 제도는 2001년부터 운영)하고 있습니다.",
    "kdic-www-rb-lbltajmt-LbltAjmtSprtLbltAjmtSyst-selectScrn#02":
        "위임장, 신청인 인감증명서, 대리인 신분증",
    "kdic-www-rb-lbltajmt-LbltAjmtSprtPsnBr-selectScrn#01":
        "대부분의 개인파산사건에서는 파산이 선고됨과 동시에 파산관재인이 선임되어 채권자들의 의견을 참조하여 채무자의 재산을 관리·조사하고 동시에 채무자에게 면책불허가 사유가 있는지 심사하게 됩니다.",
    "kdic-www-rb-lbltajmt-LbltAjmtSprtLbltAjmtSyst-selectScrn#03":
        "파산재단 채무자의 경우 고객상담센터 1588-0037 및 02-758-1000, 케이알앤씨 채무자의 경우 1899-0057에 전화문의를 통하여 전문상담직원으로부터 채무조정제도에 대하여 자세한 안내를 받으실 수 있습니다.",
    "kdic-fins-ir-msdrpr-MsdrprAttnMttr-selectScrn#02":
        "「전기통신금융사기 피해 방지 및 피해금 환급에 관한 특별법」 제2조 제2호에 따른 전기통신금융사기나 그 밖의 범죄에 이용 되었거나 이용된 것으로 의심할 만한 사정이 있는 경우",
    "kdic-fins-ir-msdrpr-MsdrprAttnMttr-selectScrn#03":
        "다음 중 하나에 해당하는 경우 공사와 착오송금인의 부당이득반환채권 매입계약이 해제됩니다.다만 착오송금인의 귀책 혹은 의사에 의해 계약이 해제되거나 착오송금인이 직접 회수하는 경우 공사가 청구하는 회수관련 비용을 상환한 후 계약이 해제됩니다.",
}


def main() -> None:
    items = load(SRC)
    cur = {c["chunk_id"]: c for c in load(CUR_CHUNKS)}
    old = {c["chunk_id"]: c for c in load(OLD_CHUNKS)}
    cur_norm = [(cid, norm(c["text"])) for cid, c in cur.items()]

    # 1) 검증 — 골라낸 스팬이 (a) 출처 원문에 있는가 (b) 현재 코퍼스에 있는가
    errors = []
    for cid, span in CURATED.items():
        source = cur.get(cid) or old.get(cid)
        if source is None:
            errors.append(f"{cid}: 원문 자체를 못 찾음(현재/구버전 둘 다 없음)")
            continue
        if norm(span) not in norm(source["text"]):
            errors.append(f"{cid}: 스팬이 출처 원문에 없음 -> {span[:50]!r}")
        if not any(norm(span) in t for _, t in cur_norm):
            errors.append(f"{cid}: 스팬이 현재 181청크 코퍼스 어디에도 없음 -> {span[:50]!r}")
    if errors:
        raise SystemExit("검증 실패:\n" + "\n".join(errors))

    # 2) 적용 — and/or 문항의 gold 청크마다 앵커를 채운다 (기존 앵커는 그대로 재사용)
    n_touched = 0
    n_filled = 0
    unresolved = []
    out = []
    for item in items:
        rel = item.get("chunk_relation") or "single"
        ids = gold_ids(item)
        have = anchors(item)
        new = dict(item)

        if rel not in ("and", "or") or len(ids) <= 1:
            new["gt_anchors"] = have
            new["gt_anchor_spans"] = have
            out.append(new)
            continue

        assigned = {}
        for cid in ids:
            source = cur.get(cid) or old.get(cid)
            hit = next((a for a in have if source and norm(a) in norm(source["text"])), None)
            if hit is not None:
                assigned[cid] = hit
            elif cid in CURATED:
                assigned[cid] = CURATED[cid]
                n_filled += 1
            else:
                unresolved.append((item["id"], cid))

        if len(assigned) != len(have) or any(cid not in [k for k in assigned] for cid in ids):
            n_touched += 1

        spans = [assigned[cid] for cid in ids if cid in assigned]
        new["gt_anchors"] = spans
        new["gt_anchor_spans"] = spans
        out.append(new)

    if unresolved:
        raise SystemExit(f"큐레이션 누락 {len(unresolved)}건: {unresolved[:10]}")

    with DST.open("w", encoding="utf-8") as f:
        for it in out:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    print(f"검증 통과: 큐레이션한 {len(CURATED)}개 청크 스팬 전부 출처 원문·현재 코퍼스 verbatim 확인")
    print(f"출력: {DST.name} ({len(out)}건) · 보강 문항 {n_touched}건 · 채운 슬롯 {n_filled}개")


if __name__ == "__main__":
    main()

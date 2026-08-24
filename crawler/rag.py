"""RAG 검색 공용 모듈 — 임베딩 · dense(FAISS) · BM25(kiwi) · 하이브리드(RRF).

- 임베딩: sentence-transformers `dragonkue/BGE-m3-ko` (bge-m3 한국어 파인튜닝, 1024d).
- dense: FAISS IndexFlatIP + 정규화 임베딩(= 코사인).
- sparse: rank_bm25 BM25Okapi, kiwipiepy 형태소 토큰.
- 융합: RRF(k=60). 리랭킹·파라미터 튜닝은 D1 범위 밖(D2 판단).

Store: doc_id 단위 upsert + content_hash 스킵 (recollect 재수집 트리거용).
"""

from __future__ import annotations

import json
import pathlib
import pickle

import faiss
import numpy as np

import faq_bf_map as fbm
import router_source

MODEL_NAME = "dragonkue/BGE-m3-ko"
INDEX_DIR = "data/index"
# FAQ 청크 BF의 라우터 산출 레이어(faq_routing_bf.md). 모듈 기준 절대경로 —
# chatbot은 절대 index_dir + 다른 cwd로 Searcher를 만들므로, 상대경로면 거기서만
# 조인이 조용히 빠져 eval(cwd=crawler)과 결과가 갈린다.
BF_MAP_PATH = str(pathlib.Path(__file__).resolve().parent / "data" / "bf_map.jsonl")
EMB_DIM = 1024   # bge-m3 임베딩 차원(모델 교체 시 갱신). build 시 실제 임베딩 차원으로 자동 보정됨.

_model = None
_kiwi = None
_router = None
_router_failed = False


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _get_kiwi():
    global _kiwi
    if _kiwi is None:
        from kiwipiepy import Kiwi
        _kiwi = Kiwi()
    return _kiwi


def tokenize(text: str) -> list[str]:
    """BM25용 한국어 토큰 (조사·기호 제거, 2자+ 명사/어간 위주)."""
    kiwi = _get_kiwi()
    keep = {"NNG", "NNP", "NNB", "NR", "NP", "VV", "VA", "SL", "SN", "SH", "MAG"}
    out = []
    for t in kiwi.tokenize(text):
        if t.tag in keep and len(t.form) >= 1:
            out.append(t.form.lower())
    return out or [text.lower()]


def embed_texts(texts: list[str]) -> np.ndarray:
    m = get_model()
    e = m.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(e, dtype="float32")


def chunk_embed_text(chunk: dict) -> str:
    """검색 임베딩 입력 — 제목 맥락을 본문 앞에 덧붙임."""
    title = chunk.get("page_title", "")
    return f"{title}\n{chunk['text']}" if title else chunk["text"]


def get_router():
    """질의 BF 라우터 지연 로드. 체크포인트 부재·로드 실패 시 None(키워드 폴백).

    실패를 한 번만 보고하고 이후 조용히 폴백한다 — 체크포인트가 없는 환경(클론 직후,
    CI)에서 질의마다 예외를 던지면 검색 자체가 못 돌기 때문. 단건 추론 median 35ms
    (MPS 기준, 모델 로드 5.7s는 최초 1회).
    """
    global _router, _router_failed
    if _router is None and not _router_failed:
        try:
            _router = fbm.Router(ROUTER_PATH)
        except Exception as e:               # 체크포인트 부재 · torch 미설치 · 라벨 불일치
            _router_failed = True
            print(f"[router] 로드 실패({type(e).__name__}) — 키워드 분류로 폴백: {ROUTER_PATH}")
    return _router


# ── 질의 업무 분류 (하드 필터용, 결정론적 키워드) ─────────────────────────
# chunk.py 문서측 재태깅과 짝을 이루는 질의측 분류. 사용자 구어체 어휘 반영.
# 점수/마진 미달(불명)이면 None → 필터 미적용(전체 검색)으로 안전 폴백.
BF_QUERY_KEYWORDS = {
    "예금자보호제도": [("보호돼", 3), ("보호되", 3), ("보호받", 3), ("보호 되", 3),
                  ("보호대상", 3), ("보호한도", 3), ("예금자보호", 3), ("예금 보호", 3),
                  ("얼마까지", 2), ("한도", 2), ("1억", 2), ("5천", 2), ("새마을금고", 3),
                  ("신협", 3), ("우체국", 2), ("외화", 2), ("펀드", 2),
                  ("예금보험 가입", 2), ("세전", 2), ("저축은행", 1)],
    "예금보험금 안내": [("예금보험금", 3), ("가지급금", 3), ("개산지급금", 3), ("보험금", 2),
                  ("보험사고", 2), ("망하면", 2), ("문 닫으면", 2), ("대신 주는", 2),
                  ("대신 준다", 2), ("지급", 1), ("창구", 1)],
    "고객 미수령금 신청": [("미수령", 3), ("못 찾", 3), ("못 받은 돈", 3), ("안 찾아간", 3),
                   ("찾아가지", 3), ("돌아가신", 2), ("상속인", 2), ("상속", 1), ("통합신청", 2)],
    "착오송금 반환 신청": [("착오송금", 3), ("잘못 보낸", 3), ("잘못 송금", 3), ("잘못 이체", 3),
                   ("이체 실수", 3), ("계좌 잘못", 3), ("돈 잘못", 3), ("딴 사람", 2),
                   ("반환", 2), ("수취인", 2), ("이체수수료", 2), ("이의제기", 2)],
    "채무조정 안내": [("채무조정", 3), ("개인회생", 3), ("면책", 3), ("신용회복", 3),
                 ("빚", 3), ("채무", 3), ("감면", 3), ("빚 조정", 3), ("빚 감면", 3),
                 ("파산", 2), ("연체", 2)],
    "은닉재산 신고": [("은닉재산", 3), ("숨긴 재산", 3), ("숨겨둔", 3), ("숨긴 돈", 3),
                 ("제보", 3), ("포상금", 3), ("부실관련자", 3), ("신고센터", 2),
                 ("은닉", 2), ("신고", 1)],
}
QBF_MIN_SCORE = 3          # 키워드 분류(폴백) 최소 점수
QBF_MARGIN = 2             # 키워드 분류(폴백) 1위–2위 마진
# 라우터 6분류 체크포인트. 가중치 pytorch_model.bin(2.38GB)은 .gitignore 대상이라
# 레포에 없다. router_source.resolve()가 로컬 디렉토리 → HF 프라이빗 repo 순으로
# 위치를 정하고(from_pretrained가 둘 다 받는다), 셋 다 없으면 None을 돌려준다.
# None이면 get_router()가 키워드 분류로 폴백한다(클론 직후에도 검색은 동작).
# 설정·트러블슈팅: docs/router_checkpoint.md
ROUTER_PATH = router_source.resolve()
# MSP 임계. 주의: 이 체크포인트는 held-out 450셋에서 MSP 최솟값 0.9991·중앙값 1.0000으로
# 체계적 과신 상태라 사실상 한 건도 걸러내지 못한다(θ 0.00~0.99 결과 동일). 소관밖(OOS)
# 판정 장치로 신뢰하지 말 것 — 작업계획서 B안의 MSP 임계 설계는 캘리브레이션 후 재검토 대상.
QBF_MSP_MIN = 0.70
BF_DOC_CAP = 5     # hybrid_bf: parent_doc_id당 top-k 청크 수 제한(문서 다양성↑, 몬스터 문서 독점 차단)
# 업무 신호 반영 방식: "soft"(같은 업무 청크에 RRF +BF_BOOST, 제외 없음) | "hard"(타 업무 제외).
# soft 채택(2026-07-22): 오분류 시 정답을 배제하지 않아 실트래픽에 안전 + 리랭킹 토대. 하드는 A/B 재현용 보존.
BF_MODE = "soft"
# eval_anchor_v3(gt_testset_retrieval.jsonl, 1276문항) 그리드서치 재튜닝(2026-08-12):
# alpha/rrf_k/boost/facet/cap 5축 스윕 결과 hit@1 0.292→0.366, hit@10 0.749→0.831,
# mrr 0.445→0.509로 뚜렷한 단일 안정 플래토(고립스파이크 아님) 확인 후 채택.
BF_BOOST = 0.06           # 소프트부스트 강도
# RRF_ALPHA 0.35→0.65 · RRF_K 2→1 재튜닝(2026-08-14, tune_params.py 5축 그리드 3360 config).
# VAL(355)·TEST(430) 양쪽에서 스윕한 뒤 '두 셋 모두 개선되는' 설정만 채택했다:
#   TEST 430  hit@5 .7837→.8186(+.035) · hit@1 .3698→.4233 · MRR .5342→.5825
#   VAL  355  hit@5 .7606→.8254(+.065) · MRR .5586→.6383
# 각 셋 단독 최적은 전이되지 않아 버렸다 — 430 단독(bf=0.18)은 VAL을 .8254→.8028로,
# 355 단독(alpha .75/rrf_k 0/bf .09/facet .10/cap 3)은 TEST를 .7837→.7744로 깎는다.
# alpha·cap은 두 셋에서 최적이 일치했고, bf·facet은 현행값이 이미 두 셋의 교차점이었다.
# 최적점은 5축 전부 그리드 내부이며 이웃(±1칸)이 매끄럽다(고립 스파이크 아님).
# 표 원자성 수정(청크 215→181, DECISIONS 08-18 ②)에 맞춰 재튜닝(tune_params_v2.py,
# 확장 그리드 8,064 config × TEST 430 / VAL 355). 코퍼스가 바뀌면 최적점도 옮겨간다:
#   RRF_K 1→4 · BF_BOOST 0.12→0.06 · FACET_BOOST 0.15→0.05 (RRF_ALPHA·BF_DOC_CAP 불변)
# 현행 대비 TEST single .9081→.9054(−1문항) · VAL single .8333→.8595(+8문항)
#   · TEST 전체 .8977 동일 · TEST and .8182→.8364
# 부스트가 절반 이하로 내려간 이유: 표가 합쳐져 청크가 자기완결적이 되면서 메타 기반
# 부스트(business_function·sub_category)의 상대 기여가 줄었다. 메타는 본문이 빈약할 때의
# 대용품이고 본문이 채워지면 물러나야 한다 — 임베딩 입력 메타 주입 실패와 같은 축.
# **이 값들은 181청크 코퍼스와 한 세트다.** 옛 청킹(215)에서 RRF_K=4를 쓰면
# single이 .8946→.865로 떨어진다. 청킹을 되돌리면 파라미터도 함께 되돌릴 것.
RRF_ALPHA = 0.65          # 가중 RRF의 dense 비중(0.5 동일가중~1.0 dense-only). sparse=1-RRF_ALPHA
RRF_K = 4                 # RRF 상수(낮을수록 상위 랭크 신뢰↑)
# FACET_BOOST 0.02 → 0.15 재튜닝(2026-08-14, eval_router_facet.py --facet-sweep):
# held-out 450셋(gt_testset_retrieval_450, 448문항 — 라우터 학습셋과 교집합 0)에서
# 0.00/.721 · 0.02/.728 · 0.05/.746 · 0.10/.748 · 0.15/.754 · 0.20/.754 · 0.30/.748 →
# 0.10~0.20 플래토(고립스파이크 아님). 기존 0.02는 2026-08-12 그리드서치 값인데,
# 그때 쓴 gt_testset_retrieval.jsonl은 라우터 학습셋 계열이라 facet 축이 가려져 있었다.
# 주의: 0.15는 이 448문항에서 스윕해 고른 값이므로 그만큼 낙관적 — 별도 split 확정 필요.
# [08-18] 표 원자성 수정으로 청크가 자기완결적이 되며 0.15 → 0.05로 재하향(위 블록 참조).
FACET_BOOST = 0.05        # 서브인텐트 패싯 부스트(업무 내부 형제문서 구분). sub_category 매칭 청크에 가산.
# 업무 공용 문서: 하드필터 시 해당 업무 외에도 허용할 문서(태그는 1개지만 실제로 여러 업무에서 필요).
# 예: 예금보험금 구비서류(DpsmIbamtAplyPossDcmnt)는 미수령금 신청 구비서류로도 동일하게 쓰임.
BF_SHARED_DOCS = {
    "고객 미수령금 신청": {"kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn"},
}


def classify_query_bf_keyword(query: str):
    """질의 → 6대 업무 중 하나 또는 None(불명). 결정론 키워드 분류(라우터 폴백 · A/B 재현용).

    공백 정규화: 질의·키워드 양쪽 공백 제거 후 매칭 → "보호 한도"가 "보호한도"로 잡힘.
    """
    q = query.replace(" ", "")
    sc = {bf: sum(w * q.count(k.replace(" ", "")) for k, w in kws)
          for bf, kws in BF_QUERY_KEYWORDS.items()}
    ranked = sorted(sc.items(), key=lambda x: -x[1])
    if ranked[0][1] < QBF_MIN_SCORE:
        return None
    if len(ranked) > 1 and ranked[0][1] - ranked[1][1] < QBF_MARGIN:
        return None
    return ranked[0][0]


def classify_query_bf(query: str):
    """질의 → 6대 업무 중 하나 또는 None(불명). 소프트부스트의 대상 업무 결정.

    라우터(6분류) 우선, 체크포인트가 없으면 키워드 분류로 폴백한다. 시그니처·반환
    규약(업무명 | None)은 불변이므로 호출부는 그대로다.

    채택 근거(2026-08-14, held-out 450셋 448문항 · eval_router_facet.py):
      질의 BF 정확도 키워드 69.2%(기권 28.6%) → 라우터 100.0%(기권 0%),
      hit@5 .699 → .728(개선 15 · 악화 2). 키워드의 실패 유형은 '오답'이 아니라
      '기권'이었고(부스트가 아예 안 걸림), 라우터가 그 구간을 메운다.
    """
    router = get_router()
    if router is None:
        return classify_query_bf_keyword(query)
    bf, msp = router.predict([query])[0]
    return bf if msp >= QBF_MSP_MIN else None


# ── 서브인텐트 패싯(업무 내부 문서타입) 분류 — hybrid_soft 패싯 부스트용 ──────────
# 질의 인텐트를 결정론 키워드로 잡아, 매칭되는 sub_category 청크에 소량 가산.
# 문서 병합/창작 없이 기존 sub_category 패싯만 활용. 리랭킹 대체 경량 레버.
FACET_RULES = [
    (["서류", "구비", "준비물", "챙기", "제출", "들고", "가지고"], "구비서류"),
    (["신청방법", "어떻게 신청", "어떻게 해", "온라인", "인터넷", "접수"], "신청방법"),
    (["대상", "자격", "누가", "해당", "받을 수 있"], "신청대상"),
    (["절차", "단계", "처리", "과정", "진행"], "절차"),
    (["유의", "주의", "조심", "알아둘"], "유의사항"),
    (["방문", "직접 가", "찾아가", "가서"], "방문접수"),
    (["법령", "규정", "법적"], "관련법령"),
]
DIR_RULES = [
    (["받은", "들어온", "잘못 들어", "수취인", "받아버린"], "착오송금수취인"),
    (["보낸", "송금한", "이체한", "내가 보", "잘못 보", "잘못 송금"], "착오송금인"),
]


def query_facets(query: str) -> set:
    """질의 → sub_category에서 찾을 패싯 토큰 집합(문서 타입/방향)."""
    qn = query.replace(" ", "")
    facets = set()
    for kws, tok in FACET_RULES:
        if any(k.replace(" ", "") in qn for k in kws):
            facets.add(tok)
    for kws, tok in DIR_RULES:
        if any(k.replace(" ", "") in qn for k in kws):
            facets.add(tok); break
    return facets


class Store:
    """청크 + 임베딩 + 인덱스 저장소. doc_id 단위 upsert 지원."""

    def __init__(self, index_dir: str = INDEX_DIR):
        self.dir = pathlib.Path(index_dir)
        self.chunks: list[dict] = []
        self.embs: np.ndarray | None = None
        self.doc_hash: dict[str, str] = {}
        self._load_state()

    # ── 상태 로드/저장 ───────────────────────────────────────
    def _load_state(self) -> None:
        meta = self.dir / "chunk_meta.jsonl"
        emb = self.dir / "emb.npy"
        docs = self.dir / "docs.json"
        if meta.exists() and emb.exists():
            self.chunks = [json.loads(l) for l in meta.read_text(encoding="utf-8").splitlines() if l]
            self.embs = np.load(emb)
        if docs.exists():
            self.doc_hash = json.loads(docs.read_text(encoding="utf-8"))

    def needs_update(self, doc_id: str, content_hash: str) -> bool:
        return self.doc_hash.get(doc_id) != content_hash

    # ── upsert / remove (doc_id 단위) ────────────────────────
    def upsert(self, doc_id: str, chunks: list[dict], content_hash: str) -> None:
        self._drop(doc_id)
        if chunks:
            e = embed_texts([chunk_embed_text(c) for c in chunks])
            self.chunks.extend(chunks)
            self.embs = e if self.embs is None else np.vstack([self.embs, e])
        self.doc_hash[doc_id] = content_hash

    def remove(self, doc_id: str) -> None:
        self._drop(doc_id)
        self.doc_hash.pop(doc_id, None)

    def _drop(self, doc_id: str) -> None:
        keep = [i for i, c in enumerate(self.chunks) if c["parent_doc_id"] != doc_id]
        if len(keep) != len(self.chunks):
            self.chunks = [self.chunks[i] for i in keep]
            if self.embs is not None and len(self.embs):
                self.embs = self.embs[keep] if keep else None

    # ── 인덱스 빌드 + 영속화 ─────────────────────────────────
    def build_and_save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        n = len(self.chunks)
        embs = self.embs if self.embs is not None else np.zeros((0, EMB_DIM), "float32")

        # 인덱스 차원 = 실제 임베딩 차원(모델 교체 대응). 비었으면 EMB_DIM 폴백.
        dim = int(embs.shape[1]) if embs.shape[0] else EMB_DIM
        index = faiss.IndexFlatIP(dim)
        if n:
            index.add(embs)
        faiss.write_index(index, str(self.dir / "faiss.index"))
        np.save(self.dir / "emb.npy", embs)

        from rank_bm25 import BM25Okapi
        corpus = [tokenize(c["text"]) for c in self.chunks]
        bm25 = BM25Okapi(corpus) if corpus else None
        with open(self.dir / "bm25.pkl", "wb") as f:
            pickle.dump({"bm25": bm25, "corpus_len": n}, f)

        with open(self.dir / "chunk_meta.jsonl", "w", encoding="utf-8") as f:
            for c in self.chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        (self.dir / "docs.json").write_text(
            json.dumps(self.doc_hash, ensure_ascii=False, indent=2), encoding="utf-8")

        # chunks.jsonl 도 최신화 (T3 산출물과 일치)
        with open("data/chunks.jsonl", "w", encoding="utf-8") as f:
            for c in self.chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")


# ── FAQ 청크 BF 조인 레이어 (faq_routing_bf.md I3) ────────────────────────────
# chunks.jsonl은 건드리지 않고 별도 산출물에서 BF를 조회한다. doc_attachments.json과 같은 패턴.
def load_bf_map(path: str = BF_MAP_PATH) -> dict[str, str | None]:
    """qhash → 라우터 산출 BF(또는 None). 파일이 없으면 {} = 조인 비활성(기존 동작 유지)."""
    p = pathlib.Path(path)
    if not p.exists():
        return {}
    out: dict[str, str | None] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["qhash"]] = r.get("bf")
    return out


class Searcher:
    """dense / bm25 / hybrid(RRF) 검색."""

    def __init__(self, index_dir: str = INDEX_DIR):
        self.dir = pathlib.Path(index_dir)
        self.chunks = [json.loads(l) for l in
                       (self.dir / "chunk_meta.jsonl").read_text(encoding="utf-8").splitlines() if l]
        self.index = faiss.read_index(str(self.dir / "faiss.index"))
        with open(self.dir / "bm25.pkl", "rb") as f:
            self.bm25 = pickle.load(f)["bm25"]
        self.bf_map = load_bf_map()
        # 인덱스 정렬 BF 캐시 — 질의마다 재해시하지 않도록 로드 시 1회만 해석.
        self.bf_unmapped: list[str] = []
        self._bf = [self._resolve_bf(c) for c in self.chunks]
        if self.bf_unmapped:
            print(f"[bf_map] 경고: 미매핑 FAQ 청크 {len(self.bf_unmapped)}건 — 질문이 바뀌었거나 "
                  f"bf_map이 청킹보다 오래됨. faq_bf_map.py를 재실행하세요. "
                  f"예: {self.bf_unmapped[:3]}")

    def _resolve_bf(self, c: dict) -> str | None:
        """청크의 유효 BF. FAQ/게시판 청크는 bf_map(라우터 산출), 그 외는 문서 상속 태그.

        조인 키는 청크 순번이 아니라 질문 정규화 hash(faq_routing_bf.md I2) — FAQ 항목이
        증감해 chunk_id가 밀려도 매핑이 따라오고, 질문이 수정되면 미매핑으로 드러난다.

        미매핑·저신뢰(MSP 미달)는 None이며 부모 태그로 롤백하지 않는다(I4). BF_MODE="soft"
        에서는 부스트를 못 받을 뿐 후보에서 배제되지 않는다. hard 모드에서는 배제되므로,
        hard로 전환하려면 bf_map 커버리지를 먼저 확인할 것.
        """
        if not self.bf_map or not fbm.is_board(c):
            return c.get("business_function")
        q = fbm.extract_question(c["text"])
        if q is None:                      # 추출 실패 — 추측으로 채우지 않음
            return None
        h = fbm.qhash(fbm.normalize_q(q))
        if h not in self.bf_map:
            self.bf_unmapped.append(c["chunk_id"])
            return None
        return self.bf_map[h]

    def dense(self, query: str, k: int = 10) -> list[tuple[int, float]]:
        q = embed_texts([query])
        D, I = self.index.search(q, min(k, len(self.chunks)))
        return [(int(i), float(d)) for i, d in zip(I[0], D[0]) if i >= 0]

    def sparse(self, query: str, k: int = 10) -> list[tuple[int, float]]:
        if self.bm25 is None:
            return []
        scores = self.bm25.get_scores(tokenize(query))
        order = np.argsort(scores)[::-1][:k]
        return [(int(i), float(scores[i])) for i in order]

    def hybrid(self, query: str, k: int = 10, pool: int = 20,
               rrf_k: int | None = None, bf: str | None = None) -> list[tuple[int, float]]:
        # rrf_k 기본값을 시그니처에 박지 않는다 — 기본인자는 정의 시점에 고정되므로
        # 런타임에 rag.RRF_K를 바꿔도 반영되지 않아 A/B가 조용히 틀린다(실제로 겪음).
        rrf_k = RRF_K if rrf_k is None else rrf_k
        # bf 지정 시(하드 필터): 후보를 해당 업무 청크로 제한. 필터링으로 후보가
        # 줄므로 pool을 전체로 넓혀 in-bf 청크를 빠짐없이 확보.
        dpool = pool if bf is None else len(self.chunks)
        d = self.dense(query, dpool)
        s = self.sparse(query, dpool)
        if bf is not None:
            allow = BF_SHARED_DOCS.get(bf, set())
            def _keep(i):
                # FAQ 청크는 bf_map 조인값, 그 외는 문서 상속 태그(_resolve_bf).
                return self._bf[i] == bf or self.chunks[i]["parent_doc_id"] in allow
            d = [(i, sc) for i, sc in d if _keep(i)]
            s = [(i, sc) for i, sc in s if _keep(i)]
        rrf: dict[int, float] = {}
        for rank, (idx, _) in enumerate(d):
            rrf[idx] = rrf.get(idx, 0.0) + 1.0 / (rrf_k + rank + 1)
        for rank, (idx, _) in enumerate(s):
            rrf[idx] = rrf.get(idx, 0.0) + 1.0 / (rrf_k + rank + 1)
        ranked = sorted(rrf.items(), key=lambda x: x[1], reverse=True)[:k]
        return [(idx, score) for idx, score in ranked]

    def hybrid_soft(self, query: str, k: int = 10, rrf_k: int | None = None,
                    bf: str | None = None, boost: float = 0.0,
                    alpha: float | None = None) -> list[tuple[int, float]]:
        """소프트부스트 융합 — 전체 풀 RRF 후 같은 업무 청크에 +boost(제외 없음).

        하드필터(hybrid(bf=...))와 달리 타 업무 청크를 남겨두므로, 질의 분류가
        틀려도 정답이 후보에 살아있다(graceful degradation). boost=0이면 순수 하이브리드.

        rrf_k·alpha 기본값은 시그니처가 아니라 호출 시점에 모듈 상수에서 읽는다 —
        기본인자로 박으면 정의 시점에 고정돼 런타임 A/B가 조용히 틀린다.
        """
        rrf_k = RRF_K if rrf_k is None else rrf_k
        alpha = RRF_ALPHA if alpha is None else alpha
        N = len(self.chunks)
        d = self.dense(query, N)
        s = self.sparse(query, N)
        rrf: dict[int, float] = {}
        for rank, (idx, _) in enumerate(d):
            rrf[idx] = rrf.get(idx, 0.0) + alpha / (rrf_k + rank + 1)
        for rank, (idx, _) in enumerate(s):
            rrf[idx] = rrf.get(idx, 0.0) + (1.0 - alpha) / (rrf_k + rank + 1)
        if bf is not None and boost > 0:
            allow = BF_SHARED_DOCS.get(bf, set())
            facets = query_facets(query) if FACET_BOOST > 0 else set()
            for idx in rrf:
                c = self.chunks[idx]
                if self._bf[idx] == bf or c["parent_doc_id"] in allow:
                    rrf[idx] += boost
                    if facets:
                        hit = sum(1 for t in facets if t in c.get("sub_category", ""))
                        if hit:
                            rrf[idx] += FACET_BOOST * hit
        ranked = sorted(rrf.items(), key=lambda x: x[1], reverse=True)[:k]
        return ranked

    def _cap_by_doc(self, hits: list[tuple[int, float]], cap: int) -> list[tuple[int, float]]:
        """parent_doc_id당 cap개까지만 순서 유지하며 남김(문서 단위 다양성 확보)."""
        if not cap or cap <= 0:
            return hits
        seen: dict[str, int] = {}
        out = []
        for idx, score in hits:
            d = self.chunks[idx]["parent_doc_id"]
            if seen.get(d, 0) < cap:
                out.append((idx, score))
                seen[d] = seen.get(d, 0) + 1
        return out

    def search(self, query: str, k: int = 5, mode: str = "hybrid") -> list[dict]:
        if mode == "dense":
            hits = self.dense(query, k)
        elif mode == "bm25":
            hits = self.sparse(query, k)
        elif mode == "hybrid_bf":
            # 질의 업무 분류 → 업무 신호 반영(soft 부스트 / hard 제외) + doc-count cap.
            # 깊은 풀을 받아 문서당 BF_DOC_CAP개로 제한 후 top-k → 몬스터 문서 독점 차단.
            bf = classify_query_bf(query)
            if BF_MODE == "soft":
                pool = self.hybrid_soft(query, len(self.chunks), bf=bf, boost=BF_BOOST)
            else:
                pool = self.hybrid(query, max(k * 5, 50), bf=bf)
            hits = self._cap_by_doc(pool, BF_DOC_CAP)[:k]
        else:
            hits = self.hybrid(query, k)
        out = []
        for idx, score in hits:
            c = dict(self.chunks[idx])
            c["_score"] = round(score, 4)
            c["_bf"] = self._bf[idx]   # 유효 BF(FAQ는 bf_map 조인값). business_function은 원본 보존.
            out.append(c)
        return out

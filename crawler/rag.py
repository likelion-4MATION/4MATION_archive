"""RAG 검색 공용 모듈 — 임베딩 · dense(FAISS) · BM25(kiwi) · 하이브리드(RRF).

- 임베딩: sentence-transformers `jhgan/ko-sroberta-multitask` (로컬 한국어 SBERT, 768d).
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

MODEL_NAME = "BAAI/bge-m3"
INDEX_DIR = "data/index"
EMB_DIM = 1024   # bge-m3 임베딩 차원(모델 교체 시 갱신). build 시 실제 임베딩 차원으로 자동 보정됨.

_model = None
_kiwi = None


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
QBF_MIN_SCORE = 3
QBF_MARGIN = 2
BF_DOC_CAP = 1     # hybrid_bf: parent_doc_id당 top-k 청크 수 제한(문서 다양성↑, 몬스터 문서 독점 차단)
# 업무 신호 반영 방식: "soft"(같은 업무 청크에 RRF +BF_BOOST, 제외 없음) | "hard"(타 업무 제외).
# soft 채택(2026-07-22): 오분류 시 정답을 배제하지 않아 실트래픽에 안전 + 리랭킹 토대. 하드는 A/B 재현용 보존.
BF_MODE = "soft"
# bge-m3 재튜닝(2026-07-22): 강한 dense에 맞춰 부스트↓·dense가중↑ (eval_rrf_tune A/B, A안).
BF_BOOST = 0.005          # 소프트부스트 강도(과보정 방지: 0.02→0.005)
RRF_ALPHA = 0.6           # 가중 RRF의 dense 비중(0.5 동일가중~1.0 dense-only). sparse=1-RRF_ALPHA
RRF_K = 5                 # RRF 상수(낮을수록 상위 랭크 신뢰↑). bge-m3 스윕 최적값(60→5).
# 업무 공용 문서: 하드필터 시 해당 업무 외에도 허용할 문서(태그는 1개지만 실제로 여러 업무에서 필요).
# 예: 예금보험금 구비서류(DpsmIbamtAplyPossDcmnt)는 미수령금 신청 구비서류로도 동일하게 쓰임.
BF_SHARED_DOCS = {
    "고객 미수령금 신청": {"kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn"},
}


def classify_query_bf(query: str):
    """질의 → 6대 업무 중 하나 또는 None(불명). 하드 필터의 대상 업무 결정.

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


class Searcher:
    """dense / bm25 / hybrid(RRF) 검색."""

    def __init__(self, index_dir: str = INDEX_DIR):
        self.dir = pathlib.Path(index_dir)
        self.chunks = [json.loads(l) for l in
                       (self.dir / "chunk_meta.jsonl").read_text(encoding="utf-8").splitlines() if l]
        self.index = faiss.read_index(str(self.dir / "faiss.index"))
        with open(self.dir / "bm25.pkl", "rb") as f:
            self.bm25 = pickle.load(f)["bm25"]

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
               rrf_k: int = RRF_K, bf: str | None = None) -> list[tuple[int, float]]:
        # bf 지정 시(하드 필터): 후보를 해당 업무 청크로 제한. 필터링으로 후보가
        # 줄므로 pool을 전체로 넓혀 in-bf 청크를 빠짐없이 확보.
        dpool = pool if bf is None else len(self.chunks)
        d = self.dense(query, dpool)
        s = self.sparse(query, dpool)
        if bf is not None:
            allow = BF_SHARED_DOCS.get(bf, set())
            def _keep(i):
                c = self.chunks[i]
                return c.get("business_function") == bf or c["parent_doc_id"] in allow
            d = [(i, sc) for i, sc in d if _keep(i)]
            s = [(i, sc) for i, sc in s if _keep(i)]
        rrf: dict[int, float] = {}
        for rank, (idx, _) in enumerate(d):
            rrf[idx] = rrf.get(idx, 0.0) + 1.0 / (rrf_k + rank + 1)
        for rank, (idx, _) in enumerate(s):
            rrf[idx] = rrf.get(idx, 0.0) + 1.0 / (rrf_k + rank + 1)
        ranked = sorted(rrf.items(), key=lambda x: x[1], reverse=True)[:k]
        return [(idx, score) for idx, score in ranked]

    def hybrid_soft(self, query: str, k: int = 10, rrf_k: int = RRF_K,
                    bf: str | None = None, boost: float = 0.0,
                    alpha: float = RRF_ALPHA) -> list[tuple[int, float]]:
        """소프트부스트 융합 — 전체 풀 RRF 후 같은 업무 청크에 +boost(제외 없음).

        하드필터(hybrid(bf=...))와 달리 타 업무 청크를 남겨두므로, 질의 분류가
        틀려도 정답이 후보에 살아있다(graceful degradation). boost=0이면 순수 하이브리드.
        """
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
            for idx in rrf:
                c = self.chunks[idx]
                if c.get("business_function") == bf or c["parent_doc_id"] in allow:
                    rrf[idx] += boost
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
            out.append(c)
        return out

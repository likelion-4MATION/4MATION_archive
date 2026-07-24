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

MODEL_NAME = "jhgan/ko-sroberta-multitask"
INDEX_DIR = "data/index"
EMB_DIM = 768

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

        index = faiss.IndexFlatIP(EMB_DIM)
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
               rrf_k: int = 60, bf: str | None = None) -> list[tuple[int, float]]:
        # bf 지정 시(하드 필터): 후보를 해당 업무 청크로 제한. 필터링으로 후보가
        # 줄므로 pool을 전체로 넓혀 in-bf 청크를 빠짐없이 확보.
        dpool = pool if bf is None else len(self.chunks)
        d = self.dense(query, dpool)
        s = self.sparse(query, dpool)
        if bf is not None:
            d = [(i, sc) for i, sc in d if self.chunks[i].get("business_function") == bf]
            s = [(i, sc) for i, sc in s if self.chunks[i].get("business_function") == bf]
        rrf: dict[int, float] = {}
        for rank, (idx, _) in enumerate(d):
            rrf[idx] = rrf.get(idx, 0.0) + 1.0 / (rrf_k + rank + 1)
        for rank, (idx, _) in enumerate(s):
            rrf[idx] = rrf.get(idx, 0.0) + 1.0 / (rrf_k + rank + 1)
        ranked = sorted(rrf.items(), key=lambda x: x[1], reverse=True)[:k]
        return [(idx, score) for idx, score in ranked]

    def search(self, query: str, k: int = 5, mode: str = "hybrid") -> list[dict]:
        if mode == "dense":
            hits = self.dense(query, k)
        elif mode == "bm25":
            hits = self.sparse(query, k)
        elif mode == "hybrid_bf":
            # 하드 필터: 질의 업무 분류 → 해당 업무 청크로만 검색. 불명이면 전체(=hybrid).
            hits = self.hybrid(query, k, bf=classify_query_bf(query))
        else:
            hits = self.hybrid(query, k)
        out = []
        for idx, score in hits:
            c = dict(self.chunks[idx])
            c["_score"] = round(score, 4)
            out.append(c)
        return out

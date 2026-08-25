# -*- coding: utf-8 -*-
"""OOS 운영 저장소.

Streamlit 챗봇과 FastAPI 관리자 서버가 서로 다른 프로세스로 접근하므로 SQLite를 쓴다.
사용자 대화는 저장 전에 반드시 ``sanitize_report_payload`` 를 거치며, 안내처와 상담
정보는 게시·활성 상태인 값만 사용자 응답에 사용할 수 있다.
"""
from __future__ import annotations

import json
import pathlib
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any


BASE = pathlib.Path(__file__).resolve().parent
DB_PATH = BASE / "data" / "oos.sqlite3"

REFERRAL_STATUSES = {"draft", "published", "disabled"}
REPORT_STATUSES = ("신규", "검토 중", "해결", "중복", "재현 불가")
LINK_STATES = {"unknown", "ok", "bad"}

_URL_OK = re.compile(r"^https?://[^\s]+$", re.I)
_PHONE_OK = re.compile(r"^[\d\-()\s~,]+$")
_ROW_ID_OK = re.compile(r"^[a-z][a-z0-9_]{2,63}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _expiry(now: str | None = None) -> str:
    base = datetime.fromisoformat((now or utc_now()).replace("Z", "+00:00"))
    return (base + timedelta(days=30)).isoformat(timespec="seconds").replace("+00:00", "Z")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=10000")
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init_db() -> None:
    with _connect() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS referrals (
                row_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                org TEXT NOT NULL,
                required_triggers TEXT NOT NULL DEFAULT '[]',
                excluded_triggers TEXT NOT NULL DEFAULT '[]',
                positive_examples TEXT NOT NULL DEFAULT '[]',
                negative_examples TEXT NOT NULL DEFAULT '[]',
                message TEXT NOT NULL,
                url TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                hours TEXT NOT NULL DEFAULT '',
                evidence TEXT NOT NULL,
                last_verified_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                active INTEGER NOT NULL DEFAULT 0,
                link_state TEXT NOT NULL DEFAULT 'unknown',
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                actor TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS phone_guide (
                singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1),
                message TEXT NOT NULL,
                phone TEXT NOT NULL,
                hours TEXT NOT NULL,
                evidence TEXT NOT NULL,
                last_verified_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                active INTEGER NOT NULL DEFAULT 0,
                version INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                actor TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reports (
                report_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                report_path TEXT NOT NULL,
                target_message_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status_changed_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT '신규',
                assigned_to TEXT NOT NULL DEFAULT '',
                duplicate_of TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_reports_status_created
                ON reports(status, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_reports_expires ON reports(expires_at);

            CREATE TABLE IF NOT EXISTS report_notes (
                note_id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id TEXT NOT NULL REFERENCES reports(report_id) ON DELETE CASCADE,
                body TEXT NOT NULL,
                actor TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                action TEXT NOT NULL,
                version INTEGER NOT NULL,
                actor TEXT NOT NULL,
                at TEXT NOT NULL,
                snapshot TEXT NOT NULL
            );
            """
        )
        # 기존 POC DB도 그대로 올릴 수 있는 가벼운 스키마 마이그레이션.
        report_columns = {r["name"] for r in con.execute("PRAGMA table_info(reports)").fetchall()}
        if "duplicate_of" not in report_columns:
            con.execute("ALTER TABLE reports ADD COLUMN duplicate_of TEXT NOT NULL DEFAULT ''")


def _loads(value: str | None, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except (json.JSONDecodeError, TypeError):
        return default


def _referral_dict(row: sqlite3.Row | dict) -> dict:
    d = dict(row)
    for key in ("required_triggers", "excluded_triggers", "positive_examples", "negative_examples"):
        d[key] = _loads(d.get(key), [])
    d["active"] = bool(d.get("active"))
    return d


def _audit(con: sqlite3.Connection, entity_type: str, entity_id: str, action: str,
           version: int, actor: str, snapshot: dict) -> None:
    con.execute(
        "INSERT INTO audit_log(entity_type,entity_id,action,version,actor,at,snapshot) "
        "VALUES(?,?,?,?,?,?,?)",
        (entity_type, entity_id, action, version, actor, utc_now(),
         json.dumps(snapshot, ensure_ascii=False)),
    )


def _terms(value: Any) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        s = " ".join(str(item).split()).strip()
        if s and s not in out:
            out.append(s[:120])
    return out


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def triggers_match(query: str, required: list[str], excluded: list[str]) -> bool:
    q = _norm(query)
    return bool(required) and all(_norm(t) in q for t in required) \
        and not any(_norm(t) in q for t in excluded)


def validate_referral(row: dict, *, publishing: bool = False) -> list[str]:
    errors: list[str] = []
    row_id = (row.get("row_id") or "").strip()
    if not _ROW_ID_OK.fullmatch(row_id):
        errors.append("row_id는 영문 소문자로 시작하는 3~64자의 영문·숫자·밑줄이어야 합니다.")
    for key, label in (("title", "표시 제목"), ("org", "기관명"), ("message", "안내문"),
                       ("evidence", "공식 근거"), ("last_verified_at", "마지막 확인일")):
        if not str(row.get(key) or "").strip():
            errors.append(f"{label}이(가) 필요합니다.")
    url, phone = str(row.get("url") or "").strip(), str(row.get("phone") or "").strip()
    if not url:
        errors.append("URL이 필요합니다.")
    elif not _URL_OK.fullmatch(url):
        errors.append("URL은 http:// 또는 https://로 시작해야 합니다.")
    if phone and not _PHONE_OK.fullmatch(phone):
        errors.append("전화번호 형식이 올바르지 않습니다.")
    verified = str(row.get("last_verified_at") or "").strip()
    if verified:
        try:
            datetime.fromisoformat(verified.replace("Z", "+00:00"))
        except ValueError:
            errors.append("마지막 확인일은 ISO 날짜 형식이어야 합니다.")
    required = _terms(row.get("required_triggers"))
    positive = _terms(row.get("positive_examples"))
    negative = _terms(row.get("negative_examples"))
    if not required:
        errors.append("필수 트리거를 한 개 이상 입력하세요.")
    if not positive:
        errors.append("정상 발동 예시를 한 개 이상 입력하세요.")
    if not negative:
        errors.append("미발동 반례를 한 개 이상 입력하세요.")
    if publishing:
        excluded = _terms(row.get("excluded_triggers"))
        if positive and not all(triggers_match(x, required, excluded) for x in positive):
            errors.append("정상 예시 중 트리거 검증을 통과하지 못한 항목이 있습니다.")
        if negative and any(triggers_match(x, required, excluded) for x in negative):
            errors.append("반례 중 안내처가 발동하는 항목이 있습니다.")
        if row.get("link_state") != "ok":
            errors.append("링크 상태가 '정상'으로 확인된 안내처만 게시할 수 있습니다.")
    return errors


def referral_conflicts(row: dict) -> list[str]:
    """게시 행끼리 같은 예시에서 동시에 발동하는 충돌을 찾는다."""
    current_id = str(row.get("row_id") or "")
    required = _terms(row.get("required_triggers"))
    excluded = _terms(row.get("excluded_triggers"))
    examples = _terms(row.get("positive_examples"))
    conflicts = []
    for other in list_referrals(published_only=True):
        if other["row_id"] == current_id:
            continue
        cross = any(triggers_match(q, other["required_triggers"], other["excluded_triggers"])
                    for q in examples)
        reverse = any(triggers_match(q, required, excluded) for q in other["positive_examples"])
        if cross or reverse:
            conflicts.append(other["row_id"])
    return sorted(set(conflicts))


def list_referrals(*, published_only: bool = False) -> list[dict]:
    init_db()
    sql = "SELECT * FROM referrals"
    args: tuple = ()
    if published_only:
        sql += " WHERE status='published' AND active=1 AND link_state='ok'"
    sql += " ORDER BY updated_at DESC, row_id"
    with _connect() as con:
        return [_referral_dict(r) for r in con.execute(sql, args).fetchall()]


def get_referral(row_id: str, *, published_only: bool = False) -> dict | None:
    init_db()
    sql = "SELECT * FROM referrals WHERE row_id=?"
    if published_only:
        sql += " AND status='published' AND active=1 AND link_state='ok'"
    with _connect() as con:
        row = con.execute(sql, (row_id,)).fetchone()
    return _referral_dict(row) if row else None


def upsert_referral(row: dict, actor: str = "admin") -> dict:
    init_db()
    row = dict(row or {})
    row_id = str(row.get("row_id") or "").strip()
    existing = get_referral(row_id) if row_id else None
    requested_status = str(row.get("status") or (existing or {}).get("status") or "draft")
    if requested_status not in REFERRAL_STATUSES:
        return {"ok": False, "errors": ["상태는 draft/published/disabled 중 하나여야 합니다."]}
    publishing = requested_status == "published"
    normalized = {
        **(existing or {}), **row, "row_id": row_id,
        "title": str(row.get("title") or "").strip()[:100],
        "org": str(row.get("org") or "").strip()[:100],
        "required_triggers": _terms(row.get("required_triggers")),
        "excluded_triggers": _terms(row.get("excluded_triggers")),
        "positive_examples": _terms(row.get("positive_examples")),
        "negative_examples": _terms(row.get("negative_examples")),
        "message": str(row.get("message") or "").strip()[:1000],
        "url": str(row.get("url") or "").strip()[:1000],
        "phone": str(row.get("phone") or "").strip()[:100],
        "hours": str(row.get("hours") or "").strip()[:300],
        "evidence": str(row.get("evidence") or "").strip()[:1000],
        "last_verified_at": str(row.get("last_verified_at") or "").strip()[:40],
        "status": requested_status,
        "active": bool(row.get("active", (existing or {}).get("active", False))),
        "link_state": str(row.get("link_state") or (existing or {}).get("link_state") or "unknown"),
    }
    if normalized["link_state"] not in LINK_STATES:
        return {"ok": False, "errors": ["링크 상태가 올바르지 않습니다."]}
    errors = validate_referral(normalized, publishing=publishing)
    if publishing:
        conflicts = referral_conflicts(normalized)
        if conflicts:
            errors.append("기존 게시 행과 트리거가 충돌합니다: " + ", ".join(conflicts))
    if errors:
        return {"ok": False, "errors": errors}
    now = utc_now()
    version = int((existing or {}).get("version") or 0) + 1
    created = (existing or {}).get("created_at") or now
    with _connect() as con:
        con.execute(
            """INSERT INTO referrals(
                row_id,title,org,required_triggers,excluded_triggers,positive_examples,
                negative_examples,message,url,phone,hours,evidence,last_verified_at,status,
                active,link_state,version,created_at,updated_at,actor)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(row_id) DO UPDATE SET
                title=excluded.title,org=excluded.org,required_triggers=excluded.required_triggers,
                excluded_triggers=excluded.excluded_triggers,positive_examples=excluded.positive_examples,
                negative_examples=excluded.negative_examples,message=excluded.message,url=excluded.url,
                phone=excluded.phone,hours=excluded.hours,evidence=excluded.evidence,
                last_verified_at=excluded.last_verified_at,status=excluded.status,active=excluded.active,
                link_state=excluded.link_state,version=excluded.version,updated_at=excluded.updated_at,
                actor=excluded.actor""",
            (row_id, normalized["title"], normalized["org"],
             json.dumps(normalized["required_triggers"], ensure_ascii=False),
             json.dumps(normalized["excluded_triggers"], ensure_ascii=False),
             json.dumps(normalized["positive_examples"], ensure_ascii=False),
             json.dumps(normalized["negative_examples"], ensure_ascii=False), normalized["message"],
             normalized["url"], normalized["phone"], normalized["hours"], normalized["evidence"],
             normalized["last_verified_at"], normalized["status"], int(normalized["active"]),
             normalized["link_state"], version, created, now, actor),
        )
        # 같은 트랜잭션 안에서 다른 연결로 다시 읽지 않는다. 아직 commit 전이라 업데이트
        # 이전 행을 볼 수 있으므로, 방금 쓴 정규화 스냅샷을 감사 로그의 정본으로 사용한다.
        saved = {**normalized, "version": version, "created_at": created,
                 "updated_at": now, "actor": actor}
        _audit(con, "referral", row_id, "create" if not existing else "update", version, actor, saved)
    return {"ok": True, "referral": get_referral(row_id)}


def referral_for_query(row_id: str | None, query: str) -> dict | None:
    if not row_id:
        return None
    row = get_referral(row_id, published_only=True)
    if not row or not triggers_match(query, row["required_triggers"], row["excluded_triggers"]):
        return None
    return row


def referral_candidates() -> list[dict]:
    """OOS LLM에 줄 최소 정보. 연락처·안내문은 모델 입력에서도 제외한다."""
    return [{"row_id": r["row_id"], "title": r["title"],
             "required_triggers": r["required_triggers"],
             "excluded_triggers": r["excluded_triggers"]}
            for r in list_referrals(published_only=True)]


def validate_phone_guide(row: dict, *, publishing: bool = False) -> list[str]:
    errors = []
    for key, label in (("message", "안내 문구"), ("phone", "대표번호"),
                       ("hours", "운영시간"), ("evidence", "공식 근거"),
                       ("last_verified_at", "마지막 확인일")):
        if not str(row.get(key) or "").strip():
            errors.append(f"{label}이(가) 필요합니다.")
    if row.get("phone") and not _PHONE_OK.fullmatch(str(row["phone"]).strip()):
        errors.append("대표번호 형식이 올바르지 않습니다.")
    verified = str(row.get("last_verified_at") or "").strip()
    if verified:
        try:
            datetime.fromisoformat(verified.replace("Z", "+00:00"))
        except ValueError:
            errors.append("마지막 확인일은 ISO 날짜 형식이어야 합니다.")
    if publishing and not bool(row.get("active")):
        errors.append("게시할 상담 정보는 활성 상태여야 합니다.")
    return errors


def get_phone_guide(*, active_only: bool = False) -> dict | None:
    init_db()
    sql = "SELECT * FROM phone_guide WHERE singleton_id=1"
    if active_only:
        sql += " AND status='published' AND active=1"
    with _connect() as con:
        row = con.execute(sql).fetchone()
    if not row:
        return None
    d = dict(row)
    d["active"] = bool(d["active"])
    return d


def save_phone_guide(row: dict, actor: str = "admin") -> dict:
    init_db()
    old = get_phone_guide() or {}
    status = str(row.get("status") or old.get("status") or "draft")
    if status not in REFERRAL_STATUSES:
        return {"ok": False, "errors": ["상태는 draft/published/disabled 중 하나여야 합니다."]}
    data = {**old, **(row or {}), "status": status,
            "active": bool(row.get("active", old.get("active", False)))}
    for key, limit in (("message", 1000), ("phone", 100), ("hours", 300),
                       ("evidence", 1000), ("last_verified_at", 40)):
        data[key] = str(data.get(key) or "").strip()[:limit]
    errors = validate_phone_guide(data, publishing=status == "published")
    if errors:
        return {"ok": False, "errors": errors}
    version = int(old.get("version") or 0) + 1
    now = utc_now()
    with _connect() as con:
        con.execute(
            """INSERT INTO phone_guide(singleton_id,message,phone,hours,evidence,last_verified_at,
               status,active,version,updated_at,actor) VALUES(1,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(singleton_id) DO UPDATE SET message=excluded.message,phone=excluded.phone,
               hours=excluded.hours,evidence=excluded.evidence,last_verified_at=excluded.last_verified_at,
               status=excluded.status,active=excluded.active,version=excluded.version,
               updated_at=excluded.updated_at,actor=excluded.actor""",
            (data["message"], data["phone"], data["hours"], data["evidence"],
             data["last_verified_at"], status, int(data["active"]), version, now, actor),
        )
        saved = {**data, "version": version, "updated_at": now, "actor": actor}
        _audit(con, "phone_guide", "singleton", "update", version, actor, saved)
    return {"ok": True, "phone_guide": get_phone_guide()}


# 저장 전 개인정보 제거. 공식 연락처가 담긴 안내처에는 적용하지 않고 오류 신고 payload에만 쓴다.
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_RRN = re.compile(r"(?<!\d)\d{6}\s*-?\s*[1-4]\d{6}(?!\d)")
_CARD = re.compile(r"(?<!\d)(?:\d{4}[ -]?){3}\d{4}(?!\d)")
_PHONE = re.compile(r"(?<!\d)(?:01[016789]|0\d{1,2})[- .]?\d{3,4}[- .]?\d{4}(?!\d)")
_ACCOUNT = re.compile(r"(?<!\d)(?:\d[- ]?){9,14}\d(?!\d)")
_AUTH = re.compile(r"((?:인증번호|인증코드|otp)\s*[:：]?\s*)\d{4,8}", re.I)
_PASSWORD = re.compile(r"((?:비밀번호|패스워드|password|pw)\s*[:：]?\s*)\S+", re.I)
_SECRET_KEYS = re.compile(r"(?:api.?key|authorization|access.?token|refresh.?token|secret|환경변수|password)", re.I)


def mask_text(text: str) -> str:
    text = _PASSWORD.sub(r"\1[마스킹]", str(text))
    text = _AUTH.sub(r"\1[마스킹]", text)
    for regex, tag in ((_EMAIL, "[이메일 마스킹]"), (_RRN, "[주민번호 마스킹]"),
                       (_CARD, "[카드번호 마스킹]"), (_PHONE, "[전화번호 마스킹]"),
                       (_ACCOUNT, "[계좌번호 마스킹]")):
        text = regex.sub(tag, text)
    return text


def sanitize_report_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): sanitize_report_payload(v) for k, v in value.items()
                if not _SECRET_KEYS.search(str(k))}
    if isinstance(value, list):
        return [sanitize_report_payload(x) for x in value]
    if isinstance(value, tuple):
        return [sanitize_report_payload(x) for x in value]
    if isinstance(value, str):
        return mask_text(value)
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return mask_text(str(value))


def purge_expired(now: str | None = None) -> int:
    init_db()
    cutoff = now or utc_now()
    with _connect() as con:
        cur = con.execute("DELETE FROM reports WHERE expires_at<=?", (cutoff,))
        return int(cur.rowcount or 0)


def create_report(payload: dict, *, session_id: str, report_path: str,
                  target_message_id: str = "") -> dict:
    init_db()
    purge_expired()
    now, report_id = utc_now(), f"rpt_{uuid.uuid4().hex[:16]}"
    clean = sanitize_report_payload(payload or {})
    with _connect() as con:
        con.execute(
            """INSERT INTO reports(report_id,session_id,report_path,target_message_id,created_at,
               updated_at,status_changed_at,expires_at,status,assigned_to,duplicate_of,payload)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (report_id, session_id, report_path, target_message_id, now, now, now,
             _expiry(now), "신규", "", "", json.dumps(clean, ensure_ascii=False)),
        )
    return get_report(report_id) or {"report_id": report_id}


def _report_dict(row: sqlite3.Row | dict, *, include_payload: bool = True) -> dict:
    d = dict(row)
    if include_payload:
        d["payload"] = _loads(d.get("payload"), {})
    else:
        d.pop("payload", None)
    return d


def list_reports(*, status: str | None = None, query: str = "", limit: int = 100,
                 offset: int = 0) -> dict:
    init_db()
    purge_expired()
    where, args = [], []
    if status:
        where.append("status=?")
        args.append(status)
    if query:
        where.append("(report_id LIKE ? OR session_id LIKE ? OR duplicate_of LIKE ? OR payload LIKE ?)")
        term = f"%{query}%"
        args.extend([term, term, term, term])
    cond = " WHERE " + " AND ".join(where) if where else ""
    with _connect() as con:
        total = con.execute("SELECT COUNT(*) FROM reports" + cond, args).fetchone()[0]
        rows = con.execute(
            "SELECT * FROM reports" + cond + " ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*args, max(1, min(int(limit), 500)), max(0, int(offset))),
        ).fetchall()
    return {"total": total, "reports": [_report_dict(r, include_payload=False) for r in rows]}


def get_report(report_id: str) -> dict | None:
    init_db()
    purge_expired()
    with _connect() as con:
        row = con.execute("SELECT * FROM reports WHERE report_id=?", (report_id,)).fetchone()
        if not row:
            return None
        notes = [dict(x) for x in con.execute(
            "SELECT note_id,body,actor,created_at FROM report_notes WHERE report_id=? ORDER BY note_id",
            (report_id,),
        ).fetchall()]
    d = _report_dict(row)
    d["notes"] = notes
    return d


def update_report(report_id: str, *, status: str | None = None, assigned_to: str | None = None,
                  duplicate_of: str | None = None, note: str | None = None,
                  actor: str = "admin") -> dict:
    init_db()
    current = get_report(report_id)
    if not current:
        return {"ok": False, "errors": ["신고를 찾을 수 없습니다."]}
    if status is not None and status not in REPORT_STATUSES:
        return {"ok": False, "errors": ["허용되지 않은 처리 상태입니다."]}
    now = utc_now()
    new_status = status or current["status"]
    status_changed = now if new_status != current["status"] else current["status_changed_at"]
    assignee = current["assigned_to"] if assigned_to is None else str(assigned_to).strip()[:100]
    duplicate = (current.get("duplicate_of") or "") if duplicate_of is None \
        else str(duplicate_of).strip()[:100]
    if duplicate == report_id:
        return {"ok": False, "errors": ["자기 자신을 중복 신고의 기준으로 지정할 수 없습니다."]}
    if duplicate and not get_report(duplicate):
        return {"ok": False, "errors": ["기준 중복 신고를 찾을 수 없습니다."]}
    if new_status == "중복" and not duplicate:
        return {"ok": False, "errors": ["중복 상태에는 기준 신고 ID가 필요합니다."]}
    if new_status != "중복":
        duplicate = ""
    clean_note = mask_text(str(note or "").strip())[:2000]
    with _connect() as con:
        con.execute("UPDATE reports SET status=?,assigned_to=?,duplicate_of=?,updated_at=?,status_changed_at=? WHERE report_id=?",
                    (new_status, assignee, duplicate, now, status_changed, report_id))
        if clean_note:
            con.execute("INSERT INTO report_notes(report_id,body,actor,created_at) VALUES(?,?,?,?)",
                        (report_id, clean_note, actor, now))
    return {"ok": True, "report": get_report(report_id)}


def oos_stats() -> dict:
    init_db()
    purge_expired()
    with _connect() as con:
        by_status = {r["status"]: r["n"] for r in con.execute(
            "SELECT status,COUNT(*) AS n FROM reports GROUP BY status").fetchall()}
        due = con.execute("SELECT COUNT(*) FROM reports WHERE expires_at<=?",
                          (_expiry(utc_now()),)).fetchone()[0]
    return {"referrals": len(list_referrals()), "published_referrals": len(list_referrals(published_only=True)),
            "reports": sum(by_status.values()), "reports_by_status": by_status,
            "expiring_within_30d": due, "phone_guide_ready": bool(get_phone_guide(active_only=True))}


init_db()

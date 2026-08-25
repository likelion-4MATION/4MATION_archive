# -*- coding: utf-8 -*-
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "chatbot"), str(ROOT / "admin"), str(ROOT / "crawler")]

import oos_policy
import oos_store
import orchestrator
import qform_flow
from query_units import split_clauses


def fixed_result(text="답변"):
    return {"text": text, "sources": [], "confidence": 0.5, "route": "rag",
            "checks": {"ok": True, "flags": []}, "attachments": [],
            "_meta": {"latency_ms": 1}}


class OOSTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        oos_store.DB_PATH = pathlib.Path(self.tmp.name) / "oos.sqlite3"
        oos_store.init_db()

    def tearDown(self):
        self.tmp.cleanup()

    def referral(self, **override):
        row = {"row_id": "personal_rehabilitation", "title": "개인회생 신청처",
               "org": "공식 기관", "required_triggers": ["개인회생"],
               "excluded_triggers": ["예금보험공사 채무조정"],
               "positive_examples": ["개인회생 신청처를 알려줘"],
               "negative_examples": ["예금보험공사 채무조정 제도를 알려줘"],
               "message": "개인회생 신청은 등록된 공식 안내처를 확인해 주세요.",
               "url": "https://example.org/official", "phone": "", "hours": "",
               "evidence": "공식 안내 페이지", "last_verified_at": "2026-08-25",
               "status": "published", "active": True, "link_state": "ok"}
        row.update(override)
        return row

    def test_clause_split_preserves_order(self):
        self.assertEqual(split_clauses("보호한도를 알려주고 개인회생 신청처도 알려줘"),
                         ["보호한도를 알려주세요", "개인회생 신청처도 알려줘"])

    def test_masking_removes_personal_and_secret_values(self):
        payload = {"text": "홍길동 900101-1234567 010-1234-5678 a@b.com 계좌 123-456-789012",
                   "api_key": "do-not-store"}
        clean = oos_store.sanitize_report_payload(payload)
        self.assertNotIn("api_key", clean)
        self.assertNotIn("900101", clean["text"])
        self.assertNotIn("010-1234", clean["text"])
        self.assertNotIn("a@b.com", clean["text"])

    def test_only_published_active_referral_is_usable(self):
        saved = oos_store.upsert_referral(self.referral())
        self.assertTrue(saved["ok"])
        self.assertIsNotNone(oos_store.referral_for_query(
            "personal_rehabilitation", "개인회생 신청처를 알려줘"))
        disabled = self.referral(status="disabled", active=False)
        self.assertTrue(oos_store.upsert_referral(disabled)["ok"])
        self.assertIsNone(oos_store.referral_for_query(
            "personal_rehabilitation", "개인회생 신청처를 알려줘"))

    def test_unverified_link_cannot_be_published(self):
        saved = oos_store.upsert_referral(self.referral(link_state="unknown"))
        self.assertFalse(saved["ok"])
        self.assertTrue(any("정상" in e for e in saved["errors"]))

    def test_invalid_oos_json_falls_back_to_phone(self):
        decision = oos_policy.classify_oos("무엇을 해야 하나요", llm_call=lambda _: "not-json")
        self.assertEqual(decision["action"], "PHONE_GUIDE")

    def test_non_referral_row_id_is_rejected(self):
        raw = '{"action":"FAR_OOS","row_id":"made_up"}'
        decision = oos_policy.classify_oos("오늘 날씨 어때", llm_call=lambda _: raw)
        self.assertEqual(decision["action"], "PHONE_GUIDE")

    def test_referral_uses_registry_value_only(self):
        self.assertTrue(oos_store.upsert_referral(self.referral())["ok"])
        raw = '{"action":"REFERRAL","row_id":"personal_rehabilitation"}'
        decision = oos_policy.classify_oos("개인회생 신청처를 알려줘", llm_call=lambda _: raw)
        result = oos_policy.build_result(decision)
        self.assertEqual(result["text"], self.referral()["message"])
        self.assertEqual(result["referral"]["url"], self.referral()["url"])

    def test_far_oos_never_contains_phone_guide(self):
        raw = '{"action":"FAR_OOS","row_id":null}'
        result = oos_policy.build_result(oos_policy.classify_oos("오늘 날씨 어때", llm_call=lambda _: raw))
        self.assertEqual(result["_meta"]["action"], "FAR_OOS")
        self.assertIsNone(result["phone_guide"])

    def test_finance_adjacent_far_candidate_falls_back(self):
        raw = '{"action":"FAR_OOS","row_id":null}'
        decision = oos_policy.classify_oos("은행 인증 오류가 나요", llm_call=lambda _: raw)
        self.assertEqual(decision["action"], "PHONE_GUIDE")

    def test_orchestrator_queues_and_never_calls_rag_for_oos(self):
        flow = qform_flow.new_state()
        answer_calls = []

        def route(text):
            if "보호한도" in text:
                return {"triggered": True, "bf": "예금자보호제도", "scores": {},
                        "source": "test", "error": None}
            return {"triggered": False, "bf": None, "scores": {},
                    "source": "test", "error": None}

        def answer(text, bf, slots):
            answer_calls.append((text, bf))
            return fixed_result()

        ev = orchestrator.start_turn(
            flow, "보호한도를 알려주고 오늘 날씨도 알려줘", route_fn=route, answer_fn=answer,
            llm_call=lambda _: '{"action":"FAR_OOS","row_id":null}')
        self.assertEqual(ev["result"]["route"], "rag")
        self.assertEqual(len(flow["unit_queue"]), 1)
        nxt = orchestrator.next_unit(flow, answer_fn=answer,
                                     llm_call=lambda _: '{"action":"FAR_OOS","row_id":null}')
        self.assertEqual(nxt["result"]["_meta"]["action"], "FAR_OOS")
        self.assertEqual(len(answer_calls), 1)

    def test_all_clauses_are_routed_before_first_answer(self):
        flow = qform_flow.new_state()
        routed = []

        def route(text):
            routed.append(text)
            return {"triggered": False, "bf": None, "scores": {},
                    "source": "test", "error": None}

        orchestrator.start_turn(
            flow, "하나? 둘? 셋? 넷? 다섯?", route_fn=route,
            llm_call=lambda _: '{"action":"FAR_OOS","row_id":null}')
        self.assertEqual(len(routed), 5)
        self.assertEqual(len(flow["unit_queue"]), 4)

    def test_report_is_masked_and_has_30_day_expiry(self):
        row = oos_store.create_report({"user": "전화 010-1234-5678"}, session_id="s1",
                                      report_path="top_button")
        self.assertNotIn("010-1234-5678", row["payload"]["user"])
        self.assertGreater(row["expires_at"], row["created_at"])

    def test_duplicate_report_must_reference_existing_report(self):
        original = oos_store.create_report({"text": "원본"}, session_id="s1",
                                           report_path="top_button")
        duplicate = oos_store.create_report({"text": "유사"}, session_id="s2",
                                            report_path="natural_language")
        bad = oos_store.update_report(duplicate["report_id"], status="중복",
                                      duplicate_of="rpt_missing")
        self.assertFalse(bad["ok"])
        saved = oos_store.update_report(duplicate["report_id"], status="중복",
                                        duplicate_of=original["report_id"])
        self.assertTrue(saved["ok"])
        self.assertEqual(saved["report"]["duplicate_of"], original["report_id"])


if __name__ == "__main__":
    unittest.main()

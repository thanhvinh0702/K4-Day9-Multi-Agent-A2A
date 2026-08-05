from __future__ import annotations

import unittest
import json
import os
import tempfile
from pathlib import Path
from decimal import Decimal
from unittest.mock import patch

from src.config import LLMSettings
from src.contracts import CaseFactBundle
from src.llm import OpenRouterClient
from src.openrouter_policy import OpenRouterPolicyAgent
from src.policy import DeterministicPolicyAgent
from src.datastore import OlistDataStore
from src.resolver import resolve_case
from src.trace import TraceWriter
from src.utils import hours_between, is_after, money, unique
from src.verifier import normalize_llm_decision
from src.verifier import VerifierAgent


class UtilityTests(unittest.TestCase):
    def test_unique_is_stable(self) -> None:
        self.assertEqual(unique(["b", "a", "b", "c"]), ["b", "a", "c"])

    def test_money_rounds_half_up(self) -> None:
        self.assertEqual(money(Decimal("1.005")), 1.01)

    def test_hour_variance(self) -> None:
        self.assertEqual(
            hours_between("2018-03-31 15:23:33", "2018-03-28 00:00:00"),
            87.39,
        )

    def test_classification_uses_raw_timestamp(self) -> None:
        self.assertTrue(
            is_after("2018-01-01 00:00:01", "2018-01-01 00:00:00")
        )


class PolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = DeterministicPolicyAgent()
        self.customer = {"repeat_customer": False}
        self.order_seller = {
            "order_id": "order-1",
            "order_status": "delivered",
            "multi_item_order": False,
            "multi_seller_order": False,
            "multiple_categories": False,
            "late_handoff_seller_ids": [],
        }
        self.payment = {
            "payment_total": Decimal("100"),
            "payment_total_brl": 100.0,
            "split_payment": False,
            "reconciled": True,
            "freight_total_brl": 10.0,
        }
        self.delivery = {
            "delivered_late": False,
            "delivered_within_estimate": True,
        }

    def decide(self, status: str = "delivered") -> dict:
        self.order_seller["order_status"] = status
        return self.agent.decide(
            CaseFactBundle(
                case_id="EC_TEST",
                order_seller=self.order_seller,
                payment=self.payment,
                delivery=self.delivery,
                customer=self.customer,
            )
        )

    def test_canceled_has_priority_and_full_refund(self) -> None:
        self.delivery["delivered_late"] = True
        self.delivery["delivered_within_estimate"] = False
        result = self.decide("canceled")
        self.assertEqual(result["primary_issue"], "canceled_order_paid")
        self.assertEqual(result["recommended_refund_brl"], 100.0)

    def test_seller_delay(self) -> None:
        self.delivery.update({"delivered_late": True, "delivered_within_estimate": False})
        self.order_seller["late_handoff_seller_ids"] = ["seller-1"]
        result = self.decide()
        self.assertEqual(result["primary_issue"], "late_delivery_seller")
        self.assertEqual(result["responsible_parties"][0]["party_id"], "seller-1")

    def test_valid_split_payment(self) -> None:
        self.payment["split_payment"] = True
        result = self.decide()
        self.assertEqual(result["primary_issue"], "valid_split_payment")
        self.assertNotIn("verify_payment_allocation", result["actions"])

    def test_normalize_accepts_confidence_only_when_policy_matches(self) -> None:
        deterministic = self.decide()
        llm = {
            "primary_issue": deterministic["primary_issue"],
            "cause_code": deterministic["cause_code"],
            "responsible_parties": deterministic["responsible_parties"],
            "recommended_refund_brl": deterministic["recommended_refund_brl"],
            "primary_action": deterministic["actions"][0],
            "confidence": 1.4,
        }
        normalized, matched = normalize_llm_decision(deterministic, llm)
        self.assertTrue(matched)
        self.assertEqual(normalized["confidence"], 1.0)

    def test_normalize_rejects_wrong_llm_business_field(self) -> None:
        deterministic = self.decide()
        llm = {
            "primary_issue": "wrong",
            "cause_code": deterministic["cause_code"],
            "responsible_parties": deterministic["responsible_parties"],
            "recommended_refund_brl": deterministic["recommended_refund_brl"],
            "primary_action": deterministic["actions"][0],
            "confidence": 0.2,
        }
        normalized, matched = normalize_llm_decision(deterministic, llm)
        self.assertFalse(matched)
        self.assertEqual(normalized, deterministic)


class OpenRouterClientTests(unittest.TestCase):
    def test_missing_client_falls_back_without_error(self) -> None:
        agent = OpenRouterPolicyAgent(None)
        decision, reason = agent.propose("EC_TEST", {"order_status": "delivered"})
        self.assertIsNone(decision)
        self.assertEqual(reason, "missing_api_key_or_llm_disabled")
        self.assertEqual(agent.fallback_count, 1)

    def test_settings_accept_arbitrary_model_without_size_declaration(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OPENROUTER_API_KEY": "test-secret",
                "OPENROUTER_MODEL": "any-model-name",
                "OPENROUTER_PARAMETER_SIZE": "",
            },
            clear=True,
        ):
            settings = LLMSettings.from_env()
        self.assertEqual(settings.model, "any-model-name")
        self.assertEqual(settings.parameter_size, "unknown")

    def test_structured_review_contract_and_usage(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def read(self):
                content = json.dumps(
                    {
                        "primary_issue": "unsupported_late_claim",
                        "cause_code": "DELIVERY_WITHIN_ESTIMATE",
                        "responsible_parties": [],
                        "recommended_refund_brl": 0.0,
                        "primary_action": "reject_late_refund",
                        "confidence": 0.94,
                    }
                )
                return json.dumps(
                    {
                        "id": "gen-test",
                        "model": "qwen/qwen-2.5-7b-instruct",
                        "choices": [{"message": {"content": content}}],
                        "usage": {"prompt_tokens": 12, "completion_tokens": 8},
                    }
                ).encode()

        captured = {}

        def fake_transport(request, timeout):
            captured["body"] = json.loads(request.data.decode())
            captured["timeout"] = timeout
            return FakeResponse()

        settings = LLMSettings(
            enabled=True,
            api_key="test-secret",
            model="qwen/qwen-2.5-7b-instruct",
            parameter_size="7B",
            timeout_seconds=10,
            max_retries=0,
        )
        client = OpenRouterClient(settings, transport=fake_transport)
        result = client.decide_policy("EC_TEST", {"reconciled": True})
        self.assertEqual(result["primary_issue"], "unsupported_late_claim")
        self.assertEqual(client.call_count, 1)
        self.assertEqual(client.prompt_tokens, 12)
        self.assertEqual(captured["body"]["response_format"]["type"], "json_schema")


class EndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.store = OlistDataStore(cls.root / "data")

    def test_all_50_cases_and_complete_trace_lifecycle(self) -> None:
        inputs = sorted((self.root / "input" / "input").glob("EC_*.json"))
        self.assertEqual(len(inputs), 50)
        with tempfile.TemporaryDirectory() as temporary:
            trace_path = Path(temporary) / "trace.jsonl"
            with TraceWriter(trace_path) as trace:
                outputs = []
                for path in inputs:
                    case = json.loads(path.read_text(encoding="utf-8"))
                    output, info = resolve_case(
                        case, self.store, trace, OpenRouterPolicyAgent(None)
                    )
                    outputs.append(output)
                    self.assertTrue(info["llm_fallback"])
            events = [
                json.loads(line)
                for line in trace_path.read_text(encoding="utf-8").splitlines()
            ]
        self.assertEqual(len(outputs), 50)
        self.assertEqual(len(events), 50 * 13)
        for case_number in range(1, 51):
            case_id = f"EC_{case_number:03}"
            case_events = [event for event in events if event["case_id"] == case_id]
            assignments = {
                event.get("to_agent")
                for event in case_events
                if event["event"] == "handoff"
                and event.get("from_agent") == "coordinator"
            }
            self.assertEqual(
                assignments,
                {"order_seller_agent", "payment_agent", "delivery_agent"},
            )
            self.assertEqual(
                sum(event["event"] == "policy_comparison" for event in case_events),
                1,
            )

    def test_verifier_rejects_missing_required_item(self) -> None:
        path = self.root / "input" / "input" / "EC_001.json"
        case = json.loads(path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            with TraceWriter(Path(temporary) / "trace.jsonl") as trace:
                output, _ = resolve_case(
                    case, self.store, trace, OpenRouterPolicyAgent(None)
                )
        output["affected_entities"]["item_ids"].pop()
        with self.assertRaisesRegex(ValueError, "item IDs are incomplete"):
            VerifierAgent(self.store).verify_output(case, output)


if __name__ == "__main__":
    unittest.main()

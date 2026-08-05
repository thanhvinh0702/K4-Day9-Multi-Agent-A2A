"""The six LLM-facing agent roles. Each domain agent is bound to exactly one
tool from tools.py (tool_choice is forced), so the only thing the LLM
decides is how to shape the tool's already-correct result into the required
JSON. The Policy Agent works the same way against the deterministic
EC_POLICY_V2 engine (policy_rules.py).
"""
from __future__ import annotations

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from . import policy_rules
from .agent_runner import run_tool_agent
from .schemas import (
    CustomerFragment,
    DeliveryFragment,
    OrderProductFragment,
    PaymentFragment,
    PolicyFragment,
)
from .tools import (
    gather_case_facts,
    get_customer_context,
    get_delivery_analysis,
    get_order_product_context,
    get_payment_reconciliation,
)
from .trace_logger import TraceLogger

CUSTOMER_SYSTEM = (
    "Ban la Customer Agent trong he thong dieu tra khieu nai Olist. "
    "Nhiem vu duy nhat: goi tool get_customer_context voi claimed_order_id duoc giao "
    "de lay customer_unique_id va related_order_ids that. "
    "Khong tu suy doan hay bia gia tri. Sau khi co ket qua tool, tra ve dung cac truong "
    "theo schema yeu cau, giu nguyen gia tri tool tra ve."
)

ORDER_PRODUCT_SYSTEM = (
    "Ban la Order & Product Agent trong he thong dieu tra khieu nai Olist. "
    "Nhiem vu duy nhat: goi tool get_order_product_context voi claimed_order_id duoc giao "
    "de lay order/item/seller/product/category lien quan. "
    "Khong tu suy doan hay bia gia tri. Tra ve dung cac truong theo schema, "
    "giu nguyen gia tri tool tra ve."
)

PAYMENT_SYSTEM = (
    "Ban la Payment Agent trong he thong dieu tra khieu nai Olist. "
    "Nhiem vu duy nhat: goi tool get_payment_reconciliation voi claimed_order_id duoc giao "
    "de lay payment va doi soat item+freight. "
    "Khong tu tinh toan lai hay bia so. Tra ve dung cac truong theo schema, "
    "giu nguyen gia tri tool tra ve ke ca null."
)

DELIVERY_SYSTEM = (
    "Ban la Delivery Agent trong he thong dieu tra khieu nai Olist. "
    "Nhiem vu duy nhat: goi tool get_delivery_analysis voi claimed_order_id duoc giao "
    "de lay do lech giao hang va do lech handoff theo seller. "
    "Khong tu tinh toan lai hay bia so. Tra ve dung cac truong theo schema, "
    "giu nguyen gia tri tool tra ve ke ca null."
)

POLICY_SYSTEM = (
    "Ban la Policy Agent, ap dung chinh sach EC_POLICY_V2 cho khieu nai Olist. "
    "Nhiem vu duy nhat: goi tool apply_ec_policy_v2 voi claimed_order_id duoc giao "
    "de lay ket qua phan loai chinh thuc (primary_issue, secondary_issues, responsible_parties, "
    "refund, root cause, actions, evidence_ids). "
    "Khong tu suy luan hay doi bat ky gia tri nao - tat ca phai lay nguyen tu tool. "
    "Tra ve dung cac truong theo schema, giu nguyen gia tri tool tra ve."
)


def run_customer_agent(llm: ChatOpenAI, trace: TraceLogger, case_id: str, order_id: str) -> CustomerFragment:
    return run_tool_agent(
        llm, trace, case_id, "customer_agent", CUSTOMER_SYSTEM,
        f"claimed_order_id: {order_id}", get_customer_context, CustomerFragment,
    )


def run_order_product_agent(llm: ChatOpenAI, trace: TraceLogger, case_id: str, order_id: str) -> OrderProductFragment:
    return run_tool_agent(
        llm, trace, case_id, "order_product_agent", ORDER_PRODUCT_SYSTEM,
        f"claimed_order_id: {order_id}", get_order_product_context, OrderProductFragment,
    )


def run_payment_agent(llm: ChatOpenAI, trace: TraceLogger, case_id: str, order_id: str) -> PaymentFragment:
    return run_tool_agent(
        llm, trace, case_id, "payment_agent", PAYMENT_SYSTEM,
        f"claimed_order_id: {order_id}", get_payment_reconciliation, PaymentFragment,
    )


def run_delivery_agent(llm: ChatOpenAI, trace: TraceLogger, case_id: str, order_id: str) -> DeliveryFragment:
    return run_tool_agent(
        llm, trace, case_id, "delivery_agent", DELIVERY_SYSTEM,
        f"claimed_order_id: {order_id}", get_delivery_analysis, DeliveryFragment,
    )


def _make_policy_tool(trace: TraceLogger, case_id: str):
    @tool
    def apply_ec_policy_v2(claimed_order_id: str) -> dict:
        """Apply the EC_POLICY_V2 rule table to the order and return its case classification."""
        facts = gather_case_facts(claimed_order_id)
        result = policy_rules.apply_policy(facts)
        used_fallback = result.pop("_used_fallback")
        if used_fallback:
            trace.log_event(
                case_id=case_id,
                event_type="warning",
                agent="policy_agent",
                message="No exact EC_POLICY_V2 rule matched priority table; used conservative fallback",
                input={"claimed_order_id": claimed_order_id},
            )
        return result

    return apply_ec_policy_v2


def run_policy_agent(llm: ChatOpenAI, trace: TraceLogger, case_id: str, order_id: str) -> PolicyFragment:
    policy_tool = _make_policy_tool(trace, case_id)
    return run_tool_agent(
        llm, trace, case_id, "policy_agent", POLICY_SYSTEM,
        f"claimed_order_id: {order_id}", policy_tool, PolicyFragment,
    )

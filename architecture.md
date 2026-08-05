# Multi-Agent Architecture - Olist E-commerce Dispute Resolution

## Overview

Pipeline xử lý mỗi file `input/EC_*.json` bằng một coordinator và các agent chuyên trách. Code chỉ đóng vai trò data tool/fallback: đọc CSV, chuẩn bị facts, tính các số liệu cơ sở và kiểm tra schema. Khi LLM chạy được, quyết định cuối đi qua các LLM agent theo batch: domain agents tạo findings, `PolicyAgent` quyết issue/refund/actions, và `VerifierAgent` phát hành `CaseOutput` cuối. LangChain dùng `with_structured_output(..., method="tool_calling")`; với version LangChain hiện tại, runtime fallback tương thích là `function_calling`, tức cơ chế tool-call structured output của OpenAI-compatible APIs.

## Agent Roles

| Agent | File | Quyền truy cập dữ liệu | Structured output schema | Output bàn giao |
| --- | --- | --- | --- | --- |
| CoordinatorAgent | `app/main.py` | Input case, tất cả handoff | `CaseOutput` | Điều phối batch, ghi output, trace và metadata |
| CustomerAgent | `app/agents.py` | `orders`, `customers` | `CustomerFinding` | `customer_unique_id`, tối đa 5 related orders |
| OrderProductAgent | `app/agents.py` | `order_items`, `products`, `sellers` | `OrderProductFinding` | Product IDs, category context, item/seller IDs |
| PaymentAgent | `app/agents.py` | `order_payments`, `order_items` | `PaymentFinding` | Tổng item, freight, payment, difference và reconciled |
| DeliveryAgent | `app/agents.py` | `orders`, `order_items` | `DeliveryFinding` | Delivery variance và seller handoff analysis |
| PolicyAgent | `app/agents.py` | Handoff đã tổng hợp | `PolicyFinding` | Primary issue, secondary issues, parties, refund và actions theo `EC_POLICY_V2` |
| VerifierAgent | `app/agents.py` | Output của mọi agent | `VerificationFinding` | Giới hạn array, dựng affected entities, evidence IDs và schema cuối |

## Handoff Flow

1. `CoordinatorAgent` đọc `CaseInput`, lấy `claimed_order_id`, gọi `OlistDataStore.get_case_records`.
2. `CustomerAgent` nhận `order + customer`, trả customer context.
3. `OrderProductAgent` nhận `items + products`, trả product context.
4. `PaymentAgent` nhận `items + payments`, tính payment reconciliation.
5. `DeliveryAgent` nhận `order + items`, tính delivery variance và handoff variance theo từng seller.
6. `PolicyAgent` nhận toàn bộ handoff, áp thứ tự ưu tiên của `EC_POLICY_V2`.
7. Sau khi chuẩn bị facts cho toàn bộ batch, coordinator gom prompt theo từng domain agent và gọi LangChain `batch()` với `with_structured_output` theo schema riêng.
8. `PolicyAgent` nhận findings của Customer, Order/Product, Payment và Delivery để quyết định `primary_issue`, `secondary_issues`, root cause, refund và actions.
9. `VerifierAgent` nhận toàn bộ findings và phát hành `CaseOutput` cuối nếu schema/evidence/money/array limits hợp lệ. Nếu Policy hoặc Verifier LLM lỗi, hệ thống dùng deterministic fallback để vẫn tạo output auditable.
10. Output được ghi vào `output/<case_id>.json`; trace mới nhất ghi vào `logging/trace.jsonl`; metadata ghi vào `logging/metadata.json`.

## Data Contracts

- Không suy diễn refund ledger, tracking checkpoint hoặc giao sai/giao thiếu vì CSV không có nguồn kiểm chứng.
- Evidence chỉ có dạng `order:<order_id>`, `item:<order_id>:<order_item_id>`, `payment:<order_id>:<payment_sequential>`, `seller:<seller_id>`, `policy:<root_cause_code>`.
- Nếu order không có item row, các trường `expected_total_brl`, `difference_brl`, `reconciled` là `null`, và item/seller/product/category/handoff là mảng rỗng.
- Timestamp giữ nguyên format trong CSV hoặc `null`.

## Runtime

```bash
.venv/bin/python -m app.main
```

Để chạy khô không gọi API nhưng vẫn kiểm chứng toàn bộ policy/schema:

```bash
.venv/bin/python -m app.main --no-llm
```

Model được đọc từ `.env` theo biến `LLM_MODEL`; API key đọc từ `OPENROUTER_API_KEY`, cùng format với `.env.example`.

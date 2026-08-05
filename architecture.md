# Multi-Agent Architecture - Olist E-commerce Dispute Resolution

## Overview

Pipeline xử lý mỗi file `input/EC_*.json` bằng một coordinator và các agent chuyên trách. Các phép tính nghiệp vụ được thực hiện deterministic từ CSV để evidence, tiền, timestamp và ID luôn truy xuất được. LangChain được dùng ở bước structured output verifier/formatter qua `with_structured_output(CaseOutput, method="tool_calling")`; với version LangChain hiện tại, runtime fallback tương thích là `function_calling`, tức cơ chế tool-call structured output của OpenAI-compatible APIs.

## Agent Roles

| Agent | File | Quyền truy cập dữ liệu | Output bàn giao |
| --- | --- | --- | --- |
| CoordinatorAgent | `app/main.py` | Input case, tất cả handoff | Điều phối batch, ghi output, trace và metadata |
| CustomerAgent | `app/agents.py` | `orders`, `customers` | `customer_unique_id`, tối đa 5 related orders |
| OrderProductAgent | `app/agents.py` | `order_items`, `products`, `sellers` | Product IDs và category context |
| PaymentAgent | `app/agents.py` | `order_payments`, `order_items` | Tổng item, freight, payment, difference và reconciled |
| DeliveryAgent | `app/agents.py` | `orders`, `order_items` | Delivery variance và seller handoff analysis |
| PolicyAgent | `app/agents.py` | Handoff đã tổng hợp | Primary issue, secondary issues, parties, refund và actions theo `EC_POLICY_V2` |
| VerifierAgent | `app/agents.py` | Output của mọi agent | Giới hạn array, dựng affected entities, evidence IDs và schema cuối |

## Handoff Flow

1. `CoordinatorAgent` đọc `CaseInput`, lấy `claimed_order_id`, gọi `OlistDataStore.get_case_records`.
2. `CustomerAgent` nhận `order + customer`, trả customer context.
3. `OrderProductAgent` nhận `items + products`, trả product context.
4. `PaymentAgent` nhận `items + payments`, tính payment reconciliation.
5. `DeliveryAgent` nhận `order + items`, tính delivery variance và handoff variance theo từng seller.
6. `PolicyAgent` nhận toàn bộ handoff, áp thứ tự ưu tiên của `EC_POLICY_V2`.
7. `VerifierAgent` dựng `CaseOutput` bằng Pydantic schema, giới hạn danh sách và evidence hợp lệ.
8. Nếu bật LLM và có `OPENROUTER_API_KEY`, `CoordinatorAgent` gọi LangChain structured output để emit đúng `CaseOutput`; prompt chỉ cho phép trả lại JSON đã kiểm chứng, không thêm fact mới.
9. Output được ghi vào `output/<case_id>.json`; trace mới nhất ghi vào `logging/trace.jsonl`; metadata ghi vào `logging/metadata.json`.

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

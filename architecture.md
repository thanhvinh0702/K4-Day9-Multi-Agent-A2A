# Kiến trúc hệ thống Multi-Agent E-commerce Dispute Resolution

## 1. Tổng quan

Hệ thống gồm 7 agent, mỗi agent sở hữu một domain dữ liệu hoặc một trách nhiệm xử lý riêng. Bốn agent domain (Customer, Order & Product, Payment, Delivery) trích xuất và tính toán tất định từ CSV Olist. Coordinator, Policy và Verifier là ba agent thực hiện lời gọi LLM thật (Groq, `llama-3.1-8b-instant`, 8B tham số — tuân thủ giới hạn ≤10B của đề bài) để tổng hợp bằng chứng, xác minh phán quyết và kiểm tra tính nhất quán trước khi ghi output.

Nguyên tắc thiết kế: **các con số bắt buộc phải chính xác tuyệt đối để chấm điểm** (delivery variance, payment reconciliation, refund...) được tính bằng công thức tất định theo đúng `EC_POLICY_V2`; LLM không được phép ghi đè các giá trị này. LLM chỉ tham gia ở các bước cần suy luận thật sự: tổng hợp bằng chứng liên-domain, xác minh độc lập việc phân loại `primary_issue`, chấm điểm `confidence`, và kiểm tra mâu thuẫn nội tại trước khi xuất file.

## 2. Sơ đồ luồng handoff

```text
                         ┌─────────────────────────┐
                         │   input/EC_XXX.json      │
                         └────────────┬─────────────┘
                                      │ claimed_order_id
                                      ▼
                         ┌─────────────────────────┐
                         │   CoordinatorAgent        │
                         │   (orchestrator)          │
                         └────────────┬─────────────┘
              ┌───────────┬───────────┼───────────┬────────────┐
              ▼           ▼           ▼            ▼            │
     ┌────────────┐┌─────────────┐┌───────────┐┌────────────┐   │
     │CustomerAgent││OrderProduct ││PaymentAgent││DeliveryAgent│  │
     │  (rule)     ││Agent (rule) ││  (rule)    ││  (rule)     │  │
     └──────┬──────┘└──────┬──────┘└─────┬──────┘└──────┬──────┘  │
            │  customer_ctx│  op_ctx     │ payment_ctx  │ delivery_ctx
            └──────────────┴─────────────┴──────────────┴─────────┘
                                      │ evidence bundle
                                      ▼
                    ┌───────────────────────────────────┐
                    │ CoordinatorAgent                    │
                    │  → LLM call #1: handoff synthesis   │──▶ logging/trace.jsonl
                    │  (llama-3.1-8b-instant via Groq)    │
                    └────────────────┬────────────────────┘
                                      ▼
                    ┌───────────────────────────────────┐
                    │ PolicyAgent                         │
                    │  1) deterministic EC_POLICY_V2 rule │
                    │     → primary/secondary issue,      │
                    │       responsible party, refund,    │
                    │       actions, evidence_ids          │
                    │  2) LLM call #2: independent re-     │──▶ logging/trace.jsonl
                    │     derivation of primary_issue +    │   (agreement flag,
                    │     confidence score + rationale     │    rationale logged)
                    └────────────────┬────────────────────┘
                                      ▼
                    ┌───────────────────────────────────┐
                    │ VerifierAgent                       │
                    │  1) deterministic schema/array-limit│
                    │     /null enforcement (source of    │
                    │     truth for output correctness)   │
                    │  2) LLM call #3: consistency audit  │──▶ logging/trace.jsonl
                    │     (case_status vs refund, empty   │   (issues_found list)
                    │     evidence for action_required...)│
                    └────────────────┬────────────────────┘
                                      ▼
                         ┌─────────────────────────┐
                         │  output/EC_XXX.json       │
                         └─────────────────────────┘
```

## 3. Vai trò, quyền truy cập dữ liệu và loại xử lý

| Agent | File | Trách nhiệm | Dữ liệu được truy cập | Xử lý |
| --- | --- | --- | --- | --- |
| **CustomerAgent** | `src/agents/customer_agent.py` | Xác định `customer_unique_id`, tìm các order khác của cùng khách hàng | `customers.csv`, `orders.csv` | Tất định (pandas) |
| **OrderProductAgent** | `src/agents/order_product_agent.py` | Trích item, seller, product, category của order đang khiếu nại | `order_items.csv`, `products.csv`, `product_category_name_translation.csv` | Tất định (pandas) |
| **PaymentAgent** | `src/agents/payment_agent.py` | Tổng hợp payment rows, đối soát `payment_total` với `item_total + freight_total` | `order_payments.csv` + item/freight từ OrderProductAgent | Tất định (pandas) |
| **DeliveryAgent** | `src/agents/delivery_agent.py` | Tính `delivery_variance_hours`, `handoff_variance_hours` theo từng seller | `orders.csv` (timestamps) + item/seller từ OrderProductAgent | Tất định (datetime arithmetic) |
| **CoordinatorAgent** | `src/agents/coordinator_agent.py` | Điều phối 4 agent domain, tổng hợp bằng chứng, gọi LLM #1 để viết handoff note, lắp ráp output cuối | Toàn bộ context từ 4 agent trên | Orchestration + **LLM call #1** (chỉ ghi vào trace, không ảnh hưởng schema) |
| **PolicyAgent** | `src/agents/policy_agent.py` | Áp dụng bảng rule `EC_POLICY_V2` theo đúng thứ tự ưu tiên để chọn `primary_issue`, `responsible_party`, `refund`, `actions`, `evidence_ids`; gọi LLM #2 để double-check + chấm `confidence` | Context tổng hợp từ Coordinator | Tất định (rule engine, **nguồn sự thật cho chấm điểm**) + **LLM call #2** (xác minh + confidence) |
| **VerifierAgent** | `src/agents/verifier_agent.py` | Cắt mảng đúng giới hạn (5/3/5/5/5/5/3/3/20/5), enforce null constraint khi order rỗng item, gọi LLM #3 kiểm tra mâu thuẫn nội tại | Output đã lắp ráp từ Policy + các agent domain | Tất định (schema enforcement, **nguồn sự thật cho tính hợp lệ**) + **LLM call #3** (audit, chỉ log) |

## 4. Vì sao dùng kiến trúc hybrid (rule engine + LLM thật)

- **Correctness bắt buộc chính xác đến 2 chữ số thập phân** (delivery variance, payment reconciliation, refund) — để một LLM tự do tính các con số này có rủi ro sai số/hallucination không kiểm soát được, trong khi các công thức trong đề bài (mục 4) là xác định 100% từ dữ liệu. Vì vậy các phép tính này luôn do code Python thực hiện.
- **Multi-agent thật sự cần suy luận, không chỉ đặt tên** — do đó 3 điểm suy luận có ý nghĩa nhất được giao cho LLM thật: (1) Coordinator tổng hợp bằng chứng liên-domain để quyết định domain nào quyết định vụ việc, (2) Policy Agent tự tái suy luận `primary_issue` một cách độc lập với rule engine để chấm `confidence` dựa trên mức độ rõ ràng của bằng chứng, (3) Verifier Agent audit tính nhất quán cuối cùng — đúng vai trò "kiểm tra ID, số tiền, null handling... trước khi ghi file" nêu trong đề bài.
- **An toàn khi LLM lỗi/timeout**: mọi lời gọi LLM đều có retry (3 lần, backoff) và fallback tất định (confidence heuristic, bỏ qua audit) — một lần gọi API thất bại không làm sập toàn bộ pipeline 50 case.

## 5. Model

- **Model**: `llama-3.1-8b-instant` — 8 tỷ tham số, tuân thủ giới hạn ≤10B (mục 9.1 README).
- **Provider**: Groq (API tương thích OpenAI, `base_url=https://api.groq.com/openai/v1`).
- **Khai báo**: `src/llm_client.py` (hằng số `MODEL_NAME`), đồng thời ghi vào `logging/metadata.json` sau mỗi lần chạy `main.py`.
- **API key**: đọc từ biến môi trường `GROQ_API_KEY` trong file `.env` (không commit — xem `.gitignore`, mẫu tại `.env.example`).

## 6. Trace

Mỗi bước xử lý (bao gồm cả 4 agent tất định và 3 lời gọi LLM thật) được ghi vào `logging/trace.jsonl` qua `src/tracer.py`, gồm hai loại record:

- `log_step`: các bước handoff giữa agent (timestamp, case_id, agent, action, input/output summary).
- `log_llm_call`: riêng cho 3 lời gọi LLM, gồm model, tóm tắt prompt, tóm tắt kết quả, usage token, và cờ `fallback_used` nếu lời gọi thất bại và hệ thống phải dùng giá trị dự phòng tất định.

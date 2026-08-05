# Member Role Report - Day 9: Multi-Agent E-commerce Dispute Resolution

## 1. Thông Tin Cá Nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Hoàng Thành Vinh |
| MSSV | 2A202601124 |
| Khóa/Lớp | [K4] |
| Vai trò chính | Multi-agent orchestration, structured output, policy/verifier pipeline |
| Ngày hoàn thành | 2026-08-05 |

## 2. Vai Trò Và Phạm Vi Công Việc

### Phần Việc Sở Hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Data tool và CSV joins | `app/data_store.py` | 9 CSV Olist, `claimed_order_id` | Records theo order, customer, items, payments, products, sellers | Hoàn thành |
| Fully agentic batch orchestration | `app/main.py` | `input/EC_*.json`, facts từ data tool | `output/EC_*.json`, `logging/trace.jsonl`, `logging/metadata.json` | Hoàn thành |
| Domain agents và fallback policy logic | `app/agents.py` | Joined records theo case | Customer, product, payment, delivery, policy, verifier fallback | Hoàn thành |
| Structured output schemas | `app/schemas.py`, `app/llm.py` | Agent facts và handoff | `CustomerFinding`, `OrderProductFinding`, `PaymentFinding`, `DeliveryFinding`, `PolicyFinding`, `VerificationFinding`, `CaseOutput` | Hoàn thành |
| Architecture documentation | `architecture.md` | Thiết kế hệ thống | Mô tả agent roles, handoff, data contracts, runtime | Hoàn thành |

### Việc Hỗ Trợ Ngoài Phạm Vi Chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Kiểm thử batch 50 case | Pipeline output | Chạy tạo đủ 50 JSON trong `output/`, 0 failures |
| Kiểm thử API/LLM fallback | Batch LLM runner | Trace ghi rõ `llm_used`, `llm_error`, `final_decision_source` |
| Chuẩn hóa metadata | Nhóm nộp bài | `logging/metadata.json` ghi model, framework, structured output, runtime |

## 3. Kết Quả Theo Vai Trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Thiết kế batch agent flow | `app/main.py` | 4 domain agents chạy batch trước, sau đó `PolicyAgent` và `VerifierAgent` quyết định | `.venv/bin/python -m app.main` |
| Dùng LangChain structured output | `app/llm.py`, `app/schemas.py` | Các agent dùng Pydantic schema qua tool/function-calling structured output | Kiểm tra `metadata.json` và `trace.jsonl` |
| Đảm bảo output đúng schema | `app/schemas.py`, `app/agents.py` | 50 file `output/EC_001.json` đến `EC_050.json` | `find output -name 'EC_*.json' | wc -l` |
| Ghi trace audit theo case | `logging/trace.jsonl` | Mỗi case có agent list, primary issue, refund, agent findings, final source | `head -1 logging/trace.jsonl` |

Artifact cụ thể đã bàn giao:

- `output/`: 50 JSON kết quả.
- `logging/trace.jsonl`: trace chạy mới nhất.
- `logging/metadata.json`: model/framework/runtime.
- `architecture.md`: mô tả thiết kế hệ thống.

## 4. Giải Thích Phần Kỹ Thuật Đã Thực Hiện

### Vấn Đề Cần Giải Quyết

Bài toán yêu cầu điều tra 50 khiếu nại e-commerce trên dữ liệu Olist. Mỗi case cần đối chiếu nhiều nguồn dữ liệu: order status, payment, item, seller, product, customer history và delivery timestamps. Output phải có primary issue, secondary issues, responsible parties, evidence IDs, refund và actions theo `EC_POLICY_V2`.

### Cách Triển Khai

Pipeline được thiết kế theo hướng fully agentic batch:

1. `FallbackCoordinator` đọc input và dùng data tool để lấy facts từ CSV.
2. `CustomerAgent`, `OrderProductAgent`, `PaymentAgent`, `DeliveryAgent` chạy theo batch để tạo structured findings.
3. `PolicyAgent` nhận findings của các domain agents và quyết định issue/refund/actions.
4. `VerifierAgent` nhận toàn bộ findings, kiểm tra schema/evidence/money/array limits và phát hành `CaseOutput`.
5. Nếu LLM/API lỗi, hệ thống dùng deterministic fallback để vẫn tạo output auditable và không mất batch.

LangChain được dùng qua `with_structured_output(...)`. Code thử `method="tool_calling"` trước; nếu version thư viện không nhận tên này thì fallback sang `function_calling`, vẫn là cơ chế structured output bằng tool/function calling của OpenAI-compatible API.

### Input, Output Và Contract

| Thành phần | Mô tả |
| --- | --- |
| Input | `input/EC_*.json`, 9 CSV trong `data/` |
| Output | `output/EC_*.json`, `logging/trace.jsonl`, `logging/metadata.json` |
| Module phụ thuộc | LangChain, `langchain-openai`, Pydantic, CSV standard library |
| Module sử dụng output | Script zip/nộp bài và hệ thống chấm đọc `output/` |
| Điều kiện lỗi cần xử lý | LLM API lỗi, thiếu credit, order không có item row, split payment, canceled/unavailable có payment, late seller/logistics |

### Cách Xác Minh

```bash
.venv/bin/python -m app.main
find output -maxdepth 1 -type f -name 'EC_*.json' | wc -l
head -1 logging/trace.jsonl
cat logging/metadata.json
```

- **Kết quả mong đợi:** 50 output JSON, 0 failures, trace và metadata được ghi mới.
- **Kết quả thực tế:** Đã chạy 50/50 case, 0 failures.
- **Artifact/log:** `output/`, `logging/trace.jsonl`, `logging/metadata.json`.

## 5. Một Quyết Định Kỹ Thuật Quan Trọng

- **Bối cảnh:** Cần hệ thống multi-agent có LLM tham gia quyết định, nhưng output vẫn phải đúng dữ liệu CSV và không hallucinate evidence.
- **Các phương án đã cân nhắc:** Để LLM tự đọc toàn bộ CSV trong prompt; tính toàn bộ bằng code deterministic; hoặc dùng hybrid agentic với data facts + structured LLM findings + fallback.
- **Phương án đã chọn:** Fully agentic batch có fallback: domain agents, `PolicyAgent`, `VerifierAgent` dùng structured output; deterministic code chỉ làm data tool/fallback khi API lỗi.
- **Lý do:** Vừa thể hiện được handoff và quyết định bởi agent, vừa giữ được khả năng tạo output khi OpenRouter lỗi hoặc thiếu credit.
- **Bằng chứng quyết định phù hợp:** `trace.jsonl` ghi `agent_llm_traces`, `final_decision_source`, `llm_used`, `llm_error`; `metadata.json` ghi `multi_agent_llm.mode = batch`.

## 6. Một Lỗi Hoặc Blocker Đã Xử Lý

- **Triệu chứng/lỗi nguyên văn:** `APIConnectionError: Connection error.` khi gọi OpenRouter; có lúc OpenRouter trả `402` do thiếu credit hoặc `401` do proxy/base URL không forward authentication.
- **Lệnh hoặc bước tái hiện:** Chạy `.venv/bin/python -m app.main` và xem `logging/trace.jsonl`.
- **Nguyên nhân gốc:** Môi trường/API key/base URL không gọi được OpenRouter ổn định; ngoài ra version LangChain không nhận trực tiếp `method="tool_calling"`.
- **Cách xử lý:** Thêm `OPENROUTER_BASE_URL`; `app/llm.py` fallback từ `tool_calling` sang `function_calling`; batch runner dùng `return_exceptions=True` và ghi lỗi từng agent vào trace.
- **Cách xác minh sau khi sửa:** Chạy batch vẫn tạo `50/50` output với `0 failures`; trace thể hiện rõ fallback nếu LLM không dùng được.
- **Điều học được:** Với pipeline cần nộp output ổn định, LLM agent nên có structured schema, trace rõ ràng và fallback auditable.

## 7. Hiểu Biết Về Luồng End-To-End

1. Case đi từ `input/EC_*.json` đến output cuối như thế nào?
2. Vì sao không đưa order lịch sử vào `affected_entities`?
3. Payment reconciliation dùng công thức nào?
4. Evidence ID hợp lệ gồm những dạng nào?
5. Khi nào refund freight và khi nào full refund?

**Câu trả lời:**

1. Coordinator đọc case, lấy `claimed_order_id`, lấy facts từ CSV, chạy domain agents theo batch, chạy `PolicyAgent`, chạy `VerifierAgent`, rồi ghi `output/EC_*.json`.
2. `affected_entities` chỉ chứa order đang bị khiếu nại; order lịch sử chỉ nằm trong `customer_context.related_order_ids`.
3. `expected_total_brl = sum(order_items.price) + sum(order_items.freight_value)`, `difference_brl = sum(payment_value) - expected_total_brl`, reconciled khi `abs(difference) <= 0.10`.
4. Evidence hợp lệ gồm `order:<order_id>`, `item:<order_id>:<order_item_id>`, `payment:<order_id>:<payment_sequential>`, `seller:<seller_id>`, `policy:<root_cause_code>`.
5. Full refund cho `canceled_order_paid` hoặc `unavailable_order_paid`; refund freight cho `late_delivery_seller` hoặc `late_delivery_logistics`.

## 8. Cam Kết Của Thành Viên

- [ ] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [ ] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [ ] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Hoàng Thành Vinh  
**Ngày xác nhận:** 2026-08-05

# Member Role Report - Day 9: Multi-Agent E-commerce Dispute Resolution

> Thay phần thông tin cá nhân trong dấu `[ ]` trước khi nộp. Nội dung kỹ thuật bên dưới mô tả phần pipeline multi-agent đã triển khai trong repo này.

## 1. Thông tin cá nhân

| Thông tin       | Nội dung     |
| --------------- | ------------ |
| Họ và tên       | [Họ và tên]  |
| MSSV            | [MSSV]       |
| Khóa/Lớp        | [K4]         |
| Vai trò chính   | Multi-agent pipeline, policy verification, structured output |
| Ngày hoàn thành | 2026-08-05 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| ------------------ | ------------------ | -------------- | ---------------- | ---------- |
| Data loading và joins | `app/data_store.py` | 9 CSV Olist, `claimed_order_id` | Records theo order, item, payment, product, seller, customer | Hoàn thành |
| Multi-agent orchestration | `app/main.py`, `app/agents.py` | `input/EC_*.json` | `output/EC_*.json`, `logging/trace.jsonl`, `logging/metadata.json` | Hoàn thành |
| Structured output schema | `app/schemas.py`, `app/llm.py` | Deterministic case result | Pydantic `CaseOutput` qua LangChain tool-call structured output | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --------- | ----------------------------- | ------- |
| Tài liệu kiến trúc | Nhóm nộp bài | `architecture.md` mô tả agent, quyền truy cập và handoff |
| Kiểm thử chạy khô | Pipeline output | Có thể chạy `--no-llm` để xác minh schema/policy không cần gọi API |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --------------------- | --------------------------- | ---------------- | ------------- |
| Áp policy `EC_POLICY_V2` theo thứ tự ưu tiên | `PolicyAgent.run` | Primary issue, responsible parties, refund, actions | Chạy `.venv/bin/python -m app.main --no-llm` |
| Dựng output schema và evidence hợp lệ | `VerifierAgent.run`, `app/schemas.py` | JSON đúng giới hạn array và ID format | Validate Pydantic khi ghi output |

Một artifact cụ thể là `logging/trace.jsonl`, ghi lại từng case đã xử lý, agent tham gia, primary issue, refund và structured output method.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Pipeline giải quyết việc điều tra khiếu nại e-commerce bằng cách đối chiếu order, item, payment, delivery, seller và customer history. Mục tiêu là đưa ra kết luận dựa trên dữ liệu kiểm chứng thay vì chỉ dựa trên nội dung khiếu nại.

### Cách triển khai

Triển khai tách thành nhiều agent có handoff rõ ràng. Các agent domain tính context riêng; `PolicyAgent` áp `EC_POLICY_V2` đúng thứ tự ưu tiên; `VerifierAgent` dựng evidence ID và ép schema bằng Pydantic. LangChain `with_structured_output` được dùng ở bước cuối để output theo schema qua cơ chế tool-call/function-call tương thích OpenAI.

### Input, output và contract

| Thành phần              | Mô tả                                  |
| ----------------------- | -------------------------------------- |
| Input                   | `input/EC_*.json`, các CSV trong `data/` |
| Output                  | `output/EC_*.json`, `logging/trace.jsonl`, `logging/metadata.json` |
| Module phụ thuộc        | `app/data_store.py`, `app/schemas.py`, LangChain, Pydantic |
| Module sử dụng output   | Script nộp/chấm đọc `output/` |
| Điều kiện lỗi cần xử lý | Missing order, order không có item row, split payment, canceled/unavailable có payment |

### Cách xác minh

```bash
.venv/bin/python -m app.main --no-llm
```

- **Kết quả mong đợi:** Tạo một JSON output cho mỗi `input/EC_*.json`; trace và metadata được ghi mới.
- **Kết quả thực tế:** Repo hiện chưa có 50 input case thật, nên cần thêm `input/EC_001.json` đến `input/EC_050.json` trước khi chạy nộp.
- **Artifact/log:** `logging/trace.jsonl`, `logging/metadata.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** LLM có thể sinh output sai evidence hoặc tự thêm sự kiện không có trong CSV.
- **Các phương án đã cân nhắc:** Cho LLM tự phân tích toàn bộ CSV trong prompt; hoặc tính deterministic bằng code rồi dùng LLM structured output ở bước verifier.
- **Phương án đã chọn:** Tính deterministic bằng code, LLM chỉ format/verify schema cuối.
- **Lý do:** Giảm hallucination, dễ tái lập, evidence và refund khớp dữ liệu nguồn.
- **Bằng chứng quyết định phù hợp:** Output được validate bằng Pydantic schema trước khi ghi file.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** LangChain version trong venv không nhận `method="tool_calling"` trực tiếp.
- **Lệnh hoặc bước tái hiện:** Gọi `ChatOpenAI(...).with_structured_output(CaseOutput, method="tool_calling")`.
- **Nguyên nhân gốc:** API version hiện expose tên method là `function_calling`, dù cơ chế phía OpenAI-compatible vẫn là tool/function call.
- **Cách xử lý:** `app/llm.py` thử `tool_calling`, nếu `ValueError` thì fallback sang `function_calling` và ghi runtime method trong metadata.
- **Cách xác minh sau khi sửa:** Khởi tạo structured runnable thành công bằng method fallback.
- **Điều học được:** Cần ghi metadata runtime để minh bạch khác biệt giữa yêu cầu bài và tên API của version thư viện.

## 7. Hiểu biết về luồng end-to-end

Giải thích ngắn gọn bằng lời của bạn:

1. Case đi từ `input/EC_*.json` đến output cuối như thế nào?
2. Vì sao không đưa order lịch sử vào `affected_entities`?
3. Payment reconciliation dùng công thức nào?
4. Evidence ID hợp lệ gồm những dạng nào?
5. Khi nào refund freight và khi nào full refund?

**Câu trả lời:**

1. Coordinator đọc case, dùng `claimed_order_id` join CSV, gọi các agent domain, áp policy, verify schema rồi ghi `output/EC_*.json`.
2. `affected_entities` chỉ chứa order đang bị khiếu nại; order lịch sử chỉ là context trong `customer_context.related_order_ids`.
3. `expected_total_brl = sum(price) + sum(freight_value)`, `difference_brl = sum(payment_value) - expected_total_brl`, reconciled khi `abs(difference) <= 0.10`.
4. Evidence hợp lệ gồm `order:<id>`, `item:<order_id>:<item_id>`, `payment:<order_id>:<payment_sequential>`, `seller:<seller_id>`, `policy:<root_cause_code>`.
5. Full refund cho canceled/unavailable có payment; refund freight cho late delivery do seller handoff muộn hoặc logistics giao trễ.

## 8. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [ ] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [ ] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [ ] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [ ] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** [Họ và tên]
**Ngày xác nhận:** [YYYY-MM-DD]

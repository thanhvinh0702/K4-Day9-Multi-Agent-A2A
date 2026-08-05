# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung                                                                                       |
| --------------- | ------------------------------------------------------------------------------------------------ |
| Họ và tên       | Hồ Thúy Hằng                                                                                     |
| MSSV            | 2A202601806                                                                                       |
| Khóa/Lớp        | K4                                                                                                 |
| Vai trò chính   | Multi-agent orchestration: Coordinator Agent, A2A handoff protocol, input intake/verification     |
| Ngày hoàn thành | 2026-08-05                                                                                         |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Coordinator Agent (dispatch/collect/merge/assemble/verify) | `src/coordinator.py` | Case state (`case_id`, `claimed_order_id`, các fragment từ domain agent) | Dossier gộp, draft output, `AgentMessage` log vào trace | Hoàn thành |
| A2A handoff envelope | `src/schemas.py` (`AgentMessage`) | — | Schema chuẩn cho mọi lần dispatch/handoff/verify giữa các agent | Hoàn thành |
| Input intake & verification | `src/coordinator.py` (`intake()`, `IntakeRejected`), `src/schemas.py` (`CaseInput`, `CustomerRequest`, `InvestigationScope`) | Raw input JSON (`customer_request`, `investigation_scope`, `policy_version`) | `CaseInput` đã validate, hoặc reject có lý do rõ ràng trước khi dispatch | Hoàn thành |
| Orchestration graph (route qua Coordinator) | `src/graph.py` | `CaseState` (LangGraph) | Gọi coordinator ở từng node fan-out/fan-in | Hoàn thành |
| Batch runner tích hợp intake | `src/main.py` (`run_batch`, `_write_case_output`) | 50 file `input/input/EC_*.json` | 50 file `output/EC_*.json`, kể cả case bị intake reject | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

Không có hoạt động hỗ trợ ngoài phạm vi chính trong phiên làm việc này.

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Thêm Coordinator Agent tường minh thay vì logic dispatch ẩn trong graph node | `src/coordinator.py` | 600 `a2a_message` event / 50 case (12 event/case) | Đếm `event_type == "a2a_message"` trong `logging/trace.jsonl` sau khi chạy `python -m src.main` |
| Vá lỗ hổng "tin ngay input người dùng" | `src/coordinator.py::intake()` | Case với `claimed_order_id` giả hoặc JSON sai schema bị reject trước khi dispatch, không echo order id chưa xác minh vào output | Script test độc lập gọi `coordinator.intake()` với 3 input: order giả, thiếu field, input thật `EC_001.json` |

Output cụ thể mà phần việc của tôi tạo ra: `logging/trace.jsonl` (lượt chạy mới nhất) chứa cặp
`task_request`/`handoff` thật cho case `EC_001` giữa `coordinator` và `customer_agent`, trích trong
`architecture.md` mục 2; 50/50 case trong `output/` có `status: "ok"`, 0 lỗi.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Kiến trúc cũ có 6 agent domain nhưng không có Coordinator Agent tường minh — dispatch và handoff
nằm rải rác trong closure của `graph.py`. Ngoài ra `main.py` đọc thẳng `claimed_order_id` từ input
JSON mà không xác minh nó tồn tại thật trước khi dùng làm khóa cho toàn bộ tính toán tài chính phía
sau — vi phạm nguyên tắc "không tin ngay input người dùng, phải verify lại".

### Cách triển khai

`src/coordinator.py` là Coordinator Agent thật sự, không gọi LLM (routing trong pipeline cố định
theo case). `intake()` là hành động đầu tiên trên mọi case: validate shape input bằng Pydantic
(`CaseInput`), sau đó tra `data_layer.get_order(claimed_order_id)` để xác nhận order tồn tại thật
trước khi dispatch cho bất kỳ domain agent nào. Mọi lần dispatch/handoff giữa các agent được log
tường minh dưới dạng `AgentMessage`, `event_type: "a2a_message"` trong trace.

### Input, output và contract

| Thành phần              | Mô tả                                                                                          |
| ------------------------ | ------------------------------------------------------------------------------------------------ |
| Input                   | Input JSON thô (`case_id`, `customer_request.claimed_order_id`, `investigation_scope`, `policy_version`) |
| Output                  | `CaseInput` (Pydantic, đã validate) khi hợp lệ; `coordinator.IntakeRejected(case_id, reason)` khi bị từ chối |
| Module phụ thuộc        | `src/data_layer.py` (`get_order`), `src/schemas.py` (`CaseInput`)                                |
| Module sử dụng output   | `src/main.py::run_batch` (gọi `intake()` trước khi build state cho `app.invoke(...)`)             |
| Điều kiện lỗi cần xử lý | JSON thiếu field bắt buộc/sai kiểu; `claimed_order_id` không khớp order nào trong CSV              |

### Cách xác minh

```bash
python -m tests.test_policy_rules
python -m src.main
```

- **Kết quả mong đợi:** 9/9 unit test pass; batch in ra `[ok] EC_0xx -> EC_0xx.json` cho cả 50 case.
- **Kết quả thực tế:** 9/9 test pass; batch thật (gọi OpenAI API) trả về 50/50 `[ok]`, 0 `event_type: "error"`, 600 `event_type: "a2a_message"` trong `logging/trace.jsonl`.
- **Artifact/log:** `logging/trace.jsonl` (không chứa secret), `output/EC_001.json` … `EC_050.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Coordinator Agent có nên tự gọi LLM để "quyết định" thứ tự/cách dispatch việc cho các agent con hay không?
- **Các phương án đã cân nhắc:** (1) Coordinator là một LLM agent, tự suy luận thứ tự dispatch mỗi case. (2) Coordinator là code xác định, luồng dispatch cố định (4 domain agent song song → Policy → Verifier), chỉ log lại các bước handoff.
- **Phương án đã chọn:** Phương án 2.
- **Lý do:** Thứ tự xử lý một khiếu nại Olist cố định theo README mục 7, không phải quyết định cần suy luận lại mỗi case. Để LLM "định tuyến" chỉ thêm rủi ro (bỏ sót agent, tự sáng tạo thứ tự) và tốn thêm LLM call không cần thiết.
- **Bằng chứng quyết định phù hợp:** 50/50 case chạy `[ok]` với Coordinator hoàn toàn deterministic; 600 `a2a_message` log đúng 12 sự kiện/case như thiết kế, không case nào bị bỏ sót bước dispatch.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Không phải lỗi runtime — phát hiện qua rà soát code: `src/main.py` (trước khi sửa) đọc `case["customer_request"]["claimed_order_id"]` trực tiếp, không validate; nếu order đó không tồn tại trong CSV, `ValueError` từ tầng `tools.py` bị bắt ở `except Exception` chung, và `_build_fallback_output(case_id, claimed_order_id)` vẫn đưa `claimed_order_id` chưa được xác minh vào `affected_entities.order_ids` của output.
- **Lệnh hoặc bước tái hiện:** Gọi `build_customer_context("not_a_real_order_id")` (trước bản vá) — hàm raise `ValueError`, giá trị order id giả vẫn lọt vào output fallback ở tầng trên.
- **Nguyên nhân gốc:** Không có bước xác minh input tách biệt trước khi dùng `claimed_order_id` làm khóa cho toàn bộ pipeline — hệ thống "tin" input người dùng đến tận khi một hàm tính toán sâu bên trong crash.
- **Cách xử lý:** Thêm `schemas.CaseInput` (validate shape) và `coordinator.intake()` (validate + xác minh `claimed_order_id` tồn tại thật qua `data_layer.get_order`) làm bước đầu tiên trong `main.py::run_batch`, trước khi build state cho graph.
- **Cách xác minh sau khi sửa:** Script test độc lập gọi `coordinator.intake()` với order id giả → bị reject đúng kỳ vọng; input thiếu `claimed_order_id` → bị reject do sai schema; input thật `EC_001.json` → pass qua `intake()` không đổi hành vi. Chạy lại `python -m src.main` cho cả 50 case thật xác nhận không case nào bị ảnh hưởng.
- **Điều học được:** "Xác minh input" phải là một bước tường minh, độc lập, chạy sớm nhất có thể — không nên trông chờ một lỗi tính toán ở tầng sâu vô tình chặn được input xấu, vì đường crash đó có thể để lọt dữ liệu chưa xác minh vào nhánh xử lý lỗi.

## 7. Hiểu biết về luồng end-to-end



1. Dữ liệu đi từ `input/input/EC_xxx.json` đến `output/EC_xxx.json` như thế nào?
2. Case được coi là "đúng" dựa trên đối chiếu CSV hay dựa trên lời khai của khách hàng?
3. Ngoài Verifier, còn cơ chế kiểm tra chất lượng nào khác trong bài lab?
4. Vì sao Coordinator/Verifier không dùng LLM trong khi 5 agent domain còn lại có?
5. `intake()` được xem là thành công dựa trên artifact và metric nào?

**Câu trả lời:**

1. `coordinator.intake()` validate schema + xác minh `claimed_order_id` tồn tại trong
   `olist_orders_dataset.csv` → LangGraph chạy song song 4 domain agent (Customer/Order&Product/
   Payment/Delivery), mỗi agent gọi đúng 1 tool đọc CSV qua `data_layer.py` →
   `coordinator.merge_dossier()` gộp 4 fragment → Policy Agent áp `EC_POLICY_V2` (tự tính lại từ
   CSV, không tin fragment) → `coordinator.assemble()` → Verifier tính lại toàn bộ ground truth,
   validate schema, lọc evidence id sai → ghi `output/EC_xxx.json`.
2. Toàn bộ số liệu trong output được tính lại từ CSV gốc ở tầng `tools.py`/`policy_rules.py`/
   `verifier.py`; nội dung `customer_request.message` không được đưa vào bất kỳ lời gọi LLM nào —
   nó chỉ là ngữ cảnh, không phải nguồn sự thật.
3. `tests/test_policy_rules.py` (9 test, không cần CSV/LLM) cover các dòng bảng `EC_POLICY_V2` và
   2 case rìa mà README không định nghĩa `primary_issue` tường minh.
4. Routing và việc kiểm tra đúng/sai là quyết định cố định theo case, giao cho LLM chỉ thêm rủi ro
   không thêm giá trị (xem mục 5); 5 agent domain dùng LLM để gọi đúng tool và format lại kết quả
   đã đúng sẵn vào schema.
5. `logging/trace.jsonl` không có `event_type: "error", stage: "intake"` nào cho 50 case thật (đều
   verify qua); test độc lập xác nhận nhánh reject hoạt động đúng với input giả (xem mục 6).

## 8. Cam kết của thành viên

- [] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x ] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x ] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x ] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x ] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Hồ Thúy Hằng
**Ngày xác nhận:** 2026-08-05

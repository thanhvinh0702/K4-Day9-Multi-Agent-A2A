# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung                                 |
| --------------- | ---------------------------------------- |
| Họ và tên       | Trần Minh Hiển                           |
| MSSV            | 01300                                    |
| Khóa/Lớp        | K4                                       |
| Vai trò chính   | Core System Architect & Verification Engineer |
| Ngày hoàn thành | 2026-08-05                               |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| ------------------ | ------------------ | -------------- | ----------------- | ---------- |
| Multi-Agent Orchestration & Core Pipeline | `main.py`, `src/agents/coordinator_agent.py` | `input/EC_XXX.json`, Olist CSVs (`data/`) | JSON output chuẩn trong `output/EC_XXX.json` & trace log | Hoàn thành |
| Policy Rule Engine & LLM Verification | `src/agents/policy_agent.py`, `src/agents/verifier_agent.py` | Bằng chứng từ 4 agent domain + `EC_POLICY_V2` | Primary/secondary issue, responsible party, financial refund, array limits & null constraints | Hoàn thành |
| Data Quality & Trace Auditing | `src/generate_inputs.py`, `src/tracer.py`, `tests/test_validation.py` | Olist raw datasets | 50 input cases `EC_001.json`-`EC_050.json`, `logging/trace.jsonl`, `logging/metadata.json` | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --------- | ----------------------------- | ------- |
| Tích hợp & Debugging LLM API | Tích hợp client Groq (`llama-3.1-8b-instant`) & OpenAI (`gpt-4o-mini`) | Xử lý fallback tất định khi LLM timeout/error, giúp pipeline 50 case chạy 100% không bị ngắt quãng |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --------------------- | --------------------------- | ----------------- | ------------- |
| Xây dựng khung Multi-Agent Hybrid | `main.py`, `src/agents/coordinator_agent.py`, `src/agents/policy_agent.py`, `src/agents/verifier_agent.py` | Pipeline chạy thông suốt 50/50 cases, đối soát dữ liệu chính xác 100% | `python3 main.py` |
| Bộ kiểm thử & đối soát tự động | `tests/test_validation.py`, `src/generate_inputs.py` | Sinh chuẩn 50 input cases và bộ test kiểm tra array bounds, null constraints, policy priority | `pytest tests/test_validation.py` |
| Trace & Metadata Logging | `src/tracer.py`, `logging/trace.jsonl`, `logging/metadata.json` | Log 1500+ dòng trace chi tiết từng bước handoff và LLM call | `cat logging/metadata.json` |

Nêu một output cụ thể mà phần việc của bạn tạo ra hoặc giúp xác minh:

File nén `output.zip` chứa đúng 50 JSON outputs từ `EC_001.json` đến `EC_050.json`, đạt 100% hợp lệ về schema, giới hạn mảng (5/3/5/5/5/5/3/3/20/5) và tính toán tài chính làm tròn 2 chữ số thập phân.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Xử lý 50 khiếu nại thương mại điện tử từ dữ liệu Olist. Cần đối soát đa nguồn (orders, items, payments, sellers, customers, delivery dates) để tìm nguyên nhân gốc, bên chịu trách nhiệm, khoản tiền hoàn và hành động xử lý mà không bị lỗi float rounding hay hallucination từ LLM.

### Cách triển khai

1. Sử dụng thiết kế **Hybrid**: Các phép tính tiền (`expected_total_brl`, `difference_brl`), chênh lệch giờ giao hàng (`delivery_variance_hours`, `handoff_variance_hours`) và các quy tắc ưu tiên trong `EC_POLICY_V2` được thực hiện hoàn toàn tất định bằng Python/Pandas để đảm bảo độ chính xác tuyệt đối (100% precision đến 2 chữ số thập phân).
2. LLM (`llama-3.1-8b-instant` / Groq) được tích hợp cho 3 nhiệm vụ suy luận chính: (1) Coordinator tổng hợp handoff note liên domain, (2) Policy Agent tự tái suy luận độc lập để chấm `confidence` score (0.0-1.0), (3) Verifier Agent audit mâu thuẫn nội tại trước khi ghi file.

### Input, output và contract

| Thành phần | Mô tả |
| ---------- | ------ |
| Input | `input/EC_XXX.json` (chứa `claimed_order_id`, `investigation_scope`, `policy_version`) |
| Output | `output/EC_XXX.json` (chứa `case_assessment`, `affected_entities`, `customer_context`, `product_context`, `delivery_analysis`, `payment_reconciliation`, `root_cause_analysis`, `evidence_ids`, `financial_resolution`, `resolution_actions`) |
| Module phụ thuộc | `src/data_loader.py`, `src/agents/*.py`, `src/llm_client.py` |
| Module sử dụng output | Submission zip (`output.zip`) & `logging/trace.jsonl` |
| Điều kiện lỗi cần xử lý | Order bị hủy/hết hàng nhưng 0 item row (`null` handling cho expected_total/reconciled, mảng rỗng cho items/sellers/products), LLM API failure (dự phòng tất định qua fallback logic) |

### Cách xác minh

```bash
python3 main.py
```

- **Kết quả mong đợi:** Hệ thống xử lý 50/50 cases, ghi metadata vào `logging/metadata.json` và đóng gói `output.zip`.
- **Kết quả thực tế:** Đã xử lý 50/50 cases thành công, tạo `output.zip` đúng 50 file JSON.
- **Artifact/log:** `logging/trace.jsonl`, `logging/metadata.json`, `output.zip`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Lựa chọn giữa việc để LLM hoàn toàn tự sinh JSON output (Pure LLM-Agent) hay kết hợp Python Rule-Engine + LLM Verification (Hybrid Architecture).
- **Các phương án đã cân nhắc:**
  1. *Option A (Pure LLM)*: Đưa toàn bộ CSV context vào prompt và bảo LLM tính toán + sinh JSON.
  2. *Option B (Hybrid Architecture)*: Python làm tính toán số học, ngày tháng và áp dụng bảng priority rule `EC_POLICY_V2` tất định. LLM tham gia tổng hợp handoff note, double-check phán quyết, chấm confidence và audit mâu thuẫn.
- **Phương án đã chọn:** Option B (Hybrid Architecture).
- **Lý do:** Bài lab yêu cầu độ chính xác tài chính tuyệt đối (làm tròn 2 chữ số thập phân, sai số <= 0.10 BRL) và ràng buộc schema nghiêm ngặt (mảng rỗng khi 0 item). LLM tự do tính toán rất dễ gặp rủi ro hallucination/làm tròn sai. Option B vừa đảm bảo 100% correctness tài chính vừa phát huy đúng thế mạnh suy luận và audit của LLM.
- **Bằng chứng quyết định phù hợp:** 50/50 cases ra kết quả chính xác 100% đối soát tiền/phí và không bị trượt bất kỳ hard-gate rule nào trong bộ test.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Khi chạy case đơn hàng bị hủy hoặc không khả dụng (VD: `EC_004`, `EC_007`-`EC_012`), order trong dữ liệu Olist không có item row nào (`num_items == 0`), dẫn đến lỗi `ZeroDivisionError` / `KeyError` khi truy nhập `item_ids`, `product_ids`, `seller_ids`, `shipping_limit_date` và tính toán `expected_total_brl`.
- **Lệnh hoặc bước tái hiện:** `python3 main.py` với `input/EC_007.json` (order_id `8e24261a7e58791d10cb1bf9da94df5c`).
- **Nguyên nhân gốc:** Code ban đầu mặc định order nào cũng có ít nhất 1 item row, không kiểm tra trường hợp `num_items == 0` theo đúng yêu cầu mục 4 của đề bài ("Với order không có item row, `expected_total_brl`, `difference_brl` và `reconciled` phải là `null`; item, seller, product, category và seller handoff để mảng rỗng").
- **Cách xử lý:** Bổ sung nhánh xử lý đặc biệt trong `OrderProductAgent`, `PaymentAgent`, `DeliveryAgent`, `PolicyAgent` và `VerifierAgent`. Khi `items` rỗng, gán `expected_total_brl`, `difference_brl`, `reconciled` = `None` (`null` trong JSON), các mảng entities liên quan gán `[]`.
- **Cách xác minh sau khi sửa:** Chạy `python3 main.py` và kiểm tra file `output/EC_007.json` ➔ `expected_total_brl: null`, `item_ids: []`, `seller_ids: []`.
- **Điều học được:** Cần phải đọc kỹ các yêu cầu xử lý giá trị khuyết/rỗng (edge cases & null constraints) trong Business Spec trước khi viết code logic.

## 7. Hiểu biết về luồng end-to-end

Giải thích ngắn gọn bằng lời của bạn:

1. **Dữ liệu đi từ Crossref đến vector index như thế nào?**  
   Dữ liệu thô từ Crossref (API/JSON) được nạp vào, làm sạch metadata, chia nhỏ thành các đoạn text (chunks), sau đó thông qua mô hình Embedding (như SentenceTransformers hoặc OpenAI Embeddings) để chuyển hóa thành các vector không gian nhiều chiều và lưu trữ vào Vector Index (như FAISS/Chroma/Qdrant) kèm metadata để phục vụ truy vấn tương đồng.

2. **Evaluation set và ground-truth document IDs dùng để đo retrieval/answer quality ra sao?**  
   Evaluation set chứa danh sách câu hỏi kèm `ground_truth_doc_ids` (hoặc câu trả lời mẫu). Để đo Retrieval Quality, hệ thống so sánh các document ID được tìm kiếm ra với ground-truth (dùng các chỉ số MRR, Hit Rate@K, Precision@K, Recall@K). Để đo Answer Quality, hệ thống so sánh câu trả lời của LLM với ground-truth (dùng ROUGE, BLEU, hoặc LLM-as-a-Judge về độ trung thực/faithfulness).

3. **Quality checks khác freshness monitoring ở điểm nào trong bài lab?**  
   - *Quality checks*: Kiểm tra tính đúng đắn, toàn vẹn của dữ liệu và hệ thống tại thời điểm chạy (như schema validation, null constraint, accuracy, array bounds, format tài chính).  
   - *Freshness monitoring*: Kiểm tra độ tươi/mới của dữ liệu theo thời gian (đảm bảo index/database được cập nhật dữ liệu mới nhất từ nguồn, phát hiện dữ liệu lỗi thời hoặc outdated checkpoint).

4. **Vì sao phải dùng cùng test set cho baseline, corrupted và repaired?**  
   Để đảm bảo tính công bằng và nhất quán tuyệt đối trong quá trình thực nghiệm (controlled experiment). Khi cố định cùng một test set, sự thay đổi của các chỉ số đo lường (metrics) giữa baseline, corrupted và repaired mới phản ánh đúng tác động của việc phá hoại dữ liệu (corruption) và hiệu quả của cơ chế sửa chữa (repair pipeline).

5. **Repair được xem là thành công dựa trên artifact và metric nào?**  
   Repair được xem là thành công khi các chỉ số (metrics) của hệ thống sau khi repair khôi phục về mức tương đương hoặc cao hơn baseline (VD: Accuracy/Hit Rate/MRR ➔ baseline level), đồng thời các artifact được tạo ra (log trace, fixed index, validation report, output files) xác nhận 100% test case vượt qua các kiểm tra ràng buộc mà không còn lỗi.

## 8. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Trần Minh Hiển  
**Ngày xác nhận:** 2026-08-05

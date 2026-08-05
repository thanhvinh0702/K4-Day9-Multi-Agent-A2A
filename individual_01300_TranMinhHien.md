# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung             |
| --------------- | -------------------- |
| Họ và tên       | Trần Minh Hiển       |
| MSSV            | 01300                |
| Khóa/Lớp        | K4                   |
| Vai trò chính   | Lead Multi-Agent Architect & Backend Developer |
| Ngày hoàn thành | 2026-08-05           |

---

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Multi-Agent Architecture | `architecture.md` | Đề bài `README.md` & `EC_POLICY_V2` | Sơ đồ Mermaid & mô tả chi tiết handoffs | Hoàn thành |
| Data Loading Engine | `src/data_loader.py` | 9 CSV datasets trong `data/` | Indexed DataFrame lookups cho 7 agents | Hoàn thành |
| Specialized Agents | `src/agents/*.py` | Case JSON & CSV Data | Context objects & Policy evaluation | Hoàn thành |
| Coordinator & Verifier | `src/agents/coordinator_agent.py`, `verifier_agent.py` | Input Case JSON | 50 Verified Output JSONs & `logging/trace.jsonl` | Hoàn thành |

---

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Xây dựng Multi-Agent Pipeline | `main.py`, `src/agents/` | 50 file JSON chuẩn trong `output/` | `python3 main.py` |
| Kiểm định Schema & Evidence ID | `src/agents/verifier_agent.py` | 0 False Positive Evidence, đúng mảng max | Re-run verifier check |
| Tạo Zip nộp bài | `output.zip` | Archive chứa 50 JSON | `unzip -l output.zip` |

---

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết
Bài toán yêu cầu điều tra 50 khiếu nại thương mại điện tử trên dữ liệu Olist. Một khiếu nại không thể chỉ tin lời khách hàng mà phải đối soát chéo nhiều nguồn dữ liệu (Order, Customer, Items, Payments, Delivery, Sellers) để xác định đúng Primary Issue, Bên chịu trách nhiệm, Refund BRL, và các Action cần thiết.

### Cách triển khai
- Sử dụng mô hình Handoff Multi-Agent:
  - `CustomerAgent`: Truy xuất `customer_unique_id` và các order lịch sử.
  - `OrderProductAgent`: Trích xuất items, sellers, products, categories.
  - `PaymentAgent`: Tính toán tổng tiền items + freight, so sánh với payment tổng để xác định `reconciled` và `split_payment`.
  - `DeliveryAgent`: Tính `delivery_variance_hours` và `handoff_variance_hours` (xác định seller giao hàng trễ).
  - `PolicyAgent`: Đánh giá quy tắc `EC_POLICY_V2` theo thứ tự ưu tiên nghiêm ngặt.
  - `VerifierAgent`: Kiểm tra schema, giới hạn mảng (max 5/3/20), định dạng Evidence ID trước khi xuất JSON.

### Cách xác minh

```bash
python3 main.py
```

- **Kết quả mong đợi:** 50/50 cases được xử lý thành công, không bị hard-gate.
- **Kết quả thực tế:** Processed 50/50 cases, tạo file `output.zip` chứa 50 file JSON hợp lệ.

---

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Lựa chọn giữa gọi LLM API ngoài vs Xây dựng Handoff Multi-Agent Engine bằng Python.
- **Phương án đã chọn:** Xây dựng Handoff Engine Python dựa trên mã quy tắc nghiệp vụ định hướng agent.
- **Lý do:** Tối ưu tốc độ, đạt độ chính xác 100% tính toán số giờ variance và số tiền BRL, tuân thủ giới hạn model <= 10B params và tránh rủi ro ngắt kết nối API khi chấm bài.

---

## 6. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end.
- [x] Đã chạy kiểm chứng thành công.
- [x] Báo cáo không chứa `.env` hay API key.

**Họ và tên:** Trần Minh Hiển  
**Ngày xác nhận:** 2026-08-05

# Báo cáo cá nhân — Day 9: Multi-Agent A2A

> Cần đổi tên file thành `individual_<5 số cuối MSSV>_<HọVàTên>.md` và điền ba trường cá nhân trước khi nộp.

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
|---|---|
| Họ và tên | [ĐIỀN HỌ TÊN] |
| MSSV | [ĐIỀN MSSV] |
| Khóa/Lớp | K4 |
| Vai trò chính | Tích hợp policy, verifier và pipeline A2A |
| Ngày hoàn thành | 2026-08-05 |

## 2. Vai trò và phạm vi công việc

| Module/deliverable | File/hàm phụ trách | Input | Output | Trạng thái |
|---|---|---|---|---|
| Điều phối case | `src/resolver.py::resolve_case` | Input case và datastore | Verified case output | Hoàn thành |
| Policy và consensus | `src/policy.py`, `src/openrouter_policy.py` | Immutable fact bundle | Normalized policy decision | Hoàn thành |
| Verification | `src/verifier.py` | Source CSV và output candidate | Pass hoặc lỗi cụ thể | Hoàn thành |
| Batch artifacts | `src/main.py` | 50 input JSON | Output, trace, metadata, ZIP | Hoàn thành |

Việc hỗ trợ ngoài phạm vi chính gồm kiểm tra payment/delivery contracts, bổ sung integration tests và hoàn thiện tài liệu kiến trúc.

## 3. Kết quả theo vai trò

| Nhiệm vụ | Artifact | Kết quả | Cách xác minh |
|---|---|---|---|
| Áp dụng EC_POLICY_V2 | `src/policy.py` | Đủ sáu primary issue theo đúng priority | `python -m unittest discover -v` |
| So sánh LLM với deterministic | `normalize_llm_decision()` | Chỉ nhận confidence khi toàn bộ business fields khớp | Unit tests policy mismatch/match |
| Exact verification | `VerifierAgent.verify_output()` | Recompute và đối chiếu toàn bộ ID, context, tiền, thời gian, policy, evidence | Integration test 50 case |
| Sinh artifacts an toàn | `src/main.py` | Staging trước khi commit và ZIP đúng danh sách case | Chạy `python -m src.main --no-llm` |

Artifact cụ thể: pipeline sinh và verify đủ 50 JSON, trace có đầy đủ vòng đời agent cho từng case, ZIP chứa đúng `EC_001.json` đến `EC_050.json`.

## 4. Giải thích kỹ thuật

### Vấn đề cần giải quyết

Một khiếu nại không thể kết luận từ message khách hàng. Hệ thống phải join order với item, seller, payment, customer và product; sau đó tính payment/delivery facts, áp dụng policy theo priority và chỉ sử dụng evidence tồn tại trong CSV.

### Cách triển khai

Coordinator được triển khai bằng `main()` và `resolve_case()`, không phải class. Ba domain agent nhận cùng order task và chạy độc lập. Kết quả được ghép thành `CaseFactBundle` frozen rồi gửi đồng thời cho deterministic policy và OpenRouter policy. Comparator giữ deterministic decision nếu LLM sai primary issue, cause, parties, refund hoặc action; nếu khớp thì chỉ nhận confidence đã clamp/làm tròn.

Verifier không chỉ kiểm tra ID là hợp lệ mà tự dựng lại expected facts từ CSV và so sánh exact. Batch sử dụng staging để lỗi ở một case không tạo tập artifact trộn giữa hai lượt chạy.

### Input, output và contract

| Thành phần | Mô tả |
|---|---|
| Input | `EC_*.json`, policy `EC_POLICY_V2`, claimed order ID |
| Domain output | Order/seller, payment và delivery facts |
| Policy output | Issue, cause, parties, refund, actions, confidence |
| Final output | JSON theo schema README |
| Điều kiện lỗi | Thiếu order/customer, policy không khớp, ID/evidence thiếu hoặc giả, schema/null/limit sai |

### Cách xác minh

```powershell
python -m unittest discover -v
python -m src.main --no-llm
```

- Kết quả mong đợi: tất cả test pass, sinh đủ 50 output và ZIP.
- Artifact: `output/`, `output.zip`, `logging/trace.jsonl`, `logging/metadata.json`.

## 5. Một quyết định kỹ thuật quan trọng

- Bối cảnh: LLM có thể hallucinate ID, số tiền hoặc policy decision.
- Phương án 1: cho LLM tạo trực tiếp output cuối.
- Phương án 2: tính deterministic facts/policy và dùng LLM như policy proposal độc lập.
- Lựa chọn: phương án 2.
- Lý do: giữ khả năng audit và reproducibility nhưng vẫn có model call/handoff thật.
- Bằng chứng: khi LLM mismatch hoặc request lỗi, integration tests xác nhận output vẫn dùng deterministic decision và pass exact verifier.

## 6. Một lỗi đã xử lý

- Triệu chứng: verifier cũ dùng phép kiểm tra `issubset`, vì vậy output thiếu item hoặc evidence vẫn có thể pass.
- Tái hiện: xóa một item ID khỏi output hợp lệ rồi gọi verifier.
- Nguyên nhân gốc: chỉ kiểm tra false-positive, không kiểm tra completeness và source order.
- Cách xử lý: verifier tự dựng expected arrays và dùng exact equality.
- Xác minh: test `test_verifier_rejects_missing_required_item` phải raise `ValueError`.
- Bài học: validation cần kiểm tra cả validity, completeness, ordering và business consistency.

## 7. Hiểu biết về luồng end-to-end

Input cung cấp claimed order ID. Coordinator giao việc cho OrderSellerAgent, PaymentAgent và DeliveryAgent. Các agent chỉ đọc datastore và trả computed facts. Customer history được tra bằng `customer_unique_id`. Cùng một fact bundle được gửi cho deterministic policy và OpenRouter policy. Comparator không cho LLM ghi đè business decision. Verifier dựng output, kiểm tra lại toàn bộ nguồn, sau đó `main()` mới commit JSON, trace, metadata và ZIP từ staging.

Baseline deterministic và lượt chạy có LLM dùng cùng input/CSV/policy. Vì vậy có thể đo model match/fallback mà không làm thay đổi correctness của các trường có thể kiểm chứng.

## 8. Cam kết

- [ ] Tôi đã điền đúng họ tên, MSSV và đổi tên file.
- [x] Nội dung phản ánh đúng pipeline và artifacts trong repo.
- [x] Tôi có thể giải thích luồng end-to-end.
- [x] Các kết quả ghi trong báo cáo đã được kiểm chứng bằng test/lượt chạy offline.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.

**Họ và tên:** [ĐIỀN HỌ TÊN]  
**Ngày xác nhận:** [ĐIỀN NGÀY]

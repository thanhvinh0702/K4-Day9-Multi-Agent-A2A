# Architecture — Multi-Agent E-commerce Dispute Resolution

## 1. Sơ đồ tổng thể

```text
Coordinator (`main` + `resolve_case`)
    │
    ├── Order & Seller Agent ──┐
    ├── Payment Agent ─────────┼──> immutable CaseFactBundle
    └── Delivery Agent ────────┘              │
                                  ┌───────────┴───────────┐
                                  v                       v
                      Deterministic Policy       OpenRouter Policy
                                  └───────────┬───────────┘
                                              v
                                      Policy Comparator
                                              │
                                              v
                                      Exact Verifier Agent
                                              │
                         JSON output + trace + metadata + ZIP
```

Hệ thống dùng kiến trúc hybrid. Các phép join, tiền, thời gian và policy chính thức chạy deterministic. OpenRouter là một policy reviewer độc lập; LLM chỉ được cung cấp facts đã tính và không có quyền ghi đè quyết định nghiệp vụ.

## 2. Coordinator

Coordinator không phải class.

- `src/main.py::main()` nạp `.env`, cấu hình, CSV, duyệt input bằng `tqdm`, ghi JSON, metadata và ZIP.
- `src/resolver.py::resolve_case()` khởi tạo các agent và điều phối đúng một case.

Luồng `resolve_case()`:

1. Kiểm tra `policy_version` và claimed order.
2. Giao task và chạy ba domain agent độc lập bằng thread pool.
3. Ghép kết quả thành `CaseFactBundle` frozen.
4. Gửi cùng một fact bundle cho hai policy branch độc lập.
5. Comparator normalize hai quyết định.
6. Verifier tự dựng lại expected facts từ CSV và exact-check output.
7. Ghi vào staging; chỉ commit JSON/trace/metadata/ZIP sau khi toàn batch pass.

Customer history được tra deterministic trong `resolve_case()` bằng `customer_unique_id`. Product/category context được thu thập trong Order & Seller Agent để vẫn đáp ứng output schema mà không tạo thêm agent ngoài kiến trúc.

## 3. OrderSellerAgent

File: `src/agents/order_seller_agent.py`.

Agent đọc order status, item, seller, product và category. Với từng item, agent so sánh trực tiếp:

```text
order_delivered_carrier_date > item.shipping_limit_date
```

Kết quả handoff gồm:

- `order_status`;
- item IDs và seller IDs theo thứ tự nguồn;
- `late_handoff_item_ids`;
- `late_handoff_seller_ids`;
- seller handoff analysis;
- product/category context và các cờ multi-item/multi-seller/multiple-category.

Policy seller delay dùng so sánh item-level. Output delivery dùng shipping limit sớm nhất của mỗi seller để tạo một record ổn định cho seller đó.

## 4. PaymentAgent

File: `src/agents/payment_agent.py`.

Agent chỉ nhận `order_id` và tự đọc item/payment từ datastore. Nó không phụ thuộc output của OrderSellerAgent, vì vậy ba domain branch có thể thực thi độc lập.

Agent tính bằng `Decimal`:

```text
item_total_brl     = sum(item.price)
freight_total_brl  = sum(item.freight_value)
expected_total_brl = item_total_brl + freight_total_brl
payment_total_brl  = sum(payment.payment_value)
difference_brl     = payment_total_brl - expected_total_brl
reconciled         = abs(difference_brl) <= 0.10
```

Tiền được làm tròn hai chữ số bằng `ROUND_HALF_UP`. `payment_installments` không được nhân vào `payment_value`. Nếu order không có item, `expected_total_brl`, `difference_brl` và `reconciled` là `null`.

## 5. DeliveryAgent

File: `src/agents/delivery_agent.py`.

Agent so sánh:

```text
order_delivered_customer_date
    với
order_estimated_delivery_date
```

Handoff có hai cờ loại trừ nhau khi đủ timestamp:

- `delivered_late`;
- `delivered_within_estimate`.

Phân loại dùng timestamp gốc; `delivery_variance_hours` chỉ được làm tròn khi đưa ra output.

## 6. DeterministicPolicyAgent

File: `src/policy.py`.

Policy engine áp dụng rule đúng thứ tự:

1. `canceled_order_paid`;
2. `unavailable_order_paid`;
3. `late_delivery_seller`;
4. `late_delivery_logistics`;
5. `valid_split_payment`;
6. `unsupported_late_claim`.

Kết quả gồm `primary_issue`, secondary issues, `cause_code`, responsible parties, refund, ordered actions, case status và confidence mặc định `1.0`. Đây là nguồn quyết định nghiệp vụ có thẩm quyền.

## 7. OpenRouterPolicyAgent

Files: `src/openrouter_policy.py` và `src/llm.py`.

Đây là thành phần LLM duy nhất. Mỗi case gọi tối đa một request tới OpenRouter Chat Completions API:

- model mặc định `qwen/qwen-2.5-7b-instruct`;
- có thể đổi qua `OPENROUTER_MODEL`;
- `temperature = 0`;
- response dùng JSON Schema;
- chỉ nhận computed facts, không nhận toàn bộ CSV/raw rows;
- không nhận deterministic decision làm câu trả lời mẫu.

Contract LLM:

```json
{
  "primary_issue": "late_delivery_seller",
  "cause_code": "SELLER_HANDOFF_AFTER_LIMIT",
  "responsible_parties": [
    {"party_type": "seller", "party_id": "<seller_id>"}
  ],
  "recommended_refund_brl": 18.27,
  "primary_action": "refund_freight",
  "confidence": 0.95
}
```

Nếu thiếu key, tắt LLM, timeout, HTTP error hoặc JSON sai schema, `OpenRouterPolicyAgent` trả fallback thay vì làm pipeline dừng.

## 8. VerifierAgent và normalize

File: `src/verifier.py`.

`normalize_llm_decision()` so sánh toàn bộ business contract:

- `primary_issue`;
- `cause_code`;
- toàn bộ `responsible_parties` theo thứ tự;
- `recommended_refund_brl`;
- action chính.

Nếu bất kỳ field nào khác deterministic result, toàn bộ business decision dùng deterministic result, kể cả confidence mặc định. Nếu tất cả khớp, chỉ confidence của LLM được nhận và clamp vào `[0, 1]`.

`VerifierAgent.build_output()`:

1. Tạo JSON cuối từ facts và normalized decision.
2. Kiểm tra exact schema keys và giới hạn array.
3. Tự tính lại item/payment/seller/product/customer/delivery từ CSV.
4. Exact-check affected IDs, context, secondary issues, policy, parties, refund, actions và evidence; thiếu một ID cũng fail.
5. Kiểm tra null, timestamp, confidence và cấm NaN/Infinity.
6. Chỉ trả output nếu mọi hard check đều pass.

## 9. Trace, metadata và ZIP

- `logging/trace.jsonl` chứa đủ ba task assignment, ba result handoff, hai policy branch, comparator và verifier result. Không chứa API key.
- `logging/metadata.json` ghi model, provider, số call, token usage, số LLM match và số fallback.
- `output/EC_001.json` đến `output/EC_050.json` là output chấm điểm.
- `output.zip` được tự động tạo khi chạy toàn bộ input, chứa các JSON ở root ZIP và không chứa source/log/secret.
- `--case EC_001` chỉ chạy thử một case và không ghi đè ZIP nộp bài.
- `--no-llm` dùng để regression offline; pipeline vẫn chạy hoàn toàn bằng deterministic policy.
- Mọi artifact được tạo trong thư mục staging. Nếu một case fail, output/trace/metadata/ZIP của lượt chạy trước được giữ nguyên.

## 10. Failure policy

```text
Domain calculation error  -> dừng case, không ghi output sai
Deterministic policy error -> dừng case, không ghi output sai
OpenRouter error          -> trace fallback, tiếp tục deterministic
LLM business mismatch     -> trace mismatch, dùng deterministic
Verifier error            -> dừng case, không ghi output sai
```

Thiết kế bảo đảm OpenRouter giúp tạo một policy proposal độc lập nhưng correctness cuối cùng luôn được kiểm soát bằng dữ liệu và rule có thể kiểm chứng.

## 11. Customer claim verification

Nội dung `customer_request.message` được xem là claim không đáng tin cậy,
không phải evidence. OpenRouter chỉ phân loại claim; Verifier đối chiếu claim
đó với computed facts từ CSV. Claim sai được ghi `claim_supported_by_data=false`
trong trace và không được phép thay đổi primary issue, responsible party, refund,
action, ID, tiền hoặc timestamp.

Comparator chấp nhận LLM khi `primary_issue` khớp với policy đã xác minh bằng
dữ liệu. Các field phụ thuộc như cause, party, refund và action luôn được
canonicalize từ policy engine trước khi Verifier exact-check lần cuối.

Trước khi commit, Coordinator mở lại ZIP và hard-check rằng archive chứa đúng
danh sách JSON ở root, không có thư mục `output/` hay file thừa.

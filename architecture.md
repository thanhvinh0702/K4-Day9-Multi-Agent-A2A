# Kiến trúc Multi-Agent E-commerce Dispute Resolution

## 1. Mục tiêu và nguyên tắc

Hệ thống xử lý độc lập 50 case khiếu nại Olist theo `EC_POLICY_V2`. Kết quả phải tái lập được, chỉ dùng bằng chứng tồn tại trong CSV và không suy diễn tracking, refund ledger hay sự kiện giao sai/giao thiếu.

Các agent trong bài là các software agent có vai trò, contract và handoff tách biệt. Phiên bản hiện tại không dùng LLM: join, phép tính và quyết định policy được thực hiện bằng Python deterministic. Vì vậy giới hạn model không quá 10B được đáp ứng và không cần API key.

## 2. Sơ đồ agent

```text
EC_*.json
    |
    v
Coordinator Agent
    |-- request --> Customer Agent ----------- customer/history facts ---|
    |-- request --> Order & Product Agent ---- item/seller/product facts -|
    |                                             |
    |                                             v
    |                                       Payment Agent
    |                                             |
    |-- request --> Delivery Agent ---------------| reconciliation/delivery
    |                                             v
    |                                        Policy Agent
    |                                             |
    |                                       policy decision
    |                                             v
    |<--------------------------------------- Coordinator
    |                                             |
    |                                             v
    |                                        Verifier Agent
    |                                             |
    v                                             v
output/EC_*.json                           logging/trace.jsonl
```

## 3. Vai trò và quyền truy cập

| Agent | Trách nhiệm | Dữ liệu được đọc | Output handoff |
|---|---|---|---|
| Coordinator | Nhận case, gọi agent, ghép schema và ghi output | Input case, kết quả agent | Output candidate |
| Customer | Xác định `customer_unique_id` và lịch sử order | Orders, customers | Customer facts |
| Order & Product | Lấy item, seller, product, category, tổng item/freight và shipping limit | Orders, items, products, sellers | Order/product facts |
| Payment | Tổng hợp payment row và đối soát | Payments và order facts | Payment facts |
| Delivery | Tính delivery/handoff variance | Order timestamps và shipping limits | Delivery facts |
| Policy | Áp dụng thứ tự ưu tiên `EC_POLICY_V2` | Tất cả domain facts | Issue, party, cause, refund, actions |
| Verifier | Kiểm tra schema, ID, evidence, null và giới hạn | Output candidate và data index | Pass hoặc lỗi có nguyên nhân |

Chỉ `Coordinator` ghi file output. Các domain agent chỉ đọc datastore. `TraceWriter` ghi một event cho từng handoff và ghi đè trace ở mỗi lượt chạy.

## 4. Contract chính

Các handoff dùng dictionary chỉ chứa fact đã được tính, không truyền prompt tự do:

- Customer facts: customer unique ID, tối đa 5 related order và cờ repeat customer.
- Order facts: source-ordered item/seller/product/category, tiền dạng `Decimal`, shipping limit sớm nhất theo seller.
- Payment facts: payment rows, tổng payment, expected total, difference và reconciled.
- Delivery facts: timestamp gốc, variance hai chữ số, late seller IDs.
- Policy decision: primary/secondary issue, root cause, responsible party, refund và ordered actions.

Thứ tự mảng được giữ theo lần xuất hiện đầu tiên trong CSV. Chỉ secondary issues và actions dùng thứ tự nghiệp vụ trong README.

## 5. Luồng xử lý

1. Coordinator kiểm tra `policy_version` và order có tồn tại.
2. Customer và Order/Product Agent tra cứu các domain độc lập.
3. Payment Agent nhận item/freight totals để đối soát payment.
4. Delivery Agent nhận shipping limit theo seller để tính handoff.
5. Policy Agent xét primary issue đúng thứ tự ưu tiên, sau đó thêm secondary issues và actions.
6. Coordinator tạo evidence từ order/item/payment, seller chịu trách nhiệm (nếu có) và policy code.
7. Verifier đối chiếu ID ngược lại datastore, kiểm tra null/limit/status.
8. Chỉ output đã pass verifier mới được ghi ra JSON.

## 6. Xử lý dữ liệu và sai số

- Tiền được cộng bằng `Decimal`, làm tròn `ROUND_HALF_UP` tới 0.01 BRL.
- Timestamp được parse trực tiếp theo giá trị CSV, không đổi múi giờ.
- Variance được tính theo tổng số giây chia 3600 và làm tròn hai chữ số.
- Order không có item trả `expected_total_brl`, `difference_brl`, `reconciled` là `null`; các mảng item/seller/product/category rỗng.
- `customer_id` chỉ nối order hiện tại; lịch sử khách hàng dùng `customer_unique_id`.

## 7. Audit và khả năng tái lập

- `logging/trace.jsonl`: handoff thật của lượt chạy mới nhất, không append.
- `logging/metadata.json`: model, framework, runtime, policy và số case.
- Mỗi output đi qua cùng một pipeline và verifier.
- Pipeline chỉ dùng Python standard library, không cần mạng hoặc secret.


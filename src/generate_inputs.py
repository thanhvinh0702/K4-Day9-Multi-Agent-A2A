import os
import json
import pandas as pd
from typing import List, Dict, Any

def generate_50_input_cases(data_dir: str = "data", input_dir: str = "input"):
    os.makedirs(input_dir, exist_ok=True)

    orders_df = pd.read_csv(os.path.join(data_dir, "olist_orders_dataset.csv"))
    payments_df = pd.read_csv(os.path.join(data_dir, "olist_order_payments_dataset.csv"))
    items_df = pd.read_csv(os.path.join(data_dir, "olist_order_items_dataset.csv"))

    # Join payment totals
    pay_sums = payments_df.groupby("order_id")["payment_value"].sum().reset_index()
    orders_with_pay = pd.merge(orders_df, pay_sums, on="order_id", how="left")
    
    # 1. Canceled paid orders
    canceled_orders = orders_with_pay[(orders_with_pay["order_status"] == "canceled") & (orders_with_pay["payment_value"] > 0)]["order_id"].tolist()
    
    # 2. Unavailable paid orders
    unavailable_orders = orders_with_pay[(orders_with_pay["order_status"] == "unavailable") & (orders_with_pay["payment_value"] > 0)]["order_id"].tolist()

    # 3. Orders with split payments
    pay_counts = payments_df.groupby("order_id").size().reset_index(name="pay_count")
    split_pay_orders = pay_counts[pay_counts["pay_count"] >= 2]["order_id"].tolist()
    delivered_split = orders_with_pay[(orders_with_pay["order_id"].isin(split_pay_orders)) & (orders_with_pay["order_status"] == "delivered")]["order_id"].tolist()

    # 4. Delivered late orders
    orders_with_pay["delivered_dt"] = pd.to_datetime(orders_with_pay["order_delivered_customer_date"])
    orders_with_pay["estimated_dt"] = pd.to_datetime(orders_with_pay["order_estimated_delivery_date"])
    orders_with_pay["carrier_dt"] = pd.to_datetime(orders_with_pay["order_delivered_carrier_date"])
    
    late_orders = orders_with_pay[(orders_with_pay["order_status"] == "delivered") & (orders_with_pay["delivered_dt"] > orders_with_pay["estimated_dt"])]["order_id"].tolist()
    
    # 5. Delivered on-time orders
    ontime_orders = orders_with_pay[(orders_with_pay["order_status"] == "delivered") & (orders_with_pay["delivered_dt"] <= orders_with_pay["estimated_dt"])]["order_id"].tolist()

    # Pool candidates proportionally to get exactly 50 distinct orders
    candidates = []
    
    # Take up to 6 canceled
    candidates.extend(canceled_orders[:6])
    # Take up to 6 unavailable
    candidates.extend(unavailable_orders[:6])
    # Take up to 10 split pay
    candidates.extend([o for o in delivered_split if o not in candidates][:10])
    # Take up to 15 late orders
    candidates.extend([o for o in late_orders if o not in candidates][:15])
    # Take on-time orders to fill up to 50
    remaining_needed = 50 - len(candidates)
    candidates.extend([o for o in ontime_orders if o not in candidates][:remaining_needed])

    # Fill if still < 50
    if len(candidates) < 50:
        all_orders = orders_df["order_id"].tolist()
        candidates.extend([o for o in all_orders if o not in candidates][:50 - len(candidates)])

    candidates = candidates[:50]

    messages = [
        "Hãy điều tra khiếu nại, kiểm tra lịch sử khách hàng và đối soát toàn bộ order.",
        "Khách hàng báo chưa nhận được hàng đúng hẹn, đề nghị làm rõ trách nhiệm đơn vị vận chuyển hoặc người bán.",
        "Kiểm tra đơn hàng có thanh toán nhiều lần và xác minh khoản tiền khớp hay không.",
        "Yêu cầu đối soát chi tiết chi phí vận chuyển và kiểm tra thời gian bàn giao seller.",
        "Đơn hàng bị hủy nhưng tài khoản đã bị trừ tiền, yêu cầu hoàn tiền full ngay lập tức."
    ]

    print(f"Generating 50 input cases in '{input_dir}'...")
    for i, order_id in enumerate(candidates, start=1):
        case_num = f"EC_{i:03d}"
        msg = messages[(i - 1) % len(messages)]
        case_data = {
            "case_id": case_num,
            "customer_request": {
                "language": "vi",
                "message": msg,
                "claimed_order_id": order_id
            },
            "investigation_scope": {
                "include_customer_history": True,
                "include_product_context": True
            },
            "policy_version": "EC_POLICY_V2"
        }

        out_path = os.path.join(input_dir, f"{case_num}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(case_data, f, ensure_ascii=False, indent=2)

    print("50 input cases generated successfully.")

if __name__ == "__main__":
    generate_50_input_cases()

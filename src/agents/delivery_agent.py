import pandas as pd
from datetime import datetime
from typing import Dict, Any, List, Optional
from src.data_loader import DataLoader

def parse_dt(dt_str: Any) -> Optional[datetime]:
    if pd.isna(dt_str) or not dt_str or str(dt_str).strip() == "":
        return None
    try:
        return datetime.strptime(str(dt_str).strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime(str(dt_str).strip(), "%Y-%m-%d")
        except ValueError:
            return None

class DeliveryAgent:
    """Agent responsible for calculating delivery variances and auditing seller handoff SLAs."""

    def __init__(self, data_loader: DataLoader):
        self.data_loader = data_loader

    def analyze(self, order_dict: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, Any]:
        delivered_at_str = order_dict.get("order_delivered_customer_date")
        estimated_at_str = order_dict.get("order_estimated_delivery_date")
        carrier_handoff_str = order_dict.get("order_delivered_carrier_date")

        dt_delivered = parse_dt(delivered_at_str)
        dt_estimated = parse_dt(estimated_at_str)
        dt_carrier = parse_dt(carrier_handoff_str)

        delivery_variance_hours = None
        if dt_delivered and dt_estimated:
            diff_sec = (dt_delivered - dt_estimated).total_seconds()
            delivery_variance_hours = round(diff_sec / 3600.0, 2)

        is_late_delivery = False
        if delivery_variance_hours is not None and delivery_variance_hours > 0:
            is_late_delivery = True

        # Group items by seller_id to find shipping_limit_date
        seller_limits: Dict[str, Optional[datetime]] = {}
        seller_limits_str: Dict[str, str] = {}

        for item in items:
            seller_id = str(item.get("seller_id"))
            limit_str = item.get("shipping_limit_date")
            limit_dt = parse_dt(limit_str)

            if seller_id and limit_dt:
                if seller_id not in seller_limits or limit_dt < seller_limits[seller_id]:
                    seller_limits[seller_id] = limit_dt
                    seller_limits_str[seller_id] = str(limit_str).strip()

        seller_handoff_analysis = []
        late_handoff_seller_ids = []

        for seller_id, limit_dt in seller_limits.items():
            handoff_variance = None
            late_handoff = False

            if dt_carrier and limit_dt:
                diff_sec = (dt_carrier - limit_dt).total_seconds()
                handoff_variance = round(diff_sec / 3600.0, 2)
                if handoff_variance > 0:
                    late_handoff = True
                    late_handoff_seller_ids.append(seller_id)

            seller_handoff_analysis.append({
                "seller_id": seller_id,
                "shipping_limit_at": seller_limits_str.get(seller_id),
                "handoff_variance_hours": handoff_variance,
                "late_handoff": late_handoff
            })

        return {
            "delivered_at": str(delivered_at_str).strip() if pd.notna(delivered_at_str) and delivered_at_str else None,
            "estimated_delivery_at": str(estimated_at_str).strip() if pd.notna(estimated_at_str) and estimated_at_str else None,
            "carrier_handoff_at": str(carrier_handoff_str).strip() if pd.notna(carrier_handoff_str) and carrier_handoff_str else None,
            "delivery_variance_hours": delivery_variance_hours,
            "is_late_delivery": is_late_delivery,
            "seller_handoff_analysis": seller_handoff_analysis,
            "late_handoff_seller_ids": late_handoff_seller_ids
        }

from typing import Dict, Any, List
import pandas as pd
from src.data_loader import DataLoader

class PaymentAgent:
    """Agent responsible for payment reconciliation and split payment auditing."""

    def __init__(self, data_loader: DataLoader):
        self.data_loader = data_loader

    def analyze(self, claimed_order_id: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        payments = self.data_loader.get_order_payments(claimed_order_id)
        
        payment_ids = []
        payment_types = []
        payment_total_brl = 0.0

        for pay in payments:
            seq = pay.get("payment_sequential")
            payment_ids.append(f"{claimed_order_id}:{seq}")
            ptype = str(pay.get("payment_type"))
            if ptype and ptype not in payment_types:
                payment_types.append(ptype)
            val = pay.get("payment_value", 0.0)
            if pd.notna(val):
                payment_total_brl += float(val)

        payment_total_brl = round(payment_total_brl, 2)

        if not items:
            return {
                "currency": "BRL",
                "item_total_brl": 0.0,
                "freight_total_brl": 0.0,
                "expected_total_brl": None,
                "payment_total_brl": payment_total_brl,
                "difference_brl": None,
                "reconciled": None,
                "payment_types": payment_types,
                "payment_ids": payment_ids[:5],
                "is_split_payment": len(payments) >= 2
            }

        item_total_brl = sum(float(i.get("price", 0.0)) for i in items if pd.notna(i.get("price")))
        freight_total_brl = sum(float(i.get("freight_value", 0.0)) for i in items if pd.notna(i.get("freight_value")))
        
        item_total_brl = round(item_total_brl, 2)
        freight_total_brl = round(freight_total_brl, 2)
        expected_total_brl = round(item_total_brl + freight_total_brl, 2)

        difference_brl = round(payment_total_brl - expected_total_brl, 2)
        reconciled = bool(abs(difference_brl) <= 0.10)

        return {
            "currency": "BRL",
            "item_total_brl": item_total_brl,
            "freight_total_brl": freight_total_brl,
            "expected_total_brl": expected_total_brl,
            "payment_total_brl": payment_total_brl,
            "difference_brl": difference_brl,
            "reconciled": reconciled,
            "payment_types": payment_types,
            "payment_ids": payment_ids[:5],
            "is_split_payment": len(payments) >= 2
        }

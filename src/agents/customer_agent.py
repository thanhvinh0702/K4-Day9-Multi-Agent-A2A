from typing import Dict, Any, List
from src.data_loader import DataLoader

class CustomerAgent:
    """Agent responsible for customer identity resolution and historical orders lookup."""

    def __init__(self, data_loader: DataLoader):
        self.data_loader = data_loader

    def analyze(self, customer_id: str, claimed_order_id: str) -> Dict[str, Any]:
        customer = self.data_loader.get_customer(customer_id)
        if not customer:
            return {
                "customer_unique_id": None,
                "related_order_ids": []
            }
        
        customer_unique_id = str(customer.get("customer_unique_id"))
        all_orders = self.data_loader.get_customer_orders(customer_unique_id)
        
        # Historical order IDs exclude the claimed order ID
        related_order_ids = [oid for oid in all_orders if oid != claimed_order_id]
        # Array limit max 5 related order IDs
        related_order_ids = related_order_ids[:5]

        return {
            "customer_unique_id": customer_unique_id,
            "related_order_ids": related_order_ids,
            "has_repeat_orders": len(related_order_ids) > 0
        }

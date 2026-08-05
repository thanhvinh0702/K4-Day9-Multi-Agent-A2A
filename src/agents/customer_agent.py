from __future__ import annotations

from src.datastore import OlistDataStore


class CustomerAgent:
    name = "customer_agent"

    def __init__(self, store: OlistDataStore):
        self.store = store

    def investigate(self, order: dict[str, str]) -> dict:
        customer = self.store.customers.get(order["customer_id"])
        if not customer:
            raise ValueError(f"Customer not found: {order['customer_id']}")
        unique_id = customer["customer_unique_id"]
        related = [
            order_id
            for order_id in self.store.orders_by_customer_unique.get(unique_id, [])
            if order_id != order["order_id"]
        ]
        return {
            "customer_unique_id": unique_id,
            "related_order_ids": related[:5],
            "repeat_customer": bool(related),
        }


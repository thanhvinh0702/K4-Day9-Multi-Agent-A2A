from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from src.datastore import OlistDataStore
from src.utils import money, unique


class OrderProductAgent:
    name = "order_product_agent"

    def __init__(self, store: OlistDataStore):
        self.store = store

    def investigate(self, order: dict[str, str]) -> dict:
        order_id = order["order_id"]
        items = self.store.items_by_order.get(order_id, [])
        seller_ids = unique(row["seller_id"] for row in items)
        product_ids = unique(row["product_id"] for row in items)
        categories = unique(
            product["product_category_name"]
            for product_id in product_ids
            if (product := self.store.products.get(product_id))
            and product["product_category_name"]
        )
        limits: dict[str, list[str]] = defaultdict(list)
        for item in items:
            if item["shipping_limit_date"]:
                limits[item["seller_id"]].append(item["shipping_limit_date"])
        shipping_limits = {
            seller_id: min(limits[seller_id]) if limits[seller_id] else None
            for seller_id in seller_ids
        }
        item_total = sum((Decimal(row["price"]) for row in items), Decimal("0"))
        freight_total = sum(
            (Decimal(row["freight_value"]) for row in items), Decimal("0")
        )
        return {
            "items": items,
            "item_ids": [f"{order_id}:{row['order_item_id']}" for row in items],
            "seller_ids": seller_ids,
            "product_ids": product_ids,
            "category_names": categories,
            "shipping_limits": shipping_limits,
            "item_total": item_total,
            "freight_total": freight_total,
            "item_total_brl": money(item_total),
            "freight_total_brl": money(freight_total),
            "multi_item_order": len(items) >= 2,
            "multi_seller_order": len(seller_ids) >= 2,
            "multiple_categories": len(categories) >= 2,
        }


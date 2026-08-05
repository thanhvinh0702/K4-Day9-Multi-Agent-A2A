from __future__ import annotations

from collections import defaultdict

from src.datastore import OlistDataStore
from src.utils import hours_between, is_after, unique


class OrderSellerAgent:
    name = "order_seller_agent"

    def __init__(self, store: OlistDataStore):
        self.store = store

    def analyze(self, order: dict[str, str]) -> dict:
        order_id = order["order_id"]
        carrier_at = order["order_delivered_carrier_date"] or None
        items = self.store.items_by_order.get(order_id, [])
        seller_ids = unique(item["seller_id"] for item in items)
        product_ids = unique(item["product_id"] for item in items)
        categories = unique(
            product["product_category_name"]
            for product_id in product_ids
            if (product := self.store.products.get(product_id))
            and product["product_category_name"]
        )

        late_item_ids: list[str] = []
        late_seller_ids: list[str] = []
        limits_by_seller: dict[str, list[str]] = defaultdict(list)
        for item in items:
            limit = item["shipping_limit_date"] or None
            if limit:
                limits_by_seller[item["seller_id"]].append(limit)
            if is_after(carrier_at, limit):
                late_item_ids.append(f"{order_id}:{item['order_item_id']}")
                late_seller_ids.append(item["seller_id"])

        # Output schema reports one stable, earliest limit per seller. Policy uses
        # the item-level comparison above, as required by the architecture.
        seller_handoff_analysis = []
        for seller_id in seller_ids:
            limits = limits_by_seller.get(seller_id, [])
            earliest_limit = min(limits) if limits else None
            seller_handoff_analysis.append(
                {
                    "seller_id": seller_id,
                    "shipping_limit_at": earliest_limit,
                    "handoff_variance_hours": hours_between(
                        carrier_at or "", earliest_limit or ""
                    ),
                    "late_handoff": seller_id in late_seller_ids,
                }
            )

        return {
            "order_id": order_id,
            "order_status": order["order_status"],
            "carrier_handoff_at": carrier_at,
            "items": items,
            "item_ids": [f"{order_id}:{item['order_item_id']}" for item in items],
            "seller_ids": seller_ids,
            "late_handoff_item_ids": late_item_ids,
            "late_handoff_seller_ids": unique(late_seller_ids),
            "seller_handoff_analysis": seller_handoff_analysis,
            "product_ids": product_ids,
            "category_names": categories,
            "multi_item_order": len(items) >= 2,
            "multi_seller_order": len(seller_ids) >= 2,
            "multiple_categories": len(categories) >= 2,
        }

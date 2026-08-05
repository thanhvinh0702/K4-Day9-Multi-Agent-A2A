"""Pandas-based data access layer over the Olist CSVs.

Loaded once per process and indexed by the join keys documented in README.md
section 2. All downstream tools/agents must go through this module instead of
reading CSVs directly, so there is a single source of truth for lookups.
"""
from __future__ import annotations

import functools
from collections import defaultdict
from typing import Any

import pandas as pd

from .config import DATA_DIR

_TIMESTAMP_COLS = {
    "orders": [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ],
    "order_items": ["shipping_limit_date"],
}


def _read(name: str, timestamp_cols: list[str] | None = None) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / name, encoding="utf-8-sig")
    for col in timestamp_cols or []:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


class OlistData:
    def __init__(self) -> None:
        self.orders = _read("olist_orders_dataset.csv", _TIMESTAMP_COLS["orders"])
        self.order_items = _read("olist_order_items_dataset.csv", _TIMESTAMP_COLS["order_items"])
        self.order_payments = _read("olist_order_payments_dataset.csv")
        self.customers = _read("olist_customers_dataset.csv")
        self.products = _read("olist_products_dataset.csv")
        self.sellers = _read("olist_sellers_dataset.csv")
        self.category_translation = _read("product_category_name_translation.csv")

        self._orders_by_id: dict[str, dict[str, Any]] = {
            rec["order_id"]: rec for rec in self.orders.to_dict("records")
        }

        self._items_by_order: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for rec in self.order_items.sort_values("order_item_id").to_dict("records"):
            self._items_by_order[rec["order_id"]].append(rec)

        self._payments_by_order: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for rec in self.order_payments.sort_values("payment_sequential").to_dict("records"):
            self._payments_by_order[rec["order_id"]].append(rec)

        self._customers_by_id: dict[str, dict[str, Any]] = {
            rec["customer_id"]: rec for rec in self.customers.to_dict("records")
        }
        self._products_by_id: dict[str, dict[str, Any]] = {
            rec["product_id"]: rec for rec in self.products.to_dict("records")
        }
        self._sellers_by_id: dict[str, dict[str, Any]] = {
            rec["seller_id"]: rec for rec in self.sellers.to_dict("records")
        }
        self._category_en = dict(
            zip(
                self.category_translation["product_category_name"],
                self.category_translation["product_category_name_english"],
            )
        )

        # customer_unique_id -> ordered list of order_ids, for history lookups
        customer_unique_by_customer_id = dict(
            zip(self.customers["customer_id"], self.customers["customer_unique_id"])
        )
        orders_sorted = self.orders.sort_values("order_purchase_timestamp").to_dict("records")
        self._orders_by_customer_unique: dict[str, list[str]] = defaultdict(list)
        for rec in orders_sorted:
            cuid = customer_unique_by_customer_id.get(rec["customer_id"])
            if cuid is not None:
                self._orders_by_customer_unique[cuid].append(rec["order_id"])

    # ---- lookups -----------------------------------------------------

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        return self._orders_by_id.get(order_id)

    def get_items(self, order_id: str) -> list[dict[str, Any]]:
        return list(self._items_by_order.get(order_id, []))

    def get_payments(self, order_id: str) -> list[dict[str, Any]]:
        return list(self._payments_by_order.get(order_id, []))

    def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        return self._customers_by_id.get(customer_id)

    def get_product(self, product_id: str) -> dict[str, Any] | None:
        return self._products_by_id.get(product_id)

    def get_seller(self, seller_id: str) -> dict[str, Any] | None:
        return self._sellers_by_id.get(seller_id)

    def category_name_english(self, category_name: str | None) -> str | None:
        if category_name is None or (isinstance(category_name, float) and pd.isna(category_name)):
            return None
        return self._category_en.get(category_name, category_name)

    def get_related_order_ids(
        self, customer_unique_id: str, exclude_order_id: str, limit: int = 5
    ) -> list[str]:
        ids = [
            oid
            for oid in self._orders_by_customer_unique.get(customer_unique_id, [])
            if oid != exclude_order_id
        ]
        return ids[:limit]


@functools.lru_cache(maxsize=1)
def get_data() -> OlistData:
    return OlistData()

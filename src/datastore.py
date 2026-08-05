from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


class OlistDataStore:
    """Load Olist CSV data once and expose stable, source-ordered indexes."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.orders = self._by_key("olist_orders_dataset.csv", "order_id")
        self.customers = self._by_key("olist_customers_dataset.csv", "customer_id")
        self.products = self._by_key("olist_products_dataset.csv", "product_id")
        self.sellers = self._by_key("olist_sellers_dataset.csv", "seller_id")
        self.items_by_order = self._group("olist_order_items_dataset.csv", "order_id")
        self.payments_by_order = self._group("olist_order_payments_dataset.csv", "order_id")
        self.orders_by_customer_unique: dict[str, list[str]] = defaultdict(list)
        for order in self.orders.values():
            customer = self.customers.get(order["customer_id"])
            if customer:
                self.orders_by_customer_unique[customer["customer_unique_id"]].append(
                    order["order_id"]
                )

    def _read(self, filename: str) -> list[dict[str, str]]:
        path = self.data_dir / filename
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def _by_key(self, filename: str, key: str) -> dict[str, dict[str, str]]:
        return {row[key]: row for row in self._read(filename)}

    def _group(self, filename: str, key: str) -> dict[str, list[dict[str, str]]]:
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in self._read(filename):
            grouped[row[key]].append(row)
        return grouped


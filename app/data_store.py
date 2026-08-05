from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.config import DATA_DIR


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


class OlistDataStore:
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.data_dir = data_dir
        self.orders = _read_csv(data_dir / "olist_orders_dataset.csv")
        self.customers = _read_csv(data_dir / "olist_customers_dataset.csv")
        self.items = _read_csv(data_dir / "olist_order_items_dataset.csv")
        self.payments = _read_csv(data_dir / "olist_order_payments_dataset.csv")
        self.products = _read_csv(data_dir / "olist_products_dataset.csv")
        self.sellers = _read_csv(data_dir / "olist_sellers_dataset.csv")

        self.orders_by_id = {row["order_id"]: row for row in self.orders}
        self.customers_by_id = {row["customer_id"]: row for row in self.customers}
        self.products_by_id = {row["product_id"]: row for row in self.products}
        self.sellers_by_id = {row["seller_id"]: row for row in self.sellers}

        self.items_by_order: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in self.items:
            self.items_by_order[row["order_id"]].append(row)
        for rows in self.items_by_order.values():
            rows.sort(key=lambda r: int(r["order_item_id"]))

        self.payments_by_order: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in self.payments:
            self.payments_by_order[row["order_id"]].append(row)
        for rows in self.payments_by_order.values():
            rows.sort(key=lambda r: int(r["payment_sequential"]))

        self.orders_by_customer_unique_id: dict[str, list[str]] = defaultdict(list)
        for order in self.orders:
            customer = self.customers_by_id.get(order["customer_id"])
            if customer:
                self.orders_by_customer_unique_id[customer["customer_unique_id"]].append(order["order_id"])

    def get_case_records(self, order_id: str) -> dict[str, Any]:
        order = self.orders_by_id.get(order_id)
        if not order:
            raise KeyError(f"Unknown order_id: {order_id}")
        customer = self.customers_by_id.get(order["customer_id"])
        items = self.items_by_order.get(order_id, [])
        payments = self.payments_by_order.get(order_id, [])
        products = [self.products_by_id.get(row["product_id"], {}) for row in items]
        sellers = [self.sellers_by_id.get(row["seller_id"], {}) for row in items]
        return {
            "order": order,
            "customer": customer,
            "items": items,
            "payments": payments,
            "products": products,
            "sellers": sellers,
        }

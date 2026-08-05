import pandas as pd
from typing import Dict, Any, List
from src.data_loader import DataLoader

class OrderProductAgent:
    """Agent responsible for analyzing items, products, sellers, and product categories."""

    def __init__(self, data_loader: DataLoader):
        self.data_loader = data_loader

    def analyze(self, claimed_order_id: str) -> Dict[str, Any]:
        items = self.data_loader.get_order_items(claimed_order_id)

        if not items:
            return {
                "items": [],
                "item_ids": [],
                "seller_ids": [],
                "product_ids": [],
                "category_names": [],
                "is_multi_item": False,
                "is_multi_seller": False,
                "has_multiple_categories": False
            }

        item_ids = []
        seller_ids = []
        product_ids = []
        category_names = []

        for item in items:
            item_seq = item.get("order_item_id")
            item_ids.append(f"{claimed_order_id}:{item_seq}")

            seller_id = str(item.get("seller_id"))
            if seller_id and seller_id not in seller_ids:
                seller_ids.append(seller_id)

            product_id = str(item.get("product_id"))
            if product_id and product_id not in product_ids:
                product_ids.append(product_id)

            product_info = self.data_loader.get_product(product_id)
            if product_info:
                cat = product_info.get("product_category_name")
                if pd.notna(cat) and cat and str(cat) not in category_names:
                    category_names.append(str(cat))

        is_multi_item = len(items) >= 2
        is_multi_seller = len(seller_ids) >= 2
        has_multiple_categories = len(category_names) >= 2

        return {
            "items": items,
            "item_ids": item_ids[:5],
            "seller_ids": seller_ids[:3],
            "product_ids": product_ids[:5],
            "category_names": category_names[:5],
            "is_multi_item": is_multi_item,
            "is_multi_seller": is_multi_seller,
            "has_multiple_categories": has_multiple_categories
        }

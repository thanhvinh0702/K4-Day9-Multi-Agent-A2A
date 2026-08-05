import os
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional

class DataLoader:
    """Loads and provides fast indexed access to Olist E-commerce CSV datasets."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self._load_datasets()

    def _load_datasets(self):
        print("Loading Olist datasets...")
        self.orders_df = pd.read_csv(os.path.join(self.data_dir, "olist_orders_dataset.csv"))
        self.customers_df = pd.read_csv(os.path.join(self.data_dir, "olist_customers_dataset.csv"))
        self.order_items_df = pd.read_csv(os.path.join(self.data_dir, "olist_order_items_dataset.csv"))
        self.order_payments_df = pd.read_csv(os.path.join(self.data_dir, "olist_order_payments_dataset.csv"))
        self.products_df = pd.read_csv(os.path.join(self.data_dir, "olist_products_dataset.csv"))
        self.sellers_df = pd.read_csv(os.path.join(self.data_dir, "olist_sellers_dataset.csv"))
        
        translation_path = os.path.join(self.data_dir, "product_category_name_translation.csv")
        if os.path.exists(translation_path):
            self.category_translation_df = pd.read_csv(translation_path)
            self.category_map = dict(zip(
                self.category_translation_df['product_category_name'],
                self.category_translation_df['product_category_name_english']
            ))
        else:
            self.category_map = {}

        # Set indexes for O(1) lookups
        self.orders_by_id = self.orders_df.set_index("order_id")
        self.customers_by_id = self.customers_df.set_index("customer_id")
        self.products_by_id = self.products_df.set_index("product_id")

        print("Olist datasets loaded successfully.")

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        if order_id in self.orders_by_id.index:
            row = self.orders_by_id.loc[order_id]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            return row.to_dict()
        return None

    def get_customer(self, customer_id: str) -> Optional[Dict[str, Any]]:
        if customer_id in self.customers_by_id.index:
            row = self.customers_by_id.loc[customer_id]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            return row.to_dict()
        return None

    def get_customer_orders(self, customer_unique_id: str) -> List[str]:
        cust_ids = self.customers_df[self.customers_df["customer_unique_id"] == customer_unique_id]["customer_id"].tolist()
        orders = self.orders_df[self.orders_df["customer_id"].isin(cust_ids)]["order_id"].tolist()
        return orders

    def get_order_items(self, order_id: str) -> List[Dict[str, Any]]:
        df = self.order_items_df[self.order_items_df["order_id"] == order_id]
        return df.to_dict(orient="records")

    def get_order_payments(self, order_id: str) -> List[Dict[str, Any]]:
        df = self.order_payments_df[self.order_payments_df["order_id"] == order_id]
        return df.to_dict(orient="records")

    def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        if product_id in self.products_by_id.index:
            row = self.products_by_id.loc[product_id]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            res = row.to_dict()
            pt_cat = res.get("product_category_name")
            if pd.notna(pt_cat):
                res["category_english"] = self.category_map.get(str(pt_cat), str(pt_cat))
            else:
                res["category_english"] = None
            return res
        return None

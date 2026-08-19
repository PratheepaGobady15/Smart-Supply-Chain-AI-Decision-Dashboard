from __future__ import annotations

import json
import shutil
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
OLIST_DIR = RAW_DIR / "olist"
MANIFEST_FILE = RAW_DIR / "source_manifest.json"

KAGGLE_SOURCE_URL = "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce"
OLIST_LICENSE = "CC BY-NC-SA 4.0"

OLIST_FILES = {
    "olist_orders_dataset.csv": "https://raw.githubusercontent.com/Mylinear/Brazilian_E_Commerce_Public_Dataset_by_Olist/main/olist_orders_dataset.csv",
    "olist_order_items_dataset.csv": "https://raw.githubusercontent.com/Mylinear/Brazilian_E_Commerce_Public_Dataset_by_Olist/main/olist_order_items_dataset.csv",
    "olist_customers_dataset.csv": "https://raw.githubusercontent.com/Mylinear/Brazilian_E_Commerce_Public_Dataset_by_Olist/main/olist_customers_dataset.csv",
    "olist_sellers_dataset.csv": "https://raw.githubusercontent.com/Mylinear/Brazilian_E_Commerce_Public_Dataset_by_Olist/main/olist_sellers_dataset.csv",
    "olist_products_dataset.csv": "https://raw.githubusercontent.com/Mylinear/Brazilian_E_Commerce_Public_Dataset_by_Olist/main/olist_products_dataset.csv",
    "product_category_name_translation.csv": "https://raw.githubusercontent.com/Mylinear/Brazilian_E_Commerce_Public_Dataset_by_Olist/main/product_category_name_translation.csv",
}


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        print(f"Already Exists: {destination}")
        return

    print(f"Downloading: {url}")
    with urllib.request.urlopen(url, timeout=120) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)
    print(f"Saved: {destination}")


def write_source_manifest() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "dataset": "Brazilian E-Commerce Public Dataset By Olist",
        "primary_source": KAGGLE_SOURCE_URL,
        "license": OLIST_LICENSE,
        "usage_scope": "Non-commercial educational use with attribution and share-alike treatment.",
        "download_note": "The automated pipeline uses public raw CSV mirrors when Kaggle credentials are not available.",
        "files": OLIST_FILES,
    }
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def download_olist() -> None:
    OLIST_DIR.mkdir(parents=True, exist_ok=True)
    for filename, url in OLIST_FILES.items():
        download_file(url, OLIST_DIR / filename)


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    download_olist()
    write_source_manifest()
    print("\nOlist Real Data Download Complete.")
    print(f"Olist Folder: {OLIST_DIR}")
    print(f"Source Manifest: {MANIFEST_FILE}")


if __name__ == "__main__":
    main()

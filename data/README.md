# Data Sources

This Project Uses Real Public Data. Raw Data Files Are Not Committed Because The Source Files Are Large And Should Be Downloaded Reproducibly.

## Source: Brazilian E-Commerce Public Dataset By Olist

- Official Source: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
- License: CC BY-NC-SA 4.0
- Use Scope: Non-Commercial Academic And Portfolio Demonstration With Attribution
- Business Use: Category/State Demand Forecasting, Delivery Delay Risk, Freight Exposure, Seller/Region Performance

Files Used:

- `olist_orders_dataset.csv`
- `olist_order_items_dataset.csv`
- `olist_customers_dataset.csv`
- `olist_sellers_dataset.csv`
- `olist_products_dataset.csv`
- `product_category_name_translation.csv`

The Download Script Uses Public Raw CSV Mirrors When Kaggle Credentials Are Not Available.

## Expected Local Layout

```text
data/
  raw/
    source_manifest.json
    olist/
      olist_orders_dataset.csv
      olist_order_items_dataset.csv
      olist_customers_dataset.csv
      olist_sellers_dataset.csv
      olist_products_dataset.csv
      product_category_name_translation.csv
  processed/
    Built By The Pipeline
```

## Important Modeling Note

The Public Dataset Does Not Contain Real Warehouse On-Hand Inventory. This Project Therefore Models **Inventory Exposure** From Real Category/State Demand Forecasts, Demand Volatility, Price, Freight, And Delivery Risk. It Does Not Pretend To Have Real Warehouse Inventory.

Customer Identifiers Are Not Exported In The Dashboard Outputs. The Model Uses State, Seller State, Category, Order Value, Freight, Lead-Time Promise, And Timing Signals, Not Direct Customer Identity.

# Data License Audit

## Dataset

**Brazilian E-Commerce Public Dataset By Olist**

- Primary Source: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
- License: CC BY-NC-SA 4.0
- Use Scope: Non-Commercial Academic Demonstration With Attribution

## Project Use

This Is A Non-Commercial Academic Analytics Demonstration Project. The Pipeline Uses The Public Olist Dataset To Build A 28-Day Category/State Demand Forecast, Predict Late Delivery Risk, Simulate Supply Chain Scenarios, And Generate A Ranked Decision Action Queue.

## Guardrails

- Raw Source Data Is Not Committed To Git.
- Customer Identifier Columns Are Not Exported In Dashboard Outputs.
- The Demand Forecast Is Trained From Real Olist Purchase History Grouped By Product Category And Customer State.
- The Delivery Risk Classifier Predicts Late Delivery From Promise-Time And Order-Time Signals Such As Price, Freight, Product Category, Customer State, Seller State, Purchase Timing, Approval Lag, And Promised Lead Time.
- The Project Does Not Invent Warehouse On-Hand Inventory. Inventory Exposure Is A Modeled Planning Signal Built From Forecasted Demand, Demand Volatility, Freight, And Delivery Risk.

## Attribution Note

Because The Dataset Is Licensed CC BY-NC-SA 4.0, This Project Should Be Presented As A Non-Commercial Educational Demonstration With Source Attribution.

# Power BI Build Notes

Import These Files From The `outputs/` Folder:

- `executive_kpis.csv`
- `demand_forecast.csv`
- `inventory_exposure_recommendations.csv`
- `delivery_risk_predictions.csv`
- `seller_risk_summary.csv`
- `state_delivery_summary.csv`
- `what_if_scenarios.csv`
- `decision_action_queue.csv`
- `model_metrics.csv`
- `feature_importance.csv`

## Suggested Report Pages

1. Executive Control Tower
   - Cards: Forecast Units 28D, Forecast Revenue 28D, Orders Scored, Delivery ROC AUC.
   - Table: Top AI-Prioritized Actions From `decision_action_queue`.
   - KPI Band: High Inventory Exposure Lanes And High Delivery Risk Orders.

2. Demand Forecast And Inventory Exposure
   - Line Chart: `forecast_units` By `date`, Split By `category`.
   - Matrix: `forecast_units_28d`, `forecast_revenue_28d`, `inventory_exposure_score`, And `recommended_action`.
   - Slicers: Category, Store, State, Risk Level.

3. Delivery Risk Network
   - Map Or Filled Shape: Customer State By `avg_delivery_risk_score`.
   - Bar Chart: Seller Risk By `seller_state` And `seller_city`.
   - Table: Highest `late_delivery_probability` Orders.

4. What-If Scenario Simulator
   - Slicer: Scenario.
   - Matrix: Scenario Forecast Units, Service Risk, Revenue At Risk, Recommended Action.
   - Bar Chart: Revenue At Risk By Category And Scenario.

5. Model Explainability
   - Bar Chart: Feature Importance By Model.
   - Cards: MAE, MAPE, ROC AUC, Average Precision, F1.
   - Note: MAE Is The Primary Demand Forecast Metric Because Retail Unit Demand Is Intermittent.

## Suggested Relationships

- `inventory_exposure_recommendations[series_id]` To `demand_forecast[series_id]`
- `inventory_exposure_recommendations[series_id]` To `what_if_scenarios[series_id]`
- `state_delivery_summary[customer_state]` To `delivery_risk_predictions[customer_state]`

## Useful DAX Measures

```DAX
Forecast Revenue 28D = SUM(demand_forecast[forecast_revenue])

Forecast Units 28D = SUM(demand_forecast[forecast_units])

Average Inventory Exposure = AVERAGE(inventory_exposure_recommendations[inventory_exposure_score])

High Risk Actions =
CALCULATE(
    COUNTROWS(decision_action_queue),
    decision_action_queue[risk_level] = "High"
)

Average Delivery Risk = AVERAGE(delivery_risk_predictions[delivery_risk_score])

Scenario Revenue At Risk = SUM(what_if_scenarios[scenario_revenue_at_risk])
```

# Smart Supply Chain AI Decision Dashboard

**Live Dashboard:** [Open Smart Supply Chain AI Decision Dashboard](https://pratheepagobady15.github.io/Smart-Supply-Chain-AI-Decision-Dashboard/)

An Advanced Real-Data Supply Chain Decision Dashboard Built For Pratheepa Gobady.
It Uses The Public Olist Marketplace Dataset To Forecast Demand, Predict Late-Delivery Risk, Rank Inventory Exposure, And Simulate Operational Decisions.
The Website Presents A Field-Specific AI Decision Experience, Not A Basic KPI Dashboard, With Model Evidence And Downloadable Analytics Outputs.

This Project Combines Demand Forecasting, Delivery-Risk Prediction, Scenario Simulation, Explainability, And Power BI-Ready Data Products Into One Recruiter-Friendly AI Portfolio Project Using One Coherent Real Marketplace Dataset.

## What Makes It Different

Most Supply Chain Dashboards Stop At Charts. This Project Acts More Like A Decision Control Tower:

- Uses Real Public Data From The Brazilian E-Commerce Public Dataset By Olist.
- Trains A Working Demand Forecast Model For 28-Day Product-Category/State Forecasts.
- Trains A Working Late-Delivery Risk Model With Temporal Validation.
- Converts Model Outputs Into Inventory Exposure, Delivery Risk, What-If Scenarios, And Ranked Operational Actions.
- Publishes Clean CSV Outputs For Power BI And A Visually Advanced Browser Dashboard.
- Clearly Separates What Is Real From What Is Modeled Instead Of Pretending Public Data Has Warehouse Inventory On Hand.

## Project Outputs

```text
outputs/
  demand_forecast.csv
  inventory_exposure_recommendations.csv
  delivery_risk_predictions.csv
  seller_risk_summary.csv
  state_delivery_summary.csv
  what_if_scenarios.csv
  executive_kpis.csv
  decision_action_queue.csv
  model_metrics.csv
  feature_importance.csv

web/
  index.html
  styles.css
  app.js
  data/dashboard_data.js
```

## Real Data Sources

- Brazilian E-Commerce Public Dataset By Olist: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
- License: CC BY-NC-SA 4.0
- Use Scope: Non-Commercial Academic And Portfolio Demonstration With Attribution

Raw Data Files Are Not Committed Because They Are Large. See `data/README.md` For The Expected Local Layout And Download Notes.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Run The Real-Data Pipeline

```powershell
python src\download_real_data.py
python src\build_real_data_outputs.py
```

## Validate The Project

```powershell
python tests\validate_real_data_outputs.py
```

The Validation Script Checks That Required Outputs Exist, The Real-Data KPIs Are Present, The Models Produced Usable Metrics, And The Dashboard JSON Is Ready.

## Open The Dashboard

Open The Live Dashboard:

```text
https://pratheepagobady15.github.io/Smart-Supply-Chain-AI-Decision-Dashboard/
```

Or Open This File Locally In A Browser:

```text
web/index.html
```

The Browser Dashboard Loads `web/data/dashboard_data.js`, So It Can Run As A Static Portfolio Demo After The Pipeline Has Been Built.

## Portfolio Story

This Project Is Best Presented As:

**Smart Supply Chain AI Decision Dashboard** - A Real-Data AI Decision Control Tower That Forecasts Demand, Predicts Late Delivery Risk, Simulates Operational Shocks, And Produces Ranked Actions For Supply Chain Planners.

Recommended Resume Bullets:

- Built A Real-Data Supply Chain AI Decision Dashboard Using Olist Marketplace Demand And Delivery Data.
- Trained Gradient-Boosted Forecasting And Classification Models To Predict 28-Day Demand And Late-Delivery Risk.
- Designed A Scenario-To-Action Decision Layer That Converts Model Outputs Into Inventory Exposure, Delivery Risk, And Operational Recommendations.
- Created Power BI-Ready Data Products And A Visually Advanced Static Web Dashboard For Recruiter Review.

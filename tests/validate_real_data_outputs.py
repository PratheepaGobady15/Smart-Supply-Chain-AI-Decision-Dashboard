from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs"
WEB_DATA_DIR = PROJECT_ROOT / "web" / "data"
SOURCE_MANIFEST = PROJECT_ROOT / "data" / "raw" / "source_manifest.json"

FORBIDDEN_OUTPUT_COLUMNS = {
    "customer_id",
    "customer_unique_id",
}


REQUIRED_OUTPUTS = [
    "demand_forecast.csv",
    "inventory_exposure_recommendations.csv",
    "delivery_risk_predictions.csv",
    "seller_risk_summary.csv",
    "state_delivery_summary.csv",
    "what_if_scenarios.csv",
    "executive_kpis.csv",
    "decision_action_queue.csv",
    "model_metrics.csv",
    "feature_importance.csv",
]


OLD_SYNTHETIC_FILES = [
    PROJECT_ROOT / "src" / "generate_sample_data.py",
    PROJECT_ROOT / "data" / "products.csv",
    PROJECT_ROOT / "data" / "suppliers.csv",
    PROJECT_ROOT / "data" / "sales_history.csv",
    PROJECT_ROOT / "data" / "inventory_snapshot.csv",
    OUTPUT_DIR / "inventory_risk_recommendations.csv",
    OUTPUT_DIR / "supplier_summary.csv",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_csv(name: str) -> pd.DataFrame:
    path = OUTPUT_DIR / name
    require(path.exists(), f"Missing Required Output: {path}")
    return pd.read_csv(path)


def main() -> None:
    missing = [name for name in REQUIRED_OUTPUTS if not (OUTPUT_DIR / name).exists()]
    require(not missing, f"Missing Output Files: {missing}")
    require(SOURCE_MANIFEST.exists(), "Missing Source Manifest")

    unexpected = [str(path) for path in OLD_SYNTHETIC_FILES if path.exists()]
    require(not unexpected, f"Old Synthetic Files Still Exist: {unexpected}")
    manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    require(manifest["dataset"] == "Brazilian E-Commerce Public Dataset By Olist", "Unexpected Source Dataset")
    require(manifest["license"] == "CC BY-NC-SA 4.0", "Unexpected Source License")

    executive = read_csv("executive_kpis.csv")
    require(len(executive) == 1, "Executive KPI Output Should Have One Row")
    kpis = executive.iloc[0]
    require(kpis["project_owner"] == "Pratheepa Gobady", "Project Owner Must Be Pratheepa Gobady")
    require("Olist" in kpis["data_sources"], "Olist Data Source Must Be Listed")
    require("CC BY-NC-SA 4.0" in kpis["data_sources"], "Olist License Must Be Listed")
    require("M5" not in kpis["data_sources"], "M5 Should Not Be Listed After Olist-Only Cleanup")
    require(int(kpis["demand_series_modeled"]) >= 50, "Demand Model Should Cover A Meaningful Number Of Series")
    require(int(kpis["delivery_orders_scored"]) >= 90000, "Delivery Model Should Score The Real Olist Order Set")
    require(float(kpis["delivery_model_roc_auc"]) >= 0.65, "Delivery Model ROC AUC Is Below The Validation Floor")
    require(float(kpis["demand_model_mae"]) > 0, "Demand Model MAE Must Be Present")
    require(int(kpis["scenario_count"]) >= 5, "Scenario Outputs Are Missing")

    demand = read_csv("demand_forecast.csv")
    require(demand["date"].nunique() == 28, "Demand Forecast Should Contain A 28-Day Horizon")
    require({"series_id", "category", "forecast_units", "forecast_revenue"}.issubset(demand.columns), "Demand Columns Missing")
    require((demand["forecast_units"] >= 0).all(), "Demand Forecast Contains Negative Units")

    inventory = read_csv("inventory_exposure_recommendations.csv")
    require(inventory["inventory_exposure_score"].between(0, 100).all(), "Inventory Exposure Scores Must Be 0-100")
    require(inventory["recommended_action"].notna().all(), "Inventory Actions Must Be Populated")

    delivery = read_csv("delivery_risk_predictions.csv")
    require(delivery["late_delivery_probability"].between(0, 1).all(), "Delivery Probabilities Must Be 0-1")
    require(delivery["delivery_risk_score"].between(0, 100).all(), "Delivery Risk Scores Must Be 0-100")
    forbidden_delivery_columns = sorted(FORBIDDEN_OUTPUT_COLUMNS & set(delivery.columns.str.lower()))
    require(not forbidden_delivery_columns, f"Customer Identifiers Should Not Be Exported: {forbidden_delivery_columns}")

    action_queue = read_csv("decision_action_queue.csv")
    require({"Demand Forecast", "Delivery Risk", "Scenario"}.issubset(set(action_queue["lane"])), "Action Queue Lanes Missing")
    require(action_queue["action"].notna().all(), "Action Queue Must Include Recommendations")

    metrics = read_csv("model_metrics.csv")
    required_metrics = {"MAE", "MAPE", "ROC AUC", "Average Precision", "F1"}
    require(required_metrics.issubset(set(metrics["metric"])), "Model Metrics Are Incomplete")

    dashboard_json = WEB_DATA_DIR / "dashboard_data.json"
    dashboard_js = WEB_DATA_DIR / "dashboard_data.js"
    require(dashboard_json.exists(), "Dashboard JSON Missing")
    require(dashboard_js.exists(), "Dashboard JS Missing")
    payload = json.loads(dashboard_json.read_text(encoding="utf-8"))
    require(payload["generatedFor"] == "Pratheepa Gobady", "Dashboard Payload Owner Is Incorrect")
    require(len(payload["actionQueue"]) >= 20, "Dashboard Action Queue Payload Is Too Small")
    require(len(payload["scenarioSummary"]) >= 5, "Dashboard Scenario Payload Is Missing")
    require("Olist" in payload["kpis"]["data_sources"], "Dashboard Payload Must Reference Olist")
    require("M5" not in payload["kpis"]["data_sources"], "Dashboard Payload Should Not Reference M5")

    print("Real-Data Output Validation Passed.")


if __name__ == "__main__":
    main()

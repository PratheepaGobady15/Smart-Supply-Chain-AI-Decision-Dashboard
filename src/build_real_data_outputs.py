from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    f1_score,
    mean_absolute_error,
    mean_absolute_percentage_error,
    roc_auc_score,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
WEB_DATA_DIR = PROJECT_ROOT / "web" / "data"

OLIST_DIR = RAW_DIR / "olist"
MANIFEST_FILE = RAW_DIR / "source_manifest.json"

RANDOM_SEED = 42
FORECAST_HORIZON_DAYS = 28
MAX_DEMAND_SERIES = 72
DATA_SOURCE_LABEL = "Brazilian E-Commerce Public Dataset By Olist (CC BY-NC-SA 4.0; Non-Commercial Educational Use)"


@dataclass(frozen=True)
class DemandArtifacts:
    forecast: pd.DataFrame
    risk: pd.DataFrame
    metrics: pd.DataFrame
    feature_importance: pd.DataFrame
    forecast_history: pd.DataFrame


@dataclass(frozen=True)
class DeliveryArtifacts:
    predictions: pd.DataFrame
    seller_summary: pd.DataFrame
    state_summary: pd.DataFrame
    metrics: pd.DataFrame
    feature_importance: pd.DataFrame


def require_files(base: Path, filenames: list[str], label: str) -> None:
    missing = [name for name in filenames if not (base / name).exists()]
    if missing:
        missing_list = "\n".join(f"- {name}" for name in missing)
        raise FileNotFoundError(
            f"Missing {label} Files In {base}:\n{missing_list}\n\n"
            "Run `python src\\download_real_data.py` First."
        )


def load_olist_inputs() -> dict[str, pd.DataFrame]:
    required = [
        "olist_orders_dataset.csv",
        "olist_order_items_dataset.csv",
        "olist_customers_dataset.csv",
        "olist_sellers_dataset.csv",
        "olist_products_dataset.csv",
        "product_category_name_translation.csv",
    ]
    require_files(OLIST_DIR, required, "Olist")
    return {name: pd.read_csv(OLIST_DIR / name) for name in required}


def mode_or_unknown(values: pd.Series) -> str:
    clean = values.dropna().astype(str)
    if clean.empty:
        return "unknown"
    modes = clean.mode()
    return str(modes.iloc[0]) if not modes.empty else str(clean.iloc[0])


def build_order_line_frame(inputs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    orders = inputs["olist_orders_dataset.csv"].copy()
    items = inputs["olist_order_items_dataset.csv"].copy()
    customers = inputs["olist_customers_dataset.csv"].copy()
    sellers = inputs["olist_sellers_dataset.csv"].copy()
    products = inputs["olist_products_dataset.csv"].copy()
    translation = inputs["product_category_name_translation.csv"].copy()

    for column in [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]:
        orders[column] = pd.to_datetime(orders[column], errors="coerce")

    numeric_item_columns = ["order_item_id", "price", "freight_value"]
    for column in numeric_item_columns:
        items[column] = pd.to_numeric(items[column], errors="coerce")

    numeric_product_columns = [
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
    ]
    for column in numeric_product_columns:
        products[column] = pd.to_numeric(products[column], errors="coerce")

    product_frame = products.merge(translation, on="product_category_name", how="left")
    product_frame["product_category_name_english"] = product_frame["product_category_name_english"].fillna("unknown")
    product_frame["volume_cm3"] = (
        product_frame["product_length_cm"].fillna(0)
        * product_frame["product_height_cm"].fillna(0)
        * product_frame["product_width_cm"].fillna(0)
    )

    frame = (
        items.merge(orders, on="order_id", how="inner")
        .merge(customers[["customer_id", "customer_state", "customer_city"]], on="customer_id", how="left")
        .merge(sellers[["seller_id", "seller_state", "seller_city"]], on="seller_id", how="left")
        .merge(
            product_frame[
                [
                    "product_id",
                    "product_category_name_english",
                    "product_weight_g",
                    "volume_cm3",
                ]
            ],
            on="product_id",
            how="left",
        )
    )

    frame = frame[frame["order_status"].eq("delivered")].copy()
    frame = frame.dropna(
        subset=[
            "order_purchase_timestamp",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
            "customer_state",
            "seller_state",
            "price",
            "freight_value",
        ]
    )
    frame["product_category_name_english"] = frame["product_category_name_english"].fillna("unknown")
    frame["late_delivery"] = (frame["order_delivered_customer_date"] > frame["order_estimated_delivery_date"]).astype(int)
    frame["purchase_date"] = frame["order_purchase_timestamp"].dt.floor("D")
    frame["promised_lead_days"] = (
        frame["order_estimated_delivery_date"] - frame["order_purchase_timestamp"]
    ).dt.total_seconds() / 86400
    frame["approval_lag_hours"] = (
        frame["order_approved_at"] - frame["order_purchase_timestamp"]
    ).dt.total_seconds() / 3600
    frame["actual_delivery_days"] = (
        frame["order_delivered_customer_date"] - frame["order_purchase_timestamp"]
    ).dt.total_seconds() / 86400
    frame["delivery_slip_days"] = (
        frame["order_delivered_customer_date"] - frame["order_estimated_delivery_date"]
    ).dt.total_seconds() / 86400
    frame["freight_ratio"] = frame["freight_value"] / np.maximum(frame["price"], 1)
    frame["approval_lag_hours"] = frame["approval_lag_hours"].clip(lower=0)
    frame["promised_lead_days"] = frame["promised_lead_days"].clip(lower=1)
    frame["product_weight_g"] = frame["product_weight_g"].fillna(frame["product_weight_g"].median()).clip(lower=0)
    frame["volume_cm3"] = frame["volume_cm3"].fillna(frame["volume_cm3"].median()).clip(lower=0)
    return frame.sort_values("order_purchase_timestamp").reset_index(drop=True)


def build_delivery_frame(line_frame: pd.DataFrame) -> pd.DataFrame:
    order_summary = (
        line_frame.groupby("order_id", as_index=False)
        .agg(
            order_purchase_timestamp=("order_purchase_timestamp", "first"),
            order_approved_at=("order_approved_at", "first"),
            order_delivered_customer_date=("order_delivered_customer_date", "first"),
            order_estimated_delivery_date=("order_estimated_delivery_date", "first"),
            customer_state=("customer_state", "first"),
            customer_city=("customer_city", "first"),
            seller_id=("seller_id", "first"),
            seller_state=("seller_state", "first"),
            seller_city=("seller_city", "first"),
            product_category_name_english=("product_category_name_english", mode_or_unknown),
            item_count=("order_item_id", "max"),
            total_price=("price", "sum"),
            total_freight=("freight_value", "sum"),
            avg_item_price=("price", "mean"),
            product_weight_g=("product_weight_g", "mean"),
            volume_cm3=("volume_cm3", "mean"),
            late_delivery=("late_delivery", "max"),
            promised_lead_days=("promised_lead_days", "first"),
            approval_lag_hours=("approval_lag_hours", "first"),
            actual_delivery_days=("actual_delivery_days", "first"),
            delivery_slip_days=("delivery_slip_days", "first"),
        )
        .dropna(subset=["promised_lead_days", "total_price", "total_freight"])
    )
    order_summary["freight_ratio"] = order_summary["total_freight"] / np.maximum(order_summary["total_price"], 1)
    order_summary["purchase_month"] = order_summary["order_purchase_timestamp"].dt.month
    order_summary["purchase_day_of_week"] = order_summary["order_purchase_timestamp"].dt.dayofweek
    order_summary["purchase_hour"] = order_summary["order_purchase_timestamp"].dt.hour
    order_summary["is_weekend_purchase"] = order_summary["purchase_day_of_week"].isin([5, 6]).astype(int)
    order_summary["is_cross_state"] = (order_summary["seller_state"] != order_summary["customer_state"]).astype(int)
    order_summary["price_log"] = np.log1p(order_summary["total_price"])
    order_summary["freight_log"] = np.log1p(order_summary["total_freight"])
    order_summary["approval_lag_hours"] = order_summary["approval_lag_hours"].fillna(order_summary["approval_lag_hours"].median())
    return order_summary.sort_values("order_purchase_timestamp").reset_index(drop=True)


def add_delivery_encodings(frame: pd.DataFrame) -> pd.DataFrame:
    encoded = frame.copy()
    for column in ["customer_state", "seller_state", "product_category_name_english"]:
        encoded[f"{column}_code"] = encoded[column].astype("category").cat.codes
    return encoded


def delivery_feature_columns() -> list[str]:
    return [
        "item_count",
        "total_price",
        "total_freight",
        "avg_item_price",
        "freight_ratio",
        "price_log",
        "freight_log",
        "product_weight_g",
        "volume_cm3",
        "promised_lead_days",
        "approval_lag_hours",
        "purchase_month",
        "purchase_day_of_week",
        "purchase_hour",
        "is_weekend_purchase",
        "is_cross_state",
        "customer_state_code",
        "seller_state_code",
        "product_category_name_english_code",
    ]


def train_delivery_model(delivery_frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    frame = add_delivery_encodings(delivery_frame)
    features = delivery_feature_columns()
    frame[features] = frame[features].replace([np.inf, -np.inf], np.nan)
    frame[features] = frame[features].fillna(frame[features].median(numeric_only=True).fillna(0))

    split_index = int(len(frame) * 0.78)
    train = frame.iloc[:split_index]
    test = frame.iloc[split_index:]

    model = HistGradientBoostingClassifier(
        learning_rate=0.07,
        max_iter=220,
        min_samples_leaf=45,
        random_state=RANDOM_SEED,
    )
    model.fit(train[features], train["late_delivery"])
    probabilities = model.predict_proba(test[features])[:, 1]
    threshold_grid = np.linspace(0.05, 0.55, 51)
    f1_values = [
        f1_score(test["late_delivery"], (probabilities >= threshold).astype(int), zero_division=0)
        for threshold in threshold_grid
    ]
    best_threshold = float(threshold_grid[int(np.argmax(f1_values))])
    labels = (probabilities >= best_threshold).astype(int)

    metrics = pd.DataFrame(
        [
            {"model": "Olist Late Delivery Risk", "metric": "ROC AUC", "value": round(float(roc_auc_score(test["late_delivery"], probabilities)), 4)},
            {"model": "Olist Late Delivery Risk", "metric": "Average Precision", "value": round(float(average_precision_score(test["late_delivery"], probabilities)), 4)},
            {"model": "Olist Late Delivery Risk", "metric": "F1", "value": round(float(f1_score(test["late_delivery"], labels, zero_division=0)), 4)},
            {"model": "Olist Late Delivery Risk", "metric": "F1 Threshold", "value": round(best_threshold, 3)},
            {"model": "Olist Late Delivery Risk", "metric": "Accuracy", "value": round(float(accuracy_score(test["late_delivery"], labels)), 4)},
            {"model": "Olist Late Delivery Risk", "metric": "Training Rows", "value": int(len(train))},
            {"model": "Olist Late Delivery Risk", "metric": "Validation Rows", "value": int(len(test))},
            {"model": "Olist Late Delivery Risk", "metric": "Late Delivery Rate", "value": round(float(frame["late_delivery"].mean()), 4)},
        ]
    )

    sample_size = min(3200, len(test))
    sample = test.sample(sample_size, random_state=RANDOM_SEED)
    result = permutation_importance(
        model,
        sample[features],
        sample["late_delivery"],
        n_repeats=3,
        random_state=RANDOM_SEED,
        scoring="roc_auc",
    )
    importance = pd.DataFrame(
        {
            "model": "Olist Late Delivery Risk",
            "feature": features,
            "importance": result.importances_mean,
        }
    ).sort_values("importance", ascending=False)

    scored = frame.copy()
    scored["late_delivery_probability"] = model.predict_proba(scored[features])[:, 1]
    scored["delivery_risk_score"] = (100 * scored["late_delivery_probability"]).round(1)
    scored["risk_level"] = pd.cut(
        scored["delivery_risk_score"],
        bins=[-0.1, 33, 66, 100],
        labels=["Low", "Medium", "High"],
    ).astype(str)
    return scored, metrics, importance


def build_delivery_artifacts(line_frame: pd.DataFrame) -> DeliveryArtifacts:
    delivery_frame = build_delivery_frame(line_frame)
    scored, metrics, importance = train_delivery_model(delivery_frame)
    predictions = scored[
        [
            "order_id",
            "order_purchase_timestamp",
            "customer_state",
            "seller_state",
            "seller_city",
            "product_category_name_english",
            "total_price",
            "total_freight",
            "promised_lead_days",
            "actual_delivery_days",
            "delivery_slip_days",
            "late_delivery",
            "late_delivery_probability",
            "delivery_risk_score",
            "risk_level",
        ]
    ].copy()
    predictions["order_purchase_date"] = predictions["order_purchase_timestamp"].dt.date.astype(str)
    predictions = predictions.drop(columns=["order_purchase_timestamp"]).sort_values("delivery_risk_score", ascending=False)

    seller_summary = (
        scored.groupby(["seller_id", "seller_state", "seller_city"], as_index=False)
        .agg(
            orders=("order_id", "nunique"),
            avg_delivery_risk_score=("delivery_risk_score", "mean"),
            late_delivery_rate=("late_delivery", "mean"),
            total_revenue=("total_price", "sum"),
            total_freight=("total_freight", "sum"),
        )
        .query("orders >= 8")
        .round({"avg_delivery_risk_score": 2, "late_delivery_rate": 4, "total_revenue": 2, "total_freight": 2})
        .sort_values("avg_delivery_risk_score", ascending=False)
    )
    state_summary = (
        scored.groupby(["customer_state"], as_index=False)
        .agg(
            orders=("order_id", "nunique"),
            avg_delivery_risk_score=("delivery_risk_score", "mean"),
            late_delivery_rate=("late_delivery", "mean"),
            total_revenue=("total_price", "sum"),
            avg_freight=("total_freight", "mean"),
        )
        .round({"avg_delivery_risk_score": 2, "late_delivery_rate": 4, "total_revenue": 2, "avg_freight": 2})
        .sort_values("avg_delivery_risk_score", ascending=False)
    )
    return DeliveryArtifacts(
        predictions=predictions,
        seller_summary=seller_summary,
        state_summary=state_summary,
        metrics=metrics,
        feature_importance=importance,
    )


def build_demand_daily_frame(line_frame: pd.DataFrame) -> pd.DataFrame:
    daily = (
        line_frame.groupby(["purchase_date", "product_category_name_english", "customer_state"], as_index=False)
        .agg(
            units_sold=("order_item_id", "count"),
            revenue=("price", "sum"),
            freight_value=("freight_value", "sum"),
            avg_price=("price", "mean"),
        )
        .rename(
            columns={
                "purchase_date": "date",
                "product_category_name_english": "category",
                "customer_state": "state_id",
            }
        )
    )
    daily["category"] = daily["category"].fillna("unknown")
    daily["state_id"] = daily["state_id"].fillna("NA")
    daily["series_id"] = daily["category"] + "::" + daily["state_id"]

    recent_cutoff = daily["date"].max() - pd.Timedelta(days=180)
    top_series = (
        daily[daily["date"] >= recent_cutoff]
        .groupby("series_id", as_index=False)
        .agg(recent_units=("units_sold", "sum"), recent_revenue=("revenue", "sum"))
        .sort_values(["recent_units", "recent_revenue"], ascending=[False, False])
        .head(MAX_DEMAND_SERIES)["series_id"]
    )
    daily = daily[daily["series_id"].isin(set(top_series))].copy()
    date_range = pd.date_range(daily["date"].min(), daily["date"].max(), freq="D")
    series_meta = daily[["series_id", "category", "state_id"]].drop_duplicates("series_id")
    grid = pd.MultiIndex.from_product([series_meta["series_id"], date_range], names=["series_id", "date"]).to_frame(index=False)
    complete = grid.merge(series_meta, on="series_id", how="left").merge(
        daily[["series_id", "date", "units_sold", "revenue", "freight_value", "avg_price"]],
        on=["series_id", "date"],
        how="left",
    )
    complete[["units_sold", "revenue", "freight_value"]] = complete[["units_sold", "revenue", "freight_value"]].fillna(0)
    complete["avg_price"] = complete.groupby("series_id")["avg_price"].ffill().bfill()
    complete["avg_price"] = complete["avg_price"].fillna(daily["avg_price"].median()).clip(lower=0)
    return complete.sort_values(["series_id", "date"]).reset_index(drop=True)


def add_demand_features(frame: pd.DataFrame) -> pd.DataFrame:
    enriched = frame.copy()
    enriched["day_of_week"] = enriched["date"].dt.dayofweek
    enriched["month"] = enriched["date"].dt.month
    enriched["day_of_year"] = enriched["date"].dt.dayofyear
    enriched["is_weekend"] = enriched["day_of_week"].isin([5, 6]).astype(int)
    enriched["series_age_days"] = (enriched["date"] - enriched.groupby("series_id")["date"].transform("min")).dt.days

    grouped = enriched.groupby("series_id", sort=False)["units_sold"]
    enriched["lag_7"] = grouped.shift(7)
    enriched["lag_14"] = grouped.shift(14)
    enriched["lag_28"] = grouped.shift(28)
    enriched["rolling_mean_7"] = grouped.transform(lambda values: values.shift(1).rolling(7).mean())
    enriched["rolling_mean_28"] = grouped.transform(lambda values: values.shift(1).rolling(28).mean())
    enriched["rolling_std_28"] = grouped.transform(lambda values: values.shift(1).rolling(28).std())
    enriched["rolling_revenue_28"] = (
        enriched.groupby("series_id", sort=False)["revenue"].transform(lambda values: values.shift(1).rolling(28).sum())
    )
    enriched["rolling_freight_28"] = (
        enriched.groupby("series_id", sort=False)["freight_value"].transform(lambda values: values.shift(1).rolling(28).sum())
    )
    enriched["freight_ratio_28"] = enriched["rolling_freight_28"] / np.maximum(enriched["rolling_revenue_28"], 1)

    for column in ["series_id", "category", "state_id"]:
        enriched[f"{column}_code"] = enriched[column].astype("category").cat.codes

    return enriched.dropna(
        subset=["lag_7", "lag_14", "lag_28", "rolling_mean_7", "rolling_mean_28", "rolling_std_28"]
    ).reset_index(drop=True)


def demand_feature_columns() -> list[str]:
    return [
        "avg_price",
        "day_of_week",
        "month",
        "day_of_year",
        "is_weekend",
        "series_age_days",
        "lag_7",
        "lag_14",
        "lag_28",
        "rolling_mean_7",
        "rolling_mean_28",
        "rolling_std_28",
        "rolling_revenue_28",
        "rolling_freight_28",
        "freight_ratio_28",
        "series_id_code",
        "category_code",
        "state_id_code",
    ]


def train_demand_model(feature_frame: pd.DataFrame) -> tuple[HistGradientBoostingRegressor, pd.DataFrame, pd.DataFrame]:
    last_date = feature_frame["date"].max()
    validation_start = last_date - pd.Timedelta(days=FORECAST_HORIZON_DAYS - 1)
    train = feature_frame[feature_frame["date"] < validation_start].copy()
    validation = feature_frame[feature_frame["date"] >= validation_start].copy()

    features = demand_feature_columns()
    train[features] = train[features].replace([np.inf, -np.inf], np.nan).fillna(0)
    validation[features] = validation[features].replace([np.inf, -np.inf], np.nan).fillna(0)

    model = HistGradientBoostingRegressor(
        learning_rate=0.075,
        max_iter=130,
        min_samples_leaf=32,
        l2_regularization=0.04,
        random_state=RANDOM_SEED,
    )
    model.fit(train[features], train["units_sold"])

    predictions = model.predict(validation[features]).clip(min=0)
    metrics = pd.DataFrame(
        [
            {"model": "Olist Demand Forecast", "metric": "MAE", "value": round(float(mean_absolute_error(validation["units_sold"], predictions)), 3)},
            {"model": "Olist Demand Forecast", "metric": "MAPE", "value": round(float(mean_absolute_percentage_error(validation["units_sold"].clip(lower=1), predictions)), 4)},
            {"model": "Olist Demand Forecast", "metric": "Training Rows", "value": int(len(train))},
            {"model": "Olist Demand Forecast", "metric": "Validation Rows", "value": int(len(validation))},
            {"model": "Olist Demand Forecast", "metric": "Series Modeled", "value": int(feature_frame["series_id"].nunique())},
        ]
    )

    sample_size = min(1800, len(validation))
    sample = validation.sample(sample_size, random_state=RANDOM_SEED)
    result = permutation_importance(
        model,
        sample[features],
        sample["units_sold"],
        n_repeats=3,
        random_state=RANDOM_SEED,
        scoring="neg_mean_absolute_error",
    )
    importance = pd.DataFrame(
        {
            "model": "Olist Demand Forecast",
            "feature": features,
            "importance": result.importances_mean,
        }
    ).sort_values("importance", ascending=False)
    return model, metrics, importance


def category_code_lookup(feature_frame: pd.DataFrame, column: str) -> dict[str, int]:
    categories = feature_frame[column].astype("category").cat.categories
    return {str(value): index for index, value in enumerate(categories)}


def forecast_future(model: HistGradientBoostingRegressor, feature_frame: pd.DataFrame) -> pd.DataFrame:
    features = demand_feature_columns()
    forecasts: list[dict[str, object]] = []
    lookups = {
        column: category_code_lookup(feature_frame, column)
        for column in ["series_id", "category", "state_id"]
    }
    for series_id, history in feature_frame.groupby("series_id", sort=False):
        history = history.sort_values("date").copy()
        units = history["units_sold"].astype(float).tolist()
        revenues = history["revenue"].astype(float).tolist()
        freights = history["freight_value"].astype(float).tolist()
        latest = history.iloc[-1]
        avg_price = float(history["avg_price"].replace(0, np.nan).ffill().bfill().median())
        avg_price = avg_price if np.isfinite(avg_price) and avg_price > 0 else 1.0
        last_date = pd.Timestamp(latest["date"])
        first_date = pd.Timestamp(history["date"].min())

        for step in range(1, FORECAST_HORIZON_DAYS + 1):
            date = last_date + pd.Timedelta(days=step)
            rolling_revenue_28 = float(np.sum(revenues[-28:]))
            rolling_freight_28 = float(np.sum(freights[-28:]))
            row = {
                "avg_price": avg_price,
                "day_of_week": date.dayofweek,
                "month": date.month,
                "day_of_year": date.dayofyear,
                "is_weekend": int(date.dayofweek in [5, 6]),
                "series_age_days": int((date - first_date).days),
                "lag_7": units[-7],
                "lag_14": units[-14],
                "lag_28": units[-28],
                "rolling_mean_7": float(np.mean(units[-7:])),
                "rolling_mean_28": float(np.mean(units[-28:])),
                "rolling_std_28": float(np.std(units[-28:])),
                "rolling_revenue_28": rolling_revenue_28,
                "rolling_freight_28": rolling_freight_28,
                "freight_ratio_28": rolling_freight_28 / max(rolling_revenue_28, 1),
                "series_id_code": lookups["series_id"].get(str(series_id), -1),
                "category_code": lookups["category"].get(str(latest["category"]), -1),
                "state_id_code": lookups["state_id"].get(str(latest["state_id"]), -1),
            }
            predicted = max(0.0, float(model.predict(pd.DataFrame([row])[features])[0]))
            units.append(predicted)
            predicted_revenue = predicted * avg_price
            predicted_freight = predicted_revenue * float(history["freight_ratio_28"].replace([np.inf, -np.inf], np.nan).fillna(0).tail(90).mean())
            revenues.append(predicted_revenue)
            freights.append(predicted_freight)
            forecasts.append(
                {
                    "date": date.date().isoformat(),
                    "series_id": series_id,
                    "category": latest["category"],
                    "store_id": latest["state_id"],
                    "state_id": latest["state_id"],
                    "forecast_units": round(predicted, 2),
                    "forecast_revenue": round(predicted_revenue, 2),
                    "forecast_freight": round(predicted_freight, 2),
                    "avg_price": round(avg_price, 2),
                }
            )
    return pd.DataFrame(forecasts)


def build_demand_risk(feature_frame: pd.DataFrame, forecast: pd.DataFrame, delivery_state: pd.DataFrame) -> pd.DataFrame:
    history = (
        feature_frame.groupby(["series_id", "category", "state_id"], as_index=False)
        .agg(
            avg_recent_units=("units_sold", lambda values: float(values.tail(56).mean())),
            demand_volatility=("units_sold", lambda values: float(values.tail(56).std())),
            avg_price=("avg_price", "mean"),
            recent_revenue_56d=("revenue", lambda values: float(values.tail(56).sum())),
        )
    )
    demand_28d = (
        forecast.groupby(["series_id", "category", "store_id", "state_id"], as_index=False)
        .agg(
            forecast_units_28d=("forecast_units", "sum"),
            forecast_revenue_28d=("forecast_revenue", "sum"),
            forecast_freight_28d=("forecast_freight", "sum"),
        )
    )
    risk = demand_28d.merge(history, on=["series_id", "category", "state_id"], how="left")
    risk = risk.merge(
        delivery_state[["customer_state", "avg_delivery_risk_score", "late_delivery_rate"]],
        left_on="state_id",
        right_on="customer_state",
        how="left",
    )
    risk["avg_delivery_risk_score"] = risk["avg_delivery_risk_score"].fillna(delivery_state["avg_delivery_risk_score"].mean())
    risk["late_delivery_rate"] = risk["late_delivery_rate"].fillna(delivery_state["late_delivery_rate"].mean())
    risk["demand_change_pct"] = (
        (risk["forecast_units_28d"] / np.maximum(risk["avg_recent_units"] * FORECAST_HORIZON_DAYS, 1)) - 1
    ).replace([np.inf, -np.inf], 0)
    risk["volatility_index"] = (risk["demand_volatility"] / np.maximum(risk["avg_recent_units"], 1)).clip(0, 3)
    delivery_pressure = (risk["avg_delivery_risk_score"] / 100).clip(0, 1)
    risk["revenue_at_risk"] = (
        risk["forecast_revenue_28d"]
        * (
            0.07
            + 0.16 * risk["volatility_index"].clip(0, 2) / 2
            + 0.22 * risk["demand_change_pct"].clip(lower=0, upper=1.5) / 1.5
            + 0.24 * delivery_pressure
        )
    ).round(2)
    raw_exposure = (
        0.34 * risk["demand_change_pct"].clip(lower=0, upper=1.5) / 1.5
        + 0.25 * risk["volatility_index"].clip(upper=2) / 2
        + 0.23 * delivery_pressure
        + 0.18 * (risk["forecast_revenue_28d"] / max(float(risk["forecast_revenue_28d"].max()), 1))
    )
    risk["inventory_exposure_score"] = (100 * raw_exposure / max(float(raw_exposure.quantile(0.96)), 0.01)).clip(0, 100).round(1)
    risk["risk_level"] = pd.cut(
        risk["inventory_exposure_score"],
        bins=[-0.1, 40, 70, 100],
        labels=["Low", "Medium", "High"],
    ).astype(str)
    risk["recommended_action"] = risk.apply(make_demand_action, axis=1)
    return risk.sort_values(["inventory_exposure_score", "forecast_revenue_28d"], ascending=[False, False])


def make_demand_action(row: pd.Series) -> str:
    if row["inventory_exposure_score"] >= 70:
        return "Prioritize Demand Review And Reserve Capacity For This Category-State Lane."
    if row["avg_delivery_risk_score"] >= 45:
        return "Pair Replenishment Plan With Delivery-Risk Guardrails For This State."
    if row["demand_change_pct"] > 0.12:
        return "Watch For Demand Acceleration And Validate Replenishment Coverage."
    if row["volatility_index"] > 1.0:
        return "Monitor Volatility Before Committing To A Fixed Reorder Plan."
    return "Maintain Baseline Planning Rhythm."


def build_demand_artifacts(line_frame: pd.DataFrame, delivery_state: pd.DataFrame) -> DemandArtifacts:
    daily = build_demand_daily_frame(line_frame)
    print(f"Prepared Olist Demand Frame: {daily['series_id'].nunique()} Series, {len(daily):,} Daily Rows", flush=True)
    feature_frame = add_demand_features(daily)
    print(f"Training Demand Model On {len(feature_frame):,} Feature Rows", flush=True)
    model, metrics, importance = train_demand_model(feature_frame)
    forecast = forecast_future(model, feature_frame)
    risk = build_demand_risk(feature_frame, forecast, delivery_state)
    history = (
        feature_frame.groupby(["date", "category"], as_index=False)["units_sold"]
        .sum()
        .tail(365 * 3)
    )
    return DemandArtifacts(forecast=forecast, risk=risk, metrics=metrics, feature_importance=importance, forecast_history=history)


def build_scenario_outputs(demand: pd.DataFrame, delivery_states: pd.DataFrame) -> pd.DataFrame:
    scenarios = [
        ("Base Case", 1.00, 1.00, 1.00),
        ("Demand Spike +15%", 1.15, 1.00, 1.00),
        ("Freight Shock +20%", 1.00, 1.20, 1.00),
        ("Delivery Slowdown +10%", 1.00, 1.00, 1.10),
        ("Combined Disruption", 1.15, 1.20, 1.10),
        ("Regional Rebalance", 0.98, 1.04, 0.84),
    ]
    demand_base = demand.head(90).copy()
    avg_delivery_risk = float(delivery_states["avg_delivery_risk_score"].mean()) / 100
    rows = []
    for scenario, demand_multiplier, freight_multiplier, service_multiplier in scenarios:
        for _, row in demand_base.iterrows():
            adjusted_units = row["forecast_units_28d"] * demand_multiplier
            local_delivery_pressure = float(row.get("avg_delivery_risk_score", avg_delivery_risk * 100)) / 100
            service_risk = min(
                1.0,
                (row["inventory_exposure_score"] / 100) * service_multiplier
                + avg_delivery_risk * 0.16
                + local_delivery_pressure * 0.18
                + max(0, freight_multiplier - 1) * 0.18,
            )
            revenue_at_risk = row["revenue_at_risk"] * demand_multiplier * freight_multiplier * service_multiplier
            rows.append(
                {
                    "scenario": scenario,
                    "series_id": row["series_id"],
                    "item_id": row["category"],
                    "category": row["category"],
                    "store_id": row["state_id"],
                    "state_id": row["state_id"],
                    "scenario_forecast_units_28d": round(float(adjusted_units), 2),
                    "scenario_service_risk": round(float(service_risk), 4),
                    "scenario_revenue_at_risk": round(float(revenue_at_risk), 2),
                    "recommended_action": make_scenario_action(service_risk, scenario),
                }
            )
    return pd.DataFrame(rows)


def make_scenario_action(service_risk: float, scenario: str) -> str:
    if service_risk >= 0.62:
        return f"Escalate {scenario}: Protect Service Levels And Review Allocation."
    if service_risk >= 0.38:
        return f"Monitor {scenario}: Rebalance Capacity Before Risk Converts To Service Loss."
    return f"Maintain {scenario}: Current Exposure Is Manageable."


def build_executive_kpis(demand: DemandArtifacts, delivery: DeliveryArtifacts, scenarios: pd.DataFrame) -> pd.DataFrame:
    demand_metrics = demand.metrics.set_index(["model", "metric"])["value"].to_dict()
    delivery_metrics = delivery.metrics.set_index(["model", "metric"])["value"].to_dict()
    return pd.DataFrame(
        [
            {
                "project_owner": "Pratheepa Gobady",
                "data_sources": DATA_SOURCE_LABEL,
                "demand_series_modeled": int(demand.risk["series_id"].nunique()),
                "forecast_units_28d": round(float(demand.forecast["forecast_units"].sum()), 2),
                "forecast_revenue_28d": round(float(demand.forecast["forecast_revenue"].sum()), 2),
                "high_inventory_exposure_lanes": int((demand.risk["risk_level"] == "High").sum()),
                "delivery_orders_scored": int(len(delivery.predictions)),
                "high_delivery_risk_orders": int((delivery.predictions["risk_level"] == "High").sum()),
                "avg_late_delivery_probability": round(float(delivery.predictions["late_delivery_probability"].mean()), 4),
                "scenario_count": int(scenarios["scenario"].nunique()),
                "demand_model_mae": demand_metrics.get(("Olist Demand Forecast", "MAE")),
                "demand_model_mape": demand_metrics.get(("Olist Demand Forecast", "MAPE")),
                "delivery_model_roc_auc": delivery_metrics.get(("Olist Late Delivery Risk", "ROC AUC")),
                "delivery_model_average_precision": delivery_metrics.get(("Olist Late Delivery Risk", "Average Precision")),
            }
        ]
    )


def build_action_queue(demand: pd.DataFrame, delivery: pd.DataFrame, scenarios: pd.DataFrame) -> pd.DataFrame:
    demand_actions = demand.head(14).assign(
        lane="Demand Forecast",
        title=lambda frame: frame["category"] + " / " + frame["state_id"],
        score=lambda frame: frame["inventory_exposure_score"],
        impact=lambda frame: frame["revenue_at_risk"],
        action=lambda frame: frame["recommended_action"],
    )[["lane", "title", "score", "risk_level", "impact", "action"]]

    delivery_actions = delivery.head(14).assign(
        lane="Delivery Risk",
        title=lambda frame: frame["seller_state"] + " To " + frame["customer_state"],
        score=lambda frame: frame["delivery_risk_score"],
        impact=lambda frame: frame["total_price"],
        action=lambda frame: "Review Seller/Region Promise Window And Freight Exposure.",
    )[["lane", "title", "score", "risk_level", "impact", "action"]]

    scenario_actions = scenarios.sort_values("scenario_service_risk", ascending=False).head(10).assign(
        lane="Scenario",
        title=lambda frame: frame["scenario"] + " / " + frame["category"] + " / " + frame["state_id"],
        score=lambda frame: frame["scenario_service_risk"] * 100,
        risk_level=lambda frame: pd.cut(
            frame["scenario_service_risk"] * 100,
            bins=[-0.1, 33, 66, 100],
            labels=["Low", "Medium", "High"],
        ).astype(str),
        impact=lambda frame: frame["scenario_revenue_at_risk"],
        action=lambda frame: frame["recommended_action"],
    )[["lane", "title", "score", "risk_level", "impact", "action"]]

    action_queue = pd.concat([demand_actions, delivery_actions, scenario_actions], ignore_index=True)
    return action_queue.sort_values(["score", "impact"], ascending=[False, False]).round({"score": 1, "impact": 2})


def frame_to_records(frame: pd.DataFrame, limit: int | None = None) -> list[dict[str, object]]:
    data = frame.head(limit).copy() if limit else frame.copy()
    data = data.replace([np.inf, -np.inf], np.nan)
    data = data.where(pd.notna(data), None)
    return data.to_dict(orient="records")


def build_web_payload(
    executive_kpis: pd.DataFrame,
    demand: DemandArtifacts,
    delivery: DeliveryArtifacts,
    scenarios: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> dict[str, object]:
    top_categories = (
        demand.forecast.groupby("category")["forecast_units"]
        .sum()
        .sort_values(ascending=False)
        .head(6)
        .index
    )
    demand_by_category = (
        demand.forecast[demand.forecast["category"].isin(top_categories)]
        .groupby(["date", "category"], as_index=False)["forecast_units"]
        .sum()
        .round({"forecast_units": 2})
    )
    scenario_summary = (
        scenarios.groupby("scenario", as_index=False)
        .agg(
            scenario_service_risk=("scenario_service_risk", "mean"),
            scenario_revenue_at_risk=("scenario_revenue_at_risk", "sum"),
            scenario_forecast_units_28d=("scenario_forecast_units_28d", "sum"),
        )
        .round({"scenario_service_risk": 4, "scenario_revenue_at_risk": 2, "scenario_forecast_units_28d": 2})
    )
    feature_importance = pd.concat([demand.feature_importance, delivery.feature_importance], ignore_index=True)
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generatedFor": "Pratheepa Gobady",
        "title": "Smart Supply Chain AI Decision Dashboard",
        "kpis": frame_to_records(executive_kpis)[0],
        "actionQueue": frame_to_records(action_queue, 38),
        "demandByCategory": frame_to_records(demand_by_category),
        "demandRisk": frame_to_records(demand.risk, 34),
        "deliveryState": frame_to_records(delivery.state_summary, 30),
        "sellerRisk": frame_to_records(delivery.seller_summary, 30),
        "scenarioSummary": frame_to_records(scenario_summary),
        "featureImportance": frame_to_records(feature_importance.head(28)),
        "modelMetrics": frame_to_records(pd.concat([demand.metrics, delivery.metrics], ignore_index=True)),
    }


def write_outputs(
    demand: DemandArtifacts,
    delivery: DeliveryArtifacts,
    scenarios: pd.DataFrame,
    executive_kpis: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)

    demand.forecast.to_csv(OUTPUT_DIR / "demand_forecast.csv", index=False)
    demand.risk.to_csv(OUTPUT_DIR / "inventory_exposure_recommendations.csv", index=False)
    delivery.predictions.to_csv(OUTPUT_DIR / "delivery_risk_predictions.csv", index=False)
    delivery.seller_summary.to_csv(OUTPUT_DIR / "seller_risk_summary.csv", index=False)
    delivery.state_summary.to_csv(OUTPUT_DIR / "state_delivery_summary.csv", index=False)
    scenarios.to_csv(OUTPUT_DIR / "what_if_scenarios.csv", index=False)
    executive_kpis.to_csv(OUTPUT_DIR / "executive_kpis.csv", index=False)
    action_queue.to_csv(OUTPUT_DIR / "decision_action_queue.csv", index=False)

    all_metrics = pd.concat([demand.metrics, delivery.metrics], ignore_index=True)
    all_metrics.to_csv(OUTPUT_DIR / "model_metrics.csv", index=False)
    all_importance = pd.concat([demand.feature_importance, delivery.feature_importance], ignore_index=True)
    all_importance.to_csv(OUTPUT_DIR / "feature_importance.csv", index=False)

    payload = build_web_payload(executive_kpis, demand, delivery, scenarios, action_queue)
    (WEB_DATA_DIR / "dashboard_data.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (WEB_DATA_DIR / "dashboard_data.js").write_text(
        "window.SUPPLY_CHAIN_DASHBOARD_DATA = "
        + json.dumps(payload, indent=2)
        + ";\n",
        encoding="utf-8",
    )


def main() -> None:
    if MANIFEST_FILE.exists():
        print(f"Using Source Manifest: {MANIFEST_FILE}", flush=True)
    print("Loading Olist Marketplace Data...", flush=True)
    inputs = load_olist_inputs()
    line_frame = build_order_line_frame(inputs)
    print(f"Prepared Olist Order Lines: {len(line_frame):,}", flush=True)

    print("Building Olist Delivery Risk Artifacts...", flush=True)
    delivery = build_delivery_artifacts(line_frame)
    print("Building Olist Demand Forecast Artifacts...", flush=True)
    demand = build_demand_artifacts(line_frame, delivery.state_summary)

    print("Building Scenario And Decision Outputs...", flush=True)
    scenarios = build_scenario_outputs(demand.risk, delivery.state_summary)
    executive_kpis = build_executive_kpis(demand, delivery, scenarios)
    action_queue = build_action_queue(demand.risk, delivery.predictions, scenarios)

    print("Writing Dashboard Outputs...", flush=True)
    write_outputs(demand, delivery, scenarios, executive_kpis, action_queue)

    print("Real-Data Dashboard Outputs Created:")
    for path in sorted(OUTPUT_DIR.glob("*.csv")):
        print(f"- {path}")
    print(f"- {WEB_DATA_DIR / 'dashboard_data.json'}")
    print("\nExecutive KPIs:")
    print(executive_kpis.to_string(index=False))


if __name__ == "__main__":
    main()

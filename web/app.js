const data = window.SUPPLY_CHAIN_DASHBOARD_DATA;

const palette = ["#39f0c2", "#f5c04e", "#ff6f61", "#54a7ff", "#a78bfa", "#82d173", "#ff9f43"];
const statePoints = {
  AM: [0.22, 0.27],
  PA: [0.43, 0.25],
  CE: [0.71, 0.31],
  PE: [0.76, 0.38],
  BA: [0.66, 0.51],
  GO: [0.52, 0.55],
  MG: [0.62, 0.65],
  RJ: [0.70, 0.74],
  SP: [0.58, 0.76],
  PR: [0.52, 0.83],
  SC: [0.55, 0.89],
  RS: [0.50, 0.95],
  DF: [0.55, 0.56],
  ES: [0.72, 0.66],
  MA: [0.59, 0.32],
  MT: [0.38, 0.58],
  MS: [0.45, 0.72],
  PI: [0.64, 0.36],
  RN: [0.78, 0.31],
  PB: [0.79, 0.35],
  AL: [0.78, 0.43],
  SE: [0.76, 0.47],
};

let selectedScenario = "Base Case";
let selectedQueueFilter = "All";

const formatNumber = (value, digits = 0) =>
  Number(value || 0).toLocaleString("en-US", { maximumFractionDigits: digits });
const formatMoney = (value) =>
  Number(value || 0).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
    notation: Math.abs(Number(value || 0)) >= 1000000 ? "compact" : "standard",
  });
const formatPct = (value) => `${(Number(value || 0) * 100).toFixed(1)}%`;
const escapeHtml = (value) =>
  String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
const titleize = (value) =>
  String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
const shorten = (value, length = 18) => {
  const text = String(value ?? "");
  return text.length > length ? `${text.slice(0, length - 1)}...` : text;
};
const categoryColor = (category, index) => palette[index % palette.length] || "#f4f7ef";

function setupCanvas(canvas) {
  const context = canvas.getContext("2d");
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  canvas.width = Math.max(1, width * ratio);
  canvas.height = Math.max(1, height * ratio);
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { context, width, height };
}

function currentScenario() {
  return data.scenarioSummary.find((scenario) => scenario.scenario === selectedScenario) || data.scenarioSummary[0];
}

function scenarioMultiplier() {
  const base = data.scenarioSummary[0]?.scenario_forecast_units_28d || 1;
  return (currentScenario()?.scenario_forecast_units_28d || base) / base;
}

function riskTone(value) {
  const score = Number(value || 0);
  if (score >= 66) return { color: "#ff6f61", label: "High" };
  if (score >= 38) return { color: "#f5c04e", label: "Medium" };
  return { color: "#82d173", label: "Low" };
}

function setKpis() {
  const kpis = data.kpis;
  document.querySelector("#kpiForecastUnits").textContent = formatNumber(kpis.forecast_units_28d);
  document.querySelector("#kpiForecastRevenue").textContent = formatMoney(kpis.forecast_revenue_28d);
  document.querySelector("#kpiOrders").textContent = formatNumber(kpis.delivery_orders_scored);
  document.querySelector("#kpiAuc").textContent = Number(kpis.delivery_model_roc_auc || 0).toFixed(2);
  document.querySelector("#highInventoryLanes").textContent = `${formatNumber(kpis.high_inventory_exposure_lanes)} High Exposure Lanes`;
  document.querySelector("#avgLateProbability").textContent = `${formatPct(kpis.avg_late_delivery_probability)} Average Late Risk`;
  const dominantState = [...data.deliveryState].sort((a, b) => Number(b.avg_delivery_risk_score) - Number(a.avg_delivery_risk_score))[0];
  document.querySelector("#dominantState").textContent = dominantState
    ? `${dominantState.customer_state} / ${Number(dominantState.avg_delivery_risk_score || 0).toFixed(1)} Risk`
    : "State Not Available";
}

function buildScenarioButtons() {
  const container = document.querySelector("#scenarioButtons");
  container.innerHTML = data.scenarioSummary
    .map(
      (scenario) =>
        `<button type="button" data-scenario="${escapeHtml(scenario.scenario)}" class="${scenario.scenario === selectedScenario ? "active" : ""}" aria-pressed="${scenario.scenario === selectedScenario}">${escapeHtml(scenario.scenario)}</button>`,
    )
    .join("");
  container.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      selectedScenario = button.dataset.scenario;
      buildScenarioButtons();
      updateScenarioReadout();
      drawMarketCanvas();
      drawForecastChart();
      renderActionQueue();
    });
  });
}

function updateScenarioReadout() {
  const scenario = currentScenario();
  const risk = Number(scenario.scenario_service_risk || 0);
  document.querySelector("#scenarioName").textContent = scenario.scenario;
  document.querySelector("#scenarioRisk").textContent = formatPct(risk);
  document.querySelector("#scenarioUnits").textContent = `${formatNumber(scenario.scenario_forecast_units_28d)} Units Impacted`;
  document.querySelector("#selectedScenarioImpact").textContent = formatMoney(scenario.scenario_revenue_at_risk);
  const riskLanguage =
    risk > 0.58
      ? "This scenario needs active capacity protection before promises are accepted."
      : risk > 0.34
        ? "This scenario is manageable only if the ranked lanes are watched early."
        : "This scenario stays within the current decision guardrails.";
  document.querySelector("#scenarioNarrative").textContent =
    `${scenario.scenario} projects ${formatMoney(scenario.scenario_revenue_at_risk)} in revenue at risk. ${riskLanguage}`;
}

function drawMarketCanvas() {
  const canvas = document.querySelector("#marketCanvas");
  const { context, width, height } = setupCanvas(canvas);
  context.clearRect(0, 0, width, height);

  const scenario = currentScenario();
  const multiplier = scenarioMultiplier();
  const topStates = data.deliveryState.slice(0, 18);
  const demandHotspots = data.demandRisk.slice(0, 12);
  const core = { x: width * 0.18, y: height * 0.63 };

  context.strokeStyle = "rgba(244,247,239,0.08)";
  context.lineWidth = 1;
  for (let x = 0; x < width; x += 42) {
    context.beginPath();
    context.moveTo(x, 0);
    context.lineTo(x, height);
    context.stroke();
  }
  for (let y = 0; y < height; y += 42) {
    context.beginPath();
    context.moveTo(0, y);
    context.lineTo(width, y);
    context.stroke();
  }

  context.fillStyle = "rgba(57,240,194,0.09)";
  context.strokeStyle = "rgba(57,240,194,0.34)";
  context.lineWidth = 2;
  context.beginPath();
  context.arc(core.x, core.y, 70, 0, Math.PI * 2);
  context.fill();
  context.stroke();
  context.fillStyle = "#f4f7ef";
  context.font = "900 12px Inter, sans-serif";
  context.fillText("MARKETPLACE CORE", core.x - 58, core.y + 4);

  topStates.forEach((state, index) => {
    const point = statePoints[state.customer_state] || [0.36 + (index % 5) * 0.105, 0.26 + Math.floor(index / 5) * 0.14];
    const x = point[0] * width;
    const y = point[1] * height;
    const risk = Number(state.avg_delivery_risk_score || 0) * multiplier;
    const tone = riskTone(risk);
    const lineWidth = 1.5 + Math.min(8, Number(state.orders || 0) / 800);

    context.globalAlpha = 0.25 + Math.min(0.5, risk / 180);
    context.strokeStyle = tone.color;
    context.lineWidth = lineWidth;
    context.beginPath();
    context.moveTo(core.x, core.y);
    const cpX = (core.x + x) / 2 + (index % 3) * 22;
    const cpY = Math.min(core.y, y) - 50 - (index % 4) * 15;
    context.quadraticCurveTo(cpX, cpY, x, y);
    context.stroke();

    context.globalAlpha = 1;
    context.fillStyle = tone.color;
    context.beginPath();
    context.arc(x, y, 5 + Math.min(12, risk / 8), 0, Math.PI * 2);
    context.fill();
    context.strokeStyle = "rgba(244,247,239,0.72)";
    context.lineWidth = 1;
    context.stroke();
    context.fillStyle = "#f4f7ef";
    context.font = "900 11px Inter, sans-serif";
    context.fillText(state.customer_state, x + 12, y + 4);
  });

  demandHotspots.forEach((row, index) => {
    const x = width * (0.42 + (index % 4) * 0.115);
    const y = height * (0.64 + Math.floor(index / 4) * 0.085);
    const score = Number(row.inventory_exposure_score || 0);
    const tone = riskTone(score);
    context.fillStyle = "rgba(7,17,15,0.78)";
    context.strokeStyle = tone.color;
    context.lineWidth = 1.5;
    context.fillRect(x, y, 118, 34);
    context.strokeRect(x, y, 118, 34);
    context.fillStyle = tone.color;
    context.fillRect(x, y + 29, 118 * Math.min(1, score / 100), 5);
    context.fillStyle = "#f4f7ef";
    context.font = "800 10px Inter, sans-serif";
    context.fillText(shorten(titleize(row.category), 15), x + 8, y + 14);
    context.fillStyle = "rgba(244,247,239,0.68)";
    context.fillText(`${row.state_id} / ${score.toFixed(1)}`, x + 8, y + 27);
  });

  const risk = Number(scenario.scenario_service_risk || 0);
  const x = width - 260;
  const y = 30;
  context.fillStyle = "rgba(7,17,15,0.72)";
  context.strokeStyle = "rgba(210,235,224,0.28)";
  context.fillRect(x, y, 220, 86);
  context.strokeRect(x, y, 220, 86);
  context.fillStyle = "#f5c04e";
  context.font = "900 11px Inter, sans-serif";
  context.fillText("SCENARIO SERVICE RISK", x + 14, y + 24);
  context.fillStyle = "rgba(244,247,239,0.12)";
  context.fillRect(x + 14, y + 46, 192, 10);
  context.fillStyle = riskTone(risk * 100).color;
  context.fillRect(x + 14, y + 46, 192 * Math.min(1, risk), 10);
  context.fillStyle = "#f4f7ef";
  context.font = "900 22px Inter, sans-serif";
  context.fillText(formatPct(risk), x + 14, y + 78);
}

function drawForecastChart() {
  const canvas = document.querySelector("#forecastCanvas");
  const { context, width, height } = setupCanvas(canvas);
  context.clearRect(0, 0, width, height);

  const margin = { top: 28, right: 30, bottom: 46, left: 60 };
  const chartWidth = width - margin.left - margin.right;
  const chartHeight = height - margin.top - margin.bottom;
  const categories = [...new Set(data.demandByCategory.map((row) => row.category))];
  const dates = [...new Set(data.demandByCategory.map((row) => row.date))];
  const multiplier = scenarioMultiplier();
  const maxUnits = Math.max(...data.demandByCategory.map((row) => Number(row.forecast_units || 0) * multiplier), 1) * 1.16;

  context.strokeStyle = "rgba(244,247,239,0.11)";
  context.lineWidth = 1;
  context.fillStyle = "rgba(244,247,239,0.58)";
  context.font = "800 12px Inter, sans-serif";
  for (let i = 0; i <= 4; i += 1) {
    const y = margin.top + chartHeight - (chartHeight * i) / 4;
    context.beginPath();
    context.moveTo(margin.left, y);
    context.lineTo(width - margin.right, y);
    context.stroke();
    context.fillText(formatNumber((maxUnits * i) / 4), 12, y + 4);
  }

  categories.forEach((category, categoryIndex) => {
    const points = data.demandByCategory.filter((row) => row.category === category);
    const color = categoryColor(category, categoryIndex);
    context.beginPath();
    context.strokeStyle = color;
    context.lineWidth = categoryIndex === 0 ? 3 : 2;
    points.forEach((point, index) => {
      const x = margin.left + (chartWidth * index) / Math.max(points.length - 1, 1);
      const adjusted = Number(point.forecast_units || 0) * multiplier;
      const y = margin.top + chartHeight - (adjusted / maxUnits) * chartHeight;
      if (index === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    });
    context.stroke();
  });

  context.fillStyle = "rgba(244,247,239,0.72)";
  context.font = "800 11px Inter, sans-serif";
  dates
    .filter((_, index) => index % 7 === 0)
    .forEach((date) => {
      const index = dates.indexOf(date);
      const x = margin.left + (chartWidth * index) / Math.max(dates.length - 1, 1);
      context.fillText(date.slice(5), x - 14, height - 16);
    });

  categories.slice(0, 6).forEach((category, index) => {
    const x = margin.left + (index % 3) * 210;
    const y = 10 + Math.floor(index / 3) * 18;
    context.fillStyle = categoryColor(category, index);
    context.fillRect(x, y, 12, 8);
    context.fillStyle = "rgba(244,247,239,0.82)";
    context.fillText(shorten(titleize(category), 20), x + 18, y + 8);
  });
}

function renderActionQueue() {
  const search = document.querySelector("#actionSearch").value.trim().toLowerCase();
  const rows = data.actionQueue.filter((row) => {
    const matchesFilter = selectedQueueFilter === "All" || row.lane === selectedQueueFilter;
    const haystack = `${row.lane} ${row.title} ${row.risk_level} ${row.action}`.toLowerCase();
    return matchesFilter && haystack.includes(search);
  });

  if (!rows.length) {
    document.querySelector("#actionList").innerHTML =
      "<div class='empty-state'>No Matching Actions Found. Adjust The Search Or Filter.</div>";
    return;
  }

  document.querySelector("#actionList").innerHTML = rows
    .map((row) => {
      const level = String(row.risk_level || "Low").toLowerCase();
      return `
        <article class="action-row ${level}">
          <div class="action-meta">
            <span>${escapeHtml(row.title)}</span>
            <b class="risk-badge ${level}">${escapeHtml(row.risk_level)} / ${Number(row.score || 0).toFixed(1)}</b>
          </div>
          <p>${escapeHtml(row.lane)} - ${escapeHtml(row.action)}</p>
          <p>Impact Signal: ${formatMoney(row.impact)}</p>
        </article>
      `;
    })
    .join("");
}

function buildQueueFilters() {
  document.querySelectorAll("#queueFilters button").forEach((button) => {
    button.addEventListener("click", () => {
      selectedQueueFilter = button.dataset.filter;
      document.querySelectorAll("#queueFilters button").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      renderActionQueue();
    });
  });
  document.querySelector("#actionSearch").addEventListener("input", renderActionQueue);
}

function renderDemandLanes() {
  const rows = data.demandRisk.slice(0, 8);
  document.querySelector("#demandLaneList").innerHTML = rows
    .map((row) => {
      const score = Number(row.inventory_exposure_score || 0);
      return `
        <article class="lane-card">
          <small>${escapeHtml(row.state_id)} / ${formatMoney(row.revenue_at_risk)} At Risk</small>
          <strong>${escapeHtml(titleize(row.category))}</strong>
          <div class="pressure-track"><i style="width:${Math.max(4, score)}%"></i></div>
          <p>${score.toFixed(1)} Exposure / ${formatNumber(row.forecast_units_28d, 1)} Forecast Units</p>
        </article>
      `;
    })
    .join("");
}

function renderStateMap() {
  const maxRisk = Math.max(...data.deliveryState.map((state) => Number(state.avg_delivery_risk_score || 0)), 1);
  document.querySelector("#stateMap").innerHTML = data.deliveryState
    .slice(0, 20)
    .map((state) => {
      const risk = Number(state.avg_delivery_risk_score || 0);
      const pct = Math.max(5, (risk / maxRisk) * 100);
      return `
        <article class="state-tile" title="${escapeHtml(state.customer_state)} Late Delivery Rate ${formatPct(state.late_delivery_rate)}">
          <strong>${escapeHtml(state.customer_state)}</strong>
          <span>${risk.toFixed(1)} Risk</span>
          <div class="state-bar"><i style="width:${pct}%"></i></div>
          <span>${formatNumber(state.orders)} Orders</span>
        </article>
      `;
    })
    .join("");
}

function renderSellerRisk() {
  document.querySelector("#sellerRiskList").innerHTML = data.sellerRisk
    .slice(0, 8)
    .map(
      (seller) => `
        <article class="seller-row">
          <div>
            <strong>${escapeHtml(seller.seller_state)} / ${escapeHtml(seller.seller_city)}</strong>
            <small>${formatNumber(seller.orders)} Orders / ${formatPct(seller.late_delivery_rate)} Late</small>
          </div>
          <b class="seller-score">${Number(seller.avg_delivery_risk_score || 0).toFixed(1)}</b>
        </article>
      `,
    )
    .join("");
}

function renderImportance() {
  const maxImportance = Math.max(...data.featureImportance.map((row) => Math.abs(Number(row.importance || 0))), 0.001);
  document.querySelector("#importanceList").innerHTML = data.featureImportance
    .slice(0, 10)
    .map((row) => {
      const width = Math.max(2, (Math.abs(Number(row.importance || 0)) / maxImportance) * 100);
      return `
        <div class="importance-row">
          <div>
            <span>${escapeHtml(titleize(row.feature))}</span>
            <small>${escapeHtml(row.model)}</small>
          </div>
          <div class="importance-track"><i style="width:${width}%"></i></div>
        </div>
      `;
    })
    .join("");
}

function renderMetrics() {
  const preferred = ["MAE", "MAPE", "ROC AUC", "Average Precision", "F1", "F1 Threshold", "Series Modeled", "Late Delivery Rate"];
  const rows = data.modelMetrics.filter((row) => preferred.includes(row.metric));
  document.querySelector("#metricList").innerHTML = rows
    .map(
      (row) => `
        <div class="metric-row">
          <span>${escapeHtml(row.metric)}</span>
          <small>${Number(row.value || 0).toLocaleString("en-US", { maximumFractionDigits: 4 })}</small>
        </div>
      `,
    )
    .join("");
}

function drawAllCanvases() {
  drawMarketCanvas();
  drawForecastChart();
}

function init() {
  if (!data) {
    document.body.innerHTML = "<main class='dashboard-shell'><h1>Dashboard Data Missing</h1></main>";
    return;
  }
  setKpis();
  buildScenarioButtons();
  updateScenarioReadout();
  buildQueueFilters();
  renderActionQueue();
  renderDemandLanes();
  renderStateMap();
  renderSellerRisk();
  renderImportance();
  renderMetrics();
  drawAllCanvases();
  window.addEventListener("resize", drawAllCanvases);
}

init();

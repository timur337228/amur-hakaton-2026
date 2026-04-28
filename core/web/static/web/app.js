const API_BASE_URL = (window.BUDGET_API_BASE_URL || "").replace(/\/$/, "");
const IMPORT_TERMINAL_STATUSES = new Set(["completed", "completed_with_errors", "failed"]);

const state = {
  batchId: localStorage.getItem("budgetAnalytics.batchId") || "",
  filterOptions: null,
  resolvedRequest: null,
};

const elements = {
  localPathInput: document.getElementById("local-path-input"),
  localImportBtn: document.getElementById("local-import-btn"),
  archiveInput: document.getElementById("archive-input"),
  folderInput: document.getElementById("folder-input"),
  batchIdInput: document.getElementById("batch-id-input"),
  loadBatchBtn: document.getElementById("load-batch-btn"),
  importStatusBadge: document.getElementById("import-status-badge"),
  batchStatus: document.getElementById("batch-status"),
  datasetSummary: document.getElementById("dataset-summary"),
  textQueryInput: document.getElementById("text-query-input"),
  dateFromInput: document.getElementById("date-from-input"),
  dateToInput: document.getElementById("date-to-input"),
  objectQueryInput: document.getElementById("object-query-input"),
  organizationQueryInput: document.getElementById("organization-query-input"),
  budgetQueryInput: document.getElementById("budget-query-input"),
  kfsrCodeInput: document.getElementById("kfsr-code-input"),
  kcsrCodeInput: document.getElementById("kcsr-code-input"),
  kvrCodeInput: document.getElementById("kvr-code-input"),
  fundingSourceInput: document.getElementById("funding-source-input"),
  metricsOptions: document.getElementById("metrics-options"),
  groupByOptions: document.getElementById("group-by-options"),
  sourceGroupsOptions: document.getElementById("source-groups-options"),
  llmBadge: document.getElementById("llm-badge"),
  resolveBtn: document.getElementById("resolve-btn"),
  runQueryBtn: document.getElementById("run-query-btn"),
  exportBtn: document.getElementById("export-btn"),
  resolveStatus: document.getElementById("resolve-status"),
  resolvedRequestOutput: document.getElementById("resolved-request-output"),
  summaryCards: document.getElementById("summary-cards"),
  timeseriesChart: document.getElementById("timeseries-chart"),
  metricsChart: document.getElementById("metrics-chart"),
  previewStatus: document.getElementById("preview-status"),
  previewTable: document.getElementById("preview-table"),
  queryStatus: document.getElementById("query-status"),
  resultsTable: document.getElementById("results-table"),
  toast: document.getElementById("toast"),
  promptChips: Array.from(document.querySelectorAll(".prompt-chip")),
};

const optionMap = {
  object_options: document.getElementById("object-options"),
  organization_options: document.getElementById("organization-options"),
  budget_options: document.getElementById("budget-options"),
  kfsr_options: document.getElementById("kfsr-options"),
  kcsr_options: document.getElementById("kcsr-options"),
  kvr_options: document.getElementById("kvr-options"),
  funding_source_options: document.getElementById("funding-source-options"),
};

const groupByOptions = [
  { value: "month", label: "По месяцам", checked: true },
  { value: "year", label: "По годам" },
  { value: "object_name", label: "По объекту" },
  { value: "organization_name", label: "По организации" },
  { value: "source_group", label: "По источнику" },
  { value: "metric", label: "По показателю" },
];

initialize().catch(handleError);

async function initialize() {
  elements.batchIdInput.value = state.batchId;
  renderGroupByOptions();
  bindEvents();
  if (state.batchId) {
    await loadBatch(state.batchId);
  } else {
    renderDatasetSummary([]);
    renderSummaryCards({});
    renderTable(elements.previewTable, []);
    renderTable(elements.resultsTable, []);
  }
}

function bindEvents() {
  elements.localImportBtn.addEventListener("click", wrapAsync(importLocalPath));
  elements.archiveInput.addEventListener("change", wrapAsync(importArchive));
  elements.folderInput.addEventListener("change", wrapAsync(importFolder));
  elements.loadBatchBtn.addEventListener("click", wrapAsync(() => loadBatch(elements.batchIdInput.value.trim())));
  elements.resolveBtn.addEventListener("click", wrapAsync(resolveTextRequest));
  elements.runQueryBtn.addEventListener("click", wrapAsync(runQuery));
  elements.exportBtn.addEventListener("click", wrapAsync(exportXlsx));
  elements.promptChips.forEach((chip) =>
    chip.addEventListener("click", () => {
      elements.textQueryInput.value = chip.dataset.prompt || "";
      elements.textQueryInput.focus();
    })
  );
}

async function importLocalPath() {
  const path = elements.localPathInput.value.trim();
  if (!path) {
    showToast("Укажи путь к папке для импорта.");
    return;
  }
  setBadge(elements.importStatusBadge, "импорт...", "warn");
  const response = await fetchJson(apiUrl("/api/v1/imports/local-path"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  await completeImport(response);
}

async function importArchive(event) {
  const file = event.target.files?.[0];
  if (!file) {
    return;
  }
  setBadge(elements.importStatusBadge, "загрузка...", "warn");
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetchJson(apiUrl("/api/v1/imports/archive"), {
    method: "POST",
    body: formData,
  });
  await completeImport(response);
  elements.archiveInput.value = "";
}

async function importFolder(event) {
  const files = Array.from(event.target.files || []);
  if (!files.length) {
    return;
  }
  setBadge(elements.importStatusBadge, "загрузка...", "warn");
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file, file.name);
    formData.append("relative_paths", file.webkitRelativePath || file.name);
  }
  const response = await fetchJson(apiUrl("/api/v1/imports/files"), {
    method: "POST",
    body: formData,
  });
  await completeImport(response);
  elements.folderInput.value = "";
}

async function completeImport(response) {
  state.batchId = response.batch_id;
  localStorage.setItem("budgetAnalytics.batchId", state.batchId);
  elements.batchIdInput.value = state.batchId;
  setBadge(elements.importStatusBadge, "в очереди", "warn");
  showToast(`Импорт поставлен в очередь. Batch: ${state.batchId}`);
  await loadBatch(state.batchId);
}

async function loadBatch(batchId, options = {}) {
  if (!batchId) {
    showToast("Укажи batch_id.");
    return;
  }
  state.batchId = batchId;
  localStorage.setItem("budgetAnalytics.batchId", batchId);
  elements.batchIdInput.value = batchId;
  setBadge(elements.batchStatus, "загрузка...", "warn");

  let batch = await fetchJson(apiUrl(`/api/v1/imports/${batchId}`));
  if (!IMPORT_TERMINAL_STATUSES.has(batch.status) && !options.skipWait) {
    batch = await waitForBatchReady(batchId, batch);
  }

  if (batch.status === "failed") {
    setBadge(elements.batchStatus, "ошибка", "danger");
    setBadge(elements.importStatusBadge, "ошибка", "danger");
    showToast(batch.message || "Импорт завершился с ошибкой.");
    return;
  }

  const [stats, preview, filterOptions] = await Promise.all([
    fetchJson(apiUrl(`/api/v1/imports/${batchId}/stats`)),
    fetchJson(apiUrl(`/api/v1/imports/${batchId}/preview?limit=20&offset=0`)),
    fetchJson(apiUrl(`/api/v1/analytics/filter-options?batch_id=${encodeURIComponent(batchId)}&limit=80`)),
  ]);

  state.filterOptions = filterOptions;
  renderDatasetSummary([
    ["Файлы", String(stats.total_files)],
    ["CSV", String(stats.csv_files)],
    ["Строки", formatInt(stats.rows_count)],
    ["Метрики", String(stats.metrics.length)],
    ["Дата от", stats.date_min || "-"],
    ["Дата до", stats.date_max || "-"],
  ]);
  setBadge(elements.batchStatus, batch.status === "completed_with_errors" ? "готов с ошибками" : "загружен", batch.status === "completed_with_errors" ? "warn" : "ok");
  setBadge(elements.importStatusBadge, batch.status === "completed_with_errors" ? "с ошибками" : "готово", batch.status === "completed_with_errors" ? "warn" : "ok");
  fillFilterOptions(filterOptions);
  renderPreview(preview);
  renderResolvePreview({
    batch_id: batchId,
    llm_applied: false,
    resolved_request: buildRequestPayload(),
  });
}

async function waitForBatchReady(batchId, initialBatch) {
  let batch = initialBatch;
  const startedAt = Date.now();

  while (!IMPORT_TERMINAL_STATUSES.has(batch.status)) {
    setBadge(elements.batchStatus, formatImportStatus(batch.status), "warn");
    if (batch.message) {
      elements.batchStatus.title = batch.message;
    }
    if (Date.now() - startedAt > 5 * 60 * 1000) {
      throw new Error("Импорт не завершился за 5 минут. Попробуй обновить статус по batch_id позже.");
    }
    await sleep(1500);
    batch = await fetchJson(apiUrl(`/api/v1/imports/${batchId}`));
  }

  return batch;
}

function fillFilterOptions(filterOptions) {
  renderMetricOptions(filterOptions.metrics || []);
  renderSourceGroupOptions(filterOptions.source_groups || []);
  fillDatalist(optionMap.object_options, filterOptions.objects || []);
  fillDatalist(optionMap.organization_options, filterOptions.organizations || []);
  fillDatalist(optionMap.budget_options, filterOptions.budgets || []);
  fillDatalist(optionMap.kfsr_options, filterOptions.kfsr_codes || []);
  fillDatalist(optionMap.kcsr_options, filterOptions.kcsr_codes || []);
  fillDatalist(optionMap.kvr_options, filterOptions.kvr_codes || []);
  fillDatalist(optionMap.funding_source_options, filterOptions.funding_sources || []);
}

function renderMetricOptions(metrics) {
  const labels = {
    limits: "Лимиты",
    obligations: "Обязательства",
    obligations_without_bo: "Без БО",
    remaining_limits: "Остаток",
    cash_payments: "Кассовые выплаты",
    agreement_amount: "Соглашения",
    contract_amount: "Контракты",
    contract_payment: "Платежи по контрактам",
    institution_payments_with_refund: "БУАУ с возвратом",
    institution_payments_execution: "БУАУ исполнение",
    institution_payments_recovery: "БУАУ восстановление",
  };
  elements.metricsOptions.innerHTML = metrics
    .map(
      (metric) => `
        <label class="option-pill">
          <input type="checkbox" name="metric" value="${escapeHtml(metric)}">
          <span>${escapeHtml(labels[metric] || metric)}</span>
        </label>
      `
    )
    .join("");
}

function renderGroupByOptions() {
  elements.groupByOptions.innerHTML = groupByOptions
    .map(
      (option) => `
        <label class="option-pill">
          <input type="radio" name="group_by" value="${option.value}" ${option.checked ? "checked" : ""}>
          <span>${option.label}</span>
        </label>
      `
    )
    .join("");
}

function renderSourceGroupOptions(sourceGroups) {
  elements.sourceGroupsOptions.innerHTML = sourceGroups
    .map(
      (value) => `
        <label class="option-pill">
          <input type="checkbox" name="source_group" value="${escapeHtml(value)}">
          <span>${escapeHtml(value)}</span>
        </label>
      `
    )
    .join("");
}

function fillDatalist(element, values) {
  element.innerHTML = values.map((value) => `<option value="${escapeHtml(value)}"></option>`).join("");
}

function formatImportStatus(status) {
  const labels = {
    created: "создан",
    queued: "в очереди",
    copying: "копирование",
    extracting: "распаковка",
    processing: "обработка",
    completed: "готово",
    completed_with_errors: "готово с ошибками",
    failed: "ошибка",
  };
  return labels[status] || status;
}

async function resolveTextRequest() {
  ensureBatch();
  const payload = buildRequestPayload();
  const response = await fetchJson(apiUrl("/api/v1/analytics/resolve-text"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (response.warning) {
    showToast(response.warning);
  }
  renderResolvePreview(response);
}

async function runQuery() {
  ensureBatch();
  const payload = buildRequestPayload();
  const response = await fetchJson(apiUrl("/api/v1/analytics/query"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (response.meta?.warning) {
    showToast(response.meta.warning);
  }
  state.resolvedRequest = response.meta?.resolved_request || payload;
  setBadge(elements.queryStatus, `${formatInt(response.meta.rows_count)} строк`, "ok");
  setBadge(elements.llmBadge, response.meta.llm_applied ? "LLM + фильтры" : "параметры", response.meta.llm_applied ? "ok" : "muted");
  renderSummaryCards(response.summary, response.execution_percent);
  renderResults(response.rows || []);
  renderCharts(response.charts);
  renderResolvePreview({
    batch_id: response.meta.batch_id,
    text_query: response.meta.text_query,
    llm_applied: response.meta.llm_applied,
    resolved_request: response.meta.resolved_request,
  });
}

async function exportXlsx() {
  ensureBatch();
  const payload = buildRequestPayload();
  const response = await fetch(apiUrl("/api/v1/analytics/export/xlsx"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const disposition = response.headers.get("Content-Disposition") || "";
  const fileNameMatch = disposition.match(/filename\*=UTF-8''([^;]+)/);
  const fileName = fileNameMatch ? decodeURIComponent(fileNameMatch[1]) : "analytics.xlsx";
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}

function buildRequestPayload() {
  const selectedMetrics = checkedValues("metric");
  const selectedSources = checkedValues("source_group");
  const selectedGroupBy = radioValue("group_by");

  const payload = {
    batch_id: state.batchId,
    text_query: textValue(elements.textQueryInput),
    date_from: textValue(elements.dateFromInput),
    date_to: textValue(elements.dateToInput),
    metrics: selectedMetrics.length ? selectedMetrics : null,
    filters: {
      source_groups: selectedSources.length ? selectedSources : null,
      object_query: textValue(elements.objectQueryInput),
      budget_query: textValue(elements.budgetQueryInput),
      organization_query: textValue(elements.organizationQueryInput),
      kfsr_code: textValue(elements.kfsrCodeInput),
      kcsr_code: textValue(elements.kcsrCodeInput),
      kvr_code: textValue(elements.kvrCodeInput),
      funding_source: textValue(elements.fundingSourceInput),
    },
    group_by: selectedGroupBy ? [selectedGroupBy] : ["month"],
    include_rows: true,
    include_charts: true,
  };

  if (!payload.text_query) {
    payload.text_query = null;
  }
  if (!payload.date_from) {
    payload.date_from = null;
  }
  if (!payload.date_to) {
    payload.date_to = null;
  }

  return payload;
}

function renderPreview(preview) {
  setBadge(elements.previewStatus, `${preview.returned_rows}/${preview.rows_count}`, "ok");
  renderTable(elements.previewTable, preview.rows || []);
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function renderResults(rows) {
  renderTable(elements.resultsTable, rows.map((row) => ({ ...row.dimensions, metric: row.metric, value: row.value })));
}

function renderResolvePreview(response) {
  state.resolvedRequest = response.resolved_request || null;
  setBadge(elements.resolveStatus, response.llm_applied ? "LLM применен" : "без LLM", response.llm_applied ? "ok" : "muted");
  setBadge(elements.llmBadge, response.llm_applied ? "LLM + фильтры" : "параметры", response.llm_applied ? "ok" : "muted");
  elements.resolvedRequestOutput.textContent = JSON.stringify(response, null, 2);
}

function renderDatasetSummary(items) {
  if (!items.length) {
    elements.datasetSummary.innerHTML = '<div class="stat-card"><span>Набор</span><strong>Не выбран</strong></div>';
    return;
  }
  elements.datasetSummary.innerHTML = items
    .map(
      ([label, value]) => `
        <div class="stat-card">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
        </div>
      `
    )
    .join("");
}

function renderSummaryCards(summary, executionPercent = null) {
  const cards = Object.entries(summary || {});
  const extra = executionPercent !== null && executionPercent !== undefined
    ? [["Исполнение", `${executionPercent}%`]]
    : [];
  const allCards = cards.concat(extra);

  if (!allCards.length) {
    elements.summaryCards.innerHTML = '<div class="summary-card"><span>Итог</span><strong>Нет данных</strong></div>';
    return;
  }

  elements.summaryCards.innerHTML = allCards
    .map(
      ([label, value]) => `
        <div class="summary-card">
          <span>${escapeHtml(prettyMetricName(label))}</span>
          <strong>${escapeHtml(typeof value === "string" ? value : formatNumber(value))}</strong>
        </div>
      `
    )
    .join("");
}

function renderCharts(charts) {
  renderTimeseries(charts?.timeseries || []);
  renderMetricBars(charts?.by_metric || []);
}

function renderTimeseries(points) {
  if (!points.length) {
    elements.timeseriesChart.classList.add("empty");
    elements.timeseriesChart.textContent = "Нет данных";
    return;
  }

  const grouped = new Map();
  for (const point of points) {
    if (!grouped.has(point.period)) {
      grouped.set(point.period, 0);
    }
    grouped.set(point.period, grouped.get(point.period) + Number(point.value));
  }
  const series = Array.from(grouped.entries());
  const maxValue = Math.max(...series.map(([, value]) => value), 1);
  const width = 540;
  const height = 220;
  const step = width / Math.max(series.length - 1, 1);
  const coords = series.map(([period, value], index) => {
    const x = 32 + index * step;
    const y = height - 28 - (value / maxValue) * 150;
    return { period, value, x, y };
  });
  const path = coords.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");

  elements.timeseriesChart.classList.remove("empty");
  elements.timeseriesChart.innerHTML = `
    <svg class="chart-svg" viewBox="0 0 ${width + 64} ${height}">
      <line x1="24" y1="${height - 28}" x2="${width + 24}" y2="${height - 28}" stroke="#cbd5e1" />
      <path d="${path}" fill="none" stroke="#0e8f78" stroke-width="3" />
      ${coords
        .map(
          (point) => `
            <circle cx="${point.x}" cy="${point.y}" r="4" fill="#1557c0" />
            <text x="${point.x}" y="${height - 10}" text-anchor="middle" class="chart-label">${escapeHtml(point.period)}</text>
          `
        )
        .join("")}
    </svg>
  `;
}

function renderMetricBars(rows) {
  if (!rows.length) {
    elements.metricsChart.classList.add("empty");
    elements.metricsChart.textContent = "Нет данных";
    return;
  }

  const values = rows.map((row) => ({
    label: prettyMetricName(row.metric),
    value: Number(row.value),
  }));
  const maxValue = Math.max(...values.map((item) => item.value), 1);
  const width = 560;
  const barHeight = 28;
  const gap = 16;
  const height = values.length * (barHeight + gap) + 24;

  elements.metricsChart.classList.remove("empty");
  elements.metricsChart.innerHTML = `
    <svg class="chart-svg" viewBox="0 0 ${width} ${height}">
      ${values
        .map((item, index) => {
          const y = 16 + index * (barHeight + gap);
          const barWidth = Math.max(12, (item.value / maxValue) * 300);
          return `
            <text x="0" y="${y + 18}" class="chart-label">${escapeHtml(item.label)}</text>
            <rect x="220" y="${y}" width="${barWidth}" height="${barHeight}" rx="6" fill="${index % 2 === 0 ? "#0e8f78" : "#1557c0"}"></rect>
            <text x="${228 + barWidth}" y="${y + 18}" class="chart-value">${escapeHtml(formatNumber(item.value))}</text>
          `;
        })
        .join("")}
    </svg>
  `;
}

function renderTable(table, rows) {
  const thead = table.querySelector("thead");
  const tbody = table.querySelector("tbody");
  if (!rows.length) {
    thead.innerHTML = "";
    tbody.innerHTML = '<tr><td>Нет данных</td></tr>';
    return;
  }
  const columns = Array.from(
    rows.reduce((set, row) => {
      Object.keys(row).forEach((key) => set.add(key));
      return set;
    }, new Set())
  );
  thead.innerHTML = `<tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr>`;
  tbody.innerHTML = rows
    .map(
      (row) =>
        `<tr>${columns
          .map((column) => `<td>${escapeHtml(formatCell(row[column]))}</td>`)
          .join("")}</tr>`
    )
    .join("");
}

function checkedValues(name) {
  return Array.from(document.querySelectorAll(`input[name="${name}"]:checked`)).map((input) => input.value);
}

function radioValue(name) {
  return document.querySelector(`input[name="${name}"]:checked`)?.value || null;
}

function textValue(element) {
  const value = element.value.trim();
  return value ? value : null;
}

function ensureBatch() {
  if (!state.batchId) {
    throw new Error("Сначала загрузи или выбери batch.");
  }
}

function apiUrl(path) {
  return `${API_BASE_URL}${path}`;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

async function readError(response) {
  try {
    const data = await response.json();
    return data.detail || JSON.stringify(data);
  } catch {
    return `${response.status} ${response.statusText}`;
  }
}

function handleError(error) {
  console.error(error);
  showToast(error.message || "Что-то пошло не так.");
}

function wrapAsync(handler) {
  return (event) => Promise.resolve(handler(event)).catch(handleError);
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.remove("hidden");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => {
    elements.toast.classList.add("hidden");
  }, 3200);
}

function setBadge(element, text, mode) {
  element.textContent = text;
  element.className = `badge ${mode}`;
}

function prettyMetricName(metric) {
  const labels = {
    limits: "Лимиты",
    obligations: "Обязательства",
    obligations_without_bo: "Обязательства без БО",
    remaining_limits: "Остаток лимитов",
    cash_payments: "Кассовые выплаты",
    agreement_amount: "Сумма соглашений",
    contract_amount: "Сумма контрактов",
    contract_payment: "Платежи по контрактам",
    institution_payments_with_refund: "БУАУ с возвратом",
    institution_payments_execution: "БУАУ исполнение",
    institution_payments_recovery: "БУАУ восстановление",
    executionPercent: "Исполнение",
  };
  return labels[metric] || metric;
}

function formatNumber(value) {
  return new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: 2,
  }).format(Number(value));
}

function formatInt(value) {
  return new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: 0,
  }).format(Number(value));
}

function formatCell(value) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  if (typeof value === "number") {
    return formatNumber(value);
  }
  return String(value);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

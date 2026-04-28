const API_BASE_URL = (window.BUDGET_API_BASE_URL || "").replace(/\/$/, "");
const IMPORT_TERMINAL_STATUSES = new Set(["completed", "completed_with_errors", "failed"]);
const ARCHIVE_EXTENSIONS = [".zip", ".rar", ".7z"];

const state = {
  batchId: localStorage.getItem("budgetAnalytics.batchId") || "",
  filterOptions: null,
};

const elements = {
  dropzone: document.getElementById("import-dropzone"),
  chooseArchiveBtn: document.getElementById("choose-archive-btn"),
  chooseFolderBtn: document.getElementById("choose-folder-btn"),
  archiveInput: document.getElementById("archive-input"),
  folderInput: document.getElementById("folder-input"),
  importStatusBadge: document.getElementById("import-status-badge"),
  batchStatus: document.getElementById("batch-status"),
  datasetSummary: document.getElementById("dataset-summary"),
  batchMeta: document.getElementById("batch-meta"),
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
  runQueryBtn: document.getElementById("run-query-btn"),
  exportBtn: document.getElementById("export-btn"),
  summaryCards: document.getElementById("summary-cards"),
  timeseriesChart: document.getElementById("timeseries-chart"),
  cumulativeChart: document.getElementById("cumulative-chart"),
  metricsChart: document.getElementById("metrics-chart"),
  yearlyChart: document.getElementById("yearly-chart"),
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
  renderGroupByOptions();
  bindEvents();
  renderEmptyState();
  await bootstrapDataset();
}

function bindEvents() {
  elements.chooseArchiveBtn.addEventListener("click", () => elements.archiveInput.click());
  elements.chooseFolderBtn.addEventListener("click", () => elements.folderInput.click());
  elements.archiveInput.addEventListener("change", wrapAsync(handleArchiveSelection));
  elements.folderInput.addEventListener("change", wrapAsync(handleFolderSelection));
  elements.runQueryBtn.addEventListener("click", wrapAsync(runQuery));
  elements.exportBtn.addEventListener("click", wrapAsync(exportXlsx));
  elements.promptChips.forEach((chip) =>
    chip.addEventListener("click", () => {
      elements.textQueryInput.value = chip.dataset.prompt || "";
      elements.textQueryInput.focus();
    })
  );

  ["dragenter", "dragover"].forEach((eventName) => {
    elements.dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      event.stopPropagation();
      elements.dropzone.classList.add("is-active");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    elements.dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (eventName === "drop") {
        return;
      }
      elements.dropzone.classList.remove("is-active");
    });
  });

  elements.dropzone.addEventListener("drop", wrapAsync(handleDrop));
}

async function bootstrapDataset() {
  if (state.batchId) {
    const loaded = await tryLoadBatch(state.batchId);
    if (loaded) {
      return;
    }
    clearBatchState();
  }

  const autoImported = await tryAutoImportDefaultDataset();
  if (!autoImported) {
    setBadge(elements.importStatusBadge, "ожидание", "muted");
    setBadge(elements.batchStatus, "нет данных", "muted");
  }
}

async function tryAutoImportDefaultDataset() {
  setBadge(elements.importStatusBadge, "поиск project_file", "muted");
  const response = await requestJson(apiUrl("/api/v1/imports/default"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) {
    if (response.status === 403 || response.status === 404) {
      return false;
    }
    throw new Error(response.error);
  }

  await completeImport(response.data, {
    toastMessage: null,
    announceQueued: false,
    autoLabel: "Локальный набор подключён автоматически",
  });
  return true;
}

async function handleArchiveSelection(event) {
  const file = event.target.files?.[0];
  if (!file) {
    return;
  }
  await uploadArchiveFile(file);
  elements.archiveInput.value = "";
}

async function handleFolderSelection(event) {
  const files = Array.from(event.target.files || []).map((file) => ({
    file,
    relativePath: file.webkitRelativePath || file.name,
  }));
  if (!files.length) {
    return;
  }
  await uploadFolderFiles(files);
  elements.folderInput.value = "";
}

async function handleDrop(event) {
  elements.dropzone.classList.remove("is-active");
  const payload = await detectDroppedPayload(event.dataTransfer);
  if (!payload) {
    showToast("Не удалось определить, что было перетащено.");
    return;
  }
  if (payload.kind === "archive") {
    await uploadArchiveFile(payload.file);
    return;
  }
  await uploadFolderFiles(payload.files);
}

async function detectDroppedPayload(dataTransfer) {
  const entries = await collectDroppedFiles(dataTransfer);
  if (!entries.length) {
    return null;
  }
  if (
    entries.length === 1 &&
    isSupportedArchive(entries[0].file.name) &&
    !entries[0].relativePath.includes("/")
  ) {
    return { kind: "archive", file: entries[0].file };
  }
  return { kind: "files", files: entries };
}

async function collectDroppedFiles(dataTransfer) {
  const items = Array.from(dataTransfer?.items || []).filter((item) => item.kind === "file");
  if (items.length) {
    const collected = [];
    for (const item of items) {
      const entry = item.webkitGetAsEntry?.();
      if (entry) {
        collected.push(...(await walkFileEntry(entry)));
        continue;
      }
      const file = item.getAsFile?.();
      if (file) {
        collected.push({ file, relativePath: file.name });
      }
    }
    if (collected.length) {
      return collected;
    }
  }

  return Array.from(dataTransfer?.files || []).map((file) => ({
    file,
    relativePath: file.webkitRelativePath || file.name,
  }));
}

async function walkFileEntry(entry, prefix = "") {
  if (entry.isFile) {
    return new Promise((resolve, reject) => {
      entry.file(
        (file) => resolve([{ file, relativePath: `${prefix}${file.name}` }]),
        (error) => reject(error)
      );
    });
  }

  if (!entry.isDirectory) {
    return [];
  }

  const reader = entry.createReader();
  const children = await readAllDirectoryEntries(reader);
  const nested = await Promise.all(
    children.map((child) => walkFileEntry(child, `${prefix}${entry.name}/`))
  );
  return nested.flat();
}

async function readAllDirectoryEntries(reader) {
  const entries = [];
  while (true) {
    const chunk = await new Promise((resolve, reject) => {
      reader.readEntries(resolve, reject);
    });
    if (!chunk.length) {
      return entries;
    }
    entries.push(...chunk);
  }
}

async function uploadArchiveFile(file) {
  if (!isSupportedArchive(file.name)) {
    showToast("Поддерживаются только архивы .zip, .rar и .7z.");
    return;
  }
  setBadge(elements.importStatusBadge, "загрузка архива", "warn");
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetchJson(apiUrl("/api/v1/imports/archive"), {
    method: "POST",
    body: formData,
  });
  await completeImport(response, {
    toastMessage: `Архив поставлен на импорт: ${file.name}`,
    announceQueued: true,
  });
}

async function uploadFolderFiles(files) {
  setBadge(elements.importStatusBadge, "загрузка папки", "warn");
  const formData = new FormData();
  for (const item of files) {
    formData.append("files", item.file, item.file.name);
    formData.append("relative_paths", item.relativePath || item.file.name);
  }
  const response = await fetchJson(apiUrl("/api/v1/imports/files"), {
    method: "POST",
    body: formData,
  });
  await completeImport(response, {
    toastMessage: `Папка поставлена на импорт. Файлов: ${files.length}`,
    announceQueued: true,
  });
}

async function completeImport(response, options = {}) {
  state.batchId = response.batch_id;
  localStorage.setItem("budgetAnalytics.batchId", state.batchId);

  if (options.autoLabel) {
    setBadge(elements.importStatusBadge, options.autoLabel, "ok");
  } else if (options.announceQueued) {
    setBadge(elements.importStatusBadge, "импорт в очереди", "warn");
  }

  if (options.toastMessage) {
    showToast(options.toastMessage);
  }

  await loadBatch(state.batchId);
}

async function tryLoadBatch(batchId) {
  try {
    await loadBatch(batchId);
    return true;
  } catch (error) {
    if (String(error.message || "").includes("Import batch not found")) {
      return false;
    }
    throw error;
  }
}

async function loadBatch(batchId, options = {}) {
  ensureBatch(batchId);
  setBadge(elements.batchStatus, "загрузка", "muted");

  let batch = await fetchJson(apiUrl(`/api/v1/imports/${batchId}`));
  if (!IMPORT_TERMINAL_STATUSES.has(batch.status) && !options.skipWait) {
    batch = await waitForBatchReady(batchId, batch);
  }

  if (batch.status === "failed") {
    setBadge(elements.batchStatus, "ошибка", "danger");
    setBadge(elements.importStatusBadge, "ошибка импорта", "danger");
    renderEmptyState();
    throw new Error(batch.message || "Импорт завершился с ошибкой.");
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
    ["Дата от", stats.date_min || "—"],
    ["Дата до", stats.date_max || "—"],
  ]);
  renderBatchMeta(batch, stats);
  fillFilterOptions(filterOptions);
  renderPreview(preview);
  resetQueryPresentation();
  setBadge(
    elements.batchStatus,
    batch.status === "completed_with_errors" ? "готов с ошибками" : "набор готов",
    batch.status === "completed_with_errors" ? "warn" : "ok"
  );
  setBadge(
    elements.importStatusBadge,
    batch.status === "completed_with_errors" ? "импорт с предупреждениями" : "данные загружены",
    batch.status === "completed_with_errors" ? "warn" : "ok"
  );
}

async function waitForBatchReady(batchId, initialBatch) {
  let batch = initialBatch;
  const startedAt = Date.now();

  while (!IMPORT_TERMINAL_STATUSES.has(batch.status)) {
    const statusText = formatImportStatus(batch.status);
    setBadge(elements.batchStatus, statusText, "warn");
    setBadge(elements.importStatusBadge, statusText, "warn");
    if (Date.now() - startedAt > 5 * 60 * 1000) {
      throw new Error("Импорт не завершился за 5 минут. Попробуй обновить страницу позже.");
    }
    await sleep(1500);
    batch = await fetchJson(apiUrl(`/api/v1/imports/${batchId}`));
  }

  return batch;
}

function renderBatchMeta(batch, stats) {
  const parts = [
    `batch: ${batch.batch_id}`,
    `создан: ${formatDateTime(batch.created_at)}`,
  ];
  if (stats.date_min || stats.date_max) {
    parts.push(`период: ${stats.date_min || "—"} — ${stats.date_max || "—"}`);
  }
  elements.batchMeta.textContent = parts.join(" · ");
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

async function runQuery() {
  ensureBatch(state.batchId);
  const payload = buildRequestPayload();
  const response = await fetchJson(apiUrl("/api/v1/analytics/query"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (response.meta?.warning) {
    showToast(response.meta.warning);
  }

  setBadge(elements.queryStatus, `${formatInt(response.meta.rows_count)} строк`, "ok");
  renderSummaryCards(response.summary, response.execution_percent);
  renderResults(response.rows || []);
  renderCharts(response.charts);
}

async function exportXlsx() {
  ensureBatch(state.batchId);
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

  return {
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
}

function renderPreview(preview) {
  setBadge(elements.previewStatus, `${preview.returned_rows}/${preview.rows_count}`, "ok");
  renderTable(elements.previewTable, preview.rows || []);
}

function renderResults(rows) {
  renderTable(
    elements.resultsTable,
    rows.map((row) => ({ ...row.dimensions, metric: row.metric, value: row.value }))
  );
}

function renderDatasetSummary(items) {
  if (!items.length) {
    elements.datasetSummary.innerHTML = '<div class="stat-card"><span>Набор</span><strong>Нет данных</strong></div>';
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
  if (executionPercent !== null && executionPercent !== undefined) {
    cards.push(["executionPercent", `${executionPercent}%`]);
  }
  if (!cards.length) {
    elements.summaryCards.innerHTML = '<div class="summary-card"><span>Итог</span><strong>Нет данных</strong></div>';
    return;
  }
  elements.summaryCards.innerHTML = cards
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
  const timeseries = normalizeTimeseries(charts?.timeseries || []);
  renderTimeseriesChart(elements.timeseriesChart, timeseries, "Сумма");
  renderCumulativeChart(timeseries);
  renderMetricBars(charts?.by_metric || []);
  renderYearlyBars(timeseries);
}

function normalizeTimeseries(points) {
  const grouped = new Map();
  for (const point of points) {
    const key = point.period;
    grouped.set(key, (grouped.get(key) || 0) + Number(point.value));
  }
  return Array.from(grouped.entries())
    .map(([period, value]) => ({ period, value }))
    .sort((left, right) => left.period.localeCompare(right.period));
}

function renderTimeseriesChart(container, series, label) {
  if (!series.length) {
    setEmptyChart(container);
    return;
  }

  const svg = buildLineChartSvg(series, {
    valueLabel: label,
    lineColor: "#1f5fd1",
    pointColor: "#1f5fd1",
    fillColor: "#edf4ff",
  });
  container.classList.remove("empty");
  container.innerHTML = svg;
}

function renderCumulativeChart(series) {
  if (!series.length) {
    setEmptyChart(elements.cumulativeChart);
    return;
  }
  let total = 0;
  const cumulative = series.map((item) => {
    total += item.value;
    return { period: item.period, value: total };
  });
  elements.cumulativeChart.classList.remove("empty");
  elements.cumulativeChart.innerHTML = buildLineChartSvg(cumulative, {
    valueLabel: "Нарастающий итог",
    lineColor: "#184daa",
    pointColor: "#184daa",
    fillColor: "#f1f6ff",
  });
}

function buildLineChartSvg(series, options) {
  const width = 760;
  const height = 250;
  const padding = { top: 24, right: 18, bottom: 44, left: 56 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const values = series.map((item) => item.value);
  const minValue = Math.min(...values, 0);
  const maxValue = Math.max(...values, 0);
  const range = maxValue - minValue || 1;
  const stepX = series.length > 1 ? plotWidth / (series.length - 1) : 0;
  const coords = series.map((item, index) => ({
    ...item,
    x: padding.left + index * stepX,
    y: padding.top + ((maxValue - item.value) / range) * plotHeight,
  }));
  const linePath = coords.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
  const fillPath = `${linePath} L ${coords[coords.length - 1].x} ${height - padding.bottom} L ${coords[0].x} ${height - padding.bottom} Z`;
  const tickCount = 4;
  const labelStep = Math.max(1, Math.ceil(series.length / 6));

  return `
    <svg class="chart-svg" viewBox="0 0 ${width} ${height}">
      ${Array.from({ length: tickCount + 1 }, (_, index) => {
        const ratio = index / tickCount;
        const y = padding.top + ratio * plotHeight;
        const value = maxValue - ratio * range;
        return `
          <line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" class="chart-grid-line"></line>
          <text x="${padding.left - 10}" y="${y + 4}" text-anchor="end" class="chart-label">${escapeHtml(shortNumber(value))}</text>
        `;
      }).join("")}
      <line x1="${padding.left}" y1="${height - padding.bottom}" x2="${width - padding.right}" y2="${height - padding.bottom}" class="chart-axis"></line>
      <path d="${fillPath}" fill="${options.fillColor}"></path>
      <path d="${linePath}" fill="none" stroke="${options.lineColor}" stroke-width="3"></path>
      ${coords.map((point, index) => `
        <circle cx="${point.x}" cy="${point.y}" r="4" fill="${options.pointColor}"></circle>
        ${index % labelStep === 0 || index === coords.length - 1 ? `<text x="${point.x}" y="${height - 16}" text-anchor="middle" class="chart-label">${escapeHtml(point.period)}</text>` : ""}
      `).join("")}
    </svg>
  `;
}

function renderMetricBars(rows) {
  if (!rows.length) {
    setEmptyChart(elements.metricsChart);
    return;
  }

  const values = rows.map((row) => ({
    label: prettyMetricName(row.metric),
    value: Number(row.value),
  }));
  renderHorizontalBars(elements.metricsChart, values);
}

function renderYearlyBars(series) {
  if (!series.length) {
    setEmptyChart(elements.yearlyChart);
    return;
  }
  const grouped = new Map();
  for (const item of series) {
    const year = item.period.slice(0, 4);
    grouped.set(year, (grouped.get(year) || 0) + item.value);
  }
  const values = Array.from(grouped.entries()).map(([label, value]) => ({ label, value }));
  renderHorizontalBars(elements.yearlyChart, values);
}

function renderHorizontalBars(container, values) {
  const width = 760;
  const barHeight = 28;
  const gap = 18;
  const labelWidth = 180;
  const maxBarWidth = 420;
  const height = 28 + values.length * (barHeight + gap);
  const maxValue = Math.max(...values.map((item) => Math.abs(item.value)), 1);

  container.classList.remove("empty");
  container.innerHTML = `
    <svg class="chart-svg" viewBox="0 0 ${width} ${height}">
      ${values.map((item, index) => {
        const y = 18 + index * (barHeight + gap);
        const barWidth = Math.max(8, (Math.abs(item.value) / maxValue) * maxBarWidth);
        return `
          <text x="0" y="${y + 18}" class="chart-label">${escapeHtml(item.label)}</text>
          <rect x="${labelWidth}" y="${y}" width="${barWidth}" height="${barHeight}" rx="10" fill="${index % 2 === 0 ? "#1f5fd1" : "#7aa4e8"}"></rect>
          <text x="${labelWidth + barWidth + 12}" y="${y + 18}" class="chart-value">${escapeHtml(formatNumber(item.value))}</text>
        `;
      }).join("")}
    </svg>
  `;
}

function setEmptyChart(container) {
  container.classList.add("empty");
  container.textContent = "Нет данных";
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
        `<tr>${columns.map((column) => `<td>${escapeHtml(formatCell(row[column]))}</td>`).join("")}</tr>`
    )
    .join("");
}

function renderEmptyState() {
  renderDatasetSummary([]);
  renderSummaryCards({});
  setEmptyChart(elements.timeseriesChart);
  setEmptyChart(elements.cumulativeChart);
  setEmptyChart(elements.metricsChart);
  setEmptyChart(elements.yearlyChart);
  renderTable(elements.previewTable, []);
  renderTable(elements.resultsTable, []);
  setBadge(elements.previewStatus, "нет данных", "muted");
  setBadge(elements.queryStatus, "нет данных", "muted");
  elements.batchMeta.textContent = "Если папка project_file найдена, система подключит её автоматически.";
}

function resetQueryPresentation() {
  renderSummaryCards({});
  setEmptyChart(elements.timeseriesChart);
  setEmptyChart(elements.cumulativeChart);
  setEmptyChart(elements.metricsChart);
  setEmptyChart(elements.yearlyChart);
  renderTable(elements.resultsTable, []);
  setBadge(elements.queryStatus, "нет данных", "muted");
}

function checkedValues(name) {
  return Array.from(document.querySelectorAll(`input[name="${name}"]:checked`)).map((input) => input.value);
}

function radioValue(name) {
  return document.querySelector(`input[name="${name}"]:checked`)?.value || null;
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

function ensureBatch(batchId) {
  if (!batchId) {
    throw new Error("Сначала загрузи данные.");
  }
}

function clearBatchState() {
  state.batchId = "";
  localStorage.removeItem("budgetAnalytics.batchId");
}

function isSupportedArchive(filename) {
  const lower = String(filename || "").toLowerCase();
  return ARCHIVE_EXTENSIONS.some((extension) => lower.endsWith(extension));
}

function textValue(element) {
  const value = element.value.trim();
  return value ? value : null;
}

function apiUrl(path) {
  return `${API_BASE_URL}${path}`;
}

async function fetchJson(url, options = {}) {
  const response = await requestJson(url, options);
  if (!response.ok) {
    throw new Error(response.error);
  }
  return response.data;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  return {
    ok: response.ok,
    status: response.status,
    data,
    error: response.ok ? null : (data?.detail || `${response.status} ${response.statusText}`),
  };
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
  }, 3600);
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

function shortNumber(value) {
  const number = Number(value);
  if (Math.abs(number) >= 1_000_000_000) {
    return `${(number / 1_000_000_000).toFixed(1)} млрд`;
  }
  if (Math.abs(number) >= 1_000_000) {
    return `${(number / 1_000_000).toFixed(1)} млн`;
  }
  if (Math.abs(number) >= 1_000) {
    return `${(number / 1_000).toFixed(1)} тыс`;
  }
  return formatNumber(number);
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

function formatDateTime(value) {
  if (!value) {
    return "—";
  }
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

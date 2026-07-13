const state = {
  title: "",
  author: "",
  contentVersion: "",
  layout: null,
  currentPageIndex: 0,
  currentLineIndex: 0,
  totalPages: 0,
  totalLines: 0,
  pageStates: [],
  slots: [],
  lineSlots: [],
  lineElements: [],
  mode: "guided",
  autoAdvance: true,
  isListening: false,
  isChecking: false,
  recognition: null,
  speechSupported: false,
  speechSubmissionPending: false,
  recognizedText: "",
  loading: false,
  error: "",
  requestId: 0,
  requestController: null,
  pendingAdvanceTimer: 0,
  pendingSelfCheck: false,
  stats: {
    attempts: 0,
    exactPasses: 0,
    assistedPasses: 0,
    hints: 0
  }
};

const STORAGE_PREFIX = "poem_recite_progress_v2:";
const LAST_RECITE_STORAGE_KEY = "poem_recite_last_v2";
const validSlotStates = new Set(["blank", "written", "ink_error"]);
const modeDescriptions = {
  learn: "完整显示正文，适合先熟读一遍并理解句意。",
  guided: "保留首字和少量线索，逐步撤去视觉提示。",
  test: "隐藏全部正文，用无提示回忆检验掌握程度。"
};

function getReciteQuery() {
  const params = new URLSearchParams(window.location.search);
  return {
    title: params.get("title")?.trim() || "",
    author: params.get("author")?.trim() || ""
  };
}

function getProgressStorageKey() {
  return `${STORAGE_PREFIX}${encodeURIComponent(`${state.title}::${state.author}`)}`;
}

function safeReadJson(key, fallback = null) {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (error) {
    console.warn(`Unable to read ${key}.`, error);
    return fallback;
  }
}

function safeWriteJson(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch (error) {
    console.warn(`Unable to write ${key}.`, error);
  }
}

function fillWorkMeta() {
  const resolvedTitle = state.title || "未选择作品";
  const resolvedAuthor = state.author || "作者未提供";
  document.getElementById("scrollTitle").textContent = resolvedTitle;
  document.getElementById("scrollAuthor").textContent = resolvedAuthor;
  document.title = `${resolvedTitle} · 背诵训练`;
}

function setStatus(message, isError = false) {
  const status = document.getElementById("scrollStatus");
  status.textContent = message;
  status.classList.toggle("is-error", isError);
  status.hidden = !message;
}

function setRecognizedText(text) {
  state.recognizedText = text;
  document.getElementById("recognizedTextOutput").textContent = `识别文本：${text || "暂未开始"}`;
}

function getCurrentPage() {
  return state.layout?.pages?.[state.currentPageIndex] || null;
}

function getCurrentPageState() {
  return state.pageStates[state.currentPageIndex] || null;
}

function getTotalLineCount() {
  return (state.layout?.pages || []).reduce((total, page) => total + (page.lines?.length || 0), 0);
}

function getPassedLineCount() {
  return state.pageStates.reduce(
    (total, pageState) => total + pageState.linePassed.filter(Boolean).length,
    0
  );
}

function isWeakLine(pageState, lineIndex) {
  const attempts = pageState.attempts[lineIndex] || 0;
  return Boolean(
    (attempts > 0 && !pageState.linePassed[lineIndex])
    || attempts > 1
    || (pageState.hintsUsed[lineIndex] || 0) > 0
    || pageState.assisted[lineIndex]
  );
}

function getWeakLines() {
  const weakLines = [];
  state.pageStates.forEach((pageState, pageIndex) => {
    pageState.linePassed.forEach((_passed, lineIndex) => {
      if (isWeakLine(pageState, lineIndex)) {
        weakLines.push({ pageIndex, lineIndex });
      }
    });
  });
  return weakLines;
}

function allPagesCompleted() {
  return state.pageStates.length > 0 && state.pageStates.every((pageState) => pageState.linePassed.every(Boolean));
}

function persistProgress() {
  if (!state.layout || !state.title) return;
  const totalLines = getTotalLineCount();
  const passedLines = getPassedLineCount();
  const percent = totalLines ? Math.round((passedLines / totalLines) * 100) : 0;
  const record = {
    schemaVersion: 2,
    title: state.title,
    author: state.author,
    contentVersion: state.contentVersion,
    currentPageIndex: state.currentPageIndex,
    mode: state.mode,
    autoAdvance: state.autoAdvance,
    pageStates: state.pageStates,
    stats: state.stats,
    updatedAt: new Date().toISOString(),
    percent
  };
  safeWriteJson(getProgressStorageKey(), record);
  safeWriteJson(LAST_RECITE_STORAGE_KEY, {
    title: state.title,
    author: state.author,
    percent,
    updatedAt: record.updatedAt
  });
}

function createInitialPageState(page) {
  const lineCount = page.columns.length;
  return {
    currentLineIndex: 0,
    completed: false,
    linePassed: Array.from({ length: lineCount }, () => false),
    assisted: Array.from({ length: lineCount }, () => false),
    attempts: Array.from({ length: lineCount }, () => 0),
    hintsUsed: Array.from({ length: lineCount }, () => 0),
    revealedHints: page.columns.map(() => []),
    slotStates: page.columns.map((column) => column.map(() => "blank"))
  };
}

function sanitizeSavedPageState(saved, page) {
  const fresh = createInitialPageState(page);
  if (!saved || !Array.isArray(saved.linePassed)) return fresh;
  const lineCount = page.columns.length;
  fresh.currentLineIndex = Math.max(0, Math.min(Number(saved.currentLineIndex) || 0, Math.max(lineCount - 1, 0)));
  fresh.linePassed = fresh.linePassed.map((_value, index) => Boolean(saved.linePassed?.[index]));
  fresh.assisted = fresh.assisted.map((_value, index) => Boolean(saved.assisted?.[index]));
  fresh.attempts = fresh.attempts.map((_value, index) => Math.max(0, Number(saved.attempts?.[index]) || 0));
  fresh.hintsUsed = fresh.hintsUsed.map((_value, index) => Math.max(0, Number(saved.hintsUsed?.[index]) || 0));
  fresh.revealedHints = fresh.revealedHints.map((_value, lineIndex) => {
    const maxIndex = page.columns[lineIndex].length - 1;
    return Array.isArray(saved.revealedHints?.[lineIndex])
      ? [...new Set(saved.revealedHints[lineIndex].map(Number).filter((index) => Number.isInteger(index) && index >= 0 && index <= maxIndex))]
      : [];
  });
  fresh.slotStates = fresh.slotStates.map((columnStates, lineIndex) => columnStates.map((_value, charIndex) => {
    if (!fresh.linePassed[lineIndex]) return "blank";
    const candidate = saved.slotStates?.[lineIndex]?.[charIndex];
    return validSlotStates.has(candidate) ? candidate : "blank";
  }));
  fresh.completed = fresh.linePassed.every(Boolean);
  return fresh;
}

function restoreProgress() {
  const saved = safeReadJson(getProgressStorageKey());
  if (!saved || saved.schemaVersion !== 2 || saved.contentVersion !== state.contentVersion) {
    return false;
  }
  if (!Array.isArray(saved.pageStates) || saved.pageStates.length !== state.layout.pages.length) {
    return false;
  }

  state.pageStates = state.layout.pages.map((page, index) => sanitizeSavedPageState(saved.pageStates[index], page));
  state.currentPageIndex = Math.max(0, Math.min(Number(saved.currentPageIndex) || 0, Math.max(state.totalPages - 1, 0)));
  state.mode = modeDescriptions[saved.mode] ? saved.mode : "guided";
  state.autoAdvance = saved.autoAdvance !== false;
  state.stats = {
    attempts: Math.max(0, Number(saved.stats?.attempts) || 0),
    exactPasses: Math.max(0, Number(saved.stats?.exactPasses) || 0),
    assistedPasses: Math.max(0, Number(saved.stats?.assistedPasses) || 0),
    hints: Math.max(0, Number(saved.stats?.hints) || 0)
  };
  return true;
}

function updateProgress() {
  const pageState = getCurrentPageState();
  const totalLines = getTotalLineCount();
  const passedLines = getPassedLineCount();
  const percent = totalLines ? Math.round((passedLines / totalLines) * 100) : 0;
  const weakLines = getWeakLines();
  const progress = document.getElementById("scrollProgress");

  if (!state.totalPages) {
    progress.textContent = "第 0 页 / 共 0 页";
  } else if (pageState?.completed) {
    progress.textContent = `第 ${state.currentPageIndex + 1} 页 / 共 ${state.totalPages} 页 · 已完成`;
  } else {
    progress.textContent = `第 ${state.currentPageIndex + 1} 页 · 第 ${state.currentLineIndex + 1}/${Math.max(state.totalLines, 1)} 句`;
  }

  document.getElementById("progressSummary").textContent = `本轮进度 ${percent}%`;
  document.getElementById("progressBar").style.width = `${percent}%`;
  document.getElementById("attemptCount").textContent = String(state.stats.attempts);
  document.getElementById("accuracyValue").textContent = state.stats.attempts
    ? `${Math.round((state.stats.exactPasses / state.stats.attempts) * 100)}%`
    : "—";
  document.getElementById("weakCount").textContent = String(weakLines.length);
  document.getElementById("practiceWeakButton").disabled = weakLines.length === 0 || state.loading || state.isChecking || state.isListening;

  const summary = document.getElementById("sessionSummary");
  summary.hidden = !allPagesCompleted();
  if (!summary.hidden) {
    const accuracy = state.stats.attempts ? Math.round((state.stats.exactPasses / state.stats.attempts) * 100) : 100;
    document.getElementById("sessionSummaryText").textContent = `完成 ${totalLines} 句，严格通过率 ${accuracy}%，还有 ${weakLines.length} 句适合再巩固一次。建议明天进行一次无提示复习。`;
  }
}

function setSlotState(slot, mode) {
  slot.state = mode;
  slot.element.dataset.state = mode;
}

function updateControlStates() {
  const startButton = document.getElementById("startReciteButton");
  const startLabel = startButton.querySelector("span:last-child");
  const pageState = getCurrentPageState();
  const busy = state.loading || state.isChecking || state.isListening;
  const manualHasText = Boolean(document.getElementById("manualReciteInput").value.trim());
  const hasActiveLine = Boolean(state.layout && pageState && !pageState.completed && state.totalLines);

  startLabel.textContent = state.isListening ? "正在聆听…" : state.isChecking ? "正在检查…" : "开始朗读";
  startButton.disabled = !hasActiveLine || busy;
  startButton.title = state.speechSupported ? "使用浏览器语音识别检查当前句" : "当前浏览器不支持语音识别，请使用下方默写或自评";

  document.getElementById("prevPageButton").disabled = busy || state.currentPageIndex <= 0;
  document.getElementById("nextPageButton").disabled = busy || state.currentPageIndex >= Math.max(state.totalPages - 1, 0);
  document.getElementById("nextLineButton").disabled = busy || !pageState?.linePassed[state.currentLineIndex];
  document.getElementById("retryLineButton").disabled = busy || !state.layout || !pageState;
  document.getElementById("showAnswerButton").disabled = busy || !hasActiveLine;
  document.getElementById("revealLineButton").disabled = busy || !hasActiveLine;
  document.getElementById("checkReciteButton").disabled = busy || !hasActiveLine || !manualHasText;
  document.getElementById("resetProgressButton").disabled = busy || !state.layout;
  document.querySelectorAll("#modeSwitcher button").forEach((button) => {
    button.disabled = busy || !state.layout;
  });
  updateProgress();
}

function syncModeControls() {
  document.getElementById("bambooScroll").dataset.mode = state.mode;
  document.getElementById("modeDescription").textContent = modeDescriptions[state.mode];
  document.querySelectorAll("#modeSwitcher button").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.mode === state.mode));
  });
  document.getElementById("autoNextToggle").checked = state.autoAdvance;
}

function syncActiveLine(shouldScroll = true) {
  const pageState = getCurrentPageState();
  state.lineElements.forEach((element, index) => {
    element.classList.toggle("is-active", Boolean(pageState && !pageState.completed && index === state.currentLineIndex));
  });
  const active = state.lineElements[state.currentLineIndex];
  if (shouldScroll && active && !pageState?.completed) {
    window.requestAnimationFrame(() => {
      active.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
    });
  }
}

function shouldShowHint(lineIndex, charIndex, pageState) {
  if (pageState.slotStates[lineIndex]?.[charIndex] !== "blank") return false;
  if (pageState.revealedHints[lineIndex]?.includes(charIndex)) return true;
  if (state.mode !== "guided") return false;
  return charIndex === 0 || (charIndex > 1 && (charIndex + lineIndex) % 4 === 0);
}

function createSlot(char, lineIndex, charIndex, pageState = null) {
  const element = document.createElement("div");
  element.className = "bamboo-char-slot";
  element.dataset.lineIndex = String(lineIndex);
  element.dataset.charIndex = String(charIndex);
  element.dataset.state = "blank";

  const glyph = document.createElement("span");
  glyph.className = "bamboo-char-glyph";
  glyph.textContent = char || "";
  glyph.setAttribute("aria-hidden", "true");
  element.appendChild(glyph);

  if (pageState && char && shouldShowHint(lineIndex, charIndex, pageState)) {
    element.classList.add("is-hint");
  }

  return { char, lineIndex, charIndex, state: "blank", element };
}

function clearTransientInputs() {
  document.getElementById("manualReciteInput").value = "";
  setRecognizedText("");
  state.pendingSelfCheck = false;
  document.getElementById("selfCheckPanel").hidden = true;
  clearDifferencePanel();
}

function renderBlankScroll(columnCount = 6, rowCount = 8) {
  const host = document.getElementById("bambooScroll");
  host.innerHTML = "";
  state.lineSlots = [];
  state.lineElements = [];
  state.slots = [];
  state.totalLines = 0;
  state.currentLineIndex = 0;

  for (let columnIndex = 0; columnIndex < columnCount; columnIndex += 1) {
    const slat = document.createElement("div");
    slat.className = "bamboo-scroll-slat";
    for (let rowIndex = 0; rowIndex < rowCount; rowIndex += 1) {
      const slot = createSlot("", columnIndex, rowIndex);
      slot.element.classList.add("is-placeholder");
      slat.appendChild(slot.element);
    }
    host.appendChild(slat);
  }
  syncModeControls();
  updateControlStates();
}

function renderCurrentPage(options = {}) {
  const host = document.getElementById("bambooScroll");
  const page = getCurrentPage();
  const pageState = getCurrentPageState();
  host.innerHTML = "";
  state.slots = [];
  state.lineSlots = [];
  state.lineElements = [];

  if (!page || !pageState) {
    renderBlankScroll();
    return;
  }

  state.totalLines = page.lines.length;
  state.currentLineIndex = Math.min(pageState.currentLineIndex, Math.max(page.lines.length - 1, 0));
  pageState.currentLineIndex = state.currentLineIndex;
  const slotCount = Math.max(
    state.layout?.line_char_capacity || 12,
    ...page.columns.map((column) => Array.isArray(column) ? column.length : 0)
  );

  page.columns.forEach((column, lineIndex) => {
    const slat = document.createElement("div");
    slat.className = "bamboo-scroll-slat";
    slat.dataset.lineIndex = String(lineIndex);
    slat.setAttribute("aria-label", `第 ${lineIndex + 1} 句练习区`);

    const indicator = document.createElement("div");
    indicator.className = "bamboo-line-indicator";
    indicator.textContent = "当前句";
    slat.appendChild(indicator);
    const lineSlots = [];

    for (let charIndex = 0; charIndex < slotCount; charIndex += 1) {
      const char = column[charIndex] || "";
      const slot = createSlot(char, lineIndex, charIndex, pageState);
      if (!char) {
        slot.element.classList.add("is-placeholder");
      } else {
        setSlotState(slot, pageState.slotStates[lineIndex]?.[charIndex] || "blank");
        state.slots.push(slot);
        lineSlots.push(slot);
      }
      slat.appendChild(slot.element);
    }

    state.lineSlots.push(lineSlots);
    state.lineElements.push(slat);
    host.appendChild(slat);
  });

  syncModeControls();
  syncActiveLine(options.scroll !== false);
  updateControlStates();
}

async function fetchReciteLayout() {
  const query = new URLSearchParams({ title: state.title, author: state.author });
  const response = await fetch(`/api/recite/layout?${query.toString()}`, { credentials: "same-origin" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.success === false) {
    throw new Error(payload.error || (response.status === 403 ? "请先完成人机验证。" : "背诵内容加载失败。"));
  }
  return payload;
}

async function fetchReciteCheck(spokenText, source, signal) {
  const response = await fetch("/api/recite/check", {
    method: "POST",
    credentials: "same-origin",
    signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: state.title,
      author: state.author,
      page_index: state.currentPageIndex,
      current_line_index: state.currentLineIndex,
      spoken_text: spokenText,
      source
    })
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.success === false) {
    throw new Error(payload.error || (response.status === 403 ? "请先完成人机验证。" : "背诵检查失败。"));
  }
  return payload;
}

function clearDifferencePanel() {
  const panel = document.getElementById("differencePanel");
  panel.hidden = true;
  document.getElementById("differenceSummary").textContent = "";
  document.getElementById("differenceAccuracy").textContent = "";
  document.getElementById("differenceDetails").replaceChildren();
  document.getElementById("selfConfirmButton").hidden = true;
}

function addDifferenceChip(text, className = "") {
  const chip = document.createElement("span");
  chip.className = `difference-chip${className ? ` ${className}` : ""}`;
  chip.textContent = text;
  document.getElementById("differenceDetails").appendChild(chip);
}

function renderDifferencePanel(result) {
  const panel = document.getElementById("differencePanel");
  const accuracy = Number(result.accuracy);
  panel.hidden = false;
  document.getElementById("differenceAccuracy").textContent = Number.isFinite(accuracy) ? `文字匹配 ${Math.round(accuracy * 100)}%` : "";
  document.getElementById("differenceSummary").textContent = result.message || (result.passed ? "本句通过。" : "请根据下面的差异再试一次。");
  document.getElementById("differenceDetails").replaceChildren();

  (result.substitutions || []).forEach((item) => {
    addDifferenceChip(`错：${item.spoken || "∅"} → ${item.expected || "∅"}`);
  });
  if (result.missing_chars?.length) {
    addDifferenceChip(`漏：${result.missing_chars.join("、")}`);
  }
  if (result.extra_chars?.length) {
    addDifferenceChip(`多：${result.extra_chars.join("、")}`, "is-extra");
  }
  if (!result.passed && !result.substitutions?.length && !result.missing_chars?.length && !result.extra_chars?.length) {
    addDifferenceChip("识别结果与当前句仍有差异");
  }
  document.getElementById("selfConfirmButton").hidden = result.status !== "speech_uncertain";
}

function applyCharResults(lineIndex, charResults) {
  const pageState = getCurrentPageState();
  const lineSlots = state.lineSlots[lineIndex] || [];
  if (!pageState) return;
  lineSlots.forEach((slot, index) => {
    const mode = charResults[index]?.status === "correct" ? "written" : "ink_error";
    pageState.slotStates[lineIndex][index] = mode;
    setSlotState(slot, mode);
  });
}

function cancelPendingAdvance() {
  if (state.pendingAdvanceTimer) {
    window.clearTimeout(state.pendingAdvanceTimer);
    state.pendingAdvanceTimer = 0;
  }
}

function scheduleAutoAdvance(pageIndex, lineIndex) {
  cancelPendingAdvance();
  if (!state.autoAdvance) return;
  state.pendingAdvanceTimer = window.setTimeout(() => {
    state.pendingAdvanceTimer = 0;
    if (state.currentPageIndex !== pageIndex || state.currentLineIndex !== lineIndex || state.isChecking || state.isListening) return;
    if (lineIndex < state.totalLines - 1) {
      moveToNextLine();
    } else if (pageIndex < state.totalPages - 1) {
      switchPage(pageIndex + 1);
    } else {
      document.getElementById("sessionSummary").scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, 1050);
}

function markCurrentLinePassed({ assisted = false, message = "本句通过。" } = {}) {
  const pageState = getCurrentPageState();
  if (!pageState) return;
  const pageIndex = state.currentPageIndex;
  const lineIndex = state.currentLineIndex;
  pageState.linePassed[lineIndex] = true;
  pageState.assisted[lineIndex] = assisted;
  pageState.slotStates[lineIndex] = pageState.slotStates[lineIndex].map(() => "written");
  (state.lineSlots[lineIndex] || []).forEach((slot) => setSlotState(slot, "written"));
  pageState.completed = pageState.linePassed.every(Boolean);
  pageState.currentLineIndex = lineIndex;
  state.pendingSelfCheck = false;
  document.getElementById("selfCheckPanel").hidden = true;
  setStatus(message);
  persistProgress();
  syncActiveLine(false);
  updateControlStates();
  scheduleAutoAdvance(pageIndex, lineIndex);
}

function revealHint() {
  const pageState = getCurrentPageState();
  const page = getCurrentPage();
  if (!pageState || !page) return;
  const lineIndex = state.currentLineIndex;
  const column = page.columns[lineIndex] || [];
  const revealed = pageState.revealedHints[lineIndex];
  const nextIndex = column.findIndex((_char, index) => {
    return pageState.slotStates[lineIndex][index] === "blank"
      && !revealed.includes(index)
      && !(state.mode === "guided" && (index === 0 || (index > 1 && (index + lineIndex) % 4 === 0)));
  });
  if (nextIndex < 0) {
    setStatus("当前句已经没有更多可追加的单字提示。", true);
    return;
  }
  revealed.push(nextIndex);
  pageState.hintsUsed[lineIndex] += 1;
  state.stats.hints += 1;
  renderCurrentPage({ scroll: false });
  persistProgress();
  setStatus(`已提示第 ${nextIndex + 1} 个字。提示通过会记为“辅助完成”，建议稍后再无提示复习。`);
}

function revealCurrentLine() {
  const pageState = getCurrentPageState();
  if (!pageState) return;
  const lineIndex = state.currentLineIndex;
  pageState.slotStates[lineIndex] = pageState.slotStates[lineIndex].map(() => "written");
  pageState.hintsUsed[lineIndex] += 1;
  state.stats.hints += 1;
  state.pendingSelfCheck = true;
  renderCurrentPage({ scroll: false });
  document.getElementById("selfCheckPanel").hidden = false;
  document.getElementById("selfCheckPanel").scrollIntoView({ behavior: "smooth", block: "nearest" });
  persistProgress();
  setStatus("已显示当前句。请如实自评，本次不会计为无提示掌握。");
}

function resetLineStates(lineIndex, options = {}) {
  const pageState = getCurrentPageState();
  if (!pageState) return;
  pageState.slotStates[lineIndex] = pageState.slotStates[lineIndex].map(() => "blank");
  if (options.clearPass !== false) {
    pageState.linePassed[lineIndex] = false;
    pageState.assisted[lineIndex] = false;
  }
  pageState.completed = false;
}

function retryCurrentLine() {
  const pageState = getCurrentPageState();
  if (!pageState || !state.totalLines) return;
  cancelPendingAdvance();
  resetLineStates(state.currentLineIndex);
  pageState.currentLineIndex = state.currentLineIndex;
  clearTransientInputs();
  renderCurrentPage({ scroll: false });
  persistProgress();
  setStatus(`第 ${state.currentLineIndex + 1} 句已重置，请重新朗读或默写。`);
}

function moveToNextLine() {
  const pageState = getCurrentPageState();
  if (!pageState) return;
  cancelPendingAdvance();
  if (!pageState.linePassed[state.currentLineIndex]) {
    setStatus("当前句尚未完成。可以朗读、默写，或点击“核对本句”自评。", true);
    return;
  }
  if (state.currentLineIndex >= state.totalLines - 1) {
    pageState.completed = true;
    persistProgress();
    updateControlStates();
    setStatus(state.currentPageIndex < state.totalPages - 1 ? "本页已完成，可进入下一页。" : "全部内容已完成。");
    return;
  }
  state.currentLineIndex += 1;
  pageState.currentLineIndex = state.currentLineIndex;
  clearTransientInputs();
  renderCurrentPage();
  persistProgress();
  setStatus(`进入第 ${state.currentLineIndex + 1} 句。先在心里回忆，再开始朗读或默写。`);
}

function switchPage(pageIndex) {
  if (state.isChecking || state.isListening || pageIndex < 0 || pageIndex >= state.totalPages || pageIndex === state.currentPageIndex) return;
  cancelPendingAdvance();
  state.currentPageIndex = pageIndex;
  clearTransientInputs();
  renderCurrentPage();
  persistProgress();
  setStatus(`已切换到第 ${pageIndex + 1} 页。`);
}

function moveToPrevPage() {
  switchPage(state.currentPageIndex - 1);
}

function moveToNextPage() {
  switchPage(state.currentPageIndex + 1);
}

async function submitRecitationText(spokenText, source = "manual") {
  const pageState = getCurrentPageState();
  if (!state.layout || !pageState || !state.totalLines || state.isChecking) return;
  if (pageState.completed) {
    setStatus("当前页已完成，可切换页面或复习薄弱句。" );
    return;
  }

  cancelPendingAdvance();
  state.requestController?.abort();
  state.requestController = new AbortController();
  const requestId = ++state.requestId;
  const context = { pageIndex: state.currentPageIndex, lineIndex: state.currentLineIndex, requestId };
  state.isChecking = true;
  pageState.attempts[context.lineIndex] += 1;
  state.stats.attempts += 1;
  updateControlStates();
  setStatus(source === "speech" ? "正在分析本句的语音识别结果…" : "正在逐字检查本句…");

  try {
    const result = await fetchReciteCheck(spokenText, source, state.requestController.signal);
    if (
      requestId !== state.requestId
      || context.pageIndex !== state.currentPageIndex
      || context.lineIndex !== state.currentLineIndex
    ) return;

    renderDifferencePanel(result);
    if (result.status === "order_error") {
      setStatus(result.message || "顺序可能有误，请先确认当前句。", true);
      persistProgress();
      return;
    }

    applyCharResults(context.lineIndex, result.char_results || []);
    if (result.status === "pass" && result.passed) {
      state.stats.exactPasses += 1;
      if (source === "manual") document.getElementById("manualReciteInput").value = "";
      markCurrentLinePassed({ message: result.message || "本句准确通过。" });
    } else if (result.status === "speech_uncertain") {
      setStatus("发音很接近，但识别文字存在同音差异。请确认是识别偏差，或重新朗读。", true);
      persistProgress();
    } else {
      pageState.linePassed[context.lineIndex] = false;
      setStatus(result.message || "还有漏字、错字或多字，请查看反馈后再试。", true);
      persistProgress();
    }
  } catch (error) {
    if (error?.name !== "AbortError") {
      setStatus(error.message || "背诵检查失败，请稍后重试。", true);
    }
  } finally {
    if (requestId === state.requestId) {
      state.isChecking = false;
      state.requestController = null;
      updateControlStates();
    }
  }
}

async function handleManualCheck() {
  const input = document.getElementById("manualReciteInput");
  const text = input.value.trim();
  if (!text) {
    setStatus("请先输入当前句。", true);
    input.focus();
    return;
  }
  setRecognizedText(text);
  await submitRecitationText(text, "manual");
}

function normalizeCandidate(text) {
  return String(text || "").replace(/[\s，。！？；：、,.!?;:'"“”‘’]/g, "");
}

function levenshteinDistance(left, right) {
  const a = [...normalizeCandidate(left)];
  const b = [...normalizeCandidate(right)];
  const row = Array.from({ length: b.length + 1 }, (_value, index) => index);
  for (let i = 1; i <= a.length; i += 1) {
    let previous = row[0];
    row[0] = i;
    for (let j = 1; j <= b.length; j += 1) {
      const saved = row[j];
      row[j] = Math.min(row[j] + 1, row[j - 1] + 1, previous + (a[i - 1] === b[j - 1] ? 0 : 1));
      previous = saved;
    }
  }
  return row[b.length];
}

function chooseBestTranscript(candidates) {
  const expected = getCurrentPage()?.lines?.[state.currentLineIndex] || "";
  return candidates
    .map((text) => ({ text, distance: levenshteinDistance(expected, text) }))
    .sort((a, b) => a.distance - b.distance || b.text.length - a.text.length)[0]?.text || "";
}

function getSpeechRecognitionCtor() {
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

async function ensureSpeechPermission() {
  if (!navigator.mediaDevices?.getUserMedia) return;
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  stream.getTracks().forEach((track) => track.stop());
}

function buildRecognition() {
  const SpeechRecognitionCtor = getSpeechRecognitionCtor();
  if (!SpeechRecognitionCtor) return null;
  const recognition = new SpeechRecognitionCtor();
  recognition.lang = "zh-CN";
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.maxAlternatives = 5;

  recognition.onstart = () => {
    state.isListening = true;
    state.speechSubmissionPending = false;
    setStatus("正在聆听当前句，请自然朗读。");
    updateControlStates();
  };

  recognition.onresult = async (event) => {
    const finalCandidates = [];
    const interimParts = [];
    for (let index = event.resultIndex || 0; index < event.results.length; index += 1) {
      const result = event.results[index];
      const alternatives = Array.from(result || []).map((item) => item?.transcript?.trim()).filter(Boolean);
      if (result.isFinal) finalCandidates.push(...alternatives);
      else if (alternatives[0]) interimParts.push(alternatives[0]);
    }

    if (interimParts.length) setRecognizedText(interimParts.join(""));
    if (!finalCandidates.length || state.speechSubmissionPending) return;
    state.speechSubmissionPending = true;
    const transcript = chooseBestTranscript(finalCandidates);
    if (!transcript) {
      setStatus("没有识别到有效文本，请重试或使用默写输入。", true);
      return;
    }
    document.getElementById("manualReciteInput").value = transcript;
    setRecognizedText(transcript);
    await submitRecitationText(transcript, "speech");
  };

  recognition.onerror = (event) => {
    const messages = {
      "audio-capture": "未检测到麦克风，请检查设备权限。",
      "not-allowed": "麦克风权限被拒绝，可使用默写或“核对本句”完成训练。",
      "service-not-allowed": "当前环境不允许语音识别，可使用默写或自评模式。",
      "no-speech": "没有听到语音，请再试一次。",
      network: "语音识别服务暂时不可用，可先使用默写。",
      aborted: "语音识别已停止。"
    };
    setStatus(messages[event.error] || "语音识别失败，可改用默写或自评模式。", true);
  };

  recognition.onend = () => {
    state.isListening = false;
    updateControlStates();
  };
  return recognition;
}

async function startSpeechRecitation() {
  const pageState = getCurrentPageState();
  if (!state.layout || !pageState || !state.totalLines) return;
  if (!state.speechSupported) {
    setStatus("当前浏览器不支持语音识别。你仍可用下方默写，或点“核对本句”进行自评。", true);
    document.getElementById("manualReciteInput").focus();
    return;
  }
  try {
    await ensureSpeechPermission();
    if (!state.recognition) state.recognition = buildRecognition();
    if (!state.recognition) throw new Error("当前浏览器无法启动语音识别。");
    setRecognizedText("正在等待识别结果…");
    state.recognition.start();
  } catch (error) {
    const denied = ["NotAllowedError", "PermissionDeniedError"].includes(error?.name);
    setStatus(denied ? "麦克风权限被拒绝，可使用默写或自评模式。" : (error.message || "无法启动语音识别，请使用默写。"), true);
    state.isListening = false;
    updateControlStates();
  }
}

function handleSelfAssessment(level) {
  const pageState = getCurrentPageState();
  if (!pageState || !state.pendingSelfCheck) return;
  const lineIndex = state.currentLineIndex;
  state.stats.attempts += 1;
  pageState.attempts[lineIndex] += 1;
  if (level === "remembered") {
    state.stats.assistedPasses += 1;
    markCurrentLinePassed({ assisted: true, message: "已按自评完成。本句已加入薄弱句，稍后请再做一次无提示复习。" });
    return;
  }
  state.pendingSelfCheck = false;
  document.getElementById("selfCheckPanel").hidden = true;
  resetLineStates(lineIndex);
  renderCurrentPage({ scroll: false });
  persistProgress();
  setStatus(level === "fuzzy" ? "已记为“有点模糊”。先看一眼提示，再重新回忆。" : "已记为“还不会”。建议切到熟读或渐隐阶段再练一次。", true);
}

function confirmSpeechRecognitionBias() {
  const pageState = getCurrentPageState();
  if (!pageState || document.getElementById("selfConfirmButton").hidden) return;
  state.stats.assistedPasses += 1;
  document.getElementById("selfConfirmButton").hidden = true;
  markCurrentLinePassed({ assisted: true, message: "已按“语音识别偏差”辅助通过，本句会保留在薄弱句中供稍后复习。" });
}

function practiceWeakLine() {
  const weakLines = getWeakLines();
  if (!weakLines.length) {
    setStatus("当前还没有薄弱句，继续保持。" );
    return;
  }
  const target = weakLines.find((item) => item.pageIndex > state.currentPageIndex || (item.pageIndex === state.currentPageIndex && item.lineIndex > state.currentLineIndex)) || weakLines[0];
  cancelPendingAdvance();
  state.currentPageIndex = target.pageIndex;
  const pageState = getCurrentPageState();
  state.currentLineIndex = target.lineIndex;
  pageState.currentLineIndex = target.lineIndex;
  resetLineStates(target.lineIndex);
  clearTransientInputs();
  renderCurrentPage();
  persistProgress();
  setStatus(`已进入薄弱句：第 ${target.pageIndex + 1} 页第 ${target.lineIndex + 1} 句。请尝试无提示回忆。`);
}

function resetAllProgress() {
  if (!state.layout) return;
  const confirmed = window.confirm("确定清空这篇作品的背诵进度并重新开始吗？");
  if (!confirmed) return;
  cancelPendingAdvance();
  state.requestController?.abort();
  state.requestId += 1;
  state.pageStates = state.layout.pages.map((page) => createInitialPageState(page));
  state.currentPageIndex = 0;
  state.stats = { attempts: 0, exactPasses: 0, assistedPasses: 0, hints: 0 };
  state.mode = "guided";
  clearTransientInputs();
  renderCurrentPage();
  persistProgress();
  setStatus("进度已清空。先用渐隐阶段回忆第一句。" );
}

function bindActions() {
  document.getElementById("startReciteButton").addEventListener("click", startSpeechRecitation);
  document.getElementById("checkReciteButton").addEventListener("click", handleManualCheck);
  document.getElementById("showAnswerButton").addEventListener("click", revealHint);
  document.getElementById("revealLineButton").addEventListener("click", revealCurrentLine);
  document.getElementById("nextLineButton").addEventListener("click", moveToNextLine);
  document.getElementById("retryLineButton").addEventListener("click", retryCurrentLine);
  document.getElementById("prevPageButton").addEventListener("click", moveToPrevPage);
  document.getElementById("nextPageButton").addEventListener("click", moveToNextPage);
  document.getElementById("practiceWeakButton").addEventListener("click", practiceWeakLine);
  document.getElementById("reviewWeakButton").addEventListener("click", practiceWeakLine);
  document.getElementById("selfConfirmButton").addEventListener("click", confirmSpeechRecognitionBias);
  document.getElementById("rememberedButton").addEventListener("click", () => handleSelfAssessment("remembered"));
  document.getElementById("fuzzyButton").addEventListener("click", () => handleSelfAssessment("fuzzy"));
  document.getElementById("forgotButton").addEventListener("click", () => handleSelfAssessment("forgot"));
  document.getElementById("resetProgressButton").addEventListener("click", resetAllProgress);
  document.getElementById("backToReaderButton").addEventListener("click", backToReader);
  document.getElementById("finishSessionButton").addEventListener("click", backToReader);

  document.getElementById("manualReciteInput").addEventListener("input", updateControlStates);
  document.getElementById("manualReciteInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      handleManualCheck();
    }
  });
  document.getElementById("autoNextToggle").addEventListener("change", (event) => {
    state.autoAdvance = event.target.checked;
    if (!state.autoAdvance) cancelPendingAdvance();
    persistProgress();
  });
  document.querySelectorAll("#modeSwitcher button").forEach((button) => {
    button.addEventListener("click", () => {
      if (!modeDescriptions[button.dataset.mode]) return;
      state.mode = button.dataset.mode;
      renderCurrentPage({ scroll: false });
      persistProgress();
      setStatus(modeDescriptions[state.mode]);
    });
  });
}

function backToReader() {
  cancelPendingAdvance();
  state.requestController?.abort();
  const query = new URLSearchParams();
  if (state.title) query.set("title", state.title);
  if (state.author) query.set("author", state.author);
  window.location.href = query.toString() ? `./reader.html?${query.toString()}` : "./reader.html";
}

async function startReciteScrollPage() {
  const { title, author } = getReciteQuery();
  state.title = title;
  state.author = author;
  state.speechSupported = Boolean(getSpeechRecognitionCtor());
  fillWorkMeta();
  bindActions();
  clearTransientInputs();
  updateControlStates();

  if (!state.title) {
    state.error = "请先从阅读页选择作品后再进入背诵训练。";
    setStatus(state.error, true);
    renderBlankScroll();
    return;
  }

  state.loading = true;
  setStatus("正在准备分句与训练进度…");
  renderBlankScroll();
  try {
    const layout = await fetchReciteLayout();
    state.layout = layout;
    state.title = layout.title || state.title;
    state.author = layout.author || state.author;
    state.contentVersion = layout.content_version || `${layout.total_pages || 0}:${layout.pages?.flatMap((page) => page.lines || []).join("|") || ""}`;
    state.totalPages = Array.isArray(layout.pages) ? layout.pages.length : 0;
    state.pageStates = (layout.pages || []).map((page) => createInitialPageState(page));
    const resumed = restoreProgress();
    fillWorkMeta();
    renderCurrentPage({ scroll: false });
    persistProgress();
    window.requestAnimationFrame(() => window.scrollTo({ left: 0, top: 0, behavior: "auto" }));
    if (resumed) {
      setStatus("已恢复上次进度。先回忆当前句，再选择朗读、默写或自评。" );
    } else if (state.speechSupported) {
      setStatus("已准备好。建议先熟读，再切到渐隐和无提示阶段。" );
    } else {
      setStatus("当前浏览器不支持语音识别，但默写和自评训练都可正常使用。", true);
    }
  } catch (error) {
    state.error = error.message || "背诵内容加载失败。";
    setStatus(state.error, true);
    renderBlankScroll();
  } finally {
    state.loading = false;
    updateControlStates();
  }
}

function bootstrap() {
  window.humanVerification.init({
    overlayId: "humanVerificationOverlay",
    checkboxId: "humanVerificationCheckbox",
    buttonId: "humanVerificationButton",
    messageId: "humanVerificationMessage",
    gateSelector: ".scroll-page",
    onVerified: startReciteScrollPage
  });
}

bootstrap();

const state = {
  title: "",
  author: "",
  layout: null,
  currentPageIndex: 0,
  currentLineIndex: 0,
  totalPages: 0,
  totalLines: 0,
  pageStates: [],
  slots: [],
  lineSlots: [],
  lineElements: [],
  isListening: false,
  recognition: null,
  speechSupported: false,
  recognizedText: "",
  loading: false,
  error: ""
};

function getReciteQuery() {
  const params = new URLSearchParams(window.location.search);
  return {
    title: params.get("title")?.trim() || "",
    author: params.get("author")?.trim() || ""
  };
}

function fillWorkMeta() {
  const resolvedTitle = state.title || "未选择作品";
  const resolvedAuthor = state.author || "作者未提供";

  document.getElementById("scrollTitle").textContent = resolvedTitle;
  document.getElementById("scrollAuthor").textContent = resolvedAuthor;
  document.title = `${resolvedTitle} - 竹简背诵`;
}

function setStatus(message, isError = false) {
  const status = document.getElementById("scrollStatus");
  status.textContent = message;
  status.classList.toggle("is-error", isError);
  status.hidden = !message;
}

function setRecognizedText(text) {
  state.recognizedText = text;
  const output = document.getElementById("recognizedTextOutput");
  output.textContent = `识别文本：${text || "暂未开始"}`;
}

function getCurrentPage() {
  return state.layout?.pages?.[state.currentPageIndex] || null;
}

function getCurrentPageState() {
  return state.pageStates[state.currentPageIndex] || null;
}

function allPagesCompleted() {
  return state.pageStates.length > 0 && state.pageStates.every((pageState) => pageState.completed);
}

function updateProgress() {
  const progress = document.getElementById("scrollProgress");
  if (!state.totalPages) {
    progress.textContent = "第 0 简 / 共 0 简";
    return;
  }

  const pageState = getCurrentPageState();
  if (!pageState) {
    progress.textContent = `第 ${state.currentPageIndex + 1} 简 / 共 ${state.totalPages} 简`;
    return;
  }

  if (pageState.completed) {
    progress.textContent = `第 ${state.currentPageIndex + 1} 简 / 共 ${state.totalPages} 简 · 本简已完成`;
    return;
  }

  progress.textContent = `第 ${state.currentPageIndex + 1} 简 / 共 ${state.totalPages} 简 · 第 ${state.currentLineIndex + 1} 句 / 共 ${state.totalLines} 句`;
}

function setSlotState(slot, mode) {
  slot.state = mode;
  slot.element.dataset.state = mode;
}

function updateControlStates() {
  const startButton = document.getElementById("startReciteButton");
  const prevPageButton = document.getElementById("prevPageButton");
  const nextPageButton = document.getElementById("nextPageButton");
  const nextLineButton = document.getElementById("nextLineButton");
  const retryButton = document.getElementById("retryLineButton");
  const showAnswerButton = document.getElementById("showAnswerButton");
  const checkButton = document.getElementById("checkReciteButton");
  const pageState = getCurrentPageState();

  startButton.textContent = state.isListening ? "正在听……" : "开始背诵";
  startButton.disabled = state.loading || !state.layout || !pageState || pageState.completed || state.isListening;

  prevPageButton.disabled = state.isListening || state.currentPageIndex <= 0;
  nextPageButton.disabled = state.isListening || state.currentPageIndex >= Math.max(state.totalPages - 1, 0);

  const canAdvanceLine = Boolean(
    pageState
    && !pageState.completed
    && state.currentLineIndex < Math.max(state.totalLines - 1, 0)
    && pageState.linePassed[state.currentLineIndex]
    && !state.isListening
  );
  nextLineButton.disabled = !canAdvanceLine;

  retryButton.disabled = !state.layout || !pageState || state.isListening;
  showAnswerButton.disabled = !state.layout || !pageState || state.isListening;
  checkButton.disabled = !state.layout || !pageState || pageState.completed || state.isListening;
}

function syncActiveLine() {
  const pageState = getCurrentPageState();
  state.lineElements.forEach((element, index) => {
    element.classList.toggle("is-active", Boolean(pageState && !pageState.completed && index === state.currentLineIndex));
  });
}

function createSlot(char, lineIndex, charIndex) {
  const element = document.createElement("div");
  element.className = "bamboo-char-slot";
  element.dataset.lineIndex = String(lineIndex);
  element.dataset.charIndex = String(charIndex);
  element.dataset.state = "blank";

  const glyph = document.createElement("span");
  glyph.className = "bamboo-char-glyph";
  glyph.textContent = char || "";
  element.appendChild(glyph);

  return {
    char,
    lineIndex,
    charIndex,
    state: "blank",
    element
  };
}

function createInitialPageState(page) {
  return {
    currentLineIndex: 0,
    completed: false,
    linePassed: Array.from({ length: page.columns.length }, () => false),
    slotStates: page.columns.map((column) => column.map(() => "blank"))
  };
}

function clearTransientInputs() {
  document.getElementById("manualReciteInput").value = "";
  setRecognizedText("");
}

function renderBlankScroll(columnCount = 8, rowCount = 12) {
  const host = document.getElementById("bambooScroll");
  host.innerHTML = "";
  host.classList.add("is-empty");
  host.classList.remove("is-short-page");
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

  updateProgress();
  updateControlStates();
}

function renderCurrentPage() {
  const host = document.getElementById("bambooScroll");
  const page = getCurrentPage();
  const pageState = getCurrentPageState();

  host.innerHTML = "";
  host.classList.remove("is-empty");
  state.slots = [];
  state.lineSlots = [];
  state.lineElements = [];

  if (!page || !pageState) {
    renderBlankScroll();
    return;
  }

  host.classList.toggle("is-short-page", page.columns.length <= 4);
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

    const indicator = document.createElement("div");
    indicator.className = "bamboo-line-indicator";
    indicator.textContent = "当前句";
    slat.appendChild(indicator);

    const lineSlots = [];

    for (let charIndex = 0; charIndex < slotCount; charIndex += 1) {
      const char = column[charIndex] || "";
      const slot = createSlot(char, lineIndex, charIndex);
      if (!char) {
        slot.element.classList.add("is-placeholder");
      } else {
        const persistedState = pageState.slotStates[lineIndex]?.[charIndex] || "blank";
        setSlotState(slot, persistedState);
        state.slots.push(slot);
        lineSlots.push(slot);
      }
      slat.appendChild(slot.element);
    }

    state.lineSlots.push(lineSlots);
    state.lineElements.push(slat);
    host.appendChild(slat);
  });

  updateProgress();
  syncActiveLine();
  updateControlStates();
}

async function fetchReciteLayout() {
  const query = new URLSearchParams({
    title: state.title,
    author: state.author
  });

  const response = await fetch(`/api/recite/layout?${query.toString()}`, {
    credentials: "same-origin"
  });
  const payload = await response.json().catch(() => ({}));

  if (!response.ok || payload.success === false) {
    throw new Error(payload.error || (response.status === 403 ? "请先完成人机验证。" : "竹简布局加载失败。"));
  }

  return payload;
}

async function fetchReciteCheck(spokenText) {
  const response = await fetch("/api/recite/check", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      title: state.title,
      author: state.author,
      page_index: state.currentPageIndex,
      current_line_index: state.currentLineIndex,
      spoken_text: spokenText
    })
  });
  const payload = await response.json().catch(() => ({}));

  if (!response.ok || payload.success === false) {
    throw new Error(payload.error || (response.status === 403 ? "请先完成人机验证。" : "背诵检查失败。"));
  }

  return payload;
}

function showAnswer() {
  const pageState = getCurrentPageState();
  if (!pageState) return;
  const shouldReveal = window.confirm("显示答案会直接展示当前这一简的正文，是否继续？");
  if (!shouldReveal) {
    return;
  }

  pageState.slotStates = pageState.slotStates.map((columnStates) => columnStates.map(() => "written"));
  renderCurrentPage();
  setStatus(`已显示第 ${state.currentPageIndex + 1} 简答案。`);
}

function resetLineStates(lineIndex) {
  const pageState = getCurrentPageState();
  if (!pageState) return;

  const lineSlots = state.lineSlots[lineIndex] || [];
  lineSlots.forEach((slot) => {
    setSlotState(slot, "blank");
  });

  pageState.slotStates[lineIndex] = pageState.slotStates[lineIndex].map(() => "blank");
  pageState.linePassed[lineIndex] = false;
  pageState.completed = false;
  updateControlStates();
}

function retryCurrentLine() {
  const pageState = getCurrentPageState();
  if (!pageState || !state.totalLines) return;

  resetLineStates(state.currentLineIndex);
  pageState.currentLineIndex = state.currentLineIndex;
  clearTransientInputs();
  updateProgress();
  syncActiveLine();
  setStatus(`已清空第 ${state.currentPageIndex + 1} 简第 ${state.currentLineIndex + 1} 句，请重新输入或朗读。`);
  updateControlStates();
}

function applyCharResults(lineIndex, charResults) {
  const pageState = getCurrentPageState();
  const lineSlots = state.lineSlots[lineIndex] || [];
  if (!pageState) return;

  lineSlots.forEach((slot, index) => {
    const result = charResults[index];
    let mode = "blank";
    if (result?.status === "correct") {
      mode = "written";
    } else if (result?.status === "wrong") {
      mode = "ink_error";
    }
    pageState.slotStates[lineIndex][index] = mode;
    setSlotState(slot, mode);
  });
}

function moveToNextLine() {
  const pageState = getCurrentPageState();
  if (!pageState) return;
  if (!pageState.linePassed[state.currentLineIndex]) {
    setStatus("当前句尚未通过，暂时不能进入下一句。", true);
    return;
  }
  if (state.currentLineIndex >= state.totalLines - 1) {
    pageState.completed = true;
    updateProgress();
    syncActiveLine();
    updateControlStates();
    setStatus(allPagesCompleted() ? "全部竹简已完成。" : "本简已完成，可切换到下一简。");
    return;
  }

  state.currentLineIndex += 1;
  pageState.currentLineIndex = state.currentLineIndex;
  clearTransientInputs();
  updateProgress();
  syncActiveLine();
  updateControlStates();
  setStatus(`已进入第 ${state.currentPageIndex + 1} 简第 ${state.currentLineIndex + 1} 句。`);
}

function switchPage(pageIndex) {
  if (pageIndex < 0 || pageIndex >= state.totalPages || pageIndex === state.currentPageIndex) {
    return;
  }
  state.currentPageIndex = pageIndex;
  clearTransientInputs();
  renderCurrentPage();
  setStatus(`已切换到第 ${state.currentPageIndex + 1} 简。`);
}

function moveToPrevPage() {
  switchPage(state.currentPageIndex - 1);
}

function moveToNextPage() {
  switchPage(state.currentPageIndex + 1);
}

async function submitRecitationText(spokenText, source = "manual") {
  const pageState = getCurrentPageState();
  if (!state.layout || !pageState || !state.totalLines) return;
  if (pageState.completed) {
    setStatus("当前简已完成，可切换到下一简或返回上一简复查。");
    return;
  }

  try {
    const result = await fetchReciteCheck(spokenText);
    if (result.status === "order_error") {
      setStatus(result.message || "顺序可能有误。", true);
      updateControlStates();
      return;
    }

    applyCharResults(state.currentLineIndex, result.char_results || []);

    if (result.status === "pass" && result.passed) {
      pageState.linePassed[state.currentLineIndex] = true;
      if (state.currentLineIndex >= state.totalLines - 1) {
        pageState.completed = true;
        setStatus(allPagesCompleted() ? "本句通过，全部竹简已完成。" : "本句通过，本简已完成。可切换到下一简。");
      } else {
        setStatus(result.message || "本句通过，可点击“下一句”继续。");
      }
      if (source === "manual") {
        document.getElementById("manualReciteInput").value = "";
      }
    } else {
      pageState.linePassed[state.currentLineIndex] = false;
      setStatus("未匹配成功，可能存在背诵错误或识别偏差。", true);
    }

    updateProgress();
    syncActiveLine();
    updateControlStates();
  } catch (error) {
    setStatus(error.message || "背诵检查失败。", true);
    updateControlStates();
  }
}

async function handleManualCheck() {
  const pageState = getCurrentPageState();
  if (!pageState) return;

  const input = document.getElementById("manualReciteInput");
  const spokenText = input.value.trim();
  if (!spokenText) {
    setStatus("请输入当前句的背诵内容。", true);
    input.focus();
    return;
  }
  setRecognizedText(spokenText);
  await submitRecitationText(spokenText, "manual");
}

function getSpeechRecognitionCtor() {
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

async function ensureSpeechPermission() {
  if (!navigator.mediaDevices?.getUserMedia) {
    return;
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  stream.getTracks().forEach((track) => track.stop());
}

function buildRecognition() {
  const SpeechRecognitionCtor = getSpeechRecognitionCtor();
  if (!SpeechRecognitionCtor) {
    return null;
  }

  const recognition = new SpeechRecognitionCtor();
  recognition.lang = "zh-CN";
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  recognition.onstart = () => {
    state.isListening = true;
    setStatus("正在听取本句，请正常朗读。");
    updateControlStates();
  };

  recognition.onresult = async (event) => {
    const transcript = Array.from(event.results || [])
      .map((result) => result?.[0]?.transcript || "")
      .join("")
      .trim();

    if (!transcript) {
      setStatus("没有识别到有效文本，请重试或改用手动输入。", true);
      return;
    }

    document.getElementById("manualReciteInput").value = transcript;
    setRecognizedText(transcript);
    await submitRecitationText(transcript, "speech");
  };

  recognition.onerror = (event) => {
    const messageMap = {
      "audio-capture": "未检测到可用麦克风，请检查设备权限。",
      "not-allowed": "麦克风权限被拒绝，无法进行语音背诵检查。",
      "service-not-allowed": "当前环境不允许使用浏览器语音识别。",
      "no-speech": "没有识别到语音，请重试。",
      "network": "语音识别服务暂时不可用，请稍后重试。",
      "aborted": "语音识别已中断，请重新开始。",
    };
    setStatus(messageMap[event.error] || "语音识别失败，请重试或改用手动输入。", true);
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
  if (pageState.completed) {
    setStatus("当前简已完成，可切换到下一简或返回上一简复查。");
    return;
  }
  if (pageState.linePassed[state.currentLineIndex]) {
    setStatus("当前句已通过，可点击“下一句”继续。");
    return;
  }

  const SpeechRecognitionCtor = getSpeechRecognitionCtor();
  state.speechSupported = Boolean(SpeechRecognitionCtor);
  if (!state.speechSupported) {
    setStatus("当前浏览器不支持语音背诵检查，请使用 Chrome 或 Edge。", true);
    updateControlStates();
    return;
  }

  try {
    await ensureSpeechPermission();
    if (!state.recognition) {
      state.recognition = buildRecognition();
    }
    if (!state.recognition) {
      setStatus("当前浏览器不支持语音背诵检查，请使用 Chrome 或 Edge。", true);
      updateControlStates();
      return;
    }
    setRecognizedText("正在等待识别结果...");
    state.recognition.start();
  } catch (error) {
    const name = error?.name || "";
    if (name === "NotAllowedError" || name === "PermissionDeniedError") {
      setStatus("麦克风权限被拒绝，无法进行语音背诵检查。", true);
    } else {
      setStatus("无法启动语音识别，请检查浏览器权限或改用手动输入。", true);
    }
    state.isListening = false;
    updateControlStates();
  }
}

function bindActions() {
  document.getElementById("showAnswerButton").addEventListener("click", showAnswer);
  document.getElementById("startReciteButton").addEventListener("click", startSpeechRecitation);
  document.getElementById("prevPageButton").addEventListener("click", moveToPrevPage);
  document.getElementById("nextPageButton").addEventListener("click", moveToNextPage);
  document.getElementById("nextLineButton").addEventListener("click", moveToNextLine);
  document.getElementById("retryLineButton").addEventListener("click", retryCurrentLine);
  document.getElementById("checkReciteButton").addEventListener("click", handleManualCheck);
  document.getElementById("manualReciteInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      handleManualCheck();
    }
  });
  document.getElementById("backToReaderButton").addEventListener("click", backToReader);
}

function backToReader() {
  const query = new URLSearchParams();

  if (state.title) query.set("title", state.title);
  if (state.author) query.set("author", state.author);

  const target = query.toString() ? `./reader.html?${query.toString()}` : "./reader.html";
  window.location.href = target;
}

async function startReciteScrollPage() {
  const { title, author } = getReciteQuery();
  state.title = title;
  state.author = author;
  state.speechSupported = Boolean(getSpeechRecognitionCtor());
  fillWorkMeta();
  bindActions();
  clearTransientInputs();
  updateProgress();
  updateControlStates();

  if (!state.title) {
    state.error = "请先从阅读页选择作品后再进入竹简背诵。";
    setStatus(state.error, true);
    renderBlankScroll();
    return;
  }

  state.loading = true;
  state.error = "";
  setStatus("");
  renderBlankScroll();

  try {
    const layout = await fetchReciteLayout();
    state.layout = layout;
    state.title = layout.title || state.title;
    state.author = layout.author || state.author;
    state.currentPageIndex = 0;
    state.totalPages = Array.isArray(layout.pages) ? layout.pages.length : 0;
    state.pageStates = (layout.pages || []).map((page) => createInitialPageState(page));
    fillWorkMeta();
    renderCurrentPage();
    setStatus("已加载竹简布局，可点击“开始背诵”，也可使用下方备用手动输入。");
  } catch (error) {
    state.error = error.message || "竹简布局加载失败。";
    setStatus(state.error, true);
    renderBlankScroll();
    updateProgress();
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

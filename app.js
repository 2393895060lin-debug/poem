const state = {
  article: null,
  showTranslation: false,
  showNotes: false,
  showPinyin: true,
  showRecitation: false,
  annotationMode: false,
  eraserMode: false,
  annotationColor: "#c84c31",
  annotationWidth: 4,
  annotations: [],
  loading: false,
  error: ""
};

const punctuationMarks = new Set(["，", "。", "；", "：", "？", "！", "“", "”", "〔", "〕", "（", "）", "《", "》", "、"]);
const inlineSymbols = new Set(["〔", "〕", "（", "）", "《", "》", "[", "]", "【", "】"]);
const toggleTargets = {
  toggleTranslation: "translationSection",
  toggleNotes: "notesSection",
  togglePinyin: "articleCanvas"
};
const annotationHelpStorageKey = "poem_annotation_help_seen_v1";
const recentWorksStorageKey = "poem_recent_works_v1";
const favoritesStorageKey = "poem_favorites_v1";
let activeStroke = null;
let activeStrokePointerId = null;
const touchPointers = new Map();
let touchPanState = null;
let removeMobileTouchGuards = null;
let touchPanFrameId = 0;
let pageScrollLockY = 0;
let deferredRenderTimer = 0;
let activeSearchController = null;
let activeSearchRequestId = 0;
let transientStatusTimer = 0;

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function escapeSvg(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function safeExternalUrl(value) {
  try {
    const url = new URL(String(value || ""), window.location.origin);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "#";
  } catch (_error) {
    return "#";
  }
}

function readStoredList(key) {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(key) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch (error) {
    console.warn(`Failed to read ${key}.`, error);
    return [];
  }
}

function writeStoredList(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch (error) {
    console.warn(`Failed to write ${key}.`, error);
  }
}

function shouldHidePinyin(char) {
  return punctuationMarks.has(char) || inlineSymbols.has(char);
}

function createGridCells(values, className, host) {
  host.innerHTML = "";
  values.forEach((value) => {
    const cell = document.createElement("div");
    cell.className = className;
    cell.textContent = value;
    host.appendChild(cell);
  });
}

function formatPreviewMeta(article) {
  if (!article) {
    return "输入题目后自动生成缩略预览";
  }
  const author = article.author || "佚名";
  return article.dynasty ? `${author} [${article.dynasty}]` : author;
}

function mountHeader(article) {
  createGridCells(article.title.split(""), "title-cell", document.getElementById("titleGrid"));
  document.getElementById("authorPinyin").innerHTML = article.authorPinyin
    .map((item) => `<span>${inlineSymbols.has(item) ? "" : escapeHtml(item)}</span>`)
    .join("");
  createGridCells(article.authorDisplay, "author-cell", document.getElementById("authorGrid"));
  document.title = `${article.title} - 古诗文排版查询`;
}

function createArticleCell(unit) {
  const cell = document.createElement("div");
  cell.className = "character-cell";
  if (punctuationMarks.has(unit.char)) {
    cell.classList.add("punctuation");
  }

  const pinyin = document.createElement("div");
  pinyin.className = "character-pinyin";
  pinyin.textContent = shouldHidePinyin(unit.char) ? "" : unit.pinyin;

  const glyph = document.createElement("div");
  glyph.className = "character-glyph";
  glyph.textContent = unit.char;

  cell.append(pinyin, glyph);

  return cell;
}

function resetAnnotations() {
  state.annotations = [];
  activeStroke = null;
  activeStrokePointerId = null;
  renderAnnotationLayer();
}

function isMobileViewport() {
  return window.matchMedia("(max-width: 900px)").matches;
}

function hasTouchInput() {
  return (navigator.maxTouchPoints || 0) > 0 || window.matchMedia("(hover: none) and (pointer: coarse)").matches;
}

function rememberAnnotationHelpShown() {
  try {
    window.localStorage.setItem(annotationHelpStorageKey, "1");
  } catch (error) {
    console.warn("Failed to persist annotation help state.", error);
  }
}

function maybeShowAnnotationHelp() {
  if (!hasTouchInput()) return;
  try {
    if (window.localStorage.getItem(annotationHelpStorageKey) === "1") {
      return;
    }
  } catch (error) {
    console.warn("Failed to read annotation help state.", error);
  }

  const dialog = document.getElementById("annotationHelpDialog");
  if (!dialog || dialog.open) return;
  rememberAnnotationHelpShown();
  dialog.showModal();
}

function shouldBlockNativeTouchGesture(target) {
  if (!isMobileViewport() || !state.annotationMode) return false;
  if (!(target instanceof Element)) return true;
  return !target.closest(".annotation-tools");
}

function syncMobileTouchGuards() {
  if (removeMobileTouchGuards) {
    removeMobileTouchGuards();
    removeMobileTouchGuards = null;
  }

  if (!isMobileViewport() || !state.annotationMode) return;

  const preventNativeGesture = (event) => {
    if (!shouldBlockNativeTouchGesture(event.target)) return;
    event.preventDefault();
  };

  document.addEventListener("touchmove", preventNativeGesture, { passive: false, capture: true });
  document.addEventListener("gesturestart", preventNativeGesture, { passive: false, capture: true });
  document.addEventListener("gesturechange", preventNativeGesture, { passive: false, capture: true });

  removeMobileTouchGuards = () => {
    document.removeEventListener("touchmove", preventNativeGesture, true);
    document.removeEventListener("gesturestart", preventNativeGesture, true);
    document.removeEventListener("gesturechange", preventNativeGesture, true);
  };
}

function createNoteGaps(unit) {
  if (!state.showNotes || !unit.noteNumbers?.length) {
    return [];
  }

  return unit.noteNumbers.map((number, idx) => {
    const gap = document.createElement("div");
    gap.className = `note-gap${idx > 0 ? " stacked" : ""}`;
    gap.dataset.noteIndex = String(number);

    const marker = document.createElement("button");
    marker.className = "note-marker";
    marker.textContent = number;
    marker.type = "button";
    marker.dataset.noteIndex = String(number);
    marker.title = `跳转到注释 ${number}`;

    gap.appendChild(marker);
    return gap;
  });
}

function renderArticle() {
  const articleCanvas = document.getElementById("articleCanvas");
  articleCanvas.replaceChildren();

  function renderEmptyState(message, isError = false) {
    const empty = document.createElement("div");
    empty.className = `empty-state${isError ? " empty-state-error" : ""}`;
    empty.textContent = message;
    articleCanvas.appendChild(empty);
  }

  if (state.loading) {
    renderEmptyState("正在查询并排版中...");
    return;
  }

  if (state.error) {
    renderEmptyState(state.error, true);
    return;
  }

  if (!state.article) {
    renderEmptyState("输入题目后开始排版。");
    return;
  }

  articleCanvas.classList.toggle("hide-pinyin", !state.showPinyin);

  state.article.lines.forEach((line) => {
    const lineBlock = document.createElement("div");
    lineBlock.className = "line-block";

    line.forEach((unit) => {
      lineBlock.appendChild(createArticleCell(unit));
      createNoteGaps(unit).forEach((gap) => lineBlock.appendChild(gap));
    });

    articleCanvas.appendChild(lineBlock);
  });

  syncAnnotationLayerSize();
}

function renderNoteEntries(items) {
  return items
    .map((item) => {
      const safeIndex = escapeHtml(item.index);
      return `
      <div class="note-entry" data-note-index="${safeIndex}">
        <button class="note-index" type="button" data-note-index="${safeIndex}" title="跳回原文第 ${safeIndex} 处注释">${safeIndex}</button>
        <div class="note-copy"><span class="note-term">${escapeHtml(item.term || "")}</span>${item.term ? "：" : ""}${escapeHtml(item.text || "")}</div>
      </div>
    `;
    })
    .join("");
}

function renderNoteGroups(article) {
  const groups = article.noteGroups?.filter((group) => group.items?.length) || [];
  if (!groups.length) {
    return renderNoteEntries(article.notes || []);
  }

  return groups
    .map((group) => `
      <section class="note-group">
        <div class="note-group-title">${escapeHtml(group.label || "")}</div>
        <div class="note-group-list">
          ${renderNoteEntries(group.items)}
        </div>
      </section>
    `)
    .join("");
}

function fillSupplementBody() {
  const article = state.article;
  if (!article) return;

  const enrichmentMessage = article.enrichment?.message
    ? `<p class="supplement-empty">${escapeHtml(article.enrichment.message)}</p>`
    : "";
  let refreshPrompt = "";
  if (shouldShowRefreshButton(article)) {
    const refreshCopy = article.enrichment?.status === "settled"
      ? "当前结果仍可继续重试，点击顶部“刷新内容”后，页面会在本次请求里重新抓取一次，再更新当前内容。"
      : "点击顶部“刷新内容”后，页面会在本次请求里等待抓取结果，再更新当前内容。";
    refreshPrompt = `<p class="supplement-empty">${refreshCopy}</p>`;
  }

  document.getElementById("translationBody").innerHTML = article.translation.length
    ? article.translation.map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`).join("")
    : `
      <p class="supplement-empty">当前未收录现成白话译文，下面给你准备了可直接打开的译文参考入口。</p>
      ${enrichmentMessage}
      ${refreshPrompt}
      <div class="reference-link-list">
        ${(article.translationReferences || [])
          .map((item) => `
            <a class="reference-link-card" href="${escapeHtml(safeExternalUrl(item.url))}" target="_blank" rel="noreferrer">
              <div class="reference-link-title">${escapeHtml(item.label)}</div>
              <div class="reference-link-copy">${escapeHtml(item.description)}</div>
            </a>
          `)
          .join("")}
      </div>
    `;

  document.getElementById("notesBody").innerHTML = article.notes.length
    ? renderNoteGroups(article)
    : `
      <div class="supplement-empty">当前还没有这篇作品的注释，后续可以继续补充教材注释或通用注释。</div>
      ${enrichmentMessage}
      ${refreshPrompt}
    `;
  document.getElementById("recitationBody").innerHTML = (article.recitationReferences || [])
    .map((item) => `
      <a class="recitation-item" href="${escapeHtml(safeExternalUrl(item.url))}" target="_blank" rel="noreferrer">
        <div class="recitation-item-title">${escapeHtml(item.label)}</div>
        <div class="recitation-item-copy">${escapeHtml(item.description)}</div>
      </a>
    `)
    .join("");
}

function getAvailability(article) {
  if (!article) {
    return {
      translation: false,
      notes: false,
      recitationReferences: false
    };
  }

  return {
    translation: true,
    notes: true,
    recitationReferences: Boolean(article.availability?.recitationReferences)
  };
}

function articleHasSupplementGap(article) {
  if (!article) return false;
  return !article.translation.length || !article.notes.length;
}

function shouldShowRefreshButton(article) {
  if (!article || !articleHasSupplementGap(article)) {
    return false;
  }
  return true;
}

function updateRefreshButton() {
  const button = document.getElementById("refreshArticleButton");
  if (!button) return;
  const shouldShow = shouldShowRefreshButton(state.article);
  button.classList.toggle("toolbar-refresh-button-hidden", !shouldShow);
  button.disabled = Boolean(state.loading);
}

function updateToggleAvailability() {
  const availability = getAvailability(state.article);

  const pairs = [
    ["toggleTranslation", "showTranslation", availability.translation],
    ["toggleNotes", "showNotes", availability.notes],
    ["toggleRecitation", "showRecitation", availability.recitationReferences]
  ];

  pairs.forEach(([id, key, enabled]) => {
    const input = document.getElementById(id);
    const row = input.closest(".toggle-row");
    if (!enabled && id === "toggleRecitation") {
      state[key] = false;
    }
    input.disabled = false;
    input.checked = state[key];
    row?.classList.toggle("is-unavailable", !enabled);
  });
}

function renderSupplementSections() {
  const availability = getAvailability(state.article);
  updateToggleAvailability();
  updateRefreshButton();

  const translationSection = document.getElementById("translationSection");
  const notesSection = document.getElementById("notesSection");
  const recitationSection = document.getElementById("recitationSection");

  if (!state.article) {
    translationSection.classList.add("hidden");
    notesSection.classList.add("hidden");
    recitationSection.classList.add("hidden");
    return;
  }

  fillSupplementBody();

  translationSection.classList.toggle("hidden", !state.showTranslation || !availability.translation);
  notesSection.classList.toggle("hidden", !state.showNotes || !availability.notes);
  recitationSection.classList.toggle("hidden", !state.showRecitation || !availability.recitationReferences);
}

function buildPrintablePreview() {
  const article = state.article;
  if (!article) {
    const empty = document.createElement("div");
    empty.className = "print-preview-sheet";
    empty.innerHTML = `<div class="empty-state">还没有可导出的内容。</div>`;
    return empty;
  }

  const sheet = document.createElement("div");
  sheet.className = "print-preview-sheet";

  const titleGrid = document.createElement("div");
  titleGrid.className = "title-grid";
  article.title.split("").forEach((char) => {
    const cell = document.createElement("div");
    cell.className = "title-cell";
    cell.textContent = char;
    titleGrid.appendChild(cell);
  });

  const authorWrap = document.createElement("div");
  authorWrap.className = "author-stack";
  authorWrap.innerHTML = `
    <div class="author-pinyin">${article.authorPinyin.map((item) => `<span>${inlineSymbols.has(item) ? "" : escapeHtml(item)}</span>`).join("")}</div>
    <div class="author-grid">${article.authorDisplay.map((item) => `<div class="author-cell">${escapeHtml(item)}</div>`).join("")}</div>
  `;

  const articleCanvas = document.createElement("section");
  articleCanvas.className = `article-canvas${state.showPinyin ? "" : " hide-pinyin"}`;
  article.lines.forEach((line) => {
    const lineBlock = document.createElement("div");
    lineBlock.className = "line-block";
    line.forEach((unit) => {
      lineBlock.appendChild(createArticleCell(unit));
      createNoteGaps(unit).forEach((gap) => lineBlock.appendChild(gap));
    });
    articleCanvas.appendChild(lineBlock);
  });

  sheet.append(titleGrid, authorWrap, articleCanvas);

  if (state.showTranslation && article.translation.length) {
    const section = document.createElement("section");
    section.className = "supplement-card";
    section.innerHTML = `<div class="section-kicker">译文</div><div class="supplement-body">${article.translation.map((item) => `<p>${escapeHtml(item)}</p>`).join("")}</div>`;
    sheet.appendChild(section);
  }

  if (state.showNotes && article.notes.length) {
    const section = document.createElement("section");
    section.className = "supplement-card";
    section.innerHTML = `<div class="section-kicker">注释</div><div class="notes-list">${renderNoteGroups(article)}</div>`;
    sheet.appendChild(section);
  }

  return sheet;
}

function shouldUseImageExport() {
  return hasTouchInput() && window.matchMedia("(max-width: 1180px)").matches;
}

function getExportFileName(extension) {
  const baseName = (state.article?.title || "古诗文排版")
    .replace(/[\\/:*?"<>|]/g, "-")
    .trim() || "古诗文排版";
  return `${baseName}.${extension}`;
}

function isAppleMobileDevice() {
  const ua = navigator.userAgent || "";
  return /iPhone|iPad|iPod/i.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

function buildImageExportUrl() {
  if (!state.article) {
    return "";
  }
  const params = new URLSearchParams({
    title: state.article.title || "",
    author: state.article.author || "",
    showTranslation: state.showTranslation ? "1" : "0",
    showNotes: state.showNotes ? "1" : "0",
    showPinyin: state.showPinyin ? "1" : "0"
  });
  return `/api/export-image?${params.toString()}`;
}

async function fetchImageExportBlob() {
  const exportUrl = buildImageExportUrl();
  if (!exportUrl) {
    throw new Error("还没有可导出的内容。");
  }

  const response = await fetch(exportUrl, {
    credentials: "same-origin"
  });

  if (!response.ok) {
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const payload = await response.json();
      throw new Error(payload.error || "长图导出失败。");
    }
    throw new Error("长图导出失败，请稍后重试。");
  }

  return response.blob();
}

async function exportLongImage() {
  if (!state.article) return;
  const exportUrl = buildImageExportUrl();
  const fileName = getExportFileName("png");
  const canUseFileShare = typeof navigator.share === "function" && typeof navigator.canShare === "function";

  if (canUseFileShare) {
    const blob = await fetchImageExportBlob();
    const file = new File([blob], fileName, { type: blob.type || "image/png" });
    if (navigator.canShare({ files: [file] })) {
      try {
        await navigator.share({
          files: [file],
          title: state.article.title,
          text: `${state.article.title} 长图`
        });
        return;
      } catch (error) {
        if (error?.name === "AbortError") {
          return;
        }
      }
    }
  }

  const link = document.createElement("a");
  link.href = exportUrl;
  link.rel = "noopener";
  if (isAppleMobileDevice()) {
    link.target = "_blank";
  } else {
    link.download = fileName;
  }
  document.body.appendChild(link);
  link.click();
  link.remove();
}

async function handlePrimaryExport() {
  if (shouldUseImageExport()) {
    await exportLongImage();
    return;
  }
  downloadPdf();
}

function syncExportButtonLabels() {
  const downloadButton = document.getElementById("downloadPdfButton");
  const previewButton = document.getElementById("previewPdfButton");
  if (downloadButton) {
    downloadButton.textContent = shouldUseImageExport() ? "保存长图" : "下载PDF";
  }
  if (previewButton) {
    previewButton.textContent = shouldUseImageExport() ? "查看长图效果" : "查看PDF效果";
  }
}

function getWorkIdentity(work) {
  return `${String(work?.title || "").trim()}::${String(work?.author || "").trim()}`;
}

function toStoredWork(article) {
  return {
    title: String(article?.title || "").trim(),
    author: String(article?.author || "").trim(),
    dynasty: String(article?.dynasty || "").trim(),
    updatedAt: new Date().toISOString()
  };
}

function recordRecentWork(article) {
  const work = toStoredWork(article);
  if (!work.title) return;
  const identity = getWorkIdentity(work);
  const items = readStoredList(recentWorksStorageKey).filter((item) => getWorkIdentity(item) !== identity);
  writeStoredList(recentWorksStorageKey, [work, ...items].slice(0, 20));
}

function isCurrentArticleFavorite() {
  if (!state.article) return false;
  const identity = getWorkIdentity(state.article);
  return readStoredList(favoritesStorageKey).some((item) => getWorkIdentity(item) === identity);
}

function syncArticleActions() {
  const favoriteButton = document.getElementById("favoriteArticleButton");
  const shareButton = document.getElementById("shareArticleButton");
  if (!favoriteButton || !shareButton) return;
  const hasArticle = Boolean(state.article && !state.loading);
  const favorite = hasArticle && isCurrentArticleFavorite();
  favoriteButton.disabled = !hasArticle;
  shareButton.disabled = !hasArticle;
  favoriteButton.setAttribute("aria-pressed", String(favorite));
  favoriteButton.textContent = favorite ? "已收藏" : "收藏";
}

function showTransientStatus(message) {
  window.clearTimeout(transientStatusTimer);
  document.getElementById("queryStatus").textContent = message;
  transientStatusTimer = window.setTimeout(() => {
    transientStatusTimer = 0;
    renderStatus();
  }, 1800);
}

function toggleFavoriteArticle() {
  if (!state.article) return;
  const identity = getWorkIdentity(state.article);
  const favorites = readStoredList(favoritesStorageKey);
  const exists = favorites.some((item) => getWorkIdentity(item) === identity);
  const next = exists
    ? favorites.filter((item) => getWorkIdentity(item) !== identity)
    : [toStoredWork(state.article), ...favorites].slice(0, 50);
  writeStoredList(favoritesStorageKey, next);
  syncArticleActions();
  showTransientStatus(exists ? "已取消收藏" : "已加入收藏");
}

async function shareArticle() {
  if (!state.article) return;
  const shareData = {
    title: `${state.article.title} · 诗境`,
    text: `${state.article.title}${state.article.author ? ` · ${state.article.author}` : ""}`,
    url: window.location.href
  };
  try {
    if (navigator.share) {
      await navigator.share(shareData);
      showTransientStatus("分享面板已打开");
      return;
    }
    await navigator.clipboard.writeText(window.location.href);
    showTransientStatus("链接已复制");
  } catch (error) {
    if (error?.name !== "AbortError") {
      window.prompt("复制这个链接分享作品：", window.location.href);
    }
  }
}

function openReciteScrollPage() {
  const title = (state.article?.title || document.getElementById("searchTitle").value || "").trim();
  const author = (state.article?.author || document.getElementById("searchAuthor").value || "").trim();

  if (!title) {
    window.alert("请先输入题目并完成查询。");
    document.getElementById("searchTitle").focus();
    return;
  }

  const query = new URLSearchParams({ title, author });
  window.location.href = `./recite-scroll.html?${query.toString()}`;
}

function renderPreviewSnapshot() {
  const host = document.getElementById("previewSnapshot");
  host.innerHTML = "";

  const previewHeader = document.createElement("div");
  previewHeader.className = "preview-header";
  previewHeader.innerHTML = `
    <div class="preview-topline"></div>
    <div class="preview-title">${escapeHtml(state.article ? state.article.title : "古诗文排版预览")}</div>
    <div class="preview-meta">${escapeHtml(formatPreviewMeta(state.article))}</div>
  `;

  const previewBody = document.createElement("div");
  previewBody.className = "preview-scale-shell";

  const previewScale = document.createElement("div");
  previewScale.className = "preview-scale";
  previewScale.appendChild(buildPrintablePreview());

  previewBody.appendChild(previewScale);
  host.append(previewHeader, previewBody);
}

function syncAnnotationLayerSize() {
  const stage = document.getElementById("readerStage");
  const layer = document.getElementById("annotationLayer");
  if (!stage || !layer) return;
  const width = Math.ceil(stage.scrollWidth || stage.getBoundingClientRect().width || 0);
  const height = Math.ceil(stage.scrollHeight || stage.getBoundingClientRect().height || 0);
  layer.setAttribute("viewBox", `0 0 ${width} ${height}`);
  layer.setAttribute("width", String(width));
  layer.setAttribute("height", String(height));
}

function getReaderPanel() {
  return document.querySelector(".reader-panel");
}

function lockPageScroll() {
  if (document.body.dataset.scrollLocked === "1") return;
  pageScrollLockY = window.scrollY || window.pageYOffset || 0;
  document.body.dataset.scrollLocked = "1";
  document.body.style.position = "fixed";
  document.body.style.top = `-${pageScrollLockY}px`;
  document.body.style.left = "0";
  document.body.style.right = "0";
  document.body.style.width = "100%";
  document.body.style.overflow = "hidden";
}

function unlockPageScroll() {
  if (document.body.dataset.scrollLocked !== "1") return;
  document.body.dataset.scrollLocked = "0";
  document.body.style.position = "";
  document.body.style.top = "";
  document.body.style.left = "";
  document.body.style.right = "";
  document.body.style.width = "";
  document.body.style.overflow = "";
  window.scrollTo({
    left: 0,
    top: pageScrollLockY,
    behavior: "auto"
  });
}

function alignReaderPanelForAnnotation() {
  if (!isMobileViewport()) return;
  const readerPanel = getReaderPanel();
  const toolbar = document.querySelector(".top-toolbar");
  if (!readerPanel || !toolbar) return;
  const toolbarHeight = Math.ceil(toolbar.getBoundingClientRect().height || 0);
  const panelTop = readerPanel.getBoundingClientRect().top + window.scrollY;
  const targetTop = Math.max(0, panelTop - toolbarHeight - 8);
  window.scrollTo({
    left: 0,
    top: targetTop,
    behavior: "auto"
  });
  readerPanel.scrollTop = 0;
}

function getActiveScrollRoot() {
  if (isMobileViewport() && state.annotationMode) {
    return getReaderPanel() || document.scrollingElement || document.documentElement;
  }
  return document.scrollingElement || document.documentElement;
}

function renderAnnotationLayer() {
  const stage = document.getElementById("readerStage");
  const layer = document.getElementById("annotationLayer");
  const modeButton = document.getElementById("annotationModeButton");
  const eraserButton = document.getElementById("eraserModeButton");
  const clearButton = document.getElementById("clearAnnotationsButton");
  if (!stage || !layer || !modeButton || !eraserButton || !clearButton) return;

  syncAnnotationLayerSize();
  stage.classList.toggle("annotation-active", state.annotationMode);
  const mobileAnnotationFocus = isMobileViewport() && state.annotationMode;
  document.body.classList.toggle("mobile-annotation-focus", mobileAnnotationFocus);
  document.documentElement.classList.toggle("mobile-annotation-focus", mobileAnnotationFocus);
  if (mobileAnnotationFocus) {
    lockPageScroll();
  } else {
    unlockPageScroll();
  }
  syncMobileTouchGuards();
  modeButton.classList.toggle("is-active", state.annotationMode);
  eraserButton.classList.toggle("is-active", state.annotationMode && state.eraserMode);
  modeButton.textContent = state.annotationMode ? "退出批注" : "批注模式";
  eraserButton.textContent = state.annotationMode && state.eraserMode ? "退出橡皮擦" : "橡皮擦";
  clearButton.disabled = state.annotations.length === 0;

  layer.innerHTML = state.annotations
    .map((stroke, index) => {
      const pathData = stroke.points
        .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`)
        .join(" ");
      return `<path class="annotation-path" data-stroke-index="${index}" d="${escapeSvg(pathData)}" stroke="${escapeSvg(stroke.color)}" stroke-width="${stroke.width}"></path>`;
    })
    .join("");
}

function openPreviewDialog() {
  const host = document.getElementById("dialogPreviewHost");
  host.innerHTML = "";
  host.appendChild(buildPrintablePreview());
  document.getElementById("pdfDialog").showModal();
}

function downloadPdf() {
  const printWindow = window.open("", "_blank", "width=1040,height=920");
  if (!printWindow) return;

  const styles = document.querySelector('link[rel="stylesheet"]').outerHTML;
  const preview = buildPrintablePreview().outerHTML;
  printWindow.document.write(`
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
      <meta charset="UTF-8" />
      <title>${escapeHtml(state.article ? state.article.title : "古文排版")} PDF 预览</title>
      ${styles}
    </head>
    <body>
      <div class="dialog-preview-host">${preview}</div>
    </body>
    </html>
  `);
  printWindow.document.close();
  printWindow.focus();
  setTimeout(() => printWindow.print(), 320);
}

async function fetchArticle(title, author, options = {}) {
  if (options.forceRefresh) {
    const response = await fetch("/api/lookup/refresh", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, author }),
      signal: options.signal
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || (response.status === 403 ? "请先完成人机验证。" : "刷新失败"));
    }
    return payload;
  }

  const query = new URLSearchParams({
    title,
    author,
    waitForEnrichment: "0"
  });
  const response = await fetch(`/api/lookup?${query.toString()}`, { signal: options.signal });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || (response.status === 403 ? "请先完成人机验证。" : "查询失败"));
  }
  return payload;
}

function getInitialQuery() {
  const params = new URLSearchParams(window.location.search);
  return {
    title: params.get("title")?.trim() || "",
    author: params.get("author")?.trim() || ""
  };
}

async function runSearch(options = {}) {
  const title = document.getElementById("searchTitle").value.trim();
  const author = document.getElementById("searchAuthor").value.trim();

  if (!title) {
    activeSearchController?.abort();
    activeSearchController = null;
    activeSearchRequestId += 1;
    state.loading = false;
    state.error = "请输入题目。";
    state.article = null;
    render();
    return;
  }

  activeSearchController?.abort();
  activeSearchController = new AbortController();
  const requestId = ++activeSearchRequestId;
  state.loading = true;
  state.error = "";
  render();

  try {
    const article = await fetchArticle(title, author, { ...options, signal: activeSearchController.signal });
    if (requestId !== activeSearchRequestId) return;
    state.article = article;
    state.annotations = [];
    activeStroke = null;
    state.eraserMode = false;
    state.error = "";
    document.getElementById("searchTitle").value = article.title;
    document.getElementById("searchAuthor").value = article.author || "";
    mountHeader(article);
    recordRecentWork(article);
    const canonicalQuery = new URLSearchParams({ title: article.title, author: article.author || "" });
    window.history.replaceState(null, "", `./reader.html?${canonicalQuery.toString()}`);
  } catch (error) {
    if (error?.name === "AbortError" || requestId !== activeSearchRequestId) return;
    state.article = null;
    state.error = error.message;
  } finally {
    if (requestId !== activeSearchRequestId) return;
    activeSearchController = null;
    state.loading = false;
    render();
    scheduleDeferredRender();
  }
}

function jumpToSection(sectionId) {
  if (!sectionId) return;
  const target = document.getElementById(sectionId);
  if (!target || target.classList.contains("hidden")) return;
  target.scrollIntoView({ behavior: "smooth", block: "start" });
}

function syncToggle(id, key, sectionId) {
  const input = document.getElementById(id);
  input.checked = state[key];

  input.addEventListener("change", () => {
    state[key] = input.checked;
    render();
  });
}

function eventPointInLayer(event) {
  const layer = document.getElementById("annotationLayer");
  if (!layer) return null;
  const rect = layer.getBoundingClientRect();
  return {
    x: event.clientX - rect.left,
    y: event.clientY - rect.top
  };
}

function isTouchAnnotationEvent(event) {
  return event.pointerType === "touch" && state.annotationMode;
}

function getViewportAdjustedTouchPoint(event) {
  const viewport = window.visualViewport;
  return {
    x: event.clientX + (viewport?.offsetLeft || 0),
    y: event.clientY + (viewport?.offsetTop || 0)
  };
}

function updateTouchPointer(event) {
  touchPointers.set(event.pointerId, getViewportAdjustedTouchPoint(event));
}

function removeTouchPointer(pointerId) {
  touchPointers.delete(pointerId);
  if (touchPointers.size < 2) {
    touchPanState = null;
    if (touchPanFrameId) {
      window.cancelAnimationFrame(touchPanFrameId);
      touchPanFrameId = 0;
    }
  }
}

function cancelActiveStroke(discard = false) {
  if (!activeStroke) return;
  if (discard) {
    state.annotations = state.annotations.filter((stroke) => stroke !== activeStroke);
    renderAnnotationLayer();
  }
  activeStroke = null;
  activeStrokePointerId = null;
}

function getTwoFingerMidpoint() {
  const [first, second] = Array.from(touchPointers.values());
  if (!first || !second) return null;
  return {
    x: (first.x + second.x) / 2,
    y: (first.y + second.y) / 2
  };
}

function beginTouchPan() {
  const midpoint = getTwoFingerMidpoint();
  if (!midpoint) return;
  cancelActiveStroke(true);
  touchPanState = {
    midpoint
  };
}

function flushTouchPan() {
  touchPanFrameId = 0;
  if (!touchPanState || touchPointers.size < 2) return;
  const midpoint = getTwoFingerMidpoint();
  if (!midpoint) return;
  const deltaX = midpoint.x - touchPanState.midpoint.x;
  const deltaY = midpoint.y - touchPanState.midpoint.y;
  const scrollRoot = getActiveScrollRoot();
  scrollRoot.scrollLeft -= deltaX;
  scrollRoot.scrollTop -= deltaY;
  touchPanState.midpoint = midpoint;
}

function updateTouchPan() {
  if (!touchPanState || touchPointers.size < 2 || touchPanFrameId) return;
  touchPanFrameId = window.requestAnimationFrame(flushTouchPan);
}

function bindAnnotationTools() {
  const modeButton = document.getElementById("annotationModeButton");
  const eraserButton = document.getElementById("eraserModeButton");
  const colorInput = document.getElementById("annotationColor");
  const widthInput = document.getElementById("annotationWidth");
  const clearButton = document.getElementById("clearAnnotationsButton");
  const layer = document.getElementById("annotationLayer");

  modeButton.addEventListener("click", () => {
    state.annotationMode = !state.annotationMode;
    if (state.annotationMode) {
      state.eraserMode = false;
      alignReaderPanelForAnnotation();
      maybeShowAnnotationHelp();
    } else {
      state.eraserMode = false;
    }
    cancelActiveStroke();
    touchPointers.clear();
    touchPanState = null;
    if (touchPanFrameId) {
      window.cancelAnimationFrame(touchPanFrameId);
      touchPanFrameId = 0;
    }
    renderAnnotationLayer();
  });

  eraserButton.addEventListener("click", () => {
    if (!state.annotationMode) {
      state.annotationMode = true;
      alignReaderPanelForAnnotation();
      maybeShowAnnotationHelp();
    }
    state.eraserMode = !state.eraserMode;
    cancelActiveStroke();
    renderAnnotationLayer();
  });

  colorInput.addEventListener("input", () => {
    state.annotationColor = colorInput.value;
  });

  widthInput.addEventListener("input", () => {
    state.annotationWidth = Number(widthInput.value);
  });

  clearButton.addEventListener("click", () => {
    resetAnnotations();
  });

  layer.addEventListener("pointerdown", (event) => {
    if (!state.article) return;
    if (isTouchAnnotationEvent(event)) {
      updateTouchPointer(event);
      layer.setPointerCapture(event.pointerId);
      if (touchPointers.size >= 2) {
        event.preventDefault();
        beginTouchPan();
        return;
      }
    }
    if (state.annotationMode && state.eraserMode) {
      const targetPath = event.target.closest(".annotation-path");
      if (!targetPath) return;
      event.preventDefault();
      const strokeIndex = Number(targetPath.dataset.strokeIndex);
      if (Number.isNaN(strokeIndex)) return;
      state.annotations = state.annotations.filter((_, index) => index !== strokeIndex);
      renderAnnotationLayer();
      return;
    }
    if (!state.annotationMode) return;
    event.preventDefault();
    const point = eventPointInLayer(event);
    if (!point) return;
    activeStroke = {
      color: state.annotationColor,
      width: state.annotationWidth,
      points: [point]
    };
    activeStrokePointerId = event.pointerId;
    state.annotations = [...state.annotations, activeStroke];
    layer.setPointerCapture(event.pointerId);
    renderAnnotationLayer();
  });

  layer.addEventListener("pointermove", (event) => {
    if (isTouchAnnotationEvent(event) && touchPointers.has(event.pointerId)) {
      updateTouchPointer(event);
      if (touchPointers.size >= 2) {
        event.preventDefault();
        updateTouchPan();
        return;
      }
    }
    if (!state.annotationMode || !activeStroke || event.pointerId !== activeStrokePointerId) return;
    event.preventDefault();
    const point = eventPointInLayer(event);
    if (!point) return;
    activeStroke.points.push(point);
    renderAnnotationLayer();
  });

  function finishStroke(event) {
    if (isTouchAnnotationEvent(event)) {
      removeTouchPointer(event.pointerId);
    }
    if (event.pointerId !== undefined && layer.hasPointerCapture(event.pointerId)) {
      layer.releasePointerCapture(event.pointerId);
    }
    if (event.pointerId === activeStrokePointerId) {
      cancelActiveStroke();
    }
  }

  layer.addEventListener("pointerup", finishStroke);
  layer.addEventListener("pointercancel", finishStroke);
  layer.addEventListener("lostpointercapture", (event) => {
    if (isTouchAnnotationEvent(event)) {
      removeTouchPointer(event.pointerId);
    }
    if (event.pointerId === activeStrokePointerId) {
      cancelActiveStroke();
    }
  });
}

function bindToolbarJumpButtons() {
  document.querySelectorAll(".toggle-jump").forEach((button) => {
    button.addEventListener("click", () => {
      if (!state.article) return;
      const sectionId = button.dataset.targetId;
      jumpToSection(sectionId);
    });
  });
}

function bindSearchInputs() {
  document.getElementById("searchButton").addEventListener("click", runSearch);
  document.getElementById("refreshArticleButton").addEventListener("click", () => runSearch({ forceRefresh: true }));
  ["searchTitle", "searchAuthor"].forEach((id) => {
    document.getElementById(id).addEventListener("keydown", (event) => {
      if (event.key === "Enter") runSearch();
    });
  });
}

function findInteractiveRoot(element) {
  return element.closest(".print-preview-sheet, .reader-panel");
}

function jumpToNote(index, trigger) {
  const root = findInteractiveRoot(trigger);
  if (!root) return;
  const target = root.querySelector(`.note-entry[data-note-index="${index}"]`);
  if (!target) return;
  target.scrollIntoView({ behavior: "smooth", block: "center" });
}

function jumpToSource(index, trigger) {
  const root = findInteractiveRoot(trigger);
  if (!root) return;
  const target = root.querySelector(`.note-gap[data-note-index="${index}"] .note-marker`);
  if (!target) return;
  target.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
}

function bindNoteNavigation() {
  document.addEventListener("click", (event) => {
    const source = event.target.closest(".note-marker");
    if (source) {
      jumpToNote(source.dataset.noteIndex, source);
      return;
    }

    const noteIndex = event.target.closest(".note-index");
    if (noteIndex) {
      jumpToSource(noteIndex.dataset.noteIndex, noteIndex);
    }
  });
}

function renderStatus() {
  const status = document.getElementById("queryStatus");
  if (state.loading) {
    status.textContent = "正在排版";
    return;
  }
  if (state.error) {
    status.textContent = "未命中或查询失败";
    return;
  }
  status.textContent = state.article ? `已排版：${state.article.title}` : "等待查询";
}

function render() {
  renderArticle();
  renderSupplementSections();
  renderPreviewSnapshot();
  renderStatus();
  syncExportButtonLabels();
  document.getElementById("searchButton").disabled = state.loading;
  syncArticleActions();
  renderAnnotationLayer();
}

function scheduleDeferredRender() {
  if (deferredRenderTimer) {
    window.clearTimeout(deferredRenderTimer);
    deferredRenderTimer = 0;
  }

  window.requestAnimationFrame(() => {
    render();
    window.requestAnimationFrame(() => {
      render();
    });
  });

  deferredRenderTimer = window.setTimeout(() => {
    deferredRenderTimer = 0;
    render();
  }, 140);
}

function startReaderApp() {
  syncToggle("toggleTranslation", "showTranslation", toggleTargets.toggleTranslation);
  syncToggle("toggleNotes", "showNotes", toggleTargets.toggleNotes);
  syncToggle("togglePinyin", "showPinyin", toggleTargets.togglePinyin);
  syncToggle("toggleRecitation", "showRecitation", "recitationSection");
  bindToolbarJumpButtons();
  bindSearchInputs();
  bindNoteNavigation();
  bindAnnotationTools();

  document.getElementById("downloadPdfButton").addEventListener("click", async () => {
    try {
      await handlePrimaryExport();
    } catch (error) {
      window.alert(error.message || "导出失败，请稍后重试。");
    }
  });
  document.getElementById("previewPdfButton").addEventListener("click", openPreviewDialog);
  document.getElementById("openReciteScrollButton").addEventListener("click", openReciteScrollPage);
  document.getElementById("favoriteArticleButton").addEventListener("click", toggleFavoriteArticle);
  document.getElementById("shareArticleButton").addEventListener("click", shareArticle);
  document.getElementById("closeDialogButton").addEventListener("click", () => {
    document.getElementById("pdfDialog").close();
  });
  document.getElementById("annotationHelpConfirmButton").addEventListener("click", () => {
    document.getElementById("annotationHelpDialog").close();
  });

  window.addEventListener("resize", scheduleDeferredRender);
  window.addEventListener("orientationchange", scheduleDeferredRender);
  window.addEventListener("pageshow", scheduleDeferredRender);
  window.visualViewport?.addEventListener("resize", scheduleDeferredRender);
  document.fonts?.ready?.then(() => {
    scheduleDeferredRender();
  });
  const initial = getInitialQuery();
  if (initial.title) {
    document.getElementById("searchTitle").value = initial.title;
    document.getElementById("searchAuthor").value = initial.author;
    window.requestAnimationFrame(() => {
      runSearch();
    });
    return;
  }
  document.getElementById("searchTitle").value = "岳阳楼记";
  document.getElementById("searchAuthor").value = "范仲淹";
  window.requestAnimationFrame(() => {
    runSearch();
  });
}

function bootstrap() {
  window.humanVerification.init({
    overlayId: "humanVerificationOverlay",
    checkboxId: "humanVerificationCheckbox",
    buttonId: "humanVerificationButton",
    messageId: "humanVerificationMessage",
    gateSelector: ".page-shell",
    onVerified: startReaderApp
  });
}

bootstrap();

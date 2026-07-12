const STORAGE_KEYS = {
  recent: "poem_recent_works_v1",
  favorites: "poem_favorites_v1",
  lastRecite: "poem_recite_last_v2"
};

const dailyPoems = [
  { title: "静夜思", author: "李白" },
  { title: "春晓", author: "孟浩然" },
  { title: "登鹳雀楼", author: "王之涣" },
  { title: "水调歌头", author: "苏轼" },
  { title: "岳阳楼记", author: "范仲淹" },
  { title: "爱莲说", author: "周敦颐" },
  { title: "陋室铭", author: "刘禹锡" }
];

function safeReadJson(key, fallback) {
  try {
    const value = window.localStorage.getItem(key);
    return value ? JSON.parse(value) : fallback;
  } catch (error) {
    console.warn(`Unable to read ${key}.`, error);
    return fallback;
  }
}

function buildReaderUrl(work) {
  const query = new URLSearchParams({
    title: work?.title || "",
    author: work?.author || ""
  });
  return `./reader.html?${query.toString()}`;
}

function buildReciteUrl(work) {
  const query = new URLSearchParams({
    title: work?.title || "",
    author: work?.author || ""
  });
  return `./recite-scroll.html?${query.toString()}`;
}

function goToReader(work = null) {
  const titleInput = document.getElementById("searchTitle");
  const authorInput = document.getElementById("searchAuthor");
  const title = (work?.title || titleInput.value).trim();
  const author = (work?.author ?? authorInput.value).trim();
  const message = document.getElementById("searchMessage");

  if (!title) {
    message.textContent = "请先输入作品题目。";
    titleInput.focus();
    return;
  }

  message.textContent = "";
  window.location.href = buildReaderUrl({ title, author });
}

function bindWorkButton(button, work, destination = "reader") {
  if (!button || !work?.title) return;
  button.disabled = false;
  button.addEventListener("click", () => {
    window.location.href = destination === "recite" ? buildReciteUrl(work) : buildReaderUrl(work);
  });
}

function renderPersonalLibrary() {
  const recents = safeReadJson(STORAGE_KEYS.recent, []);
  const favorites = safeReadJson(STORAGE_KEYS.favorites, []);
  const lastRecite = safeReadJson(STORAGE_KEYS.lastRecite, null);
  const recent = Array.isArray(recents) ? recents[0] : null;
  const favorite = Array.isArray(favorites) ? favorites[0] : null;

  if (recent?.title) {
    document.getElementById("recentTitle").textContent = recent.title;
    document.getElementById("recentMeta").textContent = `${recent.author || "作者未详"} · 最近阅读`;
    bindWorkButton(document.getElementById("recentButton"), recent);
  }

  if (favorite?.title) {
    document.getElementById("favoriteTitle").textContent = favorite.title;
    const count = Math.max(favorites.length, 1);
    document.getElementById("favoriteMeta").textContent = `${favorite.author || "作者未详"} · 共收藏 ${count} 篇`;
    bindWorkButton(document.getElementById("favoriteButton"), favorite);
  }

  if (lastRecite?.title) {
    const card = document.getElementById("continueReciteCard");
    const percent = Number.isFinite(Number(lastRecite.percent)) ? Math.max(0, Math.min(100, Math.round(Number(lastRecite.percent)))) : 0;
    card.hidden = false;
    document.getElementById("continueReciteTitle").textContent = lastRecite.title;
    document.getElementById("continueReciteMeta").textContent = `${lastRecite.author || "作者未详"} · 已完成 ${percent}%`;
    bindWorkButton(document.getElementById("continueReciteButton"), lastRecite, "recite");
  }
}

function getDailyPoem() {
  const today = new Date();
  const dayNumber = Math.floor(Date.UTC(today.getFullYear(), today.getMonth(), today.getDate()) / 86400000);
  return dailyPoems[Math.abs(dayNumber) % dailyPoems.length];
}

function bindEvents() {
  document.getElementById("searchButton").addEventListener("click", () => goToReader());
  ["searchTitle", "searchAuthor"].forEach((id) => {
    document.getElementById(id).addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        goToReader();
      }
    });
  });

  document.querySelectorAll(".quick-searches button[data-title]").forEach((button) => {
    button.addEventListener("click", () => {
      goToReader({
        title: button.dataset.title || "",
        author: button.dataset.author || ""
      });
    });
  });

  const dailyPoem = getDailyPoem();
  const dailyButton = document.getElementById("dailyPoemButton");
  dailyButton.textContent = `读今日一诗 · ${dailyPoem.title}`;
  dailyButton.addEventListener("click", () => goToReader(dailyPoem));
}

function init() {
  renderPersonalLibrary();
  window.humanVerification.init({
    overlayId: "humanVerificationOverlay",
    checkboxId: "humanVerificationCheckbox",
    buttonId: "humanVerificationButton",
    messageId: "humanVerificationMessage",
    gateSelector: ".home-page",
    onVerified: () => {
      bindEvents();
    }
  });
}

init();

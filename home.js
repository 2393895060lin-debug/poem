function goToReader() {
  const title = document.getElementById("searchTitle").value.trim();
  const author = document.getElementById("searchAuthor").value.trim();

  if (!title) {
    document.getElementById("searchTitle").focus();
    return;
  }

  const query = new URLSearchParams({ title, author });
  window.location.href = `./reader.html?${query.toString()}`;
}

function clearSearchFields() {
  document.getElementById("searchTitle").value = "";
  document.getElementById("searchAuthor").value = "";
}

function bindEvents() {
  document.getElementById("searchButton").addEventListener("click", goToReader);
  ["searchTitle", "searchAuthor"].forEach((id) => {
    document.getElementById(id).addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        goToReader();
      }
    });
  });

  window.addEventListener("pageshow", () => {
    clearSearchFields();
    document.getElementById("searchTitle").focus();
  });
}

function init() {
  clearSearchFields();
  bindEvents();
  document.getElementById("searchTitle").focus();
}

init();

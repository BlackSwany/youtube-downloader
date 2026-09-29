/**
 * Özel başlık çubuğu: küçült, büyüt/geri al, kapat ve çift tıkla büyütme.
 */
(function initWindowChrome() {
  const titlebar = document.getElementById("app-titlebar");
  if (!titlebar) return;

  document.documentElement.classList.add("desktop-chrome");

  const minimizeBtn = document.getElementById("titlebar-minimize");
  const maximizeBtn = document.getElementById("titlebar-maximize");
  const closeBtn = document.getElementById("titlebar-close");
  const dragRegion = titlebar.querySelector(".titlebar-drag");

  /**
   * pywebview JS köprüsünü güvenli şekilde çağırır.
   * @param {string} method
   * @returns {Promise<*>}
   */
  async function callDesktopApi(method) {
    const api = window.pywebview && window.pywebview.api;
    if (!api || typeof api[method] !== "function") {
      return null;
    }
    return api[method]();
  }

  /**
   * Büyütme ikonunu pencere durumuna göre günceller.
   * @param {boolean} maximized
   */
  function setMaximizedState(maximized) {
    titlebar.classList.toggle("is-maximized", Boolean(maximized));
    if (maximizeBtn) {
      maximizeBtn.setAttribute(
        "aria-label",
        maximized ? "Önceki boyuta dön" : "Tam ekran"
      );
    }
  }

  /**
   * Maximize / restore arasında geçer.
   */
  async function toggleMaximize() {
    const maximized = await callDesktopApi("toggle_maximize");
    if (typeof maximized === "boolean") {
      setMaximizedState(maximized);
      return;
    }
    titlebar.classList.toggle("is-maximized");
  }

  minimizeBtn?.addEventListener("click", (event) => {
    event.stopPropagation();
    callDesktopApi("minimize");
  });

  maximizeBtn?.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleMaximize();
  });

  closeBtn?.addEventListener("click", (event) => {
    event.stopPropagation();
    callDesktopApi("close");
  });

  dragRegion?.addEventListener("dblclick", (event) => {
    if (event.target.closest(".titlebar-controls")) return;
    toggleMaximize();
  });

  window.addEventListener("pywebviewready", async () => {
    const maximized = await callDesktopApi("is_maximized");
    if (typeof maximized === "boolean") {
      setMaximizedState(maximized);
    }
  });
})();

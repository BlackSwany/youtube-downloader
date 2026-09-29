/**
 * Timeline Runner: Chrome dino tarzı sonsuz koşu easter egg'i.
 * Yukarı ok ile açılır/zıplar, ESC veya çarpı ile kapanır.
 */
(function initTimelineRunner() {
  const overlay = document.getElementById("runner-overlay");
  const canvas = document.getElementById("runner-canvas");
  const closeBtn = document.getElementById("runner-close");
  if (!overlay || !canvas) return;

  const ctx = canvas.getContext("2d");
  const BEST_KEY = "atamation.timelineRunner.best";
  const LOGICAL = { w: 880, h: 260 };

  /** @type {{open: boolean, running: boolean, over: boolean, raf: number, last: number}} */
  const ui = {
    open: false,
    running: false,
    over: false,
    raf: 0,
    last: 0,
  };

  const world = createWorld();

  /**
   * Oyun durumunu üretir.
   * @returns {object}
   */
  function createWorld() {
    return {
      speed: 320,
      distance: 0,
      score: 0,
      best: Number(localStorage.getItem(BEST_KEY) || 0),
      gravity: 2100,
      groundY: 198,
      spawnIn: 0.9,
      player: {
        x: 72,
        y: 198,
        w: 28,
        h: 36,
        vy: 0,
        grounded: true,
      },
      obstacles: [],
      sparks: [],
    };
  }

  /**
   * Odak bir form alanındaysa easter egg tetiklenmez.
   * @param {EventTarget|null} target
   * @returns {boolean}
   */
  function isTypingTarget(target) {
    if (!(target instanceof HTMLElement)) return false;
    const tag = target.tagName;
    return (
      tag === "INPUT" ||
      tag === "TEXTAREA" ||
      tag === "SELECT" ||
      target.isContentEditable
    );
  }

  /**
   * Canvas boyutunu cihaz piksel oranına göre keskinleştirir.
   */
  function fitCanvas() {
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = LOGICAL.w * ratio;
    canvas.height = LOGICAL.h * ratio;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  }

  /**
   * Skoru ve rekoru kalıcı hale getirir.
   */
  function persistBest() {
    world.best = Math.max(world.best, Math.floor(world.score));
    localStorage.setItem(BEST_KEY, String(world.best));
  }

  /**
   * Yeni bir koşu turunu sıfırlar.
   */
  function resetRun() {
    const next = createWorld();
    next.best = world.best;
    Object.assign(world, next);
    ui.over = false;
    ui.running = true;
    ui.last = 0;
  }

  /**
   * Oyuncuyu zıplatır; oyun bittiyse yeniden başlatır.
   */
  function jump() {
    if (!ui.open) return;
    if (ui.over) {
      resetRun();
      return;
    }
    if (!ui.running) {
      resetRun();
    }
    if (world.player.grounded) {
      world.player.vy = -720;
      world.player.grounded = false;
    }
  }

  /**
   * Rastgele bir kesim işareti (engel) üretir.
   */
  function spawnObstacle() {
    const kind = Math.random();
    const tall = kind > 0.62;
    const twin = kind > 0.84;
    const height = tall ? 48 + Math.random() * 18 : 28 + Math.random() * 10;
    const width = tall ? 16 : 22;
    world.obstacles.push({
      x: LOGICAL.w + 16,
      y: world.groundY - height,
      w: width,
      h: height,
      hue: tall ? "#818cf8" : "#2dd4bf",
    });
    if (twin) {
      world.obstacles.push({
        x: LOGICAL.w + 42,
        y: world.groundY - 26,
        w: 18,
        h: 26,
        hue: "#22d3ee",
      });
    }
  }

  /**
   * Çarpışma: oyuncu ile dikdörtgen engel.
   * @param {{x:number,y:number,w:number,h:number}} a
   * @param {{x:number,y:number,w:number,h:number}} b
   * @returns {boolean}
   */
  function hits(a, b) {
    const pad = 3;
    return (
      a.x + pad < b.x + b.w &&
      a.x + a.w - pad > b.x &&
      a.y + pad < b.y + b.h &&
      a.y + a.h - pad > b.y
    );
  }

  /**
   * Bir kare simülasyonu ilerletir.
   * @param {number} dt
   */
  function step(dt) {
    world.speed = Math.min(560, world.speed + dt * 8);
    world.distance += world.speed * dt;
    world.score += dt * 12 * (world.speed / 320);
    world.spawnIn -= dt;

    if (world.spawnIn <= 0) {
      spawnObstacle();
      world.spawnIn = 0.72 + Math.random() * 0.7 - Math.min(0.28, world.speed / 2200);
    }

    const player = world.player;
    player.vy += world.gravity * dt;
    player.y += player.vy * dt;
    if (player.y >= world.groundY - player.h) {
      player.y = world.groundY - player.h;
      player.vy = 0;
      player.grounded = true;
    }

    world.obstacles.forEach((item) => {
      item.x -= world.speed * dt;
    });
    world.obstacles = world.obstacles.filter((item) => item.x + item.w > -20);

    if (world.obstacles.some((item) => hits(player, item))) {
      ui.over = true;
      ui.running = false;
      persistBest();
    }

    if (Math.random() < dt * 8) {
      world.sparks.push({
        x: LOGICAL.w + Math.random() * 40,
        y: 24 + Math.random() * 110,
        s: 0.6 + Math.random() * 1.4,
      });
    }
    world.sparks.forEach((spark) => {
      spark.x -= world.speed * dt * 0.28;
    });
    world.sparks = world.sparks.filter((spark) => spark.x > -8);
  }

  /**
   * Arka plan ızgarası ve timeline zemini çizer.
   */
  function drawBackdrop() {
    ctx.clearRect(0, 0, LOGICAL.w, LOGICAL.h);
    ctx.fillStyle = "#070b14";
    ctx.fillRect(0, 0, LOGICAL.w, LOGICAL.h);

    ctx.strokeStyle = "rgba(255,255,255,0.035)";
    ctx.lineWidth = 1;
    for (let x = 0; x < LOGICAL.w; x += 48) {
      const shift = (world.distance * 0.15) % 48;
      ctx.beginPath();
      ctx.moveTo(x - shift, 0);
      ctx.lineTo(x - shift, LOGICAL.h);
      ctx.stroke();
    }

    world.sparks.forEach((spark) => {
      ctx.fillStyle = "rgba(34,211,238,0.35)";
      ctx.fillRect(spark.x, spark.y, spark.s * 6, 1);
    });

    ctx.fillStyle = "#0b1020";
    ctx.fillRect(0, world.groundY, LOGICAL.w, LOGICAL.h - world.groundY);

    ctx.fillStyle = "#22d3ee";
    ctx.fillRect(0, world.groundY, LOGICAL.w, 2);

    const sprocket = (world.distance * 0.45) % 18;
    for (let x = -18; x < LOGICAL.w + 18; x += 18) {
      ctx.fillStyle = "#06080f";
      ctx.fillRect(x - sprocket, world.groundY + 8, 7, 9);
    }
  }

  /**
   * Oyuncu kapsülünü ve kesim işaretlerini çizer.
   */
  function drawActors() {
    world.obstacles.forEach((item) => {
      ctx.fillStyle = item.hue;
      ctx.fillRect(item.x, item.y, item.w, item.h);
      ctx.fillStyle = "rgba(6,8,15,0.35)";
      ctx.fillRect(item.x + 3, item.y + 4, 2, item.h - 8);
    });

    const p = world.player;
    ctx.fillStyle = "#22d3ee";
    roundRect(p.x, p.y, p.w, p.h, 7);
    ctx.fill();
    ctx.fillStyle = "#06080f";
    ctx.font = "700 14px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("A", p.x + p.w / 2, p.y + p.h / 2 + 1);

    if (!p.grounded) {
      ctx.strokeStyle = "rgba(34,211,238,0.35)";
      ctx.beginPath();
      ctx.moveTo(p.x - 10, p.y + p.h - 4);
      ctx.lineTo(p.x - 22, p.y + p.h + 8);
      ctx.stroke();
    }
  }

  /**
   * Skor katmanını ve durum metinlerini çizer.
   */
  function drawHud() {
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    ctx.fillStyle = "#9aabc7";
    ctx.font = "500 12px 'IBM Plex Mono', monospace";
    ctx.fillText(`SCORE ${String(Math.floor(world.score)).padStart(5, "0")}`, 18, 16);
    ctx.textAlign = "right";
    ctx.fillText(`BEST ${String(Math.floor(world.best)).padStart(5, "0")}`, LOGICAL.w - 18, 16);

    ctx.textAlign = "center";
    if (!ui.running && !ui.over) {
      ctx.fillStyle = "#e8eef8";
      ctx.font = "600 22px Inter, sans-serif";
      ctx.fillText("TIMELINE RUNNER", LOGICAL.w / 2, 88);
      ctx.fillStyle = "#22d3ee";
      ctx.font = "500 12px 'IBM Plex Mono', monospace";
      ctx.fillText("YUKARI OK İLE KESİM İŞARETLERİNİN ÜZERİNDEN ATLA", LOGICAL.w / 2, 122);
    }

    if (ui.over) {
      ctx.fillStyle = "rgba(6,8,15,0.55)";
      ctx.fillRect(0, 70, LOGICAL.w, 88);
      ctx.fillStyle = "#f97316";
      ctx.font = "700 20px Inter, sans-serif";
      ctx.fillText("SIGNAL LOST", LOGICAL.w / 2, 88);
      ctx.fillStyle = "#e8eef8";
      ctx.font = "500 12px 'IBM Plex Mono', monospace";
      ctx.fillText("YUKARI OK · YENİDEN KOŞ", LOGICAL.w / 2, 122);
    }
  }

  /**
   * Yuvarlatılmış dikdörtgen yolu çizer.
   * @param {number} x
   * @param {number} y
   * @param {number} w
   * @param {number} h
   * @param {number} r
   */
  function roundRect(x, y, w, h, r) {
    const radius = Math.min(r, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.arcTo(x + w, y, x + w, y + h, radius);
    ctx.arcTo(x + w, y + h, x, y + h, radius);
    ctx.arcTo(x, y + h, x, y, radius);
    ctx.arcTo(x, y, x + w, y, radius);
    ctx.closePath();
  }

  /**
   * Ana çizim döngüsü.
   * @param {number} stamp
   */
  function loop(stamp) {
    if (!ui.open) return;
    const dt = ui.last ? Math.min(0.032, (stamp - ui.last) / 1000) : 0.016;
    ui.last = stamp;
    if (ui.running) step(dt);
    drawBackdrop();
    drawActors();
    drawHud();
    ui.raf = requestAnimationFrame(loop);
  }

  /**
   * Overlay'i açar ve bekleme karesini çizer.
   */
  function openGame() {
    if (ui.open) return;
    ui.open = true;
    ui.over = false;
    ui.running = false;
    ui.last = 0;
    Object.assign(world, createWorld());
    world.best = Number(localStorage.getItem(BEST_KEY) || 0);
    overlay.classList.remove("hidden");
    overlay.classList.add("is-open");
    overlay.setAttribute("aria-hidden", "false");
    requestAnimationFrame(() => overlay.classList.add("is-visible"));
    fitCanvas();
    cancelAnimationFrame(ui.raf);
    ui.raf = requestAnimationFrame(loop);
  }

  /**
   * Overlay'i kapatır ve ana ekrana döner.
   */
  function closeGame() {
    if (!ui.open) return;
    ui.open = false;
    ui.running = false;
    cancelAnimationFrame(ui.raf);
    persistBest();
    overlay.classList.remove("is-visible");
    window.setTimeout(() => {
      if (!ui.open) {
        overlay.classList.remove("is-open");
        overlay.classList.add("hidden");
        overlay.setAttribute("aria-hidden", "true");
      }
    }, 220);
  }

  closeBtn?.addEventListener("click", closeGame);

  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) closeGame();
  });

  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && ui.open) {
      event.preventDefault();
      closeGame();
      return;
    }

    if (event.key !== "ArrowUp" && !(ui.open && event.code === "Space")) {
      return;
    }
    if (!ui.open && isTypingTarget(event.target)) {
      return;
    }

    event.preventDefault();
    if (!ui.open) {
      openGame();
      return;
    }
    jump();
  });

  window.addEventListener("resize", () => {
    if (ui.open) fitCanvas();
  });
})();

/* Montage Studio - interface */
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const api = async (url, body) => {
  const r = await fetch(url, body === undefined ? {} :
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const ct = r.headers.get("Content-Type") || "";
  if (!ct.includes("json")) return r;
  const j = await r.json();
  if (j && j.error) throw new Error(j.error);
  return j;
};
let MODES = { cup: "Cup", ranked_reload: "Ranked Reload", ranked_br: "Ranked BR", box_arena: "Arène Box Fight",
  creative_1v1: "Créatif 1v1" };
const unit = (mode) => mode === "cup" ? "Partie" : (mode === "box_arena" || mode === "creative_1v1") ? "Match" : "Game";
const fmt = (t, dec = true) => {
  t = Math.max(0, t || 0);
  const h = Math.floor(t / 3600), m = Math.floor(t % 3600 / 60), s = t % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:` +
    (dec ? s.toFixed(1).padStart(4, "0") : String(Math.floor(s)).padStart(2, "0"));
};
const parseTc = s => String(s).split(":").reduce((a, v) => a * 60 + parseFloat(v || 0), 0);
const fmtSize = b => b > 1e9 ? (b / 1e9).toFixed(1) + " Go" : (b / 1e6).toFixed(0) + " Mo";
const status = (m) => { $("#status-msg").textContent = m; };

const S = {
  lib: [], cur: null, proj: null, plan: null, sel: null, pxs: 0.2, music: [], settings: null,
  undo: [], thTimes: [], thFiles: [], thSel: null, jobs: [], dirty: false,
};

/* ================= bibliothèque ================= */
async function loadLibrary() {
  status("Chargement de la bibliothèque…");
  S.lib = await api("/api/library");
  renderLibrary();
  status(`${S.lib.length} rec(s) trouvé(s)`);
}

function renderLibrary() {
  const q = $("#lib-search").value.toLowerCase(), f = $("#lib-filter").value;
  const el = $("#library");
  el.innerHTML = "";
  for (const v of S.lib) {
    if (q && !v.name.toLowerCase().includes(q)) continue;
    if (f === "todo" && v.outputs.length) continue;
    if (f === "done" && !v.outputs.length) continue;
    const it = document.createElement("div");
    it.className = "lib-item" + (S.cur && S.cur.path === v.path ? " sel" : "");
    it.innerHTML = `<img loading="lazy" src="/api/thumb?path=${encodeURIComponent(v.path)}">
      <div><div class="lib-name" title="${v.name}">${v.stem}</div>
      <div class="lib-meta">${fmt(v.duration, false)} • ${fmtSize(v.size)}</div>
      <div class="chips">
        <select title="Mode">${Object.entries(MODES).map(([k, l]) =>
          `<option value="${k}" ${k === v.mode ? "selected" : ""}>${l}</option>`).join("")}</select>
        ${v.outputs.length ? '<span class="chip ok">PRÉ-UPLOAD</span>' : ""}
        ${v.scanned ? '<span class="chip scan">analysé</span>' : ""}
        ${v.archived ? '<span class="chip raw">brut</span>' : ""}
      </div></div>`;
    it.addEventListener("click", e => { if (e.target.tagName !== "SELECT") openProject(v); });
    it.querySelector("select").addEventListener("change", async e => {
      v.mode = e.target.value;
      await api("/api/mode", { path: v.path, mode: v.mode });
      if (S.cur && S.cur.path === v.path) openProject(v);
    });
    el.appendChild(it);
  }
}

/* ================= projet ================= */
async function openProject(v) {
  if (S.dirty) await savePlan();
  S.cur = { path: v.path, mode: v.mode, name: v.stem };
  S.sel = null; S.undo = []; S.thFiles = []; S.thTimes = [];
  renderLibrary();
  $("#project-title").textContent = `${v.stem} — ${MODES[v.mode]}`;
  status("Ouverture du projet…");
  S.proj = await api(`/api/project?path=${encodeURIComponent(v.path)}&mode=${v.mode}`);
  S.plan = S.proj.plan || null;
  setupPlayer();
  fitZoom();
  renderAll();
  renderThumbGrid();
  status(S.proj.scanned ? "Projet ouvert" : "Ce rec n'est pas encore analysé");
}

function setupPlayer() {
  const p = $("#player"), msg = $("#stage-msg");
  msg.classList.add("hidden");
  const src = S.proj.proxy ? null : `/file?path=${encodeURIComponent(S.proj.path)}`;
  const useProxy = async () => {
    const r = await api(`/api/proxy_url?path=${encodeURIComponent(S.proj.path)}&mode=${S.cur.mode}`);
    if (r.url) { p.src = r.url; return true; }
    return false;
  };
  p.onerror = async () => {
    if (await useProxy()) return;
    msg.innerHTML = `<div>Ton navigateur ne sait pas lire ce rec directement (HEVC 4K).<br>
      <button class="btn primary" data-cmd="proxy">Créer un aperçu léger (2-5 min)</button>
      <div class="muted" style="margin-top:8px">Le montage final utilise toujours la vidéo originale.</div></div>`;
    msg.classList.remove("hidden");
  };
  if (src) p.src = src; else useProxy();
  if (!S.proj.scanned) {
    msg.innerHTML = `<div><b>Rec pas encore analysé</b><br><span class="muted">Le scan repère les games, les kills,
      les points / le rang (quelques minutes sur ta carte graphique).</span><br>
      <button class="btn primary" data-cmd="scan">Analyser ce rec</button>
      <button class="btn" data-cmd="all">Analyser + rendre directement</button></div>`;
    msg.classList.remove("hidden");
  }
}

function pushUndo() {
  S.undo.push(JSON.stringify(S.plan));
  if (S.undo.length > 60) S.undo.shift();
}

let saveTimer = null;
function changed() {
  S.dirty = true;
  $("#save-state").textContent = "● modifications non enregistrées";
  clearTimeout(saveTimer);
  saveTimer = setTimeout(savePlan, 900);
  renderAll();
}

async function savePlan() {
  if (!S.plan || !S.cur) return;
  clearTimeout(saveTimer);
  await api("/api/plan/save", { path: S.cur.path, mode: S.cur.mode, plan: S.plan });
  S.dirty = false;
  $("#save-state").textContent = "✓ enregistré";
}

/* ================= timeline ================= */
const tlDuration = () => (S.proj && S.proj.duration) || 600;

function fitZoom() {
  const w = $("#tl-scroll").clientWidth - 20;
  S.minPxs = w / tlDuration();
  S.pxs = S.minPxs;
  $("#zoom").value = 0;
}
function setZoom(v) {
  v = Math.max(0, Math.min(100, v));
  $("#zoom").value = v;
  const center = (($("#tl-scroll").scrollLeft + $("#tl-scroll").clientWidth / 2) / S.pxs);
  S.pxs = S.minPxs * Math.pow(400 / S.minPxs / 10, v / 100) ;
  if (S.pxs < S.minPxs) S.pxs = S.minPxs;
  renderTimeline();
  $("#tl-scroll").scrollLeft = center * S.pxs - $("#tl-scroll").clientWidth / 2;
}

function gameSpan(g) {
  const tg = (S.proj.timeline.games || []).find(x => x.game === g.game);
  if (tg) return [tg.start, tg.end];
  const segs = g.segments;
  return [segs[0].start, segs[segs.length - 1].end];
}

function renderTimeline() {
  const W = tlDuration() * S.pxs;
  $("#tl-content").style.width = W + "px";
  // règle
  const ruler = $("#ruler");
  ruler.innerHTML = "";
  const steps = [1, 5, 10, 30, 60, 120, 300, 600, 900, 1800];
  const major = steps.find(s => s * S.pxs > 90) || 3600;
  for (let t = 0; t <= tlDuration(); t += major) {
    const d = document.createElement("div");
    d.className = "tick"; d.style.left = t * S.pxs + "px"; d.textContent = fmt(t, false);
    ruler.appendChild(d);
    for (let k = 1; k < 5; k++) {
      const m = document.createElement("div");
      m.className = "tick minor"; m.style.left = (t + k * major / 5) * S.pxs + "px";
      ruler.appendChild(m);
    }
  }
  const tg = $("#trk-games"), ts = $("#trk-segs"), te = $("#trk-events");
  for (const t of [tg, ts, te]) $$(".blk,.ev", t).forEach(x => x.remove());
  if (!S.plan || !S.proj.timeline) return updatePlayhead();
  // games + segments
  S.plan.games.forEach((g, gi) => {
    const [a, b] = gameSpan(g);
    const gb = document.createElement("div");
    gb.className = "blk game" + (S.sel && S.sel.gi === gi && S.sel.type === "game" ? " sel" : "") + (g.disabled ? " off" : "");
    gb.style.left = a * S.pxs + "px"; gb.style.width = Math.max(4, (b - a) * S.pxs) + "px";
    const kills = ((S.proj.timeline.games || []).find(x => x.game === g.game) || { kills: [] }).kills.length;
    const tgm = (S.proj.timeline.games || []).find(x => x.game === g.game) || {};
    gb.textContent = tgm.score ? `${unit(S.plan.mode)} ${g.game} • ${tgm.score[0]}-${tgm.score[1]}`
      : `${unit(S.plan.mode)} ${g.game} • ${kills} kill${kills > 1 ? "s" : ""}`;
    gb.title = "Clic : propriétés de la game et de son carton";
    gb.onclick = e => { e.stopPropagation(); select({ type: "game", gi }); seek(a); };
    tg.appendChild(gb);
    // marqueur du carton
    const cb = document.createElement("div");
    cb.className = "blk card"; cb.style.left = (g.segments[0] ? g.segments[0].start : a) * S.pxs - 16 + "px";
    cb.style.width = "14px"; cb.title = "Carton avant la game"; cb.textContent = "▣";
    cb.onclick = e => { e.stopPropagation(); select({ type: "game", gi }); setView("card"); };
    ts.appendChild(cb);
    g.segments.forEach((s, si) => {
      const sb = document.createElement("div");
      sb.className = "blk seg" + (S.sel && S.sel.type === "seg" && S.sel.gi === gi && S.sel.si === si ? " sel" : "");
      sb.style.left = s.start * S.pxs + "px"; sb.style.width = Math.max(3, (s.end - s.start) * S.pxs) + "px";
      sb.title = `${fmt(s.start)} → ${fmt(s.end)} (${((s.end - s.start) / 60).toFixed(1)} min)`;
      sb.innerHTML = `<span class="h l"></span><span class="h r"></span>`;
      if ((s.end - s.start) * S.pxs > 70) sb.insertAdjacentText("beforeend", ` ${((s.end - s.start) / 60).toFixed(1)} min`);
      sb.onmousedown = e => startDrag(e, gi, si);
      ts.appendChild(sb);
    });
  });
  // événements
  for (const g of S.proj.timeline.games || []) {
    for (const k of g.kills || []) addEv(te, k.t, "kill", `Kill ${k.tc || ""}`);
    for (const t of g.tops || []) addEv(te, t.t, "top", `Palier : ${t.reached}`);
  }
  updateStats();
  updatePlayhead();
}

function addEv(track, t, cls, title) {
  const e = document.createElement("div");
  e.className = "ev " + cls; e.style.left = t * S.pxs + "px"; e.title = title;
  e.onclick = ev => { ev.stopPropagation(); seek(t - 3); };
  track.appendChild(e);
}

function updateStats() {
  if (!S.plan) return $("#tl-stats").textContent = "";
  const card = (S.settings && S.settings.render.card_duration_s) || 4;
  let kept = 0, n = 0;
  for (const g of S.plan.games) if (!g.disabled) { n++; for (const s of g.segments) kept += s.end - s.start; }
  const total = kept + card * (n + (S.plan.final ? 1 : 0));
  $("#tl-stats").textContent = `${n} game(s) • durée du montage : ${fmt(total, false)} • rec : ${fmt(tlDuration(), false)}`;
}

function startDrag(e, gi, si) {
  e.preventDefault(); e.stopPropagation();
  const seg = S.plan.games[gi].segments[si];
  const edge = e.target.classList.contains("l") ? "start" : e.target.classList.contains("r") ? "end" : null;
  select({ type: "seg", gi, si });
  if (!edge) { seek(seg.start); return; }
  pushUndo();
  const segs = S.plan.games[gi].segments;
  const lo = si > 0 ? segs[si - 1].end + 0.5 : 0, hi = si < segs.length - 1 ? segs[si + 1].start - 0.5 : tlDuration();
  const x0 = e.clientX, v0 = seg[edge];
  const move = ev => {
    let v = v0 + (ev.clientX - x0) / S.pxs;
    v = edge === "start" ? Math.min(Math.max(v, lo), seg.end - 1) : Math.max(Math.min(v, hi), seg.start + 1);
    seg[edge] = Math.round(v * 10) / 10;
    seek(seg[edge]);
    renderTimeline();
  };
  const up = () => { document.removeEventListener("mousemove", move); document.removeEventListener("mouseup", up); changed(); };
  document.addEventListener("mousemove", move);
  document.addEventListener("mouseup", up);
}

/* ================= lecteur ================= */
const player = () => $("#player");
function seek(t) { const p = player(); if (p.readyState >= 1 || p.src) p.currentTime = Math.max(0, t); updatePlayhead(t); }
function updatePlayhead(t) {
  t = t === undefined ? player().currentTime || 0 : t;
  $("#playhead").style.left = t * S.pxs + "px";
  $("#tc").textContent = fmt(t);
  const info = where(t);
  $("#tc-info").textContent = info;
}
function where(t) {
  if (!S.plan) return "";
  for (const g of S.plan.games) {
    for (const s of g.segments) if (t >= s.start && t <= s.end) return `gardé • ${unit(S.plan.mode).toLowerCase()} ${g.game}`;
    const [a, b] = gameSpan(g);
    if (t >= a && t <= b) return `coupé • ${unit(S.plan.mode).toLowerCase()} ${g.game}`;
  }
  return "hors game (coupé)";
}
function allSegs() {
  const out = [];
  if (!S.plan) return out;
  S.plan.games.forEach((g, gi) => { if (!g.disabled) g.segments.forEach((s, si) => out.push({ ...s, gi, si })); });
  return out.sort((a, b) => a.start - b.start);
}
function onTime() {
  const p = player(), t = p.currentTime;
  updatePlayhead(t);
  if ($("#play-kept").checked && !p.paused) {
    const segs = allSegs();
    if (!segs.some(s => t >= s.start && t < s.end)) {
      const nx = segs.find(s => s.start > t);
      if (nx) p.currentTime = nx.start; else p.pause();
    }
  }
  const sc = $("#tl-scroll"), x = t * S.pxs;
  if (!p.paused && (x < sc.scrollLeft || x > sc.scrollLeft + sc.clientWidth - 40)) sc.scrollLeft = x - 60;
}

/* ================= sélection / inspecteur ================= */
function select(sel) {
  S.sel = sel;
  renderTimeline();
  renderProps();
  if (sel && $("#view-card").classList.contains("active")) refreshCard();
}

function field(label, html) { return `<div class="field"><label>${label}</label>${html}</div>`; }
function inp(key, val, type = "text", extra = "") {
  return `<input data-k="${key}" type="${type}" value="${val === null || val === undefined ? "" : val}" ${extra}>`;
}
function musicSelect(cur) {
  const opts = ['<option value="auto">Auto (aléatoire)</option>', `<option value="aucune" ${cur === "aucune" ? "selected" : ""}>Aucune musique</option>`]
    .concat(S.music.map(m => `<option ${m.name === cur ? "selected" : ""}>${m.name}</option>`));
  return `<div class="music-row"><select data-k="music">${opts.join("")}</select>
    <button class="icon-btn" data-cmd="music-play" title="Écouter">▶</button></div>`;
}

function renderProps() {
  const el = $("#tab-props");
  if (!S.proj) { el.innerHTML = '<p class="muted pad">Ouvre un rec dans la bibliothèque.</p>'; return; }
  if (!S.plan) {
    el.innerHTML = `<div class="insp"><h3>${S.cur.name}</h3><p class="muted">Pas encore analysé.</p>
      <button class="btn primary" data-cmd="scan">Analyser ce rec</button></div>`;
    return;
  }
  const sel = S.sel;
  if (!sel || (sel.type !== "game" && sel.type !== "seg" && sel.type !== "final")) {
    const fin = S.plan.final;
    el.innerHTML = `<div class="insp"><h3>Projet <span class="muted">${MODES[S.plan.mode]}</span></h3>
      <div class="kv"><span>Games</span><b>${S.plan.games.length}</b></div>
      <div class="kv"><span>Kills détectés</span><b>${(S.proj.timeline.games || []).reduce((a, g) => a + g.kills.length, 0)}</b></div>
      <div class="kv"><span>Montage modifié à la main</span><b>${S.plan.user_edited ? "oui" : "non"}</b></div>
      <h4>Aide</h4><p class="muted">Clique une game (bleu) pour son carton et sa musique, un segment (vert) pour ajuster
      ses bords à la souris. <b>S</b> coupe au curseur, <b>Suppr</b> retire un segment, <b>A</b> ajoute 30 s au curseur.</p>
      ${fin ? `<button class="btn" data-cmd="sel-final">Carton de fin…</button>` : ""}</div>`;
    return;
  }
  if (sel.type === "final") return renderFinalProps(el);
  const g = S.plan.games[sel.gi], c = g.card;
  let cardFields = "";
  if (c.type === "cup") {
    cardFields = field("N° de partie", inp("card.partie", c.partie, "number")) +
      field("Parties dans la cup", inp("card.cup_games", c.cup_games, "number")) +
      field("Points avant", inp("card.points", c.points, "number")) +
      (c.prev ? field("Pts gagnés (préc.)", inp("card.prev.gained", c.prev.gained, "number")) +
        field("Kills (préc.)", inp("card.prev.kills", c.prev.kills, "number")) : "");
  } else if (c.type === "box") {
    const r = c.rank || {}, sc = (c.prev && c.prev.score) || [null, null];
    cardFields = (c.prev ? field("Score match préc. (moi)", inp("card.prev.score.0", sc[0], "number")) +
        field("Score match préc. (adv.)", inp("card.prev.score.1", sc[1], "number")) +
        field("ELO match préc. (%)", inp("card.prev.gain", c.prev.gain, "number")) : "") +
      (S.plan.mode === "box_arena" ? field("Rang affiché", inp("card.rank.name", r.name, "text", 'placeholder="ex : PLATINE II"')) +
        field("Progression %", inp("card.rank.pct", r.pct, "number")) : "");
  } else {
    const r = c.rank || {};
    cardFields = field("Rang affiché", inp("card.rank.name", r.name, "text", 'placeholder="ex : DIAMANT II"')) +
      field("Progression %", inp("card.rank.pct", r.pct, "number")) +
      (c.prev ? field("ELO game préc. (%)", inp("card.prev.gain", c.prev.gain, "number")) +
        field("Kills game préc.", inp("card.prev.kills", c.prev.kills, "number")) : "");
  }
  const segs = g.segments.map((s, si) => `<div class="seg-row ${sel.type === "seg" && sel.si === si ? "sel" : ""}" data-si="${si}">
      <input data-seg="start" value="${fmt(s.start)}"><input data-seg="end" value="${fmt(s.end)}">
      <span class="muted">${((s.end - s.start) / 60).toFixed(1)}m</span>
      <button class="icon-btn" data-cmd="seg-del" title="Supprimer">✕</button></div>`).join("");
  el.innerHTML = `<div class="insp">
    <h3>${unit(S.plan.mode)} ${g.game}
      <label class="chk"><input type="checkbox" data-k="enabled" ${g.disabled ? "" : "checked"}> incluse</label></h3>
    <h4>Carton</h4>${cardFields}
    <button class="btn" data-cmd="view-card" style="margin-top:6px">Voir le carton</button>
    <h4>Musique du carton</h4>${musicSelect(c.music)}
    <h4>Segments gardés</h4>${segs || '<p class="muted">Aucun segment</p>'}
    <div style="display:flex;gap:6px;margin-top:6px">
      <button class="btn" data-cmd="add">+ Segment au curseur</button>
      <button class="btn" data-cmd="game-full">Garder toute la game</button></div>
  </div>`;
  bindProps(el, g);
}

function renderFinalProps(el) {
  const f = S.plan.final;
  let fields = "";
  if (f.type === "cup") {
    fields = field("Points finaux", inp("final.points", f.points, "number")) + field("Parties jouées", inp("final.parties", f.parties, "number"));
  } else if (f.type === "box") {
    fields = field("Victoires", inp("final.wins", f.wins, "number")) + field("Défaites", inp("final.losses", f.losses, "number")) +
      field("Manches gagnées", inp("final.rounds.0", (f.rounds || [])[0], "number")) +
      field("Manches perdues", inp("final.rounds.1", (f.rounds || [])[1], "number")) +
      (S.plan.mode === "box_arena" ? field("ELO session (%)", inp("final.session_gain", f.session_gain, "number")) +
        field("Rang d'arrivée", inp("final.rank_end.name", (f.rank_end || {}).name)) +
        field("Progression finale %", inp("final.rank_end.pct", (f.rank_end || {}).pct, "number")) : "");
  } else {
    fields = field("ELO session (%)", inp("final.session_gain", f.session_gain, "number")) +
      field("Rang de départ", inp("final.rank_start.name", (f.rank_start || {}).name)) +
      field("Rang d'arrivée", inp("final.rank_end.name", (f.rank_end || {}).name)) +
      field("Progression finale %", inp("final.rank_end.pct", (f.rank_end || {}).pct, "number"));
  }
  el.innerHTML = `<div class="insp"><h3>Carton de fin</h3>${fields}
    <h4>Musique (outro)</h4>${musicSelect(f.music)}
    <button class="btn" data-cmd="view-card" style="margin-top:8px">Voir le carton</button></div>`;
  bindProps(el, null);
}

function setPath(obj, path, val) {
  const ks = path.split(".");
  let o = obj;
  ks.slice(0, -1).forEach((k, i) => {
    if (o[k] === null || o[k] === undefined) o[k] = /^\d+$/.test(ks[i + 1]) ? [] : {};
    o = o[k];
  });
  o[ks[ks.length - 1]] = val;
}

function bindProps(el, g) {
  $$("input[data-k],select[data-k]", el).forEach(i => i.addEventListener("change", () => {
    pushUndo();
    const k = i.dataset.k;
    let v = i.type === "number" ? (i.value === "" ? null : Number(i.value)) : i.value;
    if (i.type === "checkbox") v = i.checked;
    if (k === "enabled") { g.disabled = !v; }
    else if (k === "music") { (g ? g.card : S.plan.final).music = v; }
    else if (k.startsWith("final.")) { setPath(S.plan.final, k.slice(6), v); }
    else if (k.startsWith("card.")) { setPath(g.card, k.slice(5), v); }
    changed();
    refreshCard();
  }));
  $$(".seg-row", el).forEach(row => {
    const si = +row.dataset.si;
    $$("input[data-seg]", row).forEach(i => i.addEventListener("change", () => {
      pushUndo();
      const s = g.segments[si], v = parseTc(i.value);
      if (!isNaN(v)) s[i.dataset.seg] = v;
      if (s.end <= s.start) s.end = s.start + 1;
      g.segments.sort((a, b) => a.start - b.start);
      changed();
    }));
    row.addEventListener("click", e => { if (e.target.tagName === "DIV" || e.target.tagName === "SPAN") { S.sel = { type: "seg", gi: S.sel.gi, si }; seek(g.segments[si].start); renderProps(); renderTimeline(); } });
  });
}

/* ================= carton ================= */
let cardTimer = null;
function refreshCard() {
  clearTimeout(cardTimer);
  cardTimer = setTimeout(async () => {
    if (!S.plan || !S.sel) return;
    const final = S.sel.type === "final";
    const card = final ? S.plan.final : S.plan.games[S.sel.gi].card;
    if (!card) return;
    const r = await fetch("/api/card", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ card, final }) });
    const b = await r.blob();
    $("#card-img").src = URL.createObjectURL(b);
    $("#card-msg").classList.add("hidden");
  }, 250);
}

/* ================= miniatures ================= */
function renderThumbGrid() {
  const g = $("#th-grid");
  $("#th-times").textContent = S.thTimes.length ? S.thTimes.map(t => fmt(t, false)).join(", ") : "meilleurs fights (auto)";
  g.innerHTML = S.thFiles.map((f, i) => `<figure data-i="${i}" class="${S.thSel === i ? "sel" : ""}">
    <img src="${f.url}"><figcaption>Variante ${i + 1} — ${f.name.replace(/miniature_\d_|\.jpg/g, "")}</figcaption></figure>`).join("");
  $$("figure", g).forEach(fg => fg.onclick = () => { S.thSel = +fg.dataset.i; $("#th-export").disabled = false; renderThumbGrid(); });
}
async function genThumbs() {
  if (!S.proj || !S.proj.scanned) return status("Analyse le rec d'abord");
  if (S.dirty) await savePlan();
  status("Génération des miniatures…");
  $("#th-grid").innerHTML = '<p class="muted pad">Génération en cours…</p>';
  try {
    const r = await api("/api/thumbnails", { path: S.cur.path, mode: S.cur.mode, main: $("#th-main").value,
      sub: $("#th-sub").value, times: S.thTimes });
    S.thFiles = r.files.map(f => ({ ...f, path: r.dir + (r.dir.includes("\\") ? "\\" : "/") + f.name }));
    S.thSel = null; $("#th-export").disabled = true;
    if (!$("#th-main").value) $("#th-main").placeholder = `auto : ${r.main}`;
    if (!$("#th-sub").value) $("#th-sub").placeholder = `auto : ${r.sub}`;
    renderThumbGrid();
    status("4 miniatures générées — clique celle que tu préfères puis « Exporter »");
  } catch (e) { status("Erreur miniatures : " + e.message); $("#th-grid").innerHTML = ""; }
}

/* ================= rendu / réglages ================= */
async function loadSettings() { S.settings = await api("/api/settings"); renderRenderTab(); }
function renderRenderTab() {
  const r = S.settings.render, e = S.settings.edit;
  const res = r.height >= 2160 ? "2160" : r.height >= 1440 ? "1440" : "1080";
  $("#tab-render").innerHTML = `<div class="insp">
    <h3>Rendu</h3>
    ${field("Résolution", `<select data-s="res"><option value="1080" ${res === "1080" ? "selected" : ""}>1080p</option>
      <option value="1440" ${res === "1440" ? "selected" : ""}>1440p (2K)</option><option value="2160" ${res === "2160" ? "selected" : ""}>2160p (4K)</option></select>`)}
    ${field("Images / s", `<select data-s="render.fps"><option ${r.fps == 60 ? "selected" : ""}>60</option><option ${r.fps == 30 ? "selected" : ""}>30</option></select>`)}
    ${field("Débit vidéo", `<input data-s="render.bitrate" value="${r.bitrate}">`)}
    ${field("Encodages parallèles", `<input data-s="render.parallel_encodes" type="number" min="1" max="3" value="${r.parallel_encodes}">`)}
    <h4>Musique</h4>
    ${field("Volume (calme)", `<input data-s="render.music_volume" type="range" min="0" max="1" step="0.05" value="${r.music_volume}">`)}
    ${field("Baisse sous ta voix", `<input data-s="render.duck_max_db" type="range" min="0" max="40" step="1" value="${r.duck_max_db}">`)}
    ${field("Débord sur la game", `<input data-s="render.music_tail_s" type="number" value="${r.music_tail_s}"> `)}
    ${field("Fin de zone (Cup)", `<label class="switch"><input data-s="render.endgame_music" type="checkbox" ${r.endgame_music !== false ? "checked" : ""}><i></i><span>musique stressante</span></label>`)}
    ${field("Durée fin de zone (s)", `<input data-s="render.endgame_music_s" type="number" min="30" max="300" value="${r.endgame_music_s ?? 120}">`)}
    ${field("Volume fin de zone", `<input data-s="render.endgame_volume" type="range" min="0" max="1" step="0.05" value="${r.endgame_volume ?? 0.35}">`)}
    <h4>Montage auto</h4>
    ${field("Bus coupé (s)", `<input data-s="edit.bus_skip_s" type="number" value="${e.bus_skip_s}">`)}
    ${field("Creux coupé après (s)", `<input data-s="edit.dead_gap_s" type="number" value="${e.dead_gap_s}">`)}
    ${field("Durée des cartons", `<input data-s="render.card_duration_s" type="number" step="0.5" value="${r.card_duration_s}">`)}
    <p class="muted">Les réglages « montage auto » s'appliquent au prochain « Réinitialiser le montage auto ».</p>
    <div style="display:flex;gap:6px;margin-top:10px">
      <button class="btn primary" data-cmd="render">▶ Lancer le rendu</button>
      <button class="btn" data-cmd="open-videos">Dossier Vidéos</button></div>
  </div>`;
  $$("[data-s]", $("#tab-render")).forEach(i => i.addEventListener("change", async () => {
    const k = i.dataset.s, body = { render: {}, edit: {} };
    if (k === "res") {
      const h = +i.value; body.render.height = h; body.render.width = Math.round(h * 16 / 9);
      body.render.bitrate = { 1080: "16M", 1440: "24M", 2160: "45M" }[h];
      body.render.maxrate = { 1080: "24M", 1440: "40M", 2160: "60M" }[h];
    } else {
      const [sec, key] = k.split(".");
      body[sec][key] = i.type === "checkbox" ? i.checked
        : i.type === "range" || i.type === "number" || key === "fps" ? Number(i.value) : i.value;
    }
    S.settings = await api("/api/settings", body);
    renderRenderTab(); updateStats();
    status("Réglages enregistrés");
  }));
}

async function startJob(action) {
  if (!S.cur) return status("Ouvre d'abord un rec");
  if (S.dirty) await savePlan();
  await api("/api/job", { action, mode: S.cur.mode, path: S.cur.path });
  setTab("queue");
  status(`Tâche ajoutée : ${action}`);
  pollJobs();
}

let lastJobState = {};
async function pollJobs() {
  try { S.jobs = await api("/api/jobs"); } catch (e) { return; }
  const el = $("#tab-queue");
  const active = S.jobs.filter(j => j.status === "en cours" || j.status === "en attente").length;
  $("#queue-badge").textContent = active; $("#queue-badge").classList.toggle("hidden", !active);
  const label = { scan: "Analyse", rescan: "Nouveau scan complet", render: "Rendu", all: "Analyse + rendu", proxy: "Aperçu léger" };
  el.innerHTML = S.jobs.length ? S.jobs.slice().reverse().map(j => `<div class="job ${j.status === "terminé" ? "done" : j.status === "erreur" ? "err" : ""}">
    <div class="job-top"><span class="job-name">${label[j.action] || j.action} — ${j.name}</span><span class="muted">${j.status}</span></div>
    <div class="bar"><i style="width:${j.pct.toFixed(1)}%"></i></div>
    <div class="job-msg" title="${(j.log || []).slice(-1)[0] || ""}">${j.pct.toFixed(1)}% • ${j.msg || ""}</div>
    ${j.status === "en cours" || j.status === "en attente" ? `<button class="btn ghost" data-job="${j.id}">Annuler</button>` : ""}
    ${j.output ? `<button class="btn" data-open="${encodeURIComponent(j.output)}">Ouvrir le montage</button>` : ""}
    ${j.status !== "en attente" ? `<details ${j.status === "erreur" ? "open" : ""}><summary class="muted">Détails</summary><pre style="white-space:pre-wrap;font-size:10px;user-select:text">${(j.log || []).slice(-30).join("\n")}</pre></details>` : ""}
    ${j.status === "erreur" ? `<button class="btn" data-diag="${encodeURIComponent(j.path)}|${j.mode}">Ouvrir le diagnostic</button>` : ""}
    </div>`).join("") : '<p class="muted pad">Aucune tâche.</p>';
  $$("[data-job]", el).forEach(b => b.onclick = () => api("/api/job/cancel", { id: b.dataset.job }).then(pollJobs));
  $$("[data-open]", el).forEach(b => b.onclick = () => api("/api/open", { path: decodeURIComponent(b.dataset.open) }));
  $$("[data-diag]", el).forEach(b => b.onclick = () => { const [p, m] = b.dataset.diag.split("|");
    api("/api/open", { folder: "diag", video: decodeURIComponent(p), mode: m }); });
  const running = S.jobs.find(j => j.status === "en cours");
  $("#status-right").textContent = running ? `${label[running.action]} : ${running.pct.toFixed(0)}% — ${running.name}` : "";
  // fin d'une tâche -> rafraîchir
  for (const j of S.jobs) {
    if (lastJobState[j.id] === "en cours" && j.status !== "en cours") {
      status(`${label[j.action]} ${j.status} : ${j.name}`);
      await loadLibrary();
      if (S.cur && j.name === S.cur.path.split(/[\\/]/).pop()) {
        const v = S.lib.find(x => x.name === j.name);
        if (v) openProject(v);
      }
    }
    lastJobState[j.id] = j.status;
  }
}

/* ================= commandes ================= */
function setView(v) {
  $$("#view-tabs button[data-view]").forEach(b => b.classList.toggle("active", b.dataset.view === v));
  $$(".view").forEach(x => x.classList.toggle("active", x.id === "view-" + v));
  if (v === "card") refreshCard();
  if (v === "banners") loadBanners();
}
function setTab(t) {
  $$("#right-tabs button").forEach(b => b.classList.toggle("active", b.dataset.tab === t));
  $$(".tab-body").forEach(x => x.classList.toggle("active", x.id === "tab-" + t));
}

function segAt(t) {
  if (!S.plan) return null;
  for (let gi = 0; gi < S.plan.games.length; gi++) {
    const segs = S.plan.games[gi].segments;
    for (let si = 0; si < segs.length; si++) if (t > segs[si].start && t < segs[si].end) return { gi, si };
  }
  return null;
}
function gameAt(t) {
  if (!S.plan) return -1;
  return S.plan.games.findIndex(g => { const [a, b] = gameSpan(g); return t >= a - 30 && t <= b + 30; });
}

async function pickFolder() {
  if (window.pywebview && window.pywebview.api && window.pywebview.api.pick_folder) return await window.pywebview.api.pick_folder();
  return prompt("Chemin du dossier de recs (ex : D:\\Videos\\Fortnite)");
}
function modal(html) { $("#modal-body").innerHTML = html; $("#modal").classList.remove("hidden"); }
async function foldersModal() {
  const dirs = S.settings.library_dirs;
  modal(`<h3>Dossiers de recs</h3><p class="muted">Le studio liste les vidéos de ces dossiers (et de leur sous-dossier « Vidéos brutes »).</p>
    ${dirs.map((d, i) => `<div class="kv"><span>${d}</span><button class="icon-btn" data-rmdir="${i}">✕</button></div>`).join("")}
    <button class="btn primary" id="add-dir" style="margin-top:10px">+ Ajouter un dossier</button>`);
  $("#add-dir").onclick = async () => {
    const d = await pickFolder();
    if (!d) return;
    S.settings = await api("/api/settings", { library_dirs: [...dirs, d] });
    foldersModal(); loadLibrary();
  };
  $$("[data-rmdir]").forEach(b => b.onclick = async () => {
    const nd = dirs.filter((_, i) => i !== +b.dataset.rmdir);
    S.settings = await api("/api/settings", { library_dirs: nd });
    foldersModal(); loadLibrary();
  });
}

let updManual = false;
async function pollUpdate() {
  let u;
  try { u = await api("/api/update"); } catch (e) { return; }
  const b = $("#upd-badge");
  if (u.ready) { b.textContent = `⟳ Mise à jour ${u.ready} prête — Redémarrer`; b.classList.remove("hidden"); }
  else if (u.checking && u.progress) { b.textContent = `Téléchargement mise à jour… ${u.progress}%`; b.classList.remove("hidden"); }
  else b.classList.add("hidden");
  if (updManual && !u.checking) {
    updManual = false;
    modal(`<h3>Mises à jour</h3><div class="kv"><span>Version installée</span><b>${u.version}</b></div>
      ${u.ready ? `<p>La version <b>${u.ready}</b> est téléchargée.</p>${u.notes ? `<pre style="white-space:pre-wrap">${u.notes}</pre>` : ""}
        <button class="btn primary" data-cmd="update-restart">Redémarrer maintenant</button>`
        : u.error ? `<p style="color:var(--accent2)">${u.error}</p>` : !u.configured ? `<p class="muted">Mises à jour non configurées dans ce build.</p>`
        : `<p style="color:var(--green)">Tu as la dernière version.</p>`}`);
  }
}

const CMDS = {
  "folders": foldersModal,
  "update-check": async () => { updManual = true; await api("/api/update/check", {}); status("Recherche de mises à jour…"); },
  "update-restart": async () => {
    const r = await api("/api/update/restart", {});
    if (!r.ok) return status(r.message);
    if (S.dirty) await savePlan();
    $("#modal-body").innerHTML = "<h3>Redémarrage…</h3><p class='muted'>Montage Studio se relance avec la nouvelle version.</p>";
    $("#modal").classList.remove("hidden");
  },
  "open-music": () => api("/api/open", { folder: "music" }),
  "about": () => modal(`<h3>Montage Studio ${S.settings.version}</h3>
    <button class="btn" data-cmd="update-check" style="margin-bottom:8px">Rechercher des mises à jour</button>
    <div class="kv"><span>Encodeur vidéo détecté</span><b>${{ nvenc: "NVIDIA NVENC", amf: "AMD AMF", qsv: "Intel Quick Sync", x264: "Processeur (x264)" }[S.settings.encoder]}</b></div>
    <div class="kv"><span>Dossier des données</span><b style="font-size:10px">${S.settings.data_dir}</b></div>
    <p class="muted">Polices : Luckiest Guy (Apache 2.0), Anton (OFL). Vidéo : FFmpeg. Lecture d'écran : EasyOCR / PyTorch.
    Musiques intégrées composées par code. Application non affiliée à Epic Games.</p>`),
  "refresh": loadLibrary,
  "open-videos": () => api("/api/open", {}),
  "open-thumbs": () => api("/api/open", { folder: "thumbs" }),
  "scan": () => startJob("scan"), "rescan": () => startJob("rescan"), "all": () => startJob("all"),
  "render": () => startJob("render"), "proxy": () => startJob("proxy"),
  "save": () => savePlan().then(() => status("Montage enregistré")),
  "reset": async () => {
    if (!S.cur || !confirm("Remplacer le montage par le montage automatique ? (tes retouches seront perdues)")) return;
    S.proj = await api("/api/plan/reset", { path: S.cur.path, mode: S.cur.mode });
    S.plan = S.proj.plan; S.sel = null; renderAll(); status("Montage auto restauré");
  },
  "undo": () => { if (!S.undo.length) return; S.plan = JSON.parse(S.undo.pop()); changed(); renderProps(); },
  "split": () => {
    const t = player().currentTime, at = segAt(t);
    if (!at) return status("Place le curseur dans un segment vert pour couper");
    pushUndo();
    const segs = S.plan.games[at.gi].segments, s = segs[at.si];
    segs.splice(at.si + 1, 0, { ...s, start: t + 0.05 });
    s.end = t;
    S.sel = { type: "seg", gi: at.gi, si: at.si + 1 };
    changed(); renderProps(); status("Segment coupé");
  },
  "delete": () => {
    if (!S.sel || S.sel.type !== "seg") return status("Sélectionne un segment vert à supprimer");
    pushUndo();
    S.plan.games[S.sel.gi].segments.splice(S.sel.si, 1);
    S.sel = { type: "game", gi: S.sel.gi };
    changed(); renderProps();
  },
  "seg-del": () => CMDS.delete(),
  "add": () => {
    const t = player().currentTime, gi = gameAt(t);
    if (gi < 0) return status("Place le curseur dans une game (bloc bleu)");
    if (segAt(t)) return status("Il y a déjà un segment ici");
    pushUndo();
    const segs = S.plan.games[gi].segments;
    const next = segs.find(s => s.start > t);
    const end = Math.min(t + 30, next ? next.start - 0.5 : t + 30, tlDuration());
    segs.push({ start: Math.round(t * 10) / 10, end: Math.round(end * 10) / 10 });
    segs.sort((a, b) => a.start - b.start);
    S.sel = { type: "seg", gi, si: segs.findIndex(s => Math.abs(s.start - t) < 0.2) };
    changed(); renderProps(); status("Segment de 30 s ajouté — ajuste ses bords à la souris");
  },
  "game-full": () => {
    if (!S.sel) return;
    pushUndo();
    const g = S.plan.games[S.sel.gi], [a, b] = gameSpan(g);
    g.segments = [{ start: a, end: b }];
    changed(); renderProps();
  },
  "sel-final": () => select({ type: "final" }),
  "music-play": () => {
    const sel = $("#tab-props select[data-k=music]").value, m = S.music.find(x => x.name === sel), a = $("#music-player");
    if (!m) return status("Musique auto : choisis un titre pour l'écouter");
    if (!a.paused && a.dataset.name === m.name) { a.pause(); return; }
    a.src = m.url; a.dataset.name = m.name; a.volume = 0.6; a.play();
  },
  "play": () => { const p = player(); p.paused ? p.play() : p.pause(); },
  "back5": () => seek(player().currentTime - 5), "fwd5": () => seek(player().currentTime + 5),
  "next-seg": () => { const t = player().currentTime, s = allSegs().find(x => x.start > t + 0.2); if (s) seek(s.start); },
  "prev-seg": () => { const t = player().currentTime, s = allSegs().filter(x => x.start < t - 0.5).pop(); if (s) seek(s.start); },
  "zoom-in": () => setZoom(+$("#zoom").value + 12), "zoom-out": () => setZoom(+$("#zoom").value - 12),
  "zoom-fit": () => { fitZoom(); renderTimeline(); },
  "view-video": () => setView("video"), "view-card": () => setView("card"), "view-thumbs": () => setView("thumbs"), "view-banners": () => setView("banners"),
  "tab-queue": () => setTab("queue"),
  "th-generate": genThumbs,
  "th-add-time": () => { S.thTimes.push(player().currentTime); renderThumbGrid(); },
  "th-clear-times": () => { S.thTimes = []; renderThumbGrid(); },
  "th-export": async () => {
    const f = S.thFiles[S.thSel];
    if (!f) return;
    const r = await api("/api/thumbnails/export", { path: S.cur.path, file: f.path });
    status("Miniature exportée : " + r.saved);
    api("/api/open", { path: r.saved });
  },
  "help": () => {
    $("#modal-body").innerHTML = `<h3>Raccourcis</h3><table>
      <tr><td>Espace</td><td>Lecture / pause</td></tr><tr><td>← / →</td><td>-1 s / +1 s (Maj : 5 s)</td></tr>
      <tr><td>S</td><td>Couper le segment au curseur</td></tr><tr><td>Suppr</td><td>Supprimer le segment sélectionné</td></tr>
      <tr><td>A</td><td>Ajouter 30 s au curseur</td></tr><tr><td>+ / - / 0</td><td>Zoom timeline / tout afficher</td></tr>
      <tr><td>1 / 2 / 3</td><td>Vidéo / Carton / Miniatures</td></tr><tr><td>Ctrl+S</td><td>Enregistrer</td></tr>
      <tr><td>Ctrl+Z</td><td>Annuler</td></tr><tr><td>Ctrl+R</td><td>Lancer le rendu</td></tr></table>`;
    $("#modal").classList.remove("hidden");
  },
  "modal-close": () => $("#modal").classList.add("hidden"),
};

function renderAll() { renderTimeline(); renderProps(); updateStats(); }

/* ================= studio de bannières ================= */
const BN = { info: null, tid: null, values: {}, skins: [], bg: "theme", timer: null, seq: 0 };
const bnTpl = () => BN.info && BN.info.templates.find(t => t.id === BN.tid);
async function loadBanners() {
  const q = S.cur ? `?path=${encodeURIComponent(S.cur.path)}&mode=${S.cur.mode}` : "";
  BN.info = await api("/api/banners" + q);
  const sel = $("#bn-template");
  const groups = {};
  BN.info.templates.forEach(t => (groups[t.format] = groups[t.format] || []).push(t));
  sel.innerHTML = Object.entries(groups).map(([g, ts]) =>
    `<optgroup label="${g}">${ts.map(t => `<option value="${t.id}">${t.label}</option>`).join("")}</optgroup>`).join("");
  if (!BN.tid || !bnTpl()) BN.tid = BN.info.templates[0].id;
  sel.value = BN.tid;
  sel.onchange = () => { BN.tid = sel.value; renderBnFields(); renderBnSkins(); bnPreview(); };
  // valeurs auto (points, rangs du rec ouvert) : remplacent celles d'un autre rec
  const proj = S.cur ? S.cur.path : "";
  if (BN.proj !== proj) { BN.proj = proj; for (const k of ["points", "rang_depart", "rang_actuel", "objectif", "progression", "gain", "theme"]) delete BN.values[k]; }
  BN.skins = BN.skins.filter(p => BN.info.skins.some(s => s.path === p));
  renderBnFields(); renderBnSkins(); bnPreview();
}
function renderBnFields() {
  const t = bnTpl();
  $("#bn-fields").innerHTML = t.fields.map(f => {
    const v = BN.values[f.key] ?? f.default ?? "";
    let input;
    if (f.type === "select") {
      const labels = f.key === "theme" ? BN.info.themes : null;
      input = `<select data-bn="${f.key}">${f.options.map(o => `<option value="${o}" ${String(o) === String(v) ? "selected" : ""}>${labels ? labels[o] : o}</option>`).join("")}</select>`;
    } else {
      input = `<input data-bn="${f.key}" ${f.type === "number" ? 'type="number"' : ""} value="${String(v).replace(/"/g, "&quot;")}">`;
    }
    return `<div class="bn-row"><label>${f.label}</label>${input}</div>`;
  }).join("");
  $$("[data-bn]", $("#bn-fields")).forEach(i => i.addEventListener("input", () => {
    BN.values[i.dataset.bn] = i.value;
    clearTimeout(BN.timer); BN.timer = setTimeout(bnPreview, 350);
  }));
}
function renderBnSkins() {
  const t = bnTpl(), box = $("#bn-skins");
  $("#bn-skin-hint").textContent = t.skins ? `ce modèle en utilise ${t.skins}` : "pas de skin sur ce modèle";
  if (!BN.info.skins.length) { box.innerHTML = `<div class="bn-empty">Aucun skin pour l'instant.</div>`; return; }
  box.innerHTML = BN.info.skins.map(s => {
    const n = BN.skins.indexOf(s.path);
    return `<div class="bn-skin ${n >= 0 ? "sel" : ""}" data-p="${s.path.replace(/"/g, "&quot;")}" style="background-image:url('${s.url}')" title="${s.name}">
      ${n >= 0 ? `<span class="n">${n + 1}</span>` : ""}<button class="x" title="Supprimer">✕</button></div>`;
  }).join("");
  $$(".bn-skin", box).forEach(el => {
    el.onclick = (e) => {
      const p = el.dataset.p;
      if (e.target.classList.contains("x")) {
        return api("/api/banner/skin_delete", { path: p }).then(() => { BN.skins = BN.skins.filter(x => x !== p); loadBanners(); });
      }
      if (BN.skins.includes(p)) BN.skins = BN.skins.filter(x => x !== p);
      else { BN.skins.push(p); while (BN.skins.length > Math.max(1, t.skins)) BN.skins.shift(); }
      renderBnSkins(); bnPreview();
    };
  });
}
function bnPayload() {
  const values = {};
  bnTpl().fields.forEach(f => { values[f.key] = BN.values[f.key] ?? f.default; });
  return { id: BN.tid, values, skins: BN.skins, bg: BN.bg,
    path: S.cur ? S.cur.path : null, t: S.cur ? player().currentTime : 0 };
}
async function bnPreview() {
  if (!BN.info) return;
  const seq = ++BN.seq, wrap = $(".bn-preview");
  wrap.classList.add("loading");
  try {
    const r = await api("/api/banner/render", bnPayload());
    if (seq !== BN.seq) return;
    $("#bn-img").src = r.url; $("#bn-msg").classList.add("hidden");
    const t = bnTpl();
    $("#bn-info").textContent = `${t.label} • ${r.size[0]} × ${r.size[1]}`;
  } catch (e) { status("Bannière : " + e.message); }
  finally { if (seq === BN.seq) wrap.classList.remove("loading"); }
}
$$("#bn-bg button").forEach(b => b.onclick = () => {
  if (b.dataset.bg === "frame" && !S.cur) return status("Ouvre un rec pour utiliser une de ses images en fond");
  BN.bg = b.dataset.bg;
  $$("#bn-bg button").forEach(x => x.classList.toggle("active", x === b));
  bnPreview();
});
CMDS["bn-export"] = async () => {
  const r = await api("/api/banner/export", bnPayload());
  status("Exporté : " + r.saved);
  modal(`<h3>Bannière exportée</h3><p class="muted" style="word-break:break-all">${r.saved}</p>
    <button class="btn" id="bn-open">Afficher dans le dossier</button>`);
  $("#bn-open").onclick = () => api("/api/open", { path: r.saved });
};
CMDS["bn-cutout"] = async () => {
  if (!S.cur) return status("Ouvre d'abord un rec et place le curseur sur ton skin");
  status("Détourage du skin… (quelques secondes, plus long la 1re fois)");
  const r = await api("/api/banner/cutout", { path: S.cur.path, t: player().currentTime });
  if (!r.ok) return modal(`<h3>Détourage impossible</h3><p>${r.message}</p>`);
  BN.skins = [r.skin.path, ...BN.skins.filter(p => p !== r.skin.path)].slice(0, Math.max(1, bnTpl().skins));
  status("Skin détouré et ajouté");
  loadBanners();
};
CMDS["bn-skin-folder"] = () => api("/api/open", { path: BN.info.skin_dir });
CMDS["bn-assets"] = () => modal(`<h3>Tes icônes de rangs et de cups</h3>
  <p>Dépose tes images PNG (fond transparent) dans ces dossiers. Elles remplacent automatiquement les badges dessinés par l'app.</p>
  <p class="muted"><b>rangs\\</b> : un fichier par rang, nommé <b>bronze.png</b>, <b>argent.png</b>, <b>or.png</b>, <b>platine.png</b>,
  <b>diamant.png</b>, <b>elite.png</b>, <b>champion.png</b>, <b>unreal.png</b>.<br><b>cups\\</b> : l'icône de cup à utiliser à la place du trophée.</p>
  <button class="btn" id="bn-open-assets">Ouvrir le dossier</button>`) || ($("#bn-open-assets").onclick = () => api("/api/open", { path: BN.info.assets_dir }));

/* ================= fenêtre façon macOS ================= */
const winApi = () => (window.pywebview && window.pywebview.api && window.pywebview.api.win_close) ? window.pywebview.api : null;
async function syncWindowChrome() {
  const w = winApi();
  let frameless = false;
  if (w && w.win_info) { try { frameless = !!(await w.win_info()).frameless; } catch (e) { frameless = false; } }
  document.body.classList.toggle("native", frameless);
  const on = !(S.settings && S.settings.ui && S.settings.ui.mac_window === false);
  $("#mac-window-item").classList.toggle("checked", on);
}
window.addEventListener("pywebviewready", syncWindowChrome);
$$(".traffic button").forEach(b => b.addEventListener("click", e => {
  e.stopPropagation(); const w = winApi(); if (w) w["win_" + b.dataset.win]();
}));
$("#titlebar").addEventListener("dblclick", e => {
  if (e.target.closest("button, .menu, input, select, .titlebar-right")) return;
  const w = winApi(); if (w) w.win_max();
});
CMDS["toggle-mac-window"] = async () => {
  const on = !(S.settings.ui && S.settings.ui.mac_window === false);
  S.settings = await api("/api/settings", { ui: { mac_window: !on } });
  syncWindowChrome();
  modal(`<h3>${on ? "Cadre Windows classique" : "Fenêtre façon Mac"}</h3>
    <p>Le changement s'appliquera au prochain lancement de Montage Studio.</p>`);
};

/* ================= init ================= */
document.addEventListener("click", e => {
  const c = e.target.closest("[data-cmd]");
  $$(".menu.open").forEach(m => { if (!m.contains(e.target)) m.classList.remove("open"); });
  if (c) { e.preventDefault(); $$(".menu.open").forEach(m => m.classList.remove("open")); (CMDS[c.dataset.cmd] || (() => {}))(); }
});
$$(".menu > button").forEach(b => b.addEventListener("click", e => {
  e.stopPropagation(); const m = b.parentElement, open = m.classList.contains("open");
  $$(".menu.open").forEach(x => x.classList.remove("open")); if (!open) m.classList.add("open");
}));
$$(".menu").forEach(m => m.addEventListener("mouseenter", () => { if ($(".menu.open") && !m.classList.contains("open")) { $$(".menu.open").forEach(x => x.classList.remove("open")); m.classList.add("open"); } }));
$$("#view-tabs button[data-view]").forEach(b => b.onclick = () => setView(b.dataset.view));
$$("#right-tabs button").forEach(b => b.onclick = () => setTab(b.dataset.tab));
$("#lib-search").oninput = renderLibrary; $("#lib-filter").onchange = renderLibrary;
$("#zoom").oninput = e => setZoom(+e.target.value);
$("#ruler").onclick = e => { const r = $("#tl-content").getBoundingClientRect(); seek((e.clientX - r.left) / S.pxs); };
$("#trk-segs").onclick = e => { if (e.target.id === "trk-segs") { const r = $("#tl-content").getBoundingClientRect(); seek((e.clientX - r.left) / S.pxs); } };
$("#trk-events").onclick = $("#trk-segs").onclick;
$("#tl-scroll").addEventListener("wheel", e => { if (e.ctrlKey) { e.preventDefault(); setZoom(+$("#zoom").value + (e.deltaY < 0 ? 6 : -6)); } }, { passive: false });
const p = player();
p.addEventListener("timeupdate", onTime);
p.addEventListener("play", () => $("#play-btn").textContent = "❚❚");
p.addEventListener("pause", () => $("#play-btn").textContent = "▶");
p.addEventListener("click", () => CMDS.play());

document.addEventListener("keydown", e => {
  if (["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName)) return;
  const k = e.key;
  if (e.ctrlKey && k.toLowerCase() === "s") { e.preventDefault(); return CMDS.save(); }
  if (e.ctrlKey && k.toLowerCase() === "z") { e.preventDefault(); return CMDS.undo(); }
  if (e.ctrlKey && k.toLowerCase() === "r") { e.preventDefault(); return CMDS.render(); }
  if (k === " ") { e.preventDefault(); return CMDS.play(); }
  if (k === "ArrowLeft") return seek(player().currentTime - (e.shiftKey ? 5 : 1));
  if (k === "ArrowRight") return seek(player().currentTime + (e.shiftKey ? 5 : 1));
  const map = { s: "split", S: "split", Delete: "delete", Backspace: "delete", a: "add", A: "add", "+": "zoom-in", "=": "zoom-in",
    "-": "zoom-out", "0": "zoom-fit", "1": "view-video", "2": "view-card", "3": "view-thumbs", "4": "view-banners", F5: "refresh" };
  if (map[k]) { e.preventDefault(); CMDS[map[k]](); }
});
window.addEventListener("resize", () => { if (S.proj) { const v = +$("#zoom").value; fitZoom(); setZoom(v); } });
window.addEventListener("beforeunload", () => { if (S.dirty) navigator.sendBeacon && savePlan(); });

(async () => {
  S.music = await api("/api/music");
  await loadSettings();
  MODES = S.settings.modes || MODES;
  syncWindowChrome();
  await loadLibrary();
  renderProps();
  setInterval(pollJobs, 1000);
  setInterval(pollUpdate, 3000);
  pollJobs();
})();

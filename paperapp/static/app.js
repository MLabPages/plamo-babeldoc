"use strict";
(() => {
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const params = new URLSearchParams(location.search);
if (params.get("t")) { localStorage.setItem("token", params.get("t")); history.replaceState(null, "", "/"); }
const TOKEN = localStorage.getItem("token") || "";
const api = async (path, opt = {}) => {
  const r = await fetch("/api" + path, {...opt, headers: {...(opt.headers || {}), "X-Token": TOKEN}});
  const ct = r.headers.get("content-type") || "";
  const data = ct.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new Error((data && data.error) || ("HTTP " + r.status));
  return data;
};
const fileUrl = (path) => "/api" + path + "?t=" + encodeURIComponent(TOKEN);
const toast = (msg) => { const t = $("#toast"); t.textContent = msg; t.classList.remove("hidden"); clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.add("hidden"), 3500); };
const fmtSec = (s) => s >= 60 ? Math.floor(s / 60) + "分" + Math.round(s % 60) + "秒" : Math.round(s) + "秒";

let state = null, library = [], pollTimer = null;
const prefs = Object.assign({theme: "light", font: "serif", fs: 19, lh: 1.95, w: 38, orig: false, figs: true, rate: 1.1, voice: ""},
  JSON.parse(localStorage.getItem("prefs") || "{}"));
const savePrefs = () => localStorage.setItem("prefs", JSON.stringify(prefs));

// ---------------- ライブラリ ----------------
async function loadState() {
  state = await api("/state");
  document.querySelectorAll(".local-only").forEach((el) => el.classList.toggle("hidden", !state.is_local));
  const sel = $("#engineSel");
  sel.innerHTML = state.engines.map((e) => '<option value="' + e.id + '"' + (e.available ? "" : " disabled") + ">" + esc(e.label) + "</option>").join("");
  const def = state.engines.find((e) => e.id === state.settings.engine && e.available) || state.engines.find((e) => e.available);
  if (def) sel.value = def.id;
  updateEngineNote();
}
function updateEngineNote() {
  const e = state.engines.find((x) => x.id === $("#engineSel").value);
  $("#engineNote").textContent = e ? e.note : "";
}
$("#engineSel").addEventListener("change", () => { updateEngineNote(); api("/settings", {method: "POST", body: JSON.stringify({engine: $("#engineSel").value})}).catch(() => {}); });

async function loadLibrary() {
  library = await api("/library");
  renderLibrary();
  const busy = library.some((d) => Object.values(d.translations || {}).some((t) => t.status === "running" || t.status === "queued"));
  clearTimeout(pollTimer);
  if (busy) pollTimer = setTimeout(loadLibrary, 1500);
}
function engineOptions(exclude) {
  return state.engines.filter((e) => e.available && !exclude.includes(e.id)).map((e) => '<option value="' + e.id + '">' + esc(e.label) + "</option>").join("");
}
function renderLibrary() {
  const el = $("#library");
  if (!library.length) { el.innerHTML = '<div class="empty">まだ論文がありません。PDFをドロップすると翻訳が始まります。</div>'; return; }
  el.innerHTML = library.map((d) => {
    const trs = Object.entries(d.translations || {});
    const chips = trs.map(([eng, t]) => {
      const label = esc(t.label || eng);
      if (t.status === "done") return '<span class="chip done" data-read="' + d.id + '" data-engine="' + eng + '">📖 ' + label + (t.seconds ? " · " + fmtSec(t.seconds) : "") + "</span>";
      if (t.status === "error") return '<span class="chip err" title="' + esc(t.error) + '">⚠ ' + label + " 失敗 <button data-retry=\"" + d.id + '" data-engine="' + eng + '">再試行</button></span>';
      if (t.status === "canceled") return '<span class="chip">' + label + ' · 中止 <button data-retry="' + d.id + '" data-engine="' + eng + '">やり直す</button></span>';
      return '<span class="chip">' + label + " · " + esc(t.stage || "") + ' <span class="bar-mini"><i style="width:' + (t.progress || 0) + '%"></i></span> ' + Math.round(t.progress || 0) + '% <button data-cancel="' + d.id + '" data-engine="' + eng + '" title="中止">×</button></span>';
    }).join("");
    const errs = trs.filter(([, t]) => t.status === "error" || (t.status === "done" && t.warning)).map(([, t]) => '<div class="note">⚠ ' + esc(t.label || "") + "：" + esc(t.error || t.warning) + "</div>").join("");
    const opts = engineOptions(trs.map(([e]) => e));
    const firstDone = trs.find(([, t]) => t.status === "done");
    return '<div class="card"><div class="card-title" ' + (firstDone ? 'data-read="' + d.id + '" data-engine="' + firstDone[0] + '"' : "") + ">" + esc(d.title_ja || d.title) + "</div>" +
      '<div class="card-sub">' + esc(d.filename) + (d.pages ? " · " + d.pages + "ページ" : "") + " · " + new Date(d.created * 1000).toLocaleString("ja-JP") + "</div>" +
      '<div class="chips">' + chips + "</div>" + errs +
      '<div class="card-actions">' + (opts ? '<select data-eng-for="' + d.id + '">' + opts + '</select><button data-more="' + d.id + '">このエンジンでも翻訳</button>' : "") +
      '<span class="grow"></span><a class="btn" style="font-size:13px;min-height:32px;padding:5px 10px" target="_blank" href="' + fileUrl("/doc/" + d.id + "/original") + '">原文PDF</a><button data-del="' + d.id + '">削除</button></div></div>';
  }).join("");
}
$("#library").addEventListener("click", async (ev) => {
  const t = ev.target.closest("[data-read],[data-retry],[data-more],[data-del],[data-cancel]");
  if (!t) return;
  try {
    if (t.dataset.read) openReader(t.dataset.read, t.dataset.engine);
    else if (t.dataset.cancel) { await api("/doc/" + t.dataset.cancel + "/cancel?engine=" + t.dataset.engine, {method: "POST"}); loadLibrary(); }
    else if (t.dataset.retry) { await api("/doc/" + t.dataset.retry + "/translate?engine=" + t.dataset.engine, {method: "POST"}); loadLibrary(); }
    else if (t.dataset.more) { const eng = document.querySelector('[data-eng-for="' + t.dataset.more + '"]').value; await api("/doc/" + t.dataset.more + "/translate?engine=" + eng, {method: "POST"}); loadLibrary(); }
    else if (t.dataset.del) { if (confirm("この論文と翻訳結果を削除しますか？")) { await api("/doc/" + t.dataset.del + "/delete", {method: "POST"}); loadLibrary(); } }
  } catch (e) { toast(e.message); }
});

async function uploadFiles(files) {
  const engine = $("#engineSel").value;
  for (const f of files) {
    if (!/\.pdf$/i.test(f.name) && f.type !== "application/pdf") { toast(f.name + " はPDFではありません"); continue; }
    try {
      await api("/translate?engine=" + encodeURIComponent(engine) + "&name=" + encodeURIComponent(f.name), {method: "POST", body: f, headers: {"Content-Type": "application/pdf"}});
    } catch (e) { toast(e.message); }
  }
  loadLibrary();
}
$("#file").addEventListener("change", (e) => { uploadFiles([...e.target.files]); e.target.value = ""; });
const drop = $("#drop");
["dragenter", "dragover"].forEach((n) => document.addEventListener(n, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((n) => document.addEventListener(n, (e) => { e.preventDefault(); if (n === "drop" || !e.relatedTarget) drop.classList.remove("over"); }));
document.addEventListener("drop", (e) => { if ($("#home").classList.contains("hidden")) return; const fs = [...(e.dataTransfer?.files || [])]; if (fs.length) uploadFiles(fs); });

// ---------------- 設定・共有 ----------------
function modal(html) { $("#modalBox").innerHTML = html; $("#modal").classList.remove("hidden"); }
function closeModal() { $("#modal").classList.add("hidden"); }
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal" || e.target.dataset.close !== undefined) closeModal(); });

$("#btnSettings").addEventListener("click", async () => {
  const s = state.settings;
  modal('<h3>設定</h3>' +
    '<label>Gemini APIキー ' + (s.has_gemini_key ? "（登録済み）" : "") + '</label><input type="password" id="gKey" placeholder="' + (s.has_gemini_key ? "変更するときだけ入力" : "AIza... を貼り付け") + '" autocomplete="off">' +
    '<label>Geminiのモデル</label><select id="gModel"><option>' + esc(s.gemini_model) + "</option></select>" +
    '<p class="note">キーはこのPCの中（%APPDATA%\\PLaMoPaperReader）だけに保存されます。Geminiを選ぶと論文の本文がGoogleに送られます。無料枠では送った内容がGoogleの品質改善に使われることがあります。</p>' +
    '<div class="modal-actions">' + (s.has_gemini_key ? '<button id="gDel">キーを削除</button>' : "") + '<span class="grow"></span><button data-close>閉じる</button><button class="primary" id="gSave">保存</button></div>');
  if (s.has_gemini_key) {
    api("/gemini/models").then((list) => {
      if (!list.length) return;
      const cur = s.gemini_model;
      $("#gModel").innerHTML = [...new Set([cur, ...list])].map((m) => "<option" + (m === cur ? " selected" : "") + ">" + esc(m) + "</option>").join("");
    }).catch((e) => toast("モデル一覧を取得できませんでした: " + e.message));
  }
  $("#gSave").onclick = async () => {
    const body = {gemini_model: $("#gModel").value};
    const k = $("#gKey").value.trim();
    if (k) body.gemini_api_key = k;
    await api("/settings", {method: "POST", body: JSON.stringify(body)});
    closeModal(); await loadState(); toast("保存しました");
  };
  const del = $("#gDel");
  if (del) del.onclick = async () => { await api("/settings", {method: "POST", body: JSON.stringify({gemini_api_key: ""})}); closeModal(); await loadState(); toast("キーを削除しました"); };
});

async function showShare() {
  const info = state.share;
  if (!info.enabled) {
    modal('<h3>iPadで読む</h3><p>このPCとiPadを同じWi‑Fiにつなぐと、iPadのSafariでライブラリと読書モードを使えます。翻訳はこのPCで動きます。</p>' +
      '<p class="note">開始するとWindowsのファイアウォール確認が出ることがあります。「プライベート ネットワーク」を許可してください。アプリを閉じると共有も止まります。</p>' +
      '<div class="modal-actions"><button data-close>閉じる</button><button class="primary" id="shareOn">共有を開始</button></div>');
    $("#shareOn").onclick = async () => { try { state.share = await api("/share", {method: "POST", body: JSON.stringify({enable: true})}); showShare(); } catch (e) { toast(e.message); } };
  } else {
    modal('<h3>iPadで読む</h3><p>iPadのカメラでQRコードを読み取ってください。Safariで開いたら、共有メニューの「ホーム画面に追加」でアプリのように使えます。</p>' +
      '<img class="qr" src="' + fileUrl("/share/qr.svg") + "&r=" + Date.now() + '" alt="QRコード"><div class="url">' + esc(info.url) + "</div>" +
      '<p class="note">このリンクを知っている同じネットワーク内の端末だけが開けます。</p>' +
      '<div class="modal-actions"><button id="shareOff">共有を止める</button><span class="grow"></span><button class="primary" data-close>閉じる</button></div>');
    $("#shareOff").onclick = async () => { state.share = await api("/share", {method: "POST", body: JSON.stringify({enable: false})}); closeModal(); toast("共有を止めました"); };
  }
}
$("#btnShare").addEventListener("click", showShare);

// ---------------- 読書モード ----------------
let cur = {id: null, engine: null, items: [], mode: "read"};
const article = $("#article");

function applyPrefs() {
  document.body.classList.remove("theme-light", "theme-sepia", "theme-dark");
  document.body.classList.add("theme-" + prefs.theme);
  document.body.classList.toggle("font-sans", prefs.font === "sans");
  document.body.classList.toggle("bilingual", !!prefs.orig);
  document.body.classList.toggle("no-figs", !prefs.figs);
  const r = document.documentElement.style;
  r.setProperty("--fs", prefs.fs + "px"); r.setProperty("--lh", prefs.lh); r.setProperty("--w", prefs.w + "em");
  document.querySelectorAll("#themeSeg button").forEach((b) => b.classList.toggle("on", b.dataset.v === prefs.theme));
  document.querySelectorAll("#fontSeg button").forEach((b) => b.classList.toggle("on", b.dataset.v === prefs.font));
  $("#fontSize").value = prefs.fs; $("#lineHeight").value = prefs.lh; $("#colWidth").value = prefs.w;
  $("#showOrig").checked = prefs.orig; $("#showFigs").checked = prefs.figs;
  $("#ttsRate").value = prefs.rate; $("#ttsRateVal").textContent = Number(prefs.rate).toFixed(1) + "×";
  document.querySelector('meta[name=theme-color]').content = getComputedStyle(document.body).getPropertyValue("--bg").trim() || "#f7f4ee";
}
$("#themeSeg").addEventListener("click", (e) => { if (e.target.dataset.v) { prefs.theme = e.target.dataset.v; savePrefs(); applyPrefs(); } });
$("#fontSeg").addEventListener("click", (e) => { if (e.target.dataset.v) { prefs.font = e.target.dataset.v; savePrefs(); applyPrefs(); } });
[["#fontSize", "fs"], ["#lineHeight", "lh"], ["#colWidth", "w"]].forEach(([s, k]) => $(s).addEventListener("input", (e) => { prefs[k] = Number(e.target.value); savePrefs(); applyPrefs(); }));
$("#showOrig").addEventListener("change", (e) => { prefs.orig = e.target.checked; savePrefs(); applyPrefs(); });
$("#showFigs").addEventListener("change", (e) => { prefs.figs = e.target.checked; savePrefs(); applyPrefs(); });
$("#btnDisplay").addEventListener("click", () => $("#displayPanel").classList.toggle("hidden"));
document.addEventListener("click", (e) => { if (!e.target.closest("#displayPanel,#btnDisplay")) $("#displayPanel").classList.add("hidden"); });

async function openReader(id, engine) {
  const meta = library.find((d) => d.id === id) || await api("/doc/" + id);
  const done = Object.entries(meta.translations || {}).filter(([, t]) => t.status === "done");
  if (!done.length) return;
  if (!engine || !done.some(([e]) => e === engine)) engine = done[0][0];
  cur = {id, engine, items: [], mode: cur.mode || "read", meta};
  $("#readEngine").innerHTML = done.map(([e, t]) => '<option value="' + e + '"' + (e === engine ? " selected" : "") + ">" + esc(t.label || e) + "</option>").join("");
  $("#docTitle").textContent = meta.title_ja || meta.title;
  $("#home").classList.add("hidden"); $("#reader").classList.remove("hidden");
  location.hash = "read/" + id + "/" + engine;
  const data = await api("/doc/" + id + "/reading/" + engine);
  cur.items = data.items;
  renderArticle(data);
  setMode(cur.mode);
  restorePos();
}
$("#readEngine").addEventListener("change", (e) => { savePos(); ttsStop(); openReader(cur.id, e.target.value); });

function renderArticle(data) {
  let html = "";
  if (data.title) html += '<div class="doc-h1">' + esc(data.title) + "</div>";
  let n = 0, skippedTitle = false;
  for (const it of data.items) {
    if (it.t === "page") { html += '<div class="page-mark" data-page="' + it.page + '">' + it.page + " ページ</div>"; continue; }
    if (it.t === "fig") { html += '<figure><img loading="lazy" src="' + fileUrl("/doc/" + cur.id + "/fig/" + cur.engine + "/" + it.src) + '" width="' + it.w + '" height="' + it.h + '" alt="図"></figure>'; continue; }
    if (!skippedTitle && it.text === data.title) { skippedTitle = true; continue; }
    if (it.t === "eq") {
      html += it.src ? '<div class="eq"><img loading="lazy" src="' + fileUrl("/doc/" + cur.id + "/fig/" + cur.engine + "/" + it.src) + '" style="width:' + (it.w / 2.1) + 'px" alt="数式"></div>' : '<div class="eq">' + esc(it.text) + "</div>";
      continue;
    }
    const tag = it.t === "h2" ? "h2" : it.t === "h3" ? "h3" : "p";
    const cls = it.t === "cap" ? ' class="cap"' : "";
    html += "<" + tag + cls + ' data-i="' + (n++) + '">' + esc(it.text) + "</" + tag + ">";
    if (it.orig && tag === "p") html += '<div class="orig">' + esc(it.orig) + "</div>";
  }
  article.innerHTML = html;
}
const units = () => [...article.querySelectorAll("[data-i]")];

article.addEventListener("click", (e) => {
  const el = e.target.closest("[data-i]");
  if (!el) return;
  const o = el.nextElementSibling;
  if (o && o.classList.contains("orig") && !prefs.orig) o.classList.toggle("open");
  setCurrent(el);
  if (tts.playing) ttsStart(Number(el.dataset.i));
});

function setCurrent(el) {
  article.querySelectorAll(".current").forEach((x) => x.classList.remove("current"));
  if (el) el.classList.add("current");
}

let scrollRaf = 0;
window.addEventListener("scroll", () => {
  if ($("#reader").classList.contains("hidden") || cur.mode !== "read") return;
  cancelAnimationFrame(scrollRaf);
  scrollRaf = requestAnimationFrame(() => {
    const h = document.documentElement.scrollHeight - innerHeight;
    $("#progressFill").style.width = (h > 0 ? (scrollY / h) * 100 : 0) + "%";
    if (!tts.playing) {
      const mid = innerHeight * 0.42;
      let best = null, bd = 1e9;
      for (const el of units()) { const r = el.getBoundingClientRect(); const d = Math.abs((r.top + r.bottom) / 2 - mid); if (d < bd) { bd = d; best = el; } if (r.top > innerHeight) break; }
      setCurrent(best);
    }
    savePos();
  });
}, {passive: true});

const posKey = () => "pos:" + cur.id + ":" + cur.engine;
function savePos() {
  if (!cur.id) return;
  const el = article.querySelector(".current");
  if (el) localStorage.setItem(posKey(), el.dataset.i);
}
function restorePos() {
  const i = localStorage.getItem(posKey());
  const el = i !== null ? article.querySelector('[data-i="' + i + '"]') : null;
  if (el) { el.scrollIntoView({block: "center"}); setCurrent(el); } else window.scrollTo(0, 0);
}

function setMode(mode) {
  cur.mode = mode;
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.mode === mode));
  const read = mode === "read";
  $("#readPane").classList.toggle("hidden", !read);
  $("#ttsBar").classList.toggle("hidden", !read);
  $("#pdfPane").classList.toggle("hidden", read);
  $("#btnFocus").classList.toggle("hidden", !read);
  if (!read) {
    ttsStop();
    const url = fileUrl("/doc/" + cur.id + "/" + (mode === "pdf" ? "translated" : "dual") + "/" + cur.engine);
    $("#pdfOpen").href = url;
    if ($("#pdfFrame").dataset.src !== url) { $("#pdfFrame").src = url; $("#pdfFrame").dataset.src = url; }
  }
}
$("#tabs").addEventListener("click", (e) => { if (e.target.dataset.mode) setMode(e.target.dataset.mode); });

$("#btnBack").addEventListener("click", () => {
  savePos(); ttsStop(); document.body.classList.remove("focus", "show-bar");
  $("#reader").classList.add("hidden"); $("#home").classList.remove("hidden");
  $("#pdfFrame").src = "about:blank"; $("#pdfFrame").dataset.src = "";
  history.replaceState(null, "", "/"); loadLibrary();
});

// 集中モード: バーを隠し、いま読んでいる段落以外を薄くする
function toggleFocus() { document.body.classList.toggle("focus"); document.body.classList.remove("show-bar"); }
$("#btnFocus").addEventListener("click", toggleFocus);
document.addEventListener("mousemove", (e) => { if (document.body.classList.contains("focus")) document.body.classList.toggle("show-bar", e.clientY < 70 || e.clientY > innerHeight - 90); });
let lastTap = 0;
$("#readPane").addEventListener("touchend", (e) => {
  if (!document.body.classList.contains("focus")) return;
  const now = Date.now();
  if (now - lastTap < 320) document.body.classList.toggle("show-bar");
  lastTap = now;
});
document.addEventListener("keydown", (e) => {
  if ($("#reader").classList.contains("hidden") || e.target.matches("input,select,textarea")) return;
  if (e.key === "f" || e.key === "F") toggleFocus();
  else if (e.key === " " && cur.mode === "read" && (e.ctrlKey || e.altKey)) { e.preventDefault(); ttsToggle(); }
  else if (e.key === "Escape") { document.body.classList.remove("focus", "show-bar"); $("#displayPanel").classList.add("hidden"); }
  else if (e.key === "ArrowDown" && e.altKey) { e.preventDefault(); stepPara(1); }
  else if (e.key === "ArrowUp" && e.altKey) { e.preventDefault(); stepPara(-1); }
});
function stepPara(d) {
  const list = units(); const c = article.querySelector(".current");
  const i = Math.max(0, Math.min(list.length - 1, (c ? Number(c.dataset.i) : 0) + d));
  if (tts.playing) ttsStart(i); else { setCurrent(list[i]); list[i].scrollIntoView({block: "center", behavior: "smooth"}); }
}

// ---------------- 読み上げ ----------------
const synth = window.speechSynthesis;
const tts = {playing: false, idx: 0, queue: [], gen: 0};
function loadVoices() {
  if (!synth) { $("#ttsBar").classList.add("hidden"); return; }
  const vs = synth.getVoices().filter((v) => /^ja/i.test(v.lang));
  vs.sort((a, b) => (/(natural|online|nanami|kyoko|siri|enhanced)/i.test(b.name) ? 1 : 0) - (/(natural|online|nanami|kyoko|siri|enhanced)/i.test(a.name) ? 1 : 0));
  $("#ttsVoice").innerHTML = vs.length ? vs.map((v) => '<option value="' + esc(v.name) + '"' + (v.name === prefs.voice ? " selected" : "") + ">" + esc(v.name.replace(/^Microsoft /, "").replace(/ - Japanese \(Japan\)/, "")) + "</option>").join("") : "<option>日本語の声がありません</option>";
}
if (synth) { loadVoices(); synth.onvoiceschanged = loadVoices; }
$("#ttsVoice").addEventListener("change", (e) => { prefs.voice = e.target.value; savePrefs(); if (tts.playing) ttsStart(tts.idx); });
$("#ttsRate").addEventListener("input", (e) => { prefs.rate = Number(e.target.value); savePrefs(); applyPrefs(); });
$("#ttsRate").addEventListener("change", () => { if (tts.playing) ttsStart(tts.idx); });

const cleanForSpeech = (s) => s
  .replace(/\[[\d,\s\u2013\-–]+\]/g, "")
  .replace(/[（(][^（）()]{0,80}?\d{4}[a-z]?[^（）()]{0,40}?[)）]/g, "")
  .replace(/https?:\/\/\S+/g, "").replace(/\s+/g, " ").trim();
const sentences = (s) => (s.match(/[^。！？!?]+[。！？!?」』）)]*|[^。！？!?]+$/g) || [s]).map((x) => x.trim()).filter(Boolean);

function speakNext(gen) {
  if (gen !== tts.gen || !tts.playing) return;
  if (!tts.queue.length) {
    const list = units();
    if (tts.idx + 1 >= list.length) { ttsStop(); return; }
    loadPara(tts.idx + 1);
  }
  const text = tts.queue.shift();
  if (!text) { speakNext(gen); return; }
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "ja-JP"; u.rate = prefs.rate;
  const v = synth.getVoices().find((x) => x.name === prefs.voice) || synth.getVoices().find((x) => /^ja/i.test(x.lang));
  if (v) u.voice = v;
  u.onend = () => speakNext(gen);
  u.onerror = (e) => { if (e.error !== "interrupted" && e.error !== "canceled") speakNext(gen); };
  synth.speak(u);
}
function loadPara(i) {
  const list = units();
  tts.idx = i;
  article.querySelectorAll(".speaking").forEach((x) => x.classList.remove("speaking"));
  const el = list[i];
  if (!el) return;
  el.classList.add("speaking"); setCurrent(el);
  el.scrollIntoView({block: "center", behavior: "smooth"});
  tts.queue = sentences(cleanForSpeech(el.textContent));
  savePos();
}
function ttsStart(i) {
  if (!synth) return;
  synth.cancel();
  tts.playing = true; tts.gen++;
  loadPara(i);
  $("#ttsPlay").textContent = "⏸ 停止";
  const g = tts.gen;
  setTimeout(() => speakNext(g), 60);
}
function ttsStop() {
  tts.playing = false; tts.gen++;
  if (synth) synth.cancel();
  article.querySelectorAll(".speaking").forEach((x) => x.classList.remove("speaking"));
  $("#ttsPlay").textContent = "▶ 読み上げ";
}
function ttsToggle() {
  if (tts.playing) ttsStop();
  else { const c = article.querySelector(".current") || units()[0]; if (c) ttsStart(Number(c.dataset.i)); }
}
$("#ttsPlay").addEventListener("click", ttsToggle);
$("#ttsPrev").addEventListener("click", () => stepPara(-1));
$("#ttsNext").addEventListener("click", () => stepPara(1));
// Chrome系は長時間の読み上げが止まることがあるため定期的に起こす
setInterval(() => { if (tts.playing && synth && synth.speaking && !synth.paused) { synth.pause(); synth.resume(); } }, 12000);

// ---------------- 起動 ----------------
applyPrefs();
(async () => {
  try {
    await loadState();
    await loadLibrary();
    const m = location.hash.match(/^#read\/([a-z0-9]+)\/([\w.\-]+)/);
    if (m) openReader(m[1], m[2]);
  } catch (e) {
    $("#library").innerHTML = '<div class="empty">' + esc(e.message) + "<br>PCのアプリに表示されたQRコード（またはリンク）から開き直してください。</div>";
  }
})();
})();

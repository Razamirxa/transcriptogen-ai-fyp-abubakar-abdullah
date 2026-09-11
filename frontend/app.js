/* TranscriptoGen AI - front-end logic (vanilla JS, talks to the FastAPI backend) */
(() => {
  const $ = (id) => document.getElementById(id);
  const API = "";                       // same origin; set e.g. "http://localhost:8000" when served elsewhere
  const state = { job: null, result: null, images: [], imageData: null, translations: {} };

  // ---------- theme ----------
  const root = document.documentElement;
  const applyTheme = (t) => { root.dataset.theme = t; document.querySelector(".tt-label").textContent = t === "dark" ? "Dark" : "Light"; };
  const qTheme = new URLSearchParams(location.search).get("theme");   // ?theme=dark for links / screenshots
  try { applyTheme(qTheme || localStorage.getItem("tg-theme") || "light"); } catch { applyTheme(qTheme || "light"); }
  $("themeToggle").onclick = () => { const t = root.dataset.theme === "dark" ? "light" : "dark"; applyTheme(t); try { localStorage.setItem("tg-theme", t); } catch {} };

  // ---------- hero demo (orbit, waveform, typing transcript) ----------
  // 3D illustration + parallax (layers move by data-depth with the mouse; card tilts)
  const art = $("heroArt"); art.innerHTML = window.TG_SCENE.hero;
  const orbit = $("orbit");
  [["English", "var(--accent)"], ["اردو", "var(--amber)"], ["العربية", "#10B981"], ["हिन्दी", "#EC4899"], ["Español", "#0EA5E9"], ["Français", "#8B5CF6"]]
    .forEach(([label, c], i) => { const o = document.createElement("div"); o.className = "o"; o.style.transform = `rotateZ(${i * 60}deg) translateX(145px)`;
      o.innerHTML = `<div class="un" style="transform:rotateZ(${-i * 60}deg)"><div class="chip3d" style="--c:${c}"><i></i>${label}</div></div>`; orbit.appendChild(o); });
  document.querySelectorAll("[data-tile]").forEach((el) => { el.innerHTML = window.TG_SCENE.tiles[el.dataset.tile]; });
  const stage = document.querySelector(".stage"); const layers = art.querySelectorAll(".layer"); const card = document.querySelector(".float-card");
  stage.classList.add("parallax");
  const setParallax = (nx, ny) => {  // nx, ny in [-1, 1]
    layers.forEach((l) => { const d = +l.dataset.depth || 0; l.style.transform = `translate(${(nx * 22 * d).toFixed(1)}px, ${(ny * 16 * d).toFixed(1)}px)`; });
    if (card) card.style.transform = `translateY(-6px) rotateY(${(-14 + nx * 8).toFixed(1)}deg) rotateX(${(6 - ny * 6).toFixed(1)}deg)`;
  };
  stage.addEventListener("mousemove", (e) => { const r = stage.getBoundingClientRect(); setParallax(((e.clientX - r.left) / r.width - .5) * 2, ((e.clientY - r.top) / r.height - .5) * 2); });
  stage.addEventListener("mouseleave", () => { layers.forEach((l) => l.style.transform = ""); if (card) card.style.transform = ""; });
  if (window.DeviceOrientationEvent && matchMedia("(pointer: coarse)").matches) window.addEventListener("deviceorientation", (e) => setParallax(Math.max(-1, Math.min(1, (e.gamma || 0) / 30)), Math.max(-1, Math.min(1, ((e.beta || 0) - 45) / 30))));
  const wave = $("demoWave");
  for (let i = 0; i < 48; i++) { const b = document.createElement("i"); b.style.height = (12 + Math.round(Math.abs(Math.sin(i * .55)) * 40 + (i % 5) * 3)) + "px";
    b.style.animationDelay = (-((i * .09) % 1.4)).toFixed(2) + "s"; b.style.animationDuration = (1.1 + ((i * 7) % 5) * .14).toFixed(2) + "s"; if (i % 9 === 0) b.style.background = "var(--amber)"; wave.appendChild(b); }
  const DEMO = [
    { spk: 1, t: "00:02", text: "Welcome to the lecture on photosynthesis. Plants convert light energy into chemical energy." },
    { spk: 1, t: "00:09", text: "The light reactions happen in the thylakoid membranes of the chloroplast." },
    { spk: 2, t: "00:15", text: "Sir, is the Calvin cycle also part of the light reactions?" },
    { spk: 1, t: "00:19", text: "No. The Calvin cycle runs in the stroma and it does not need light directly." },
  ];
  let li = 0, wi = 0;
  const renderDemo = () => {
    $("demoClock").textContent = DEMO[li].t + " / 06:32";
    $("demoLines").innerHTML = DEMO.slice(0, li + 1).map((l, idx) => {
      const words = l.text.split(" ").map((w, i) => { let c = "var(--text)"; if (idx === li) c = i < wi ? "var(--text)" : (i === wi ? "var(--accent)" : "var(--border)"); return `<span style="color:${c}">${w}</span>`; }).join("");
      const two = l.spk === 2;
      return `<div class="dl"><div class="spk"><span class="chip" style="background:${two ? "rgba(217,119,6,.14)" : "color-mix(in srgb, var(--accent) 14%, transparent)"};color:${two ? "var(--amber)" : "var(--accent)"}">SPK ${l.spk}</span><span class="faint tiny">${l.t}</span></div><div class="words">${words}</div></div>`;
    }).join("");
  };
  setInterval(() => { const n = DEMO[li].text.split(" ").length; if (wi < n) wi++; else if (li < DEMO.length - 1) { li++; wi = 0; } else { li = 0; wi = 0; } renderDemo(); }, 230);
  renderDemo();

  // ---------- helpers ----------
  const fmt = (s) => { s = Math.max(0, Math.round(s)); return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`; };
  const isRtl = (t) => { const s = (t || "").slice(0, 600); let n = 0; for (const ch of s) if (ch >= "؀" && ch <= "ۿ") n++; return n > s.length * .2; };
  const showErr = (id, e) => { const el = $(id); el.textContent = typeof e === "string" ? e : (e.message || String(e)); el.classList.remove("hidden"); };
  const clearErr = (id) => $(id).classList.add("hidden");
  const blobUrl = (text, type = "text/plain") => URL.createObjectURL(new Blob([text], { type }));
  const escapeHtml = (s) => s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  const md = (src) => {  // tiny markdown -> html (headings, bullets, numbered, tables, bold)
    const lines = src.split("\n"); let out = [], inTable = false;
    for (const ln of lines) {
      const l = escapeHtml(ln).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
      if (/^\|.*\|$/.test(ln)) { if (/^\|[-\s|]+\|$/.test(ln)) continue; if (!inTable) { out.push("<table>"); inTable = true; } out.push("<tr>" + l.split("|").slice(1, -1).map((c) => `<td>${c.trim()}</td>`).join("") + "</tr>"); continue; }
      if (inTable) { out.push("</table>"); inTable = false; }
      if (/^# /.test(l)) out.push(`<h2>${l.slice(2)}</h2>`); else if (/^## /.test(l)) out.push(`<h3>${l.slice(3)}</h3>`);
      else if (/^- /.test(l)) out.push(`<li>${l.slice(2)}</li>`); else if (/^\d+\. /.test(l)) out.push(`<li>${l.replace(/^\d+\. /, "")}</li>`);
      else if (l.trim()) out.push(`<p>${l}</p>`);
    }
    if (inTable) out.push("</table>");
    return out.join("\n").replace(/(<li>[\s\S]*?<\/li>\n?)+/g, (m) => `<ul>${m}</ul>`);
  };
  const api = async (path, opts = {}) => {
    const r = await fetch(API + path, opts);
    if (!r.ok) { let msg = r.statusText; try { const j = await r.json(); msg = j.detail || JSON.stringify(j); } catch {} throw new Error(`${r.status}: ${msg}`); }
    return r.json();
  };
  const tabs = (containerId, onPick) => {
    const c = $(containerId);
    c.querySelectorAll(".tab").forEach((b) => b.onclick = () => { c.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === b)); onPick(b.dataset.tab); });
  };

  // ---------- config / health ----------
  let CFG = null;
  (async () => {
    try {
      const h = await api("/api/health");
      $("healthLine").textContent = h.ok ? `Server ready · ${h.keys_configured} API key(s) · FFmpeg ${h.ffmpeg ? "ok" : "missing"}` : `Server needs setup: keys=${h.keys_configured}, ffmpeg=${h.ffmpeg}`;
      CFG = await api("/api/config");
      const sel = $("langSel"); Object.keys(CFG.language_options).forEach((k) => { const o = document.createElement("option"); o.value = CFG.language_options[k].join(","); o.textContent = k; sel.appendChild(o); });
      const tr = $("trTarget"); CFG.translation_targets.forEach((t) => { const o = document.createElement("option"); o.textContent = t; tr.appendChild(o); });
    } catch (e) { $("healthLine").textContent = "Cannot reach the API: " + e.message; }
  })();

  // ---------- step 1 ----------
  let srcMode = "file";
  tabs("srcTabs", (t) => { srcMode = t; document.querySelectorAll("[data-pane]").forEach((p) => p.classList.toggle("hidden", p.dataset.pane !== t)); });
  document.querySelectorAll('a[data-mode="url"]').forEach((a) => a.onclick = () => setTimeout(() => $("srcTabs").querySelector('[data-tab="url"]').click(), 50));
  const drop = $("drop"), fileInput = $("fileInput");
  fileInput.onchange = () => $("fileName").textContent = fileInput.files[0] ? `${fileInput.files[0].name} · ${(fileInput.files[0].size / 1e6).toFixed(1)} MB` : "No file selected";
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => { if (e.dataTransfer.files[0]) { fileInput.files = e.dataTransfer.files; fileInput.onchange(); } });
  $("modeSel").onchange = () => { const smart = $("modeSel").value === "smart"; $("diarChk").disabled = smart; $("tsChk").disabled = smart; };

  $("goBtn").onclick = async () => {
    clearErr("err1");
    const smart = $("modeSel").value === "smart";
    const settings = { language_codes: $("langSel").value, diarization: !smart && $("diarChk").checked, word_timestamps: !smart && $("tsChk").checked, smart_mode: smart, custom_vocabulary: $("vocabInput").value, fix_urdu_script: $("fixChk").checked };
    try {
      let job;
      $("goBtn").disabled = true; $("progress").classList.remove("hidden"); $("barFill").style.width = "2%"; $("progMsg").textContent = "Uploading…"; $("progTime").textContent = "";
      if (srcMode === "file") {
        if (!fileInput.files[0]) throw new Error("Choose a file first");
        const fd = new FormData(); fd.append("file", fileInput.files[0]); Object.entries(settings).forEach(([k, v]) => fd.append(k, String(v)));
        job = await api("/api/transcribe", { method: "POST", body: fd });
      } else {
        if (!$("urlInput").value.trim()) throw new Error("Paste a URL first");
        $("progMsg").textContent = "Downloading audio…";
        job = await api("/api/transcribe/url", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: $("urlInput").value.trim(), ...settings, language_codes: settings.language_codes.split(",").filter(Boolean), custom_vocabulary: settings.custom_vocabulary.split(",").map((s) => s.trim()).filter(Boolean) }) });
      }
      state.job = job.job_id;
      await pollJob(job.job_id);
    } catch (e) { showErr("err1", e); $("progress").classList.add("hidden"); }
    finally { $("goBtn").disabled = false; }
  };

  const pollJob = (id) => new Promise((resolve, reject) => {
    const tick = async () => {
      try {
        const p = await api(`/api/jobs/${id}`);
        $("barFill").style.width = Math.round(p.fraction * 100) + "%";
        $("progMsg").textContent = p.message;
        $("progTime").textContent = p.estimate ? `elapsed ${fmt(p.elapsed)} · est. ~${fmt(p.estimate)} · remaining ~${p.remaining > 0 ? fmt(p.remaining) : "almost done"}` : `elapsed ${fmt(p.elapsed)}`;
        if (p.status === "done") { const r = await api(`/api/jobs/${id}/result`); $("progMsg").textContent = `Done in ${fmt(r.took_seconds)}`; showResult(r); resolve(r); }
        else if (p.status === "error") reject(new Error(p.error || "Transcription failed"));
        else setTimeout(tick, 700);
      } catch (e) { reject(e); }
    };
    tick();
  });

  // ---------- step 3 ----------
  let tView = "text";
  const showResult = (r) => {
    state.result = r; state.translations = {};
    $("step3").classList.remove("hidden"); $("step4").classList.remove("hidden");
    $("tStats").textContent = `${r.text.length.toLocaleString()} chars · ${r.cues.length} cues · ${r.speakers.length} speaker(s) · ${fmt(r.duration || 0)} media · ${r.chunks} chunk(s)`;
    $("dlRow").innerHTML = [["txt", ".txt"], ["speakers", "speakers .txt"], ["srt", ".srt"], ["vtt", ".vtt"]].map(([f, l]) => `<a class="btn btn-ghost small-btn" href="${API}/api/jobs/${r.id}/download/${f}">Download ${l}</a>`).join("");
    renderT(); updateSrcLine();
    $("step3").scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const renderT = () => { const r = state.result; if (!r) return; const v = { text: r.text, speakers: r.speakers_text || "(enable diarization to get speaker turns)", srt: r.srt, vtt: r.vtt }[tView];
    const ta = $("tView"); ta.value = v; ta.classList.toggle("rtl-area", tView !== "srt" && tView !== "vtt" && isRtl(v)); };
  tabs("tTabs", (t) => { tView = t; renderT(); });

  // ---------- step 2 images ----------
  $("imgInput").onchange = () => {
    state.images = Array.from($("imgInput").files).slice(0, 10);
    $("thumbs").innerHTML = state.images.map((f) => `<img src="${URL.createObjectURL(f)}" alt="${escapeHtml(f.name)}">`).join("");
    $("imgGo").disabled = state.images.length === 0;
  };
  const imgForm = () => { const fd = new FormData(); state.images.forEach((f) => fd.append("images", f)); fd.append("language", $("imgLang").value); return fd; };
  $("imgGo").onclick = async () => {
    clearErr("err2"); $("imgGo").disabled = true; $("imgGo").textContent = "Reading images…";
    try {
      const r = await api("/api/images/analyse", { method: "POST", body: imgForm() });
      state.imageData = r.data;
      $("imgResult").classList.remove("hidden"); $("imgTitle").textContent = `${r.data.title} · ${r.data.content_type} · ${r.data.detected_language}`;
      $("imgDesc").textContent = r.data.description; $("imgPoints").innerHTML = r.data.key_points.map((k) => `<li>${escapeHtml(k)}</li>`).join("");
      const ta = $("imgText"); ta.value = r.data.extracted_text; ta.classList.toggle("rtl-area", isRtl(ta.value));
      $("imgDl").href = blobUrl(r.markdown, "text/markdown");
      $("step4").classList.remove("hidden"); updateSrcLine();
    } catch (e) { showErr("err2", e); }
    finally { $("imgGo").disabled = false; $("imgGo").textContent = "Extract text & describe"; }
  };
  $("imgAsk").onclick = async () => {
    clearErr("err2"); const q = $("imgQ").value.trim(); if (!q || !state.images.length) return;
    const fd = imgForm(); fd.append("question", q); fd.append("context", state.result ? state.result.text : "");
    $("imgAsk").disabled = true;
    try { const r = await api("/api/images/ask", { method: "POST", body: fd }); const a = $("imgAnswer"); a.textContent = r.answer; a.classList.remove("hidden"); a.classList.toggle("rtl", isRtl(r.answer)); }
    catch (e) { showErr("err2", e); } finally { $("imgAsk").disabled = false; }
  };
  $("useImages").onchange = updateSrcLine;

  // ---------- step 4 ----------
  const sourceText = () => {
    const parts = []; if (state.result) parts.push(state.result.text);
    if (state.imageData && $("useImages").checked) parts.push(`[Content of ${state.images.length} uploaded image(s): ${state.imageData.content_type}]\nDescription: ${state.imageData.description}\n\nExtracted text:\n${state.imageData.extracted_text}`);
    return parts.join("\n\n");
  };
  function updateSrcLine() { const s = []; if (state.result) s.push("transcript"); if (state.imageData && $("useImages").checked) s.push("image text"); $("srcLine").textContent = s.length ? `Source: ${s.join(" + ")} · nothing runs automatically` : ""; }
  tabs("gTabs", (t) => document.querySelectorAll("[data-gpane]").forEach((p) => p.classList.toggle("hidden", p.dataset.gpane !== t)));
  const post = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const busy = async (btn, label, fn) => { const old = btn.textContent; btn.disabled = true; btn.textContent = label; clearErr("err4"); try { await fn(); } catch (e) { showErr("err4", e); } finally { btn.disabled = false; btn.textContent = old; } };

  $("trGo").onclick = () => busy($("trGo"), "Translating…", async () => {
    const target = $("trTarget").value;
    const r = await post("/api/generate/translate", { text: sourceText(), target, cues: state.result ? state.result.cues : null });
    const ta = $("trView"); ta.value = r.text; ta.classList.remove("hidden"); ta.classList.toggle("rtl-area", isRtl(r.text));
    const links = [`<a class="btn btn-ghost small-btn" href="${blobUrl(r.text)}" download="translation.${target}.txt">.txt</a>`];
    if (r.srt) links.push(`<a class="btn btn-ghost small-btn" href="${blobUrl(r.srt)}" download="translation.${target}.srt">.srt</a>`, `<a class="btn btn-ghost small-btn" href="${blobUrl(r.vtt, "text/vtt")}" download="translation.${target}.vtt">.vtt</a>`);
    $("trDl").innerHTML = links.join("");
  });

  $("qGo").onclick = () => busy($("qGo"), "Generating…", async () => {
    const r = await post("/api/generate/quiz", { text: sourceText(), n: +$("qN").value, difficulty: $("qDiff").value, language: $("qLang").value });
    const q = r.data, L = "ABCD";
    $("quizBox").innerHTML = `<h3 class="display">${escapeHtml(q.title)}</h3>` + q.questions.map((qu, i) => `<div class="q" data-i="${i}"><b>Q${i + 1}. ${escapeHtml(qu.question)}</b>${qu.options.slice(0, 4).map((o, j) => `<div class="opt" data-j="${j}">${L[j]}. ${escapeHtml(o.text)}</div>`).join("")}${qu.hint ? `<div class="faint small">Hint: ${escapeHtml(qu.hint)}</div>` : ""}<div class="why hidden"></div></div>`).join("") + `<button class="btn btn-accent" id="qCheck" type="button">Check answers</button><div id="qScore" class="muted"></div>`;
    $("quizBox").querySelectorAll(".opt").forEach((o) => o.onclick = () => { o.parentElement.querySelectorAll(".opt").forEach((x) => x.classList.remove("picked")); o.classList.add("picked"); o.style.borderColor = "var(--accent)"; o.parentElement.querySelectorAll(".opt").forEach((x) => { if (x !== o) x.style.borderColor = ""; }); });
    $("qCheck").onclick = () => { let score = 0; q.questions.forEach((qu, i) => { const box = $("quizBox").querySelector(`.q[data-i="${i}"]`); const picked = box.querySelector(".opt.picked"); const cj = qu.options.findIndex((o) => o.is_correct);
      box.querySelectorAll(".opt").forEach((x, j) => { x.classList.toggle("right", j === cj); x.classList.toggle("wrong", picked === x && j !== cj); });
      if (picked && +picked.dataset.j === cj) score++; const why = box.querySelector(".why"); why.textContent = qu.options[cj]?.rationale || ""; why.classList.remove("hidden"); });
      $("qScore").textContent = `Score: ${score} / ${q.questions.length}`; };
    $("qDl").href = blobUrl(r.markdown, "text/markdown"); $("qDl").classList.remove("hidden");
  });

  $("nGo").onclick = () => busy($("nGo"), "Writing notes…", async () => {
    const r = await post(`/api/generate/${$("nKind").value}`, { text: sourceText(), language: $("nLang").value });
    $("notesBox").innerHTML = md(r.markdown); $("notesBox").classList.toggle("rtl", isRtl(r.markdown)); $("nDl").href = blobUrl(r.markdown, "text/markdown"); $("nDl").classList.remove("hidden");
  });

  $("mGo").onclick = () => busy($("mGo"), "Writing minutes…", async () => {
    const r = await post("/api/generate/minutes", { text: sourceText(), language: $("mLang").value });
    $("minutesBox").innerHTML = md(r.markdown); $("minutesBox").classList.toggle("rtl", isRtl(r.markdown)); $("mDl").href = blobUrl(r.markdown, "text/markdown"); $("mDl").classList.remove("hidden");
  });
})();

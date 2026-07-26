// app.js -- fetches the bias snapshot, renders the single-screen dashboard.

const $ = (id) => document.getElementById(id);
const fmt = (n, d = 2) => (n == null ? "\u2014" : Number(n).toLocaleString(undefined, { maximumFractionDigits: d }));
const money = (n) => {
  if (n == null) return "\u2014";
  const a = Math.abs(n);
  if (a >= 1e9) return (n / 1e9).toFixed(2) + "B";
  if (a >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (a >= 1e3) return (n / 1e3).toFixed(0) + "K";
  return n.toFixed(0);
};
const biasClass = (l) => l.includes("LONG") ? "up" : l.includes("SHORT") ? "down" : "flat";

function render(d) {
  const ratio = d.ratio || 0;
  const nq = (p) => (ratio && p != null) ? Math.round(p * ratio).toLocaleString() : null;
  const nqSub = (p) => { const v = nq(p); return v ? `<span class="nq">\u2248 ${v}</span>` : ""; };

  // header
  $("ticker").textContent = d.ticker;
  $("generatedAt").textContent = d.generated_at;
  $("mockBadge").classList.toggle("hidden", !d.mock);
  $("expiriesBadge").textContent = d.expiries_loaded + " EXP";

  // hero
  const b = d.bias;
  const hb = $("biasLabel");
  hb.textContent = b.label; hb.className = "hero-bias " + biasClass(b.label);
  $("biasScore").textContent = b.score;
  $("biasConviction").textContent = b.conviction;
  $("biasSummary").textContent = b.summary;

  // level action map
  $("levelMap").innerHTML = (d.level_map || []).map(r =>
    `<li class="${r.cls}"><span class="lm-price">${fmt(r.price)}${nqSub(r.price)}</span>` +
    `<span class="lm-role">${r.role}</span><span class="lm-tag ${r.cls}">${r.tag}</span></li>`).join("");
  const nz = $("negZone");
  if (d.neg_zone) { nz.textContent = "\u26A0 " + d.neg_zone.note; nz.classList.remove("hidden"); }
  else nz.classList.add("hidden");

  // gex chips
  const g = d.gex, em = d.expected_move;
  $("gexNet").textContent = "$" + money(g.net_gex);
  const reg = $("gexRegime"); reg.textContent = g.regime + " gamma"; reg.className = "tag " + g.regime;
  $("gexMagnet").innerHTML = fmt(g.control_node) + nqSub(g.control_node);
  $("gexFlip").innerHTML = fmt(g.gamma_flip) + nqSub(g.gamma_flip);
  $("gexCallWall").innerHTML = fmt(g.call_wall) + nqSub(g.call_wall);
  $("gexPutWall").innerHTML = fmt(g.put_wall) + nqSub(g.put_wall);
  $("gexPC").textContent = fmt(g.put_call_ratio);
  $("gexRatio").textContent = ratio ? ratio.toFixed(2) + "\u00D7" : "\u2014";
  $("gexEM").textContent = em ? `\u00B1$${em.dollars} (${em.pct}%)` : "\u2014";
  $("gexRange").innerHTML = em ? `${fmt(em.low)}\u2013${fmt(em.high)}` + (ratio ? `<span class="nq">NQ ${nq(em.low)}\u2013${nq(em.high)}</span>` : "") : "\u2014";
  drawGex(g);

  // session levels
  const L = d.levels;
  $("levelsTable").innerHTML = [
    ["Spot", L.spot], ["PD High", L.prior_day_high], ["PD Mid", L.prior_day_mid],
    ["PD Low", L.prior_day_low], ["ON High", L.overnight_high], ["ON Low", L.overnight_low],
  ].map(([k, v]) => `<tr><td>${k}</td><td>${fmt(v)}</td></tr>`).join("");

  // smt
  const sc = d.smt.lean > 0 ? "up" : d.smt.lean < 0 ? "down" : "none";
  const se = $("smtSignal"); se.textContent = d.smt.signal.replace(/_/g, " ").toUpperCase(); se.className = "smt-signal " + sc;
  $("smtNote").textContent = d.smt.note;

  // confluence
  $("expiryConfluence").innerHTML = (d.expiry_confluence || []).length
    ? d.expiry_confluence.map(c => `<li><b>${c.type} ${fmt(c.price)}</b> \u2014 <span class="${c.full ? 'conf-full' : ''}">${c.count}/${c.total}${c.full ? ' \u2713' : ''}</span></li>`).join("")
    : `<li class="muted">No multi-expiry agreement.</li>`;
  $("confluences").innerHTML = d.confluences.length
    ? d.confluences.map(c => `<li><b>${fmt(c.price)}</b> \u2014 ${c.label}</li>`).join("")
    : `<li class="muted">None right now.</li>`;

  // news
  $("news").innerHTML = (d.news.items || []).map(n =>
    `<li><span class="impact-${n.impact}">${n.time ? n.time + " " : ""}${n.event}</span></li>`).join("")
    || `<li class="muted">No items.</li>`;

  // why
  $("signals").innerHTML = b.signals.map(s => {
    const cls = s.lean > 0 ? "up" : s.lean < 0 ? "down" : "";
    return `<li><span class="sig-name ${cls}">${s.name}</span><span class="sig-reason">${s.reason}</span></li>`;
  }).join("");

  // brief
  $("brief").innerHTML = mdLite(d.brief);

  // track record
  const t = d.track || {};
  const rate = t.dir_hit_rate;
  const re = $("trackRate");
  re.querySelector("span").textContent = rate != null ? rate + "%" : "—";
  re.className = "track-rate " + (rate == null ? "" : rate >= 55 ? "good" : rate <= 45 ? "bad" : "mid");
  $("trackRecord").textContent = t.n ? `${t.wins}\u2013${t.losses} record` : "no data yet";
  $("trackOverall").textContent = t.n ? `${t.hit_rate}% overall \u00B7 ${t.n} graded${t.pending ? ` \u00B7 ${t.pending} pending` : ""}` : "build history to grade";
  $("trackDots").innerHTML = (t.recent || []).map(r =>
    `<span class="dot ${r.correct ? 'win' : 'loss'}" title="${r.date} ${r.bias} \u2192 ${r.actual} (${r.move_pct}%)"></span>`).join("");
  const bt = t.by_type || {};
  $("trackByType").innerHTML = ["LONG", "SHORT", "NEUTRAL"].filter(k => bt[k]).map(k =>
    `${k[0] + k.slice(1).toLowerCase()} <b>${bt[k].wins}/${bt[k].n}</b>`).join(" \u00B7 ");
  $("trackNote").textContent = (t.n && t.n < 30)
    ? `\u26A0 Small sample (${t.n}) — treat as noise until ~30+. Directional baseline is 50%.`
    : "";
}

function mdLite(s) {
  const lines = s.split("\n"); let html = "", inList = false;
  for (let ln of lines) {
    ln = ln.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    if (/^\s*[-*]\s+/.test(ln)) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += "<li>" + ln.replace(/^\s*[-*]\s+/, "") + "</li>";
    } else { if (inList) { html += "</ul>"; inList = false; } if (ln.trim()) html += "<p>" + ln + "</p>"; }
  }
  if (inList) html += "</ul>";
  return html;
}

// --- GEX-by-strike chart (pure SVG) ----------------------------------------
function drawGex(g) {
  const svg = $("gexChart");
  const W = 660, H = 420, padL = 66, padR = 86, padT = 14, padB = 26;
  let prof = g.profile.filter(p => Math.abs(p.strike - g.spot) / g.spot < 0.03);
  if (prof.length < 6) prof = g.profile;
  const maxAbs = Math.max(...prof.map(p => Math.abs(p.gex)), 1);
  const strikes = prof.map(p => p.strike);
  const sMin = Math.min(...strikes), sMax = Math.max(...strikes);
  const y = (s) => padT + (1 - (s - sMin) / (sMax - sMin || 1)) * (H - padT - padB);
  const midX = padL + (W - padL - padR) / 2;
  const halfW = (W - padL - padR) / 2;
  const barH = Math.max(2, (H - padT - padB) / prof.length - 1.5);

  let s = `<line x1="${midX}" y1="${padT}" x2="${midX}" y2="${H - padB}" stroke="#1e2733"/>`;
  for (const p of prof) {
    const w = (Math.abs(p.gex) / maxAbs) * halfW;
    const yy = y(p.strike) - barH / 2;
    const pos = p.gex >= 0;
    s += `<rect x="${pos ? midX : midX - w}" y="${yy}" width="${w}" height="${barH}" rx="1" fill="${pos ? '#26a69a' : '#ef5350'}" opacity="0.85"/>`;
  }
  // dashed reference lines
  const line = (val, color, label, side) => {
    if (val == null) return "";
    const yy = y(val);
    const tx = side === "right" ? W - padR + 5 : padL - 6;
    const anchor = side === "right" ? "start" : "end";
    return `<line x1="${padL}" y1="${yy}" x2="${W - padR}" y2="${yy}" stroke="${color}" stroke-dasharray="4 3" opacity="0.85"/>`
      + `<text x="${tx}" y="${yy + 3}" fill="${color}" font-size="10" font-family="monospace" text-anchor="${anchor}">${label}</text>`;
  };
  s += line(g.spot, "#cdd6e4", "spot " + g.spot, "left");
  s += line(g.gamma_flip, "#e6b450", "flip " + g.gamma_flip, "left");
  s += line(g.call_wall, "#26a69a", "CALL WALL " + g.call_wall, "right");
  s += line(g.put_wall, "#ef5350", "PUT WALL " + g.put_wall, "right");
  // axis + legend
  s += `<text x="4" y="${padT + 8}" fill="#6b7888" font-size="10" font-family="monospace">${fmt(sMax)}</text>`;
  s += `<text x="4" y="${H - padB}" fill="#6b7888" font-size="10" font-family="monospace">${fmt(sMin)}</text>`;
  s += `<text x="${midX + 6}" y="${H - 8}" fill="#26a69a" font-size="9" font-family="monospace">+ call gamma (resistance) \u2192</text>`;
  s += `<text x="${midX - 6}" y="${H - 8}" fill="#ef5350" font-size="9" font-family="monospace" text-anchor="end">\u2190 put gamma (support)</text>`;
  svg.innerHTML = s;
}

// --- loaders + live-feed control -------------------------------------------
let pollTimer = null;

async function load() {
  try { render(await (await fetch("/api/bias")).json()); } catch (e) {}
}

function setFeed(on) {
  const fs = document.querySelector(".feed-status");
  fs.classList.toggle("paused", !on);
  $("feedLabel").textContent = on ? "LIVE" : "PAUSED";
  $("startBtn").disabled = on;
  $("stopBtn").disabled = !on;
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  load();
  pollTimer = setInterval(load, 60000);
  setFeed(true);
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  setFeed(false);
}

startPolling();   // live on page load

$("startBtn").addEventListener("click", async () => {
  try { render(await (await fetch("/api/start", { method: "POST" })).json()); } catch (e) {}
  startPolling();
});

$("stopBtn").addEventListener("click", async () => {
  stopPolling();
  try { await fetch("/api/stop", { method: "POST" }); } catch (e) {}
});

$("refreshBtn").addEventListener("click", async () => {
  const btn = $("refreshBtn");
  btn.classList.add("spin"); btn.textContent = "\u21BB Refreshing\u2026";
  try { render(await (await fetch("/api/refresh", { method: "POST" })).json()); }
  catch (e) {}
  btn.classList.remove("spin"); btn.textContent = "\u21BB Refresh";
});

$("logBtn").addEventListener("click", async () => {
  const btn = $("logBtn"); btn.textContent = "Logging\u2026";
  try { await fetch("/api/log", { method: "POST" }); btn.textContent = "\u2713 Logged"; }
  catch { btn.textContent = "\u2717 Failed"; }
  setTimeout(() => (btn.textContent = "\u2913 Obsidian"), 2500);
});

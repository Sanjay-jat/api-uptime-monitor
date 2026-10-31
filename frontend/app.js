"use strict";
const API_URL = "http://localhost:8000"; // backend base URL, change here only
const WS_URL = API_URL.replace(/^http/, "ws") + "/ws/dashboard";
const MAX_EPS = 10;
const $ = (s) => document.querySelector(s);
const app = $("#app");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const p2 = (n) => String(n).padStart(2, "0");
const hms = (d) => { d = new Date(d); return `${p2(d.getHours())}:${p2(d.getMinutes())}:${p2(d.getSeconds())}`; };
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const dmy = (d) => { d = new Date(d); return `${d.getDate()} ${MON[d.getMonth()]}, ${hms(d)}`; };
const mins = (ms) => { const m = Math.max(1, Math.round(ms / 6e4)); return m < 60 ? `${m} min` : m < 1440 ? `${Math.round(m / 6) / 10} h` : `${Math.round(m / 144) / 10} d`; };
const every = (s) => s >= 3600 && s % 3600 === 0 ? (s === 3600 ? "1 hour" : `${s / 3600} hours`) : s % 60 === 0 ? `${s / 60} min` : `${Math.round(s / 6) / 10} min`;
const host = (u) => { try { return new URL(u).host; } catch { return u; } };
 
/* ---------- state ---------- */
const S = { eps: [], last: {}, st: {}, inc: {}, ws: null, tries: 0, cur: null };
let nav = 0;
const tok = {
  get a() { return localStorage.getItem("ua"); },
  get r() { return localStorage.getItem("ur"); },
  set(p) { localStorage.setItem("ua", p.access_token); localStorage.setItem("ur", p.refresh_token); },
  clear() { localStorage.removeItem("ua"); localStorage.removeItem("ur"); },
};
 
/* ---------- api ---------- */
let refreshing = null;
function refresh() {
  if (!refreshing) {
    refreshing = fetch(API_URL + "/auth/refresh", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: tok.r }) })
      .then((r) => { if (!r.ok) throw 0; return r.json(); })
      .then((p) => { tok.set(p); return true; })
      .catch(() => false)
      .finally(() => { refreshing = null; });
  }
  return refreshing;
}
function errMsg(r, d) {
  if (r.status === 429) { const s = r.headers.get("Retry-After"); return `Too many tries. Wait ${s ? s + " seconds" : "a moment"} and try again.`; }
  if (Array.isArray(d.detail)) return d.detail[0]?.msg || "Check the fields and try again.";
  if (typeof d.detail === "string" && r.status < 500) return d.detail;
  return "Something went wrong on our side. Try again in a moment.";
}
async function api(path, { method = "GET", body, auth = true } = {}, retry = true) {
  let r;
  try {
    r = await fetch(API_URL + path, {
      method,
      headers: { ...(body && { "Content-Type": "application/json" }), ...(auth && tok.a && { Authorization: "Bearer " + tok.a }) },
      body: body && JSON.stringify(body),
    });
  } catch { throw { status: 0, msg: "Cannot reach the server. Check your connection and try again." }; }
  if (r.status === 401 && auth) {
    if (retry && tok.r && (await refresh())) return api(path, { method, body, auth }, false);
    signOut(true);
    throw { status: 401, msg: "Your session ended. Sign in again." };
  }
  if (r.status === 204) return null;
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw { status: r.status, msg: errMsg(r, d), fields: Array.isArray(d.detail) ? d.detail : null };
  return d;
}
 
/* ---------- shell ---------- */
const LINKS = [["#/", "Endpoints"], ["#/alerts", "Alerts"], ["#/account", "Account"]];
function shell(h) {
  const cur = h.startsWith("#/alerts") ? "#/alerts" : h.startsWith("#/account") ? "#/account" : "#/";
  const html = LINKS.map(([href, t]) => `<a href="${href}"${href === cur ? ' aria-current="page"' : ""}>${t}</a>`).join("");
  $("#nav").innerHTML = html; $("#tabs").innerHTML = html;
  document.body.classList.toggle("auth", h === "#/signin");
}
function setLive(s) { const el = $("#live"); el.dataset.s = s; el.textContent = s === "on" ? "Live" : s === "wait" ? "Connecting" : "Offline, retrying"; }
let tt;
function toast(t) { const el = $("#toast"); el.textContent = t; el.classList.add("on"); clearTimeout(tt); tt = setTimeout(() => el.classList.remove("on"), 4000); }
const set = (h) => { app.innerHTML = h; };
const skeleton = () => set(`<div aria-busy="true" aria-label="Loading"><div class="sk" style="width:55%;height:56px"></div><div class="sk" style="width:35%"></div><div class="sk" style="margin-top:64px"></div><div class="sk"></div><div class="sk"></div></div>`);
const go = (h) => { if (location.hash === h) route(); else location.hash = h; };
 
/* ---------- live socket ---------- */
function applyLive(d) {
  S.last[d.endpoint_id] = { ok: d.ok, status_code: d.status_code, response_ms: d.response_ms, checked_at: d.checked_at };
  S.st[d.endpoint_id] = d.status;
}
function onUpdate(d) {
  const was = S.st[d.endpoint_id];
  applyLive(d);
  const c = S.cur;
  if (!c) return;
  if (c.kind === "home") { if (was !== d.status) c.reload(); else drawHome(); }
  else if (c.kind === "detail" && String(c.id) === String(d.endpoint_id)) c.reload();
}
function connect() {
  if (S.ws || !tok.a) return;
  setLive("wait");
  const ws = new WebSocket(WS_URL); S.ws = ws;
  let ok = false;
  ws.onopen = () => ws.send(JSON.stringify({ token: tok.a }));
  ws.onmessage = (ev) => {
    let m; try { m = JSON.parse(ev.data); } catch { return; }
    if (!ok) { ok = true; S.tries = 0; setLive("on"); }
    if (m.type === "snapshot") { m.data.forEach(applyLive); if (S.cur?.kind === "home") drawHome(); }
    else if (m.type === "update") onUpdate(m.data);
  };
  ws.onclose = async (ev) => {
    if (S.ws !== ws) return;
    S.ws = null;
    if (!tok.a) return;
    setLive("off");
    if (ev.code === 1008 && !ok && !(await refresh())) { signOut(true); return; }
    setTimeout(connect, Math.min(30000, 1000 * 2 ** S.tries++));
  };
}
function signOut(expired) {
  const r = tok.r;
  if (r && !expired) fetch(API_URL + "/auth/logout", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: r }) }).catch(() => {});
  tok.clear(); localStorage.removeItem("uwh");
  const ws = S.ws; S.ws = null; ws?.close();
  Object.assign(S, { eps: [], last: {}, st: {}, inc: {}, cur: null });
  S.flash = expired ? "Your session ended. Sign in again." : "";
  go("#/signin");
}
 
/* ---------- endpoint helpers ---------- */
const LBL = { up: "Up", down: "Down", pause: "Paused", wait: "Waiting for first check" };
function state(e) {
  if (!e.is_active) return "pause";
  if (!S.last[e.id]) return "wait";
  return S.st[e.id] || e.status || "up";
}
const what = (p, e) => !p || p.ok ? "" : ({
  unexpected_status: `Unexpected status. Expected ${e.expected_status}.`,
  timeout: `Timed out after ${e.timeout_seconds} seconds.`,
  connection_error: "Could not connect.",
  blocked_url: "This address is not allowed.",
}[p.error] || "The check failed.");
const join = (a) => a.length < 2 ? a.join("") : a.slice(0, -1).join(", ") + " and " + a.at(-1);
async function loadLast(eps) {
  await Promise.all(eps.map(async (e) => {
    if (e.status) S.st[e.id] = e.status;
    const p = (await api(`/endpoints/${e.id}/pings?limit=1`).catch(() => []))[0];
    const l = S.last[e.id];
    if (p && (!l || new Date(p.checked_at) >= new Date(l.checked_at))) S.last[e.id] = p;
  }));
}
 
/* ---------- home ---------- */
const acts = (e) => `<button class="lnk" data-act="toggle" data-id="${e.id}">${e.is_active ? "Pause" : "Resume"}</button><a class="lnk" href="#/e/${e.id}/edit">Edit</a><button class="lnk strong" data-act="del" data-id="${e.id}">Delete</button>`;
function rowH(e) {
  const s = state(e), l = S.last[e.id];
  return `<li class="row ${s}"><div class="st"><i class="sq ${s}"></i>${LBL[s]}</div>
<div class="ad"><a class="url" href="#/e/${e.id}">${esc(e.url)}</a><div class="meta"><span>${e.method}</span><span>Every ${every(e.interval_seconds)}</span><span>${l ? "Checked " + hms(l.checked_at) : "Not checked yet"}</span></div></div>
<div class="ms mono">${l?.response_ms != null ? `<b>${l.response_ms}</b> ms` : "—"}</div><div class="cd mono">${l?.status_code ?? "—"}</div><div class="acts">${acts(e)}</div></li>`;
}
function drawHome() {
  const eps = S.eps, n = eps.length, st = eps.map(state);
  const c = (k) => st.filter((x) => x === k).length;
  const up = c("up"), down = c("down"), pa = c("pause"), wa = c("wait");
  const extra = [pa && `${pa} ${pa === 1 ? "is" : "are"} paused`, wa && `${wa} ${wa === 1 ? "is" : "are"} waiting for its first check`].filter(Boolean);
  let h1, sub;
  if (!n) { h1 = "No endpoints yet."; sub = "Add the first web address you want us to watch."; }
  else if (down) { h1 = `${down} ${down === 1 ? "endpoint is" : "endpoints are"} down.`; sub = `The other ${up} running ${up === 1 ? "endpoint is" : "endpoints are"} fine.${extra.length ? " " + join(extra).replace(/^./, (x) => x.toUpperCase()) + "." : ""}`; }
  else if (up) { h1 = "Everything is running."; sub = join([`${up} ${up === 1 ? "is" : "are"} up`, ...extra]) + "."; }
  else { h1 = "Nothing is running."; sub = join(extra).replace(/^./, (x) => x.toUpperCase()) + "."; }
  const full = n >= MAX_EPS;
  const banners = eps.filter((e) => state(e) === "down").map((e) => `<div class="banner"><div><b>Incident open</b> ${esc(host(e.url))} stopped answering${S.inc[e.id] ? " at " + `<span class="mono">${hms(S.inc[e.id].opened_at)}</span>` : ""}. 3 checks in a row failed.</div><a class="lnk strong" href="#/e/${e.id}">View incident</a></div>`).join("");
  set(`<div class="head"><div><h1>${h1}</h1><p class="sub">${esc(sub)}</p></div>
<div class="cta">${full ? `<button class="btn" disabled>Add endpoint</button>` : `<a class="btn" href="#/new">Add endpoint</a>`}<small>${n} of ${MAX_EPS} used${full ? ". Delete one to add another." : ""}</small></div></div>${banners}
${n ? `<div class="cols" aria-hidden="true"><span>Status</span><span>Address</span><span>Response time</span><span>Code</span><span></span></div><ul>${eps.map(rowH).join("")}</ul><p class="foot">Updates by itself when a new check comes in.</p>` : ""}`);
}
async function home(k, silent) {
  if (!silent) skeleton();
  const eps = await api("/endpoints");
  await loadLast(eps);
  S.eps = eps;
  await Promise.all(eps.filter((e) => state(e) === "down").map(async (e) => { S.inc[e.id] = (await api(`/endpoints/${e.id}/incidents?limit=1`).catch(() => []))[0]; }));
  if (k !== nav) return;
  S.cur = { kind: "home", reload: () => home(nav, true).catch(() => {}) };
  drawHome();
}
 
/* ---------- detail ---------- */
async function detail(k, id, silent) {
  if (!silent) skeleton();
  const [e, pings, inc, u1, u7, u30] = await Promise.all([
    api(`/endpoints/${id}`), api(`/endpoints/${id}/pings?limit=50`), api(`/endpoints/${id}/incidents?limit=20`),
    ...["24h", "7d", "30d"].map((w) => api(`/endpoints/${id}/uptime?window=${w}`).catch(() => null)),
  ]);
  if (k !== nav) return;
  if (pings[0]) { const l = S.last[id]; if (!l || new Date(pings[0].checked_at) >= new Date(l.checked_at)) S.last[id] = pings[0]; }
  if (e.status) S.st[id] = e.status;
  const D = { e, pings, more: pings.length === 50, inc, up: [u1, u7, u30] };
  S.cur = { kind: "detail", id, reload: () => detail(nav, id, true).catch(() => {}) };
  drawDetail(D);
}
const pct = (u) => u && u.uptime_percent != null ? `${u.uptime_percent.toFixed(2)}<small>%</small>` : `<span class="n none" style="display:block">No data yet</span>`;
const pingRow = (p, e) => `<div class="tr"><span>${hms(p.checked_at)}</span><span class="${p.ok ? "" : "red"}">${p.ok ? "Worked" : "Failed"}</span><span>${p.status_code ?? "—"}</span><span>${p.response_ms ?? "—"} ms</span><span class="${p.ok ? "w" : "x"}">${esc(what(p, e))}</span></div>`;
function drawDetail(D) {
  const { e, pings, inc } = D, s = state(e), l = pings[0];
  const open = inc.find((i) => !i.resolved_at);
  let banner;
  if (s === "pause") banner = `<div class="rule"></div><p class="note"><b>Paused.</b> We are not checking this endpoint. Resume to start again.</p>`;
  else if (!l) banner = `<div class="rule"></div><p class="note"><b>Waiting for the first check.</b> It runs soon.</p>`;
  else if (s === "down") banner = `<div class="rule down"></div><p class="note"><b class="red">Down since${open ? ` <span class="mono">${hms(open.opened_at)}</span>` : ""}</b> An incident is open. The last check failed${l.status_code ? " with " + l.status_code : ""}.</p>`;
  else banner = `<div class="rule"></div><p class="note"><b>Up.</b> The last check worked at <span class="mono">${hms(l.checked_at)}</span>.</p>`;
  const ok = pings.slice(0, 50).reverse();
  const maxOk = Math.max(0, ...ok.filter((p) => p.ok).map((p) => p.response_ms || 0));
  const bars = ok.map((p) => `<i class="${p.ok ? "" : "f"}" style="height:${p.ok ? Math.max(24, Math.round(((p.response_ms || 0) / (maxOk || 1)) * 100)) : 100}%"></i>`).join("");
  const incs = inc.map((i) => { const end = i.resolved_at ? new Date(i.resolved_at) : Date.now(); const o = !i.resolved_at; return `<div class="tr inc"><span>${dmy(i.opened_at)}</span><span class="${o ? "w" : ""}">${o ? "Still open" : dmy(i.resolved_at)}</span><span>${mins(end - new Date(i.opened_at))}${o ? " so far" : ""}</span><span class="${o ? "x" : "w"}">${o ? "Ongoing" : "Resolved"}</span></div>`; }).join("");
  set(`<p class="crumb"><a href="#/">Endpoints</a> &nbsp;/&nbsp; ${esc(host(e.url))}</p>
<div class="dh"><div><h1>${esc(e.url)}</h1><p class="sub" style="font-size:16px">Checked with ${e.method} every ${every(e.interval_seconds)}. Gives up after ${e.timeout_seconds} seconds.</p></div>
<div class="acts" style="margin-top:8px">${acts(e)}</div></div><div style="height:36px"></div>${banner}
<div class="stats"><div class="stat">Uptime, last 24 hours<span class="n">${pct(D.up[0])}</span></div><div class="stat">Last 7 days<span class="n">${pct(D.up[1])}</span></div><div class="stat">Last 30 days<span class="n">${pct(D.up[2])}</span></div>
<div class="stat">Last response<span class="n">${l?.response_ms != null ? `${l.response_ms}<small> ms</small>` : `<span class="n none" style="display:block">No data yet</span>`}</span></div></div>
<section><h2>How fast it answered</h2>${ok.length ? `<p>Last ${ok.length} checks, oldest on the left. Red bars are failed checks.${maxOk ? ` Slowest working answer: ${maxOk} ms.` : ""}</p><div class="bars" role="img" aria-label="Response time of the last ${ok.length} checks">${bars}</div>` : `<p class="empty">No checks yet. The first one runs soon.</p>`}</section>
<section><h2>Recent checks</h2><p>Newest first.</p>${pings.length ? `<div class="tr th" aria-hidden="true"><span>Time</span><span>Result</span><span>Code</span><span>Response</span><span>What happened</span></div><div id="pl">${pings.map((p) => pingRow(p, e)).join("")}</div>${D.more ? `<button class="btn ghost more" data-act="more">Show older checks</button>` : ""}` : `<p class="empty">Nothing yet.</p>`}</section>
<section><h2>Incidents</h2><p>Opened when 3 checks in a row fail.</p>${inc.length ? `<div class="tr inc th" aria-hidden="true"><span>Started</span><span>Ended</span><span>Lasted</span><span>Status</span></div>${incs}` : `<p class="empty">No incidents. That is good.</p>`}</section>`);
  S.D = D;
}
 
/* ---------- add / edit ---------- */
function parseDur(v, def) {
  const m = String(v).trim().toLowerCase().match(/^(\d+(?:\.\d+)?)\s*([a-z]*)$/);
  if (!m) return NaN;
  const u = m[2] || def;
  const mult = /^s/.test(u) ? 1 : /^m/.test(u) ? 60 : /^h/.test(u) ? 3600 : NaN;
  return Math.round(parseFloat(m[1]) * mult);
}
const fmtI = (s) => s % 3600 === 0 ? `${s / 3600} ${s === 3600 ? "hour" : "hours"}` : s % 60 === 0 ? `${s / 60} ${s === 60 ? "minute" : "minutes"}` : `${s} seconds`;
async function form(k, id) {
  skeleton();
  let e = { url: "", method: "GET", interval_seconds: 60, timeout_seconds: 10, expected_status: 200 };
  if (id) e = await api(`/endpoints/${id}`);
  else { S.eps = await api("/endpoints"); if (S.eps.length >= MAX_EPS) { if (k === nav) set(`<p class="crumb"><a href="#/">Endpoints</a> &nbsp;/&nbsp; New</p><h1>Limit reached.</h1><p class="sub">You use ${MAX_EPS} of ${MAX_EPS} endpoints. Delete one to add another.</p><p style="margin-top:32px"><a class="btn" href="#/">Back to endpoints</a></p>`); return; } }
  if (k !== nav) return;
  S.cur = null;
  const err = (n) => `<p class="err" id="e-${n}" data-err="${n}" hidden></p>`;
  set(`<p class="crumb"><a href="#/">Endpoints</a> &nbsp;/&nbsp; ${id ? esc(host(e.url)) : "New"}</p><h1>${id ? "Edit endpoint" : "Add an endpoint"}</h1><div style="height:56px"></div>
<div class="formgrid"><form id="f" novalidate><div id="gen" class="msg bad" hidden role="alert"></div>
<div class="fld"><label for="url">Web address to watch</label><div class="in"><input id="url" name="url" value="${esc(e.url)}" placeholder="https://api.example.com/health" inputmode="url" autocomplete="off" spellcheck="false" aria-describedby="e-url"></div>${err("url")}</div>
<div class="fld"><span class="lab" id="hm">How to check it</span><div class="seg" role="radiogroup" aria-labelledby="hm"><input type="radio" name="method" id="mg" value="GET"${e.method === "GET" ? " checked" : ""}><label for="mg">GET</label><input type="radio" name="method" id="mh" value="HEAD"${e.method === "HEAD" ? " checked" : ""}><label for="mh">HEAD</label></div><p class="hint">GET loads the whole page. HEAD only asks if it is there, which is lighter.</p></div>
<div class="two fld"><div><label for="iv">Check every</label><div class="in"><input id="iv" name="interval_seconds" value="${fmtI(e.interval_seconds)}" autocomplete="off" aria-describedby="e-interval_seconds"><span>1 min to 24 h</span></div>${err("interval_seconds")}</div>
<div><label for="to">Give up waiting after</label><div class="in"><input id="to" name="timeout_seconds" value="${e.timeout_seconds} seconds" autocomplete="off" aria-describedby="e-timeout_seconds"><span>1 to 30 s</span></div>${err("timeout_seconds")}</div></div>
<div class="fld"><label for="es">Counts as working when it answers</label><div class="in" style="max-width:300px"><input id="es" name="expected_status" value="${e.expected_status}" inputmode="numeric" autocomplete="off" aria-describedby="e-expected_status"></div>${err("expected_status")}<p class="hint" style="max-width:300px">${e.expected_status} means OK. Change it only if your endpoint answers with another code.</p></div>
<div class="btns"><button class="btn" type="submit">${id ? "Save changes" : "Add endpoint"}</button><a class="btn ghost" href="${id ? "#/e/" + id : "#/"}">Cancel</a></div></form>
<aside class="side"><h2 style="font-size:16px">What happens next</h2><p>We check on your schedule. After 3 failed checks in a row, we open an incident and show it here.</p></aside></div>`);
  const f = $("#f");
  const show = (n, m) => { const el = $(`#e-${n}`); if (!el) { const g = $("#gen"); g.textContent = m; g.hidden = false; return; } el.textContent = m; el.hidden = false; f.elements[n]?.setAttribute("aria-invalid", "true"); };
  f.onsubmit = async (ev) => {
    ev.preventDefault();
    f.querySelectorAll(".err").forEach((x) => (x.hidden = true)); f.querySelectorAll("[aria-invalid]").forEach((x) => x.removeAttribute("aria-invalid")); $("#gen").hidden = true;
    const b = { url: f.url.value.trim(), method: f.method.value, interval_seconds: parseDur(f.interval_seconds.value, "min"), timeout_seconds: parseDur(f.timeout_seconds.value, "s"), expected_status: Number(f.expected_status.value) };
    const bad = [];
    if (!/^https?:\/\/[^\s/]+/i.test(b.url)) bad.push(["url", "Use a web address that starts with http:// or https://."]);
    if (!(b.interval_seconds >= 60 && b.interval_seconds <= 86400)) bad.push(["interval_seconds", "Pick between 1 minute and 24 hours. Example: 5 minutes."]);
    if (!(b.timeout_seconds >= 1 && b.timeout_seconds <= 30)) bad.push(["timeout_seconds", "Pick between 1 and 30 seconds."]);
    if (!Number.isInteger(b.expected_status) || b.expected_status < 100 || b.expected_status > 599) bad.push(["expected_status", "Use a status code from 100 to 599."]);
    if (bad.length) { bad.forEach(([n, m]) => show(n, m)); f.elements[bad[0][0]].focus(); return; }
    const btn = f.querySelector("button"); btn.disabled = true; const t = btn.textContent; btn.textContent = "Saving…";
    try {
      await api(id ? `/endpoints/${id}` : "/endpoints", { method: id ? "PATCH" : "POST", body: b });
      toast(id ? "Changes saved." : "Endpoint added."); go(id ? `#/e/${id}` : "#/");
    } catch (x) {
      btn.disabled = false; btn.textContent = t;
      if (x.status === 422 && x.fields) x.fields.forEach((d) => { const n = d.loc?.at(-1); show(n, n === "url" ? (/resolve/i.test(d.msg) ? "We could not find that address. Check the spelling." : "This address is private. Use a public one that starts with http:// or https://.") : d.msg); });
      else if (x.status === 401) return;
      else { const g = $("#gen"); g.textContent = x.msg; g.hidden = false; g.scrollIntoView({ block: "center" }); }
    }
  };
  f.url.focus();
}
 
/* ---------- auth ---------- */
function signin(mode = "in") {
  S.cur = null;
  const reg = mode === "up";
  set(`<div class="authbox"><h1>${reg ? "Create your account" : "Welcome back"}</h1><p class="sub" style="font-size:17px">${reg ? "Add your endpoints and we watch them for you." : "Sign in to see how your endpoints are doing."}</p>
<div class="tablist" role="tablist"><button role="tab" aria-selected="${!reg}" data-act="tab" data-mode="in">Sign in</button><button role="tab" aria-selected="${reg}" data-act="tab" data-mode="up">Create account</button></div>
<form id="af" novalidate><div id="ae" class="msg" role="alert" hidden></div>
<div class="fld"><label for="em">Email</label><div class="in"><input id="em" type="email" name="email" autocomplete="email" required></div></div>
<div class="fld" style="margin-bottom:0"><label for="pw">Password</label><div class="in pw"><input id="pw" type="password" name="password" autocomplete="${reg ? "new-password" : "current-password"}" required><button type="button" class="lnk" data-act="pw" aria-pressed="false">Show</button></div><p class="hint">8 to 72 characters.</p></div>
<button class="btn" type="submit">${reg ? "Create account" : "Sign in"}</button></form></div>`);
  const ae = $("#ae");
  if (S.flash) { ae.textContent = S.flash; ae.hidden = false; S.flash = ""; }
  $("#af").onsubmit = async (ev) => {
    ev.preventDefault();
    const f = ev.target, body = { email: f.email.value.trim(), password: f.password.value };
    ae.hidden = true;
    if (!body.email || body.password.length < 8 || new TextEncoder().encode(body.password).length > 72) { ae.textContent = "Enter your email and a password of 8 to 72 characters."; ae.hidden = false; return; }
    const btn = f.querySelector(".btn"), t = btn.textContent; btn.disabled = true; btn.textContent = "One moment…";
    try {
      if (reg) await api("/auth/register", { method: "POST", body, auth: false });
      tok.set(await api("/auth/login", { method: "POST", body, auth: false }));
      go("#/");
    } catch (x) {
      btn.disabled = false; btn.textContent = t;
      ae.textContent = x.status === 401 ? "That email or password is not right. Check both and try again." : x.status === 409 ? "An account with this email already exists. Sign in instead." : x.msg;
      ae.hidden = false;
    }
  };
}
 
/* ---------- alerts + account ---------- */
async function alerts() {
  S.cur = null;
  const on = localStorage.getItem("uwh") === "1";
  set(`<h1>Alerts</h1><p class="sub">We send a message to your web address when an endpoint goes down and when it comes back.</p><div style="height:48px"></div>
<div class="formgrid"><form id="wf" novalidate><div id="we" class="msg bad" role="alert" hidden></div>
<div class="fld"><label for="wh">Alert web address</label><div class="in"><input id="wh" name="url" placeholder="https://hooks.example.com/uptime" inputmode="url" autocomplete="off" spellcheck="false"></div><p class="hint">${on ? "An alert address is set. Save a new one to replace it." : "No alert address yet. Public addresses only."}</p></div>
<div class="btns"><button class="btn" type="submit">Save alert address</button>${on ? `<button class="btn ghost" type="button" data-act="rmwh">Remove</button>` : ""}</div><div id="sec"></div></form>
<aside class="side" style="margin-top:0"><h2 style="font-size:16px">How we sign messages</h2><p>Each message has an X-Signature header. Check it with the secret shown after you save. Saving again makes a new secret.</p></aside></div>`);
  $("#wf").onsubmit = async (ev) => {
    ev.preventDefault();
    const we = $("#we"), url = ev.target.url.value.trim(); we.hidden = true;
    if (!/^https?:\/\/[^\s/]+/i.test(url)) { we.textContent = "Use a web address that starts with http:// or https://."; we.hidden = false; return; }
    try {
      const r = await api("/auth/me/webhook", { method: "PUT", body: { url } });
      localStorage.setItem("uwh", "1");
      $("#sec").innerHTML = `<div class="msg" style="margin-top:40px"><b>Copy your secret now.</b> It is shown once.<div class="copy"><code id="sv">${esc(r.webhook_secret)}</code><button type="button" class="btn ghost" data-act="copy">Copy</button></div></div>`;
      toast("Alert address saved.");
    } catch (x) { if (x.status === 401) return; we.textContent = x.status === 422 && x.fields ? "This address is private or not valid. Use a public one that starts with http:// or https://." : x.msg; we.hidden = false; }
  };
}
async function account() {
  S.cur = null; skeleton();
  const me = await api("/auth/me");
  set(`<h1>Account</h1><dl class="acc"><dt>Email</dt><dd>${esc(me.email)}</dd><dt>Endpoints</dt><dd>${S.eps.length ? S.eps.length + " of " + MAX_EPS + " used" : "Open Endpoints to see usage"}</dd></dl><button class="btn ghost" data-act="out">Sign out</button>`);
}
const notFound = () => { S.cur = null; set(`<h1>We could not find that.</h1><p class="sub">It may have been deleted, or it is not in your account.</p><p style="margin-top:32px"><a class="btn" href="#/">Back to endpoints</a></p>`); };
const failed = (x) => { S.cur = null; set(`<h1>That did not load.</h1><p class="sub">${esc(x.msg || "Something went wrong.")}</p><p style="margin-top:32px"><button class="btn" data-act="retry">Try again</button></p>`); };
 
/* ---------- router ---------- */
const R = [[/^#\/$/, (k) => home(k)], [/^#\/new$/, (k) => form(k)], [/^#\/e\/(\d+)$/, (k, id) => detail(k, id)], [/^#\/e\/(\d+)\/edit$/, (k, id) => form(k, id)], [/^#\/alerts$/, () => alerts()], [/^#\/account$/, () => account()]];
async function route() {
  const k = ++nav;
  let h = location.hash || "#/";
  if (!tok.a && !tok.r) h = "#/signin"; else if (h === "#/signin") h = "#/";
  if (location.hash !== h) { history.replaceState(null, "", h); }
  shell(h); window.scrollTo(0, 0);
  if (h === "#/signin") { signin(); return; }
  connect();
  const r = R.find(([re]) => re.test(h));
  if (!r) { notFound(); return; }
  try { await r[1](k, ...(h.match(r[0]).slice(1))); }
  catch (x) { if (k !== nav || x.status === 401) return; x.status === 404 ? notFound() : failed(x); }
}
 
/* ---------- clicks ---------- */
document.addEventListener("click", async (ev) => {
  const b = ev.target.closest("[data-act]");
  if (!b) return;
  const { act, id } = b.dataset;
  try {
    if (act === "tab") signin(b.dataset.mode);
    else if (act === "pw") { const i = $("#pw"), s = i.type === "password"; i.type = s ? "text" : "password"; b.textContent = s ? "Hide" : "Show"; b.setAttribute("aria-pressed", s); }
    else if (act === "toggle") { const e = S.eps.find((x) => x.id == id) || S.D?.e; await api(`/endpoints/${id}`, { method: "PATCH", body: { is_active: !e.is_active } }); toast(e.is_active ? "Paused." : "Resumed."); route(); }
    else if (act === "del") {
      const e = S.eps.find((x) => x.id == id) || S.D?.e, d = $("#dlg");
      d.innerHTML = `<form method="dialog"><h2>Delete this endpoint?</h2><p class="mono">${esc(e.url)}</p><p>Its checks and incidents are deleted too. This cannot be undone.</p><div class="btns"><button class="btn" value="ok">Delete endpoint</button><button class="btn ghost" value="no">Cancel</button></div></form>`;
      d.returnValue = "";
      d.onclose = async () => {
        if (d.returnValue !== "ok") return;
        try { await api(`/endpoints/${id}`, { method: "DELETE" }); delete S.last[id]; delete S.st[id]; toast("Endpoint deleted."); go("#/"); } catch (x) { toast(x.msg); }
      };
      d.showModal();
    }
    else if (act === "more") {
      const D = S.D; b.disabled = true;
      const more = await api(`/endpoints/${D.e.id}/pings?limit=50&offset=${D.pings.length}`);
      D.pings.push(...more); D.more = more.length === 50;
      $("#pl").insertAdjacentHTML("beforeend", more.map((p) => pingRow(p, D.e)).join(""));
      if (D.more) b.disabled = false; else b.remove();
    }
    else if (act === "copy") { await navigator.clipboard.writeText($("#sv").textContent); toast("Secret copied."); }
    else if (act === "rmwh") { await api("/auth/me/webhook", { method: "DELETE" }); localStorage.removeItem("uwh"); toast("Alert address removed."); alerts(); }
    else if (act === "out") signOut(false);
    else if (act === "retry") route();
  } catch (x) { if (x.status !== 401) toast(x.msg || "Something went wrong."); b.disabled = false; }
});
 
window.addEventListener("hashchange", route);
window.addEventListener("online", () => { if (!S.ws) connect(); });
route();
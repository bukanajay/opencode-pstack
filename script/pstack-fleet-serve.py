#!/usr/bin/env python3
"""Animated pstack fleet board for opencode (web version).

The CLI board (pstack-fleet.py) is a live table. This is the motion
version: a local page where every agent is a node, live ones glow and
pulse, edges flow toward busy children, and todo progress draws as a
ring. Same store, same cast, zero dependencies beyond Python stdlib.

    python3 script/pstack-fleet-serve.py            # http://127.0.0.1:8901
    python3 script/pstack-fleet-serve.py --open     # plus open a browser
    python3 script/pstack-fleet-serve.py --port 8902 --session ses_abc123
    python3 script/pstack-fleet-serve.py --theme island   # force the village

Query params mirror the CLI flags: ?session=, ?all=1, ?max=, ?fleet=.

Two views share one API: `/` is the cozy village where each agent
is a villager with its own hut, `/graph` is the node graph. Live
villagers wander and work, idle ones go home to rest.
"""

import argparse
import json
import os
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))


def load_core():
    import importlib.util

    path = os.path.join(HERE, "pstack-fleet.py")
    spec = importlib.util.spec_from_file_location("pstack_fleet_core", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CORE = load_core()

HEX = {
    "red": "#f87171", "green": "#4ade80", "yellow": "#facc15",
    "blue": "#60a5fa", "magenta": "#e879f9", "cyan": "#22d3ee",
    "white": "#e5e7eb", "dim": "#6b7280",
    "bright_red": "#fca5a5", "bright_green": "#86efac",
    "bright_yellow": "#fde047", "bright_blue": "#93c5fd",
    "bright_magenta": "#f0abfc", "bright_cyan": "#67e8f9",
    "bright_white": "#ffffff",
}

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>pstack fleet</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; background: #0b0f1a; color: #e5e7eb;
         font: 14px/1.45 -apple-system, "Segoe UI", Inter, sans-serif;
         overflow: hidden; }
  #cv { position: fixed; inset: 0; display: block; }
  header { position: fixed; top: 0; left: 0; right: 0; display: flex;
           align-items: baseline; gap: 14px; padding: 12px 18px;
           pointer-events: none; }
  header h1 { font-size: 15px; margin: 0; letter-spacing: .04em; }
  header h1 .dot { color: #4ade80; animation: blink 1.6s infinite; }
  select#proj { background: #111827; color: #d1d5db; border: 1px solid #374151;
                border-radius: 999px; padding: 4px 10px; font-size: 12px; max-width: 230px; }
  @keyframes blink { 50% { opacity: .25; } }
  header .meta { color: #9ca3af; font-size: 12px; }
  #panel { position: fixed; top: 64px; right: 14px; width: 300px;
           background: rgba(17,24,39,.92); border: 1px solid #1f2937;
           border-radius: 10px; padding: 12px 14px; display: none;
           backdrop-filter: blur(4px); }
  #panel h2 { margin: 0 0 6px; font-size: 14px; }
  #panel dl { margin: 0; font-size: 12px; color: #cbd5e1; }
  #panel dt { color: #6b7280; float: left; width: 74px; }
  #panel dd { margin: 0 0 4px 74px; }
  #panel .x { float: right; cursor: pointer; color: #6b7280; border: 0;
              background: none; font-size: 14px; }
  footer { position: fixed; left: 18px; bottom: 10px; color: #4b5563;
           font-size: 11px; pointer-events: none; }
</style>
</head>
<body>
<canvas id="cv"></canvas>
<header><h1><span class="dot">●</span> pstack fleet</h1><span class="meta" id="meta"></span><select id="proj" title="project"></select><span style="margin-left:auto"><a href="/" style="color:#93c5fd;font-size:12px">chakravyuh</a></span></header>
<aside id="panel"><button class="x" id="px">✕</button><h2 id="p-title"></h2><dl id="p-dl"></dl></aside>
<footer>click a node for detail · live = store changed recently, heuristic</footer>
<script>
"use strict";
const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
const meta = document.getElementById('meta'), panel = document.getElementById('panel');
let W = 0, H = 0;
function resize() {
  const d = Math.min(2, window.devicePixelRatio || 1);
  W = window.innerWidth; H = window.innerHeight;
  cv.width = W * d; cv.height = H * d;
  cv.style.width = W + 'px'; cv.style.height = H + 'px';
  ctx.setTransform(d, 0, 0, d, 0, 0);
}
window.addEventListener('resize', resize); resize();
const stars = Array.from({length: 130}, () => ({x: Math.random(), y: Math.random(), r: Math.random() * 1.3 + .3, p: Math.random() * 6.28}));
let D = {sessions: [], fleet: [], now: 0, live: 0, shown: 0};
let nodes = new Map(), selected = null, pollAt = 0;
const projSel = document.getElementById('proj');
projSel.addEventListener('change', (e) => {
  const u = new URLSearchParams(window.location.search);
  u.set('dir', e.target.value);
  window.location.search = u.toString();
});
function syncProj() {
  const key = (D.projects || []).map(p => p.dir).join(String.fromCharCode(10));
  if (projSel._key !== key) {
    projSel._key = key;
    projSel.innerHTML = '';
    for (const p of (D.projects || [])) {
      const o = document.createElement('option');
      o.value = p.dir;
      o.textContent = (p.dir.split('/').pop() || p.dir) + ' (' + p.sessions + ')';
      projSel.appendChild(o);
    }
  }
  if (document.activeElement !== projSel) projSel.value = D.dir || '';
}
document.getElementById('px').onclick = () => { selected = null; panel.style.display = 'none'; };
cv.addEventListener('click', (e) => {
  let best = null, bd = 34 * 34;
  for (const n of nodes.values()) {
    const dx = n.x - e.clientX, dy = n.y - e.clientY, d = dx * dx + dy * dy;
    if (d < bd) { bd = d; best = n.id; }
  }
  selected = best; panel.style.display = best ? 'block' : 'none';
});
async function poll() {
  try {
    const r = await fetch('api/fleet' + window.location.search);
    D = await r.json(); pollAt = performance.now(); retarget(); syncProj();
  } catch (e) { /* keep last frame on error */ }
  setTimeout(poll, 1500);
}
function retarget() {
  const seen = new Set();
  const roots = D.sessions.filter(s => !s.parent || !D.sessions.some(p => p.id === s.parent));
  roots.forEach((s, i) => {
    seen.add(s.id);
    const kids = D.sessions.filter(k => k.parent === s.id);
    const cx = W * (i + 1) / (roots.length + 1), cy = H * 0.46;
    place(s.id, cx, cy);
    const R = Math.min(200, 96 + kids.length * 16);
    kids.forEach((k, j) => {
      seen.add(k.id);
      const a = kids.length === 1 ? -Math.PI / 2 : (j / kids.length) * Math.PI * 2 - Math.PI / 2;
      place(k.id, cx + Math.cos(a) * R, cy + Math.sin(a) * R * 0.82);
    });
  });
  D.fleet.forEach((f, i) => {
    seen.add(f.id);
    place(f.id, W * (i + 1) / (D.fleet.length + 1), 118);
  });
  for (const id of [...nodes.keys()]) if (!seen.has(id) && id !== selected) nodes.delete(id);
}
function place(id, x, y) {
  let n = nodes.get(id);
  if (!n) { n = {id, x, y, ph: Math.random() * 6.28}; nodes.set(id, n); }
  n.tx = x; n.ty = y;
}
function byId(id) {
  return D.sessions.find(s => s.id === id) || D.fleet.find(f => f.id === id);
}
function qpoint(a, b, t) {
  const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2 - 34;
  const u = 1 - t;
  return {x: u * u * a.x + 2 * u * t * mx + t * t * b.x,
          y: u * u * a.y + 2 * u * t * my + t * t * b.y};
}
function draw(t) {
  ctx.clearRect(0, 0, W, H);
  for (const s of stars) {
    ctx.globalAlpha = .25 + .2 * Math.sin(t / 1400 + s.p);
    ctx.fillStyle = '#93c5fd'; ctx.fillRect(s.x * W, s.y * H, s.r, s.r);
  }
  ctx.globalAlpha = 1;
  // edges parent -> child, flowing toward the child
  for (const s of D.sessions) {
    if (!s.parent || !nodes.has(s.parent) || !nodes.has(s.id)) continue;
    const a = nodes.get(s.parent), b = nodes.get(s.id);
    const col = (s.character && s.character.hex) || '#4b5563';
    ctx.strokeStyle = col; ctx.globalAlpha = s.live ? .75 : .28;
    ctx.lineWidth = s.live ? 2 : 1.25;
    ctx.setLineDash([7, 9]); ctx.lineDashOffset = -t / 28;
    ctx.beginPath(); ctx.moveTo(a.x, a.y);
    ctx.quadraticCurveTo((a.x + b.x) / 2, (a.y + b.y) / 2 - 34, b.x, b.y);
    ctx.stroke(); ctx.setLineDash([]);
    if (s.live) { // packets travelling to busy children
      ctx.fillStyle = col;
      for (let k = 0; k < 2; k++) {
        const p = qpoint(a, b, (t * 0.00045 + k * 0.5 + s.id.length * 0.07) % 1);
        ctx.globalAlpha = .95; ctx.beginPath(); ctx.arc(p.x, p.y, 2.6, 0, 6.29); ctx.fill();
      }
    }
    ctx.globalAlpha = 1;
  }
  for (const [id, n] of nodes) {
    const d = byId(id); if (!d) continue;
    n.x += (n.tx - n.x) * 0.07; n.y += (n.ty - n.y) * 0.07;
    const fx = n.x + Math.sin(t / 1100 + n.ph) * 5, fy = n.y + Math.cos(t / 1300 + n.ph) * 5;
    n.dx = fx; n.dy = fy;
    const col = (d.character && d.character.hex) || '#6b7280';
    const R = d.is_root ? 30 : 25;
    if (d.live) { // breathing halo
      const hr = R + 9 + 3 * Math.sin(t / 420 + n.ph);
      ctx.strokeStyle = col; ctx.globalAlpha = .55; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(fx, fy, hr, 0, 6.29); ctx.stroke();
      ctx.globalAlpha = 1; ctx.shadowColor = col; ctx.shadowBlur = 22;
    }
    ctx.fillStyle = '#111827';
    ctx.beginPath(); ctx.arc(fx, fy, R, 0, 6.29); ctx.fill();
    ctx.shadowBlur = 0;
    ctx.strokeStyle = col; ctx.lineWidth = d.live ? 2.4 : 1.4;
    ctx.globalAlpha = d.live ? 1 : .6;
    ctx.beginPath(); ctx.arc(fx, fy, R, 0, 6.29); ctx.stroke();
    ctx.globalAlpha = 1;
    if (d.todos && d.todos.total) { // progress ring
      ctx.strokeStyle = '#4ade80'; ctx.lineWidth = 3.5;
      ctx.beginPath(); ctx.arc(fx, fy, R - 5, -Math.PI / 2,
        -Math.PI / 2 + Math.PI * 2 * d.todos.done / d.todos.total);
      ctx.stroke();
    }
    ctx.fillStyle = col; ctx.font = '19px sans-serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText((d.character && d.character.symbol) || '·', fx, fy - 2);
    ctx.fillStyle = d.live ? '#f3f4f6' : '#9ca3af';
    ctx.font = (id === selected ? 'bold ' : '') + '12px sans-serif';
    ctx.fillText(short2(d.label), fx, fy + R + 13);
    ctx.fillStyle = '#4b5563'; ctx.font = '10px sans-serif';
    ctx.fillText(d.sub || '', fx, fy + R + 26);
  }
  const ago = ((performance.now() - pollAt) / 1000).toFixed(0);
  meta.textContent = D.live + ' live / ' + D.shown + ' shown · refreshed ' + ago + 's ago';
  if (selected) showPanel(selected);
  requestAnimationFrame(draw);
}
function short2(s) {
  s = s || '';
  return s.length > 30 ? s.slice(0, 29) + '…' : s;
}
function row(k, v) { return '<dt>' + k + '</dt><dd>' + (v || '—') + '</dd>'; }
function showPanel(id) {
  const d = byId(id); if (!d) return;
  document.getElementById('p-title').textContent =
    ((d.character && d.character.symbol + ' ' + d.character.name + ' · ') || '') + d.label;
  document.getElementById('p-dl').innerHTML =
    row('state', d.live ? 'live' : 'idle') + row('agent', d.agent) +
    row('model', d.model) + row('elapsed', d.elapsed) + row('active', d.active) +
    row('todos', d.todos ? d.todos.done + '/' + d.todos.total : null) +
    row('doing', d.todos && d.todos.current) +
    row('tool', d.tool ? d.tool.name + ':' + d.tool.status : null) +
    row('bearing', d.character && d.character.bearing);
}
poll(); requestAnimationFrame(draw);
</script>
</body>
</html>
"""

ISLAND = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>pstack island</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; background: #12241a; color: #e5e7eb;
         font: 14px/1.45 -apple-system, "Segoe UI", Inter, sans-serif;
         overflow: hidden; }
  #cv { position: fixed; inset: 0; display: block; }
  header { position: fixed; top: 12px; left: 14px; right: 14px; display: flex;
           align-items: center; gap: 10px; pointer-events: none; }
  .pill { background: rgba(20,32,24,.85); border: 1px solid #2c4433;
          border-radius: 999px; padding: 5px 13px; font-size: 12px; }
  select.pill { color: #d7e5da; max-width: 220px; }
  select.pill option { color: #111; }
  header nav { margin-left: auto; pointer-events: auto; }
  header nav a { color: #a7c4ad; text-decoration: none; font-size: 12px;
                 background: rgba(20,32,24,.85); border: 1px solid #2c4433;
                 border-radius: 999px; padding: 5px 13px; }
  #card { position: fixed; top: 64px; right: 14px; width: 250px;
          background: #fdf6e3; color: #4a3f2a; border-radius: 12px;
          padding: 12px 14px; display: none;
          box-shadow: 0 8px 30px rgba(0,0,0,.45); }
  #card h2 { margin: 0; font-size: 16px; }
  #card .sub { color: #8a7a58; font-size: 12px; margin-bottom: 8px; }
  #card .tag { display: inline-block; font-size: 11px; border-radius: 999px;
               padding: 2px 10px; margin-right: 6px; }
  #card .work { background: #dcefe0; color: #2f6b3a; }
  #card .rest { background: #e8e2d2; color: #7a6f52; }
  #card .role { background: #e3ecf7; color: #37587e; }
  #card dl { margin: 8px 0 0; font-size: 12px; }
  #card dt { color: #a2936f; float: left; width: 64px; }
  #card dd { margin: 0 0 3px 64px; }
  #card .x { float: right; cursor: pointer; color: #a2936f; border: 0;
             background: none; font-size: 14px; }
  footer { position: fixed; left: 16px; bottom: 10px; color: #5d7a64;
           font-size: 11px; pointer-events: none; }
</style>
</head>
<body>
<canvas id="cv"></canvas>
<header>
  <span class="pill" id="clock"></span>
  <span class="pill">⚙️ <b id="c-work">0</b> working</span>
  <span class="pill">💤 <b id="c-rest">0</b> resting</span>
  <span class="pill">🏠 <b id="c-home">0</b> huts</span>
  <select id="proj" class="pill" title="project"></select>
  <nav><a href="/graph">graph view</a></nav>
</header>
<aside id="card"><button class="x" id="cx">✕</button><h2 id="c-name"></h2>
  <div class="sub" id="c-sub"></div><div id="c-tags"></div><dl id="c-dl"></dl></aside>
<footer>click a villager or hut for detail · villagers rest at home when idle</footer>
<script>
"use strict";
const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
let W = 0, H = 0, geo = null;
function resize() {
  const d = Math.min(2, window.devicePixelRatio || 1);
  W = window.innerWidth; H = window.innerHeight;
  cv.width = W * d; cv.height = H * d;
  cv.style.width = W + 'px'; cv.style.height = H + 'px';
  ctx.setTransform(d, 0, 0, d, 0, 0);
  layout();
}
window.addEventListener('resize', resize);
const TOOL_EMOJI = {bash: '⌨️', read: '📖', edit: '✏️', grep: '🔍', glob: '🗂️',
  task: '📦', skill: '✨', todowrite: '✅', question: '💬', webfetch: '🌐',
  websearch: '🌐', lsp: '🔧'};
const PLOTS = 16;
function seeded(n) { let s = n; return () => (s = (s * 16807) % 2147483647) / 2147483647; }
function layout() {
  const cx = W / 2, cy = H * 0.60;
  const rx = Math.min(W * 0.44, 560), ry = Math.min(H * 0.35, 330);
  geo = {cx, cy, rx, ry,
    pond: {x: cx - rx * 0.52, y: cy - ry * 0.28, r: Math.min(rx, ry) * 0.20},
    plots: []};
  for (let i = 0; i < PLOTS; i++) {
    const a = (i / PLOTS) * Math.PI * 2 + 0.35;
    const px = cx + Math.cos(a) * rx * 0.68, py = cy + Math.sin(a) * ry * 0.68;
    const dp = Math.hypot(px - geo.pond.x, py - geo.pond.y);
    geo.plots.push({x: px, y: py + (dp < 110 ? 46 : 0)});
  }
  const rnd = seeded(7);
  geo.trees = [];
  for (let i = 0; i < 26; i++) {
    const a = rnd() * Math.PI * 2, r = 0.78 + rnd() * 0.16;
    geo.trees.push({x: cx + Math.cos(a) * rx * r, y: cy + Math.sin(a) * ry * r,
      s: 0.75 + rnd() * 0.6, apples: rnd() > 0.55, ph: rnd() * 6.28});
  }
  geo.tufts = [];
  for (let i = 0; i < 90; i++) {
    const a = rnd() * Math.PI * 2, r = Math.sqrt(rnd()) * 0.9;
    geo.tufts.push({x: cx + Math.cos(a) * rx * r, y: cy + Math.sin(a) * ry * r, ph: rnd() * 6.28});
  }
  geo.flowers = [];
  for (let i = 0; i < 26; i++) {
    const a = rnd() * Math.PI * 2, r = 0.25 + Math.sqrt(rnd()) * 0.6;
    geo.flowers.push({x: cx + Math.cos(a) * rx * r, y: cy + Math.sin(a) * ry * r,
      c: ['#f9a8d4', '#fde68a', '#ffffff'][i % 3]});
  }
}
function onGrass(x, y) {
  const dx = (x - geo.cx) / (geo.rx * 0.86), dy = (y - geo.cy) / (geo.ry * 0.86);
  if (dx * dx + dy * dy > 1) return false;
  return Math.hypot(x - geo.pond.x, y - geo.pond.y) > geo.pond.r + 22;
}
function grassPoint() {
  for (let k = 0; k < 24; k++) {
    const a = Math.random() * Math.PI * 2, r = Math.sqrt(Math.random()) * 0.8;
    const x = geo.cx + Math.cos(a) * geo.rx * r, y = geo.cy + Math.sin(a) * geo.ry * r;
    if (onGrass(x, y)) return {x, y};
  }
  return {x: geo.cx, y: geo.cy + 40};
}
let D = {sessions: [], fleet: [], scope: ''};
let vils = new Map(), selected = null, smoke = [], drops = [], sparks = [];
const projSel = document.getElementById('proj');
projSel.addEventListener('change', (e) => {
  const u = new URLSearchParams(window.location.search);
  u.set('dir', e.target.value);
  window.location.search = u.toString();
});
function syncProj() {
  const key = (D.projects || []).map(p => p.dir).join(String.fromCharCode(10));
  if (projSel._key !== key) {
    projSel._key = key;
    projSel.innerHTML = '';
    for (const p of (D.projects || [])) {
      const o = document.createElement('option');
      o.value = p.dir;
      o.textContent = (p.dir.split('/').pop() || p.dir) + ' (' + p.sessions + ')';
      projSel.appendChild(o);
    }
  }
  if (document.activeElement !== projSel) projSel.value = D.dir || '';
}
document.getElementById('cx').onclick = () => { selected = null; hideCard(); };
function hideCard() { document.getElementById('card').style.display = 'none'; }
cv.addEventListener('click', (e) => {
  let best = null, bd = 30 * 30;
  for (const v of vils.values()) {
    if (v.inside) continue;
    const dx = v.x - e.clientX, dy = v.y - e.clientY, d = dx * dx + dy * dy;
    if (d < bd) { bd = d; best = v; }
  }
  if (!best) for (let pi = 0; pi < geo.plots.length; pi++) {
    const p = geo.plots[pi];
    const dx = p.x - e.clientX, dy = (p.y - 20) - e.clientY;
    if (dx * dx + dy * dy < 34 * 34) { const occ = [...vils.values()].find(v => v.pi === pi); if (occ) best = occ; }
  }
  selected = best ? best.id : null;
  if (best) showCard(best); else hideCard();
});
function allAgents() { return D.sessions.concat(D.fleet); }
async function poll() {
  try {
    const r = await fetch('api/fleet' + window.location.search);
    D = await r.json(); sync(); syncProj();
  } catch (e) { /* keep last frame */ }
  setTimeout(poll, 2000);
}
function houseIdx(name, pos) {
  if (typeof pos === 'number' && pos >= 0) return pos % PLOTS;
  let h = 0; const k = (name || '?').toLowerCase();
  for (let i = 0; i < k.length; i++) h = (h * 31 + k.charCodeAt(i)) % 997;
  return h % PLOTS;
}
function sync() {
  const seen = new Set();
  for (const a of allAgents()) {
    seen.add(a.id);
    const ch = a.character || {};
    let v = vils.get(a.id);
    if (!v) {
      v = {id: a.id, x: geo.cx, y: geo.cy + 40, tx: geo.cx, ty: geo.cy + 40,
           wx: geo.cx, wy: geo.cy + 40,
           pause: 0, face: 1, step: Math.random() * 6.28,
           inside: false, wasLive: false, pi: 0};
      vils.set(a.id, v);
      burst(v.x, v.y, '#fde68a');
    }
    v.data = a;
    v.pi = houseIdx(ch.name, ch.pos);
    if (a.live && !v.wasLive && v.inside) { v.inside = false; v.x = geo.plots[v.pi].x; v.y = geo.plots[v.pi].y + 8; burst(v.x, v.y, '#bbf7d0'); }
    if (!a.live && v.wasLive && v.inside) v.inside = false;
    v.wasLive = a.live;
  }
  for (const [id, v] of [...vils]) if (!seen.has(id)) vils.delete(id);
  if (selected && ![...vils.keys()].includes(selected)) { selected = null; hideCard(); }
}
function burst(x, y, c) {
  for (let i = 0; i < 10; i++)
    sparks.push({x, y, vx: (Math.random() - .5) * 90, vy: -40 - Math.random() * 70, l: 1, c});
}
function rr(x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}
function draw(t, dt) {
  // sky + sea
  let g = ctx.createLinearGradient(0, 0, 0, H * 0.24);
  g.addColorStop(0, '#7ec8e3'); g.addColorStop(1, '#cdeaf5');
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H * 0.24);
  ctx.fillStyle = '#fef9c3'; ctx.shadowColor = '#fde68a'; ctx.shadowBlur = 40;
  ctx.beginPath(); ctx.arc(W * 0.72, H * 0.09, 20, 0, 6.29); ctx.fill(); ctx.shadowBlur = 0;
  ctx.fillStyle = 'rgba(255,255,255,.9)';
  for (let i = 0; i < 3; i++) {
    const cxp = ((t * 0.008 * (i + 1) + i * W * 0.4) % (W + 240)) - 120;
    const cyp = H * (0.05 + i * 0.045);
    ctx.beginPath();
    ctx.arc(cxp, cyp, 14, 0, 6.29); ctx.arc(cxp + 16, cyp - 5, 17, 0, 6.29); ctx.arc(cxp + 34, cyp, 13, 0, 6.29);
    ctx.fill();
  }
  ctx.strokeStyle = 'rgba(51,65,85,.55)'; ctx.lineWidth = 2;
  for (let i = 0; i < 3; i++) {
    const bx = (t * 0.012 * (i + 1) + i * W * 0.33) % (W + 60) - 30, by = H * (0.13 + i * 0.02);
    ctx.beginPath(); ctx.moveTo(bx - 7, by); ctx.quadraticCurveTo(bx - 2, by - 5, bx, by);
    ctx.quadraticCurveTo(bx + 2, by - 5, bx + 7, by); ctx.stroke();
  }
  g = ctx.createLinearGradient(0, H * 0.2, 0, H);
  g.addColorStop(0, '#38bdf8'); g.addColorStop(1, '#0369a1');
  ctx.fillStyle = g; ctx.fillRect(0, H * 0.2, W, H * 0.8);
  ctx.strokeStyle = 'rgba(255,255,255,.35)'; ctx.lineWidth = 2;
  for (let i = 0; i < 4; i++) {
    const wy = H * (0.3 + i * 0.17), off = (t * 0.03 * (i % 2 ? 1 : -1)) % 90;
    ctx.beginPath();
    for (let x = -90; x < W + 90; x += 18)
      ctx.lineTo(x + off, wy + Math.sin((x + t * 0.05) / 46 + i) * 4);
    ctx.stroke();
  }
  const {cx, cy, rx, ry} = geo;
  // sand + grass
  ctx.fillStyle = '#f0dcb0';
  ctx.beginPath(); ctx.ellipse(cx, cy, rx, ry, 0, 0, 6.29); ctx.fill();
  ctx.fillStyle = '#8fd18b';
  ctx.beginPath(); ctx.ellipse(cx, cy, rx * 0.9, ry * 0.88, 0, 0, 6.29); ctx.fill();
  ctx.fillStyle = '#84cc7f';
  for (const f of geo.tufts) {
    const s = 1 + 0.15 * Math.sin(t / 900 + f.ph);
    ctx.fillRect(f.x, f.y, 3 * s, 5); ctx.fillRect(f.x + 4, f.y + 1, 3 * s, 4);
  }
  for (const f of geo.flowers) {
    ctx.fillStyle = '#3f7d44'; ctx.fillRect(f.x, f.y, 2, 6);
    ctx.fillStyle = f.c; ctx.beginPath(); ctx.arc(f.x + 1, f.y - 1, 2.6, 0, 6.29); ctx.fill();
  }
  // paths plaza -> huts
  ctx.strokeStyle = '#e7cf9e'; ctx.lineWidth = 9; ctx.lineCap = 'round';
  for (const p of geo.plots) {
    ctx.beginPath(); ctx.moveTo(cx, cy); ctx.quadraticCurveTo((cx + p.x) / 2, (cy + p.y) / 2 + 24, p.x, p.y + 14); ctx.stroke();
  }
  // pond
  ctx.fillStyle = '#5ec4e6';
  ctx.beginPath(); ctx.ellipse(geo.pond.x, geo.pond.y, geo.pond.r, geo.pond.r * 0.75, 0, 0, 6.29); ctx.fill();
  ctx.strokeStyle = 'rgba(255,255,255,.5)'; ctx.lineWidth = 2;
  ctx.beginPath(); ctx.ellipse(geo.pond.x, geo.pond.y, geo.pond.r * (0.55 + 0.03 * Math.sin(t / 700)), geo.pond.r * 0.42, 0, 0, 6.29); ctx.stroke();
  // plaza + fountain
  ctx.fillStyle = '#c9c2b4';
  ctx.beginPath(); ctx.ellipse(cx, cy, 64, 46, 0, 0, 6.29); ctx.fill();
  ctx.strokeStyle = '#a8a091'; ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.ellipse(cx, cy, 48, 33, 0, 0, 6.29); ctx.stroke();
  ctx.beginPath(); ctx.ellipse(cx, cy, 30, 20, 0, 0, 6.29); ctx.stroke();
  ctx.fillStyle = '#8fa3b8';
  ctx.beginPath(); ctx.ellipse(cx, cy - 4, 20, 13, 0, 0, 6.29); ctx.fill();
  ctx.fillStyle = '#bfe3f2';
  ctx.beginPath(); ctx.ellipse(cx, cy - 6, 14, 8, 0, 0, 6.29); ctx.fill();
  ctx.fillStyle = '#7dd3fc';
  for (let i = 0; i < 3; i++) {
    const fh = 12 + 8 * Math.sin(t / 300 + i * 2.1);
    ctx.fillRect(cx - 2 + i * 2 - 2, cy - 8 - fh, 3, fh);
  }
  if (Math.random() < 0.5) drops.push({x: cx + (Math.random() - .5) * 26, y: cy - 14, vy: 30 + Math.random() * 40, l: 1});
  // trees
  for (const tr of geo.trees) {
    const sw = Math.sin(t / 1200 + tr.ph) * 2;
    ctx.fillStyle = '#7c5a3a'; ctx.fillRect(tr.x - 3, tr.y - 14 * tr.s, 6, 16 * tr.s);
    ctx.fillStyle = '#3e9e4f';
    ctx.beginPath(); ctx.arc(tr.x + sw, tr.y - 24 * tr.s, 13 * tr.s, 0, 6.29); ctx.fill();
    ctx.fillStyle = '#4db45e';
    ctx.beginPath(); ctx.arc(tr.x - 4 + sw, tr.y - 28 * tr.s, 8 * tr.s, 0, 6.29); ctx.fill();
    if (tr.apples) { ctx.fillStyle = '#ef4444'; for (const [ax, ay] of [[-6, -22], [5, -26], [0, -18]]) { ctx.beginPath(); ctx.arc(tr.x + ax * tr.s + sw, tr.y + ay * tr.s, 2.2, 0, 6.29); ctx.fill(); } }
  }
  // huts
  for (let pi = 0; pi < geo.plots.length; pi++) {
    const p = geo.plots[pi];
    const occ = [...vils.values()].filter(v => v.pi === pi);
    const col = (occ[0] && occ[0].data.character && occ[0].data.character.hex) || '#94a3b8';
    ctx.fillStyle = 'rgba(0,0,0,.15)';
    ctx.beginPath(); ctx.ellipse(p.x, p.y + 16, 30, 8, 0, 0, 6.29); ctx.fill();
    ctx.fillStyle = '#f7ead0'; ctx.fillRect(p.x - 21, p.y - 22, 42, 38);
    ctx.strokeStyle = '#b99a68'; ctx.lineWidth = 2; ctx.strokeRect(p.x - 21, p.y - 22, 42, 38);
    ctx.fillStyle = col;
    ctx.beginPath(); ctx.moveTo(p.x - 27, p.y - 20); ctx.lineTo(p.x, p.y - 44); ctx.lineTo(p.x + 27, p.y - 20); ctx.closePath(); ctx.fill();
    ctx.strokeStyle = 'rgba(0,0,0,.25)'; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.fillStyle = occ.some(v => v.inside) ? '#fcd34d' : '#5b4a33';
    ctx.fillRect(p.x - 7, p.y - 6, 14, 22);
    const glow = occ.some(v => v.inside);
    ctx.fillStyle = glow ? '#fde68a' : '#9db8c9';
    ctx.fillRect(p.x - 17, p.y - 14, 8, 8); ctx.fillRect(p.x + 9, p.y - 14, 8, 8);
    ctx.fillStyle = '#8a8f96'; ctx.fillRect(p.x + 12, p.y - 52, 7, 14);
    if (glow && Math.random() < 0.25)
      smoke.push({x: p.x + 15, y: p.y - 54, vy: -22 - Math.random() * 10, l: 1});
  }
  // villagers, sorted by y
  const order = [...vils.values()].sort((a, b) => a.y - b.y);
  let work = 0, rest = 0;
  for (const v of order) {
    const d = v.data;
    if (d.live) work++; else rest++;
    step(t, dt, v, d);
    if (!v.inside) drawVil(t, v, d);
  }
  // particles
  ctx.fillStyle = '#e5e7eb';
  for (const s of sparks) {
    s.x += s.vx * dt; s.y += s.vy * dt; s.vy += 160 * dt; s.l -= dt * 1.4;
    if (s.l <= 0) continue;
    ctx.globalAlpha = Math.max(0, s.l); ctx.fillStyle = s.c;
    ctx.fillRect(s.x, s.y, 3, 3);
  }
  ctx.globalAlpha = 1; sparks = sparks.filter(s => s.l > 0);
  ctx.fillStyle = '#7dd3fc';
  for (const dr of drops) {
    dr.y += dr.vy * dt; dr.l -= dt * 2;
    if (dr.l <= 0) continue;
    ctx.globalAlpha = Math.max(0, dr.l) * .8;
    ctx.beginPath(); ctx.arc(dr.x, dr.y, 2, 0, 6.29); ctx.fill();
  }
  ctx.globalAlpha = 1; drops = drops.filter(d => d.l > 0);
  ctx.fillStyle = 'rgba(148,163,184,.7)';
  for (const s of smoke) {
    s.y += s.vy * dt; s.vy *= 0.99; s.l -= dt * 0.5;
    if (s.l <= 0) continue;
    ctx.globalAlpha = Math.max(0, s.l) * .5;
    ctx.beginPath(); ctx.arc(s.x + Math.sin(t / 500 + s.y) * 4, s.y, 9 * (1.4 - s.l), 0, 6.29); ctx.fill();
  }
  ctx.globalAlpha = 1; smoke = smoke.filter(s => s.l > 0);
  // counters + clock
  document.getElementById('c-work').textContent = work;
  document.getElementById('c-rest').textContent = rest;
  document.getElementById('c-home').textContent = geo.plots.length;
  const now = new Date();
  document.getElementById('clock').textContent = now.toLocaleTimeString([], {hour: 'numeric', minute: '2-digit'}) + '  ' +
    now.toLocaleDateString([], {weekday: 'short', month: 'short', day: 'numeric'});
}
function step(t, dt, v, d) {
  const home = geo.plots[v.pi] || geo.plots[0];
  if (!d.live) { // head home, then rest
    if (!v.inside) {
      const dx = home.x - v.x, dy = (home.y + 8) - v.y, dist = Math.hypot(dx, dy);
      if (dist < 6) v.inside = true;
      else { v.x += dx / dist * 46 * dt; v.y += dy / dist * 46 * dt; v.face = dx >= 0 ? 1 : -1; v.step += dt * 9; }
    }
    return;
  }
  if (v.inside) return;
  v.pause -= dt;
  const dx = v.wx - v.x, dy = v.wy - v.y, dist = Math.hypot(dx, dy);
  if (dist < 5) {
    if (v.pause <= 0) {
      if (Math.random() < 0.6) { const p = grassPoint(); v.wx = p.x; v.wy = p.y; }
      else v.pause = 1 + Math.random() * 2.5;
    }
  } else {
    v.x += dx / dist * 30 * dt; v.y += dy / dist * 30 * dt;
    v.face = dx >= 0 ? 1 : -1; v.step += dt * 8;
  }
  if (!v.wx && !v.wy) { const p = grassPoint(); v.wx = p.x; v.wy = p.y; }
}
function drawVil(t, v, d) {
  const col = (d.character && d.character.hex) || '#94a3b8';
  const moving = Math.hypot(v.wx - v.x, v.wy - v.y) > 6 && d.live;
  const bob = moving ? Math.abs(Math.sin(v.step)) * -2.5 : Math.sin(t / 800 + v.step) * 0.8;
  const x = v.x, y = v.y + bob;
  ctx.fillStyle = 'rgba(0,0,0,.18)';
  ctx.beginPath(); ctx.ellipse(x, y + 14, 11, 4, 0, 0, 6.29); ctx.fill();
  if (moving) { // feet
    const f = Math.sin(v.step) * 4;
    ctx.fillStyle = '#334155';
    ctx.beginPath(); ctx.arc(x - 5, y + 13 + f * 0.3, 3, 0, 6.29); ctx.fill();
    ctx.beginPath(); ctx.arc(x + 5, y + 13 - f * 0.3, 3, 0, 6.29); ctx.fill();
  }
  ctx.fillStyle = col; ctx.strokeStyle = 'rgba(0,0,0,.35)'; ctx.lineWidth = 1.5;
  rr(x - 11, y - 12, 22, 26, 9); ctx.fill(); ctx.stroke();
  ctx.fillStyle = 'rgba(255,255,255,.25)';
  rr(x - 7, y - 8, 14, 12, 6); ctx.fill();
  ctx.fillStyle = '#fff';
  ctx.beginPath(); ctx.arc(x - 4.5 + v.face * 1.5, y - 3, 3.4, 0, 6.29); ctx.fill();
  ctx.beginPath(); ctx.arc(x + 4.5 + v.face * 1.5, y - 3, 3.4, 0, 6.29); ctx.fill();
  ctx.fillStyle = '#1f2937';
  ctx.beginPath(); ctx.arc(x - 4.5 + v.face * 2.5, y - 3, 1.7, 0, 6.29); ctx.fill();
  ctx.beginPath(); ctx.arc(x + 4.5 + v.face * 2.5, y - 3, 1.7, 0, 6.29); ctx.fill();
  // name tag
  const nm = (d.character && d.character.name) || short2(d.label);
  ctx.font = '11px sans-serif';
  const nw = ctx.measureText(nm).width + 12;
  ctx.fillStyle = 'rgba(20,32,24,.82)';
  rr(x - nw / 2, y - 36, nw, 16, 8); ctx.fill();
  ctx.fillStyle = col; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText(nm, x, y - 28);
  // work bubble
  const em = d.tool ? (TOOL_EMOJI[d.tool.name] || '⚙️') : null;
  if (d.live && em && (d.tool.status === 'running' || d.tool.status === 'pending')) {
    const by = y - 52 + Math.sin(t / 500) * 2;
    ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(x + 16, by, 11, 0, 6.29); ctx.fill();
    ctx.strokeStyle = '#cbd5e1'; ctx.lineWidth = 1; ctx.stroke();
    ctx.font = '12px sans-serif'; ctx.fillText(em, x + 16, by + 1);
  }
  if (v.id === selected) {
    ctx.strokeStyle = '#fff'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(x, y + 2, 20, 0, 6.29); ctx.stroke();
  }
  // resting zzz over the hut
  if (v.inside) return;
}
function drawZzz(t) {
  ctx.font = 'bold 13px sans-serif'; ctx.fillStyle = '#cbd5e1'; ctx.textAlign = 'center';
  for (const v of vils.values()) {
    if (!v.inside) continue;
    const home = geo.plots[v.pi] || geo.plots[0];
    for (let k = 0; k < 2; k++) {
      const ph = ((t / 1600) + k * 0.5 + home.x) % 1;
      ctx.globalAlpha = 1 - ph;
      ctx.fillText('z', home.x + 20 + ph * 12, home.y - 50 - ph * 22);
    }
  }
  ctx.globalAlpha = 1;
}
function short2(s) {
  s = s || '';
  return s.length > 22 ? s.slice(0, 21) + '…' : s;
}
function showCard(v) {
  const d = v.data, ch = d.character || {};
  document.getElementById('card').style.display = 'block';
  document.getElementById('c-name').textContent = (ch.symbol ? ch.symbol + ' ' : '') + (ch.name || short2(d.label));
  document.getElementById('c-sub').textContent = D.scope ? 'island · ' + D.scope : 'island';
  const st = d.live ? 'working' : 'resting';
  document.getElementById('c-tags').innerHTML =
    '<span class="tag ' + (d.live ? 'work' : 'rest') + '">' + st + '</span>' +
    '<span class="tag role">' + (d.agent || '?') + '</span>';
  const r = (k, val) => '<dt>' + k + '</dt><dd>' + (val || '—') + '</dd>';
  document.getElementById('c-dl').innerHTML =
    r('doing', (d.todos && d.todos.current) || (d.tool ? d.tool.name + ':' + d.tool.status : null)) +
    r('todos', d.todos && d.todos.total ? d.todos.done + '/' + d.todos.total : null) +
    r('active', d.active) + r('bearing', ch.bearing);
}
let last = performance.now();
function frame(t) {
  const dt = Math.min(0.05, (t - last) / 1000); last = t;
  draw(t, dt); drawZzz(t);
  requestAnimationFrame(frame);
}
resize(); poll(); requestAnimationFrame(frame);
</script>
</body>
</html>
"""

WAR = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>chakravyuh</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; background: #170f0e; color: #f5e8d5;
         font: 14px/1.45 -apple-system, "Segoe UI", Inter, sans-serif;
         overflow: hidden; }
  #cv { position: fixed; inset: 0; display: block; }
  header { position: fixed; top: 12px; left: 14px; right: 14px; display: flex;
           align-items: center; gap: 10px; pointer-events: none; }
  .pill { background: rgba(30,16,12,.85); border: 1px solid #6b3a1f;
          border-radius: 999px; padding: 5px 13px; font-size: 12px; }
  select.pill { color: #f0d9b5; max-width: 220px; }
  select.pill option { color: #111; }
  header nav { margin-left: auto; pointer-events: auto; display: flex; gap: 8px; }
  header nav a { color: #e8b26a; text-decoration: none; font-size: 12px;
                 background: rgba(30,16,12,.85); border: 1px solid #6b3a1f;
                 border-radius: 999px; padding: 5px 13px; }
  #card { position: fixed; top: 64px; right: 14px; width: 260px;
          background: #f7ecd4; color: #4a2f1a; border-radius: 12px;
          padding: 12px 14px; display: none;
          box-shadow: 0 8px 30px rgba(0,0,0,.5); border-top: 4px solid #b45309; }
  #card h2 { margin: 0; font-size: 16px; }
  #card .sub { color: #8a6f45; font-size: 12px; margin-bottom: 8px; }
  #card .tag { display: inline-block; font-size: 11px; border-radius: 999px;
               padding: 2px 10px; margin-right: 6px; }
  #card .field { background: #f3ddba; color: #8a4b12; }
  #card .camp { background: #e6dcc4; color: #6f6250; }
  #card .role { background: #e8d9c2; color: #6b4a26; }
  #card dl { margin: 8px 0 0; font-size: 12px; }
  #card dt { color: #a3855a; float: left; width: 64px; }
  #card dd { margin: 0 0 3px 64px; }
  #card .x { float: right; cursor: pointer; color: #a3855a; border: 0;
             background: none; font-size: 14px; }
  footer { position: fixed; left: 0; right: 0; bottom: 10px; text-align: center;
           color: #8a6a4a; font-size: 11px; pointer-events: none; }
  #cv { touch-action: none; cursor: grab; }
  #cv:active { cursor: grabbing; }
  header nav a#spinBtn { cursor: pointer; }
  #ctrls { position: fixed; right: 14px; bottom: 30px; display: flex; flex-direction: column;
           gap: 6px; z-index: 5; }
  #ctrls button { width: 34px; height: 34px; border-radius: 9px; font-size: 17px; line-height: 1;
                  color: #f0d9b5; background: rgba(30,16,12,.85); border: 1px solid #6b3a1f;
                  cursor: pointer; }
  #ctrls button:hover { background: rgba(60,32,20,.95); }
</style>
</head>
<body>
<canvas id="cv"></canvas>
<header>
  <span class="pill" id="clock"></span>
  <span class="pill">⚔️ <b id="c-field">0</b> on field</span>
  <span class="pill">⛺ <b id="c-camp">0</b> at camp</span>
  <select id="proj" class="pill" title="project"></select>
  <nav><a href="#" id="spinBtn">▶ 360°</a><a href="/island">village</a><a href="/graph">graph</a></nav>
</header>
<aside id="card"><button class="x" id="cx">✕</button><h2 id="c-name"></h2>
  <div class="sub" id="c-sub"></div><div id="c-tags"></div><dl id="c-dl"></dl></aside>
<div id="ctrls">
  <button id="zin" title="zoom in">＋</button>
  <button id="zout" title="zoom out">－</button>
  <button id="zreset" title="reset view">⟲</button>
</div>
<footer>drag to orbit · scroll or ± to zoom · ⟲ or double-click resets · click a warrior for detail</footer>
<script>
"use strict";
const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
let W = 0, H = 0, deco = null;
function resize() {
  const d = Math.min(2, window.devicePixelRatio || 1);
  W = window.innerWidth; H = window.innerHeight;
  cv.width = W * d; cv.height = H * d;
  cv.style.width = W + 'px'; cv.style.height = H + 'px';
  ctx.setTransform(d, 0, 0, d, 0, 0);
  decor();
  // A resize can strand troops seeded under a smaller viewport; re-seat anyone
  // not yet on the field back at the camp (world coordinates, so orbit-safe).
  if (typeof troops !== 'undefined' && troops.size) {
    const F = field();
    for (const s of troops.values()) if (s.mode !== 'field') { s.wx = F.camp.wx; s.wz = F.camp.wz; }
  }
}
window.addEventListener('resize', resize);
const TOOL_EMOJI = {bash: '⌨️', read: '📖', edit: '✏️', grep: '🔍', glob: '🗂️',
  task: '📦', skill: '✨', todowrite: '✅', question: '💬', webfetch: '🌐',
  websearch: '🌐', lsp: '🔧'};
function seeded(n) { let s = n; return () => (s = (s * 16807) % 2147483647) / 2147483647; }
function decor() {
  const r = seeded(21), d = [];
  for (let i = 0; i < 120; i++)
    d.push({x: r(), y: 0.36 + r() * 0.62, l: 4 + r() * 14, a: 0.10 + r() * 0.20});
  const tufts = [];
  for (let i = 0; i < 64; i++) tufts.push({x: r(), y: 0.40 + r() * 0.56, ph: r() * 6.28});
  // The Kaurava host manning the rings. The layout is fixed; each ring slowly
  // marches its file around (alternating direction), so the vyuh turns like a
  // wheel while the single gate stays put on the camp side.
  const counts = [50, 44, 38, 31, 24, 18, 12], army = [];
  for (let i = 0; i < 7; i++) {
    const n = counts[i], speed = (0.0000052 + i * 0.0000011) * (i % 2 ? -1 : 1);
    for (let j = 0; j < n; j++) {
      const q = r();
      let type = 'foot';
      if (i < 4 && q < 0.055) type = 'elephant';
      else if (q < 0.20) type = 'horse';
      army.push({i, base: (j + 0.5) / n, type, speed,
                 ph: r() * 6.28, seed: r(), ro: (r() - 0.5) * 6});
    }
  }
  // A far host smudged along the horizon, banners swaying.
  const far = [];
  for (let i = 0; i < 120; i++)
    far.push({x: r(), row: i % 3, ph: r() * 6.28, banner: r() < 0.10, tall: r()});
  deco = {dust: d, tufts, army, far};
}
// --- Camera -----------------------------------------------------------------
// The battlefield is a flat ground plane. We orbit it (yaw), tilt it (pitch)
// and zoom. Everything works in world coordinates on that plane — wx (east),
// wz (toward the viewer), wy (up) — and proj() maps a world point to the
// screen, so the whole scene can be spun a full 360 and seen from any angle.
const cam = {yaw: 0, pitch: 0.62, zoom: 1, spin: false, idle: 0};
const GA0 = Math.PI / 2;        // the gate opens toward the viewer at yaw 0
const SUNAZ = -0.6;             // the sun's world bearing
let CX = 0, CY = 0, SQ = 0.58, HZ = 0.8, ZM = 1;
function setCam() {
  cam.pitch = Math.max(0.32, Math.min(1.2, cam.pitch));
  cam.zoom = Math.max(0.5, Math.min(3, cam.zoom));
  SQ = Math.sin(cam.pitch); HZ = Math.cos(cam.pitch); ZM = cam.zoom;
  CX = W * 0.5; CY = H * 0.6;
}
// Project a ground-plane point (wx, wz) at height wy to the screen. ez is the
// depth after the orbit (larger => nearer the viewer, lower on screen).
function proj(wx, wz, wy) {
  const c = Math.cos(cam.yaw), s = Math.sin(cam.yaw);
  const ex = wx * c - wz * s, ez = wx * s + wz * c;
  return {x: CX + ex * ZM, y: CY + ez * SQ * ZM - (wy || 0) * HZ * ZM, ez};
}
function field() {
  const R0 = Math.min(W * 0.30, H * 0.32), gap = Math.min(30, R0 / 8.2);
  const Rend = Math.max(30, R0 - 6 * gap - 16);
  // The camp rests on the ground just outside the gate, so it orbits with the
  // field and the gate always faces it.
  const cr = R0 + 150, camp = {wx: Math.cos(GA0) * cr, wz: Math.sin(GA0) * cr};
  return {R0, gap, Rend, turns: 2.3, camp, fire: camp};
}
// The gate sways gently around its world bearing; the wheel's motion comes from
// the marching host, not from swinging the opening away from the path.
function gateA(t) { return GA0 + 0.09 * Math.sin(t * 0.00015); }
// A point on ring R at world angle a, projected to the screen.
function ringPt(F, R, a) { return proj(Math.cos(a) * R, Math.sin(a) * R, 0); }
// The open path, in world coordinates: one spiral corridor. s=0 outer gate,
// s=1 the heart, s<0 the short approach from the camp — one revolution so the
// gates of every ring line up along it.
function corridorW(F, s, t) {
  const r = F.R0 - s * (F.R0 - F.Rend), a = gateA(t) + s * F.turns * Math.PI * 2;
  return {wx: Math.cos(a) * r, wz: Math.sin(a) * r, a, r};
}
// World angle at which the corridor pierces ring i (its gate).
function ringGap(F, i, t) {
  const si = (i * F.gap) / (F.R0 - F.Rend);
  return gateA(t) + si * F.turns * Math.PI * 2;
}
// World position along the corridor with a lateral marching offset (files
// don't stack).
function corrPosW(F, st, t) {
  const lane = st.lane || 0, e = 0.01;
  const c = corridorW(F, st.s, t), a = corridorW(F, st.s - e, t), b = corridorW(F, st.s + e, t);
  let tx = b.wx - a.wx, tz = b.wz - a.wz;
  const l = Math.hypot(tx, tz) || 1; tx /= l; tz /= l;
  return {wx: c.wx - tz * lane, wz: c.wz + tx * lane};
}
let D = {sessions: [], fleet: [], scope: ''};
let troops = new Map(), selected = null, embers = [], smoke = [];
const projSel = document.getElementById('proj');
projSel.addEventListener('change', (e) => {
  const u = new URLSearchParams(window.location.search);
  u.set('dir', e.target.value);
  window.location.search = u.toString();
});
function syncProj() {
  const key = (D.projects || []).map(p => p.dir).join(String.fromCharCode(10));
  if (projSel._key !== key) {
    projSel._key = key;
    projSel.innerHTML = '';
    for (const p of (D.projects || [])) {
      const o = document.createElement('option');
      o.value = p.dir;
      o.textContent = (p.dir.split('/').pop() || p.dir) + ' (' + p.sessions + ')';
      projSel.appendChild(o);
    }
  }
  if (document.activeElement !== projSel) projSel.value = D.dir || '';
}
document.getElementById('cx').onclick = () => { selected = null; hideCard(); };
function hideCard() { document.getElementById('card').style.display = 'none'; }
cv.addEventListener('click', (e) => {
  if (dragMoved) return;                        // that was an orbit drag, not a pick
  let best = null, bd = 34 * 34;
  for (const s of troops.values()) {
    const dx = (s.sx || 0) - e.clientX, dy = (s.sy || 0) - e.clientY, d = dx * dx + dy * dy;
    if (d < bd) { bd = d; best = s.id; }
  }
  selected = best;
  if (best) showCard(best); else hideCard();
});
// --- Orbit / tilt / zoom controls ------------------------------------------
let dragging = false, dragMoved = false, lastX = 0, lastY = 0, pinchD = 0;
function wake() { cam.idle = 0; }
cv.addEventListener('pointerdown', (e) => {
  dragging = true; dragMoved = false; lastX = e.clientX; lastY = e.clientY; wake();
  try { cv.setPointerCapture(e.pointerId); } catch (x) {}
});
cv.addEventListener('pointermove', (e) => {
  if (!dragging) return;
  const dx = e.clientX - lastX, dy = e.clientY - lastY; lastX = e.clientX; lastY = e.clientY;
  if (Math.abs(dx) + Math.abs(dy) > 3) dragMoved = true;
  cam.yaw += dx * 0.006;
  cam.pitch -= dy * 0.004;
  wake();
});
cv.addEventListener('pointerup', () => { dragging = false; wake(); });
cv.addEventListener('pointercancel', () => { dragging = false; });
cv.addEventListener('wheel', (e) => {
  e.preventDefault(); cam.zoom *= (1 - e.deltaY * 0.0012); wake();
}, {passive: false});
cv.addEventListener('touchmove', (e) => {
  if (e.touches.length === 2) {
    const a = e.touches[0], b = e.touches[1];
    const d = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
    if (pinchD) cam.zoom *= d / pinchD;
    pinchD = d; dragMoved = true; wake(); e.preventDefault();
  }
}, {passive: false});
cv.addEventListener('touchend', () => { pinchD = 0; });
cv.addEventListener('dblclick', () => { cam.yaw = 0; cam.pitch = 0.62; cam.zoom = 1; wake(); });
function resetCam() { cam.yaw = 0; cam.pitch = 0.62; cam.zoom = 1; wake(); }
function nudgeZoom(f) { cam.zoom *= f; wake(); }
function toggleSpin() {
  cam.spin = !cam.spin; wake();
  const b = document.getElementById('spinBtn');
  if (b) b.textContent = cam.spin ? '⏸ spin' : '▶ 360°';
}
document.getElementById('spinBtn').addEventListener('click', (e) => { e.preventDefault(); toggleSpin(); });
document.getElementById('zin').addEventListener('click', () => nudgeZoom(1.2));
document.getElementById('zout').addEventListener('click', () => nudgeZoom(1 / 1.2));
document.getElementById('zreset').addEventListener('click', resetCam);
function allAgents() { return D.sessions.concat(D.fleet); }
async function poll() {
  try {
    const r = await fetch('api/fleet' + window.location.search);
    D = await r.json(); sync(); syncProj();
  } catch (e) { /* keep last frame */ }
  setTimeout(poll, 2000);
}
function progress(a) {
  if (!a.todos || !a.todos.total) return 0;
  return a.todos.done / a.todos.total;
}
function sync() {
  if (W < 200 || H < 200) return;          // wait for a real viewport before mustering
  const seen = new Set(), F = field();
  allAgents().forEach((a, idx) => {
    seen.add(a.id);
    let s = troops.get(a.id);
    if (!s) {
      s = {id: a.id, wx: F.camp.wx, wz: F.camp.wz, s: 0,
           mode: a.live ? 'gate' : 'camp', ph: Math.random() * 6.28,
           lane: ((idx % 3) - 1) * 10, jit: (idx % 5) * 0.006, face: 1, sx: 0, sy: 0};
      troops.set(a.id, s);
    }
    // Tent slots (world coords, so they orbit with the camp). Idle warriors
    // rest in theirs; marchers keep their own position.
    s.slotwx = F.camp.wx + ((idx % 3) - 1) * 26;
    s.slotwz = F.camp.wz + (idx % 2) * 20;
    if (s.mode === 'camp') { s.wx = s.slotwx; s.wz = s.slotwz; }
    s.data = a;
    s.depth = progress(a);
  });
  for (const id of [...troops.keys()]) if (!seen.has(id)) troops.delete(id);
  if (selected && ![...troops.keys()].includes(selected)) { selected = null; hideCard(); }
}
// March discipline: nobody crosses a ring wall. The field is entered and
// left along the open corridor; only open ground is walked straight.
function march(t, dt, s, F) {
  const d = s.data, V = 108 * dt;
  const stepTo = (wx, wz) => {
    const dx = wx - s.wx, dz = wz - s.wz, dist = Math.hypot(dx, dz);
    if (dist < 8) return true;
    const k = Math.min(1, V / dist);
    s.wx += dx * k; s.wz += dz * k;
    return false;
  };
  // The muster point sits just outside the gate. Warriors always reach the
  // field through it, then thread the spiral inward; leaving, they unwind back
  // to it before crossing open ground to their tent.
  const ga = gateA(t), sr = F.R0 + 52, stx = Math.cos(ga) * sr, stz = Math.sin(ga) * sr;
  if (d.live) {
    if (s.mode !== 'field') {
      if (stepTo(stx, stz)) { s.mode = 'field'; s.s = Math.max(0, s.s); }
    } else {
      const target = Math.min(1, s.depth + s.jit);
      s.s += Math.sign(target - s.s) * Math.min(Math.abs(target - s.s), dt * 0.14);
      const p = corrPosW(F, s, t); s.wx = p.wx; s.wz = p.wz;
    }
  } else if (s.mode === 'field') {
    s.s -= dt * 0.16;
    if (s.s <= 0.002) { s.s = 0; s.mode = 'leave'; }
    else { const p = corrPosW(F, s, t); s.wx = p.wx; s.wz = p.wz; }
  } else if (s.mode === 'leave') {
    if (stepTo(stx, stz)) s.mode = 'walk';
  } else if (!stepTo(s.slotwx === undefined ? F.camp.wx : s.slotwx,
                      s.slotwz === undefined ? F.camp.wz : s.slotwz)) {
    s.mode = 'walk';
  } else {
    s.mode = 'camp';
  }
  // Project to the screen for drawing, hit-testing and facing.
  const p = proj(s.wx, s.wz, 0);
  if (s.psx !== undefined && Math.abs(p.x - s.psx) > 0.3) s.face = p.x > s.psx ? 1 : -1;
  s.psx = p.x; s.sx = p.x; s.sy = p.y;
  // Heroes grow sub-linearly with zoom (the host scales linearly): zoomed in
  // they settle to a human scale beside the soldiers and elephants instead of
  // towering over them; zoomed out they stay a touch larger to stand out.
  const depth = 0.86 + 0.28 * (0.5 + 0.5 * p.ez / (F.R0 * 1.15));
  s.scr = 0.85 * Math.sqrt(ZM) * depth;
}
function rr(x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}
function draw(t, dt) {
  const F = field();
  setCam();
  if (cam.spin && cam.idle > 4000 && !selected && !dragging) cam.yaw += dt * 0.12;
  cam.idle += dt * 1000;
  const horizonY = CY - (F.R0 + 220) * SQ * ZM - 10, skyBot = Math.max(0, horizonY);
  // ---- sky (only what shows above the horizon) ----
  if (skyBot > 1) {
    let g = ctx.createLinearGradient(0, 0, 0, skyBot);
    g.addColorStop(0, '#150d2a'); g.addColorStop(0.5, '#4d2340');
    g.addColorStop(0.8, '#a6421f'); g.addColorStop(1, '#df7a2b');
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, skyBot);
    const rel = SUNAZ - cam.yaw, vis = Math.cos(rel);          // sun sweeps + sets on orbit
    if (vis > -0.2) {
      const sx = CX + Math.sin(rel) * W * 0.42, sy = skyBot - 24;
      const halo = ctx.createRadialGradient(sx, sy, 6, sx, sy, 130);
      halo.addColorStop(0, 'rgba(255,205,120,' + (0.5 * Math.min(1, vis + 0.3)) + ')');
      halo.addColorStop(1, 'rgba(255,150,70,0)');
      ctx.fillStyle = halo; ctx.beginPath(); ctx.arc(sx, sy, 130, 0, 6.29); ctx.fill();
      ctx.fillStyle = '#ffce70'; ctx.beginPath(); ctx.arc(sx, sy, 30, 0, 6.29); ctx.fill();
    }
    ctx.fillStyle = '#2b1526';                                 // hills, parallax on orbit
    const ph = cam.yaw * W * 0.6;
    ctx.beginPath(); ctx.moveTo(0, skyBot);
    for (let x = 0; x <= W; x += 60) ctx.lineTo(x, skyBot - 12 - 10 * Math.sin((x + ph) / 200 + 2));
    ctx.lineTo(W, skyBot); ctx.closePath(); ctx.fill();
  }
  // ---- ground ----
  let gg = ctx.createLinearGradient(0, skyBot, 0, H);
  gg.addColorStop(0, '#7a4e2a'); gg.addColorStop(0.3, '#6c4324'); gg.addColorStop(1, '#341d0e');
  ctx.fillStyle = gg; ctx.fillRect(0, skyBot, W, H - skyBot);
  farHost(t, horizonY);
  // ---- the chakravyuh: seven rings on the ground plane ----
  for (let i = 0; i < 7; i++) {
    const R = F.R0 - i * F.gap, rot = ringGap(F, i, t) + cam.yaw, gate = 0.5 + i * 0.04;
    ctx.strokeStyle = i % 2 ? 'rgba(120,62,26,.55)' : 'rgba(150,82,32,.6)';
    ctx.lineWidth = Math.max(1.5, 6 * ZM);
    ctx.beginPath(); ctx.ellipse(CX, CY, R * ZM, R * SQ * ZM, 0, rot + gate / 2, rot + Math.PI * 2 - gate / 2); ctx.stroke();
    ctx.strokeStyle = 'rgba(255,214,150,.13)'; ctx.lineWidth = Math.max(0.6, 1.5 * ZM);
    ctx.beginPath(); ctx.ellipse(CX, CY, R * ZM, R * SQ * ZM, 0, rot + gate / 2, rot + Math.PI * 2 - gate / 2); ctx.stroke();
  }
  // ---- the Kaurava host manning the rings (foot, horse, war elephants) ----
  drawArmy(t, F);
  // ---- the royal standard at the heart ----
  heartStandard(t, F);
  // ---- our camp ----
  drawCamp(t, F);
  // ---- dust drifting across the field ----
  ctx.fillStyle = '#e8b26a';
  for (const m of deco.dust) {
    const x = (m.x * W + t * 0.006 * m.l) % (W + 40) - 20, y = Math.max(skyBot + 4, m.y * H);
    ctx.globalAlpha = m.a * (0.5 + 0.4 * Math.sin(t / 800 + x));
    ctx.fillRect(x, y, m.l, 1.5);
  }
  ctx.globalAlpha = 1;
  // ---- our heroes: march them, then draw back-to-front ----
  let onField = 0, atCamp = 0;
  for (const s of troops.values()) {
    if (s.data.live) onField++; else atCamp++;
    march(t, dt, s, F);
  }
  const order = [...troops.values()].sort((a, b) => a.sy - b.sy);
  for (const s of order) drawWarrior(t, s, s.data);
  // embers + smoke
  for (const e of embers) {
    e.y += e.vy * dt; e.l -= dt * 1.2;
    if (e.l <= 0) continue;
    ctx.globalAlpha = Math.max(0, e.l); ctx.fillStyle = '#fb923c';
    ctx.fillRect(e.x, e.y, 2.4, 2.4);
  }
  ctx.globalAlpha = 1; embers = embers.filter(e => e.l > 0);
  for (const s of smoke) {
    s.y += s.vy * dt; s.l -= dt * 0.45;
    if (s.l <= 0) continue;
    ctx.globalAlpha = Math.max(0, s.l) * 0.4; ctx.fillStyle = '#a8a29e';
    ctx.beginPath(); ctx.arc(s.x + Math.sin(t / 600 + s.y) * 5, s.y, 10 * (1.5 - s.l), 0, 6.29); ctx.fill();
  }
  ctx.globalAlpha = 1; smoke = smoke.filter(s => s.l > 0);
  document.getElementById('c-field').textContent = onField;
  document.getElementById('c-camp').textContent = atCamp;
  const now = new Date();
  document.getElementById('clock').textContent = now.toLocaleTimeString([], {hour: 'numeric', minute: '2-digit'}) + ' · Kurukshetra, day 14';
  if (selected) showCard(selected);
}
function tent(x, y, col, t) {
  ctx.fillStyle = 'rgba(0,0,0,.3)';
  ctx.beginPath(); ctx.ellipse(x, y + 18, 30, 7, 0, 0, 6.29); ctx.fill();
  ctx.fillStyle = col;
  ctx.beginPath(); ctx.moveTo(x - 26, y + 18); ctx.lineTo(x, y - 22); ctx.lineTo(x + 26, y + 18); ctx.closePath(); ctx.fill();
  ctx.fillStyle = 'rgba(0,0,0,.28)';
  ctx.beginPath(); ctx.moveTo(x, y - 22); ctx.lineTo(x + 26, y + 18); ctx.lineTo(x + 8, y + 18); ctx.closePath(); ctx.fill();
  ctx.fillStyle = '#1c0f0c';
  ctx.beginPath(); ctx.moveTo(x - 8, y + 18); ctx.lineTo(x, y - 2); ctx.lineTo(x + 8, y + 18); ctx.closePath(); ctx.fill();
  ctx.strokeStyle = '#3f2a18'; ctx.lineWidth = 3;
  ctx.beginPath(); ctx.moveTo(x, y - 22); ctx.lineTo(x, y - 34); ctx.stroke();
  const wv = Math.sin(t / 400 + x) * 4;
  ctx.fillStyle = '#f59e0b';
  ctx.beginPath(); ctx.moveTo(x, y - 34); ctx.quadraticCurveTo(x + 16, y - 31 + wv, x + 22, y - 26 + wv);
  ctx.lineTo(x, y - 24); ctx.closePath(); ctx.fill();
}
const SKIN = '#e0a46b', DARK = '#20121a', IRON = '#c7ccd4',
      GOLD = '#f2c14e', GOLD2 = '#a9761f', WOOD = '#6b4423';
function shade(hex, f) {
  const m = /^#([0-9a-f]{6})$/i.exec(hex || '');
  if (!m) return '#a8a29e';
  const n = parseInt(m[1], 16), c = v => Math.max(0, Math.min(255, Math.round(v)));
  return 'rgb(' + c(((n >> 16) & 255) * f) + ',' +
         c(((n >> 8) & 255) * f) + ',' + c((n & 255) * f) + ')';
}
function skinOf(nm) {
  if (nm === 'Krishna') return '#7091d6';               // the dark-blue lord
  if (nm === 'Bhishma' || nm === 'Vidura') return '#dcb891';
  return SKIN;
}
// ---- the horizon host: a smudge of spears and banners far off ----
function farHost(t, horizonY) {
  if (horizonY < 4) return;
  const scr = cam.yaw * W * 0.6;
  for (const f of deco.far) {
    const x = ((f.x * W - scr) % (W + 20) + (W + 20)) % (W + 20) - 10;
    const y = horizonY + f.row * 3, sw = Math.sin(t / 900 + f.ph) * 1.2;
    ctx.fillStyle = 'rgba(20,12,14,' + (0.5 - f.row * 0.12) + ')';
    ctx.fillRect(x + sw, y - 9 - f.tall * 3, 1.4, 9 + f.tall * 3);
    ctx.beginPath(); ctx.arc(x + sw, y - 10 - f.tall * 3, 1.7, 0, 6.29); ctx.fill();
    if (f.banner) { ctx.fillStyle = 'rgba(120,40,30,.5)'; ctx.fillRect(x + sw, y - 16 - f.tall * 3, 4, 3); }
  }
}
// ---- the royal standard planted at the heart of the vyuh ----
function heartStandard(t, F) {
  const pulse = 1 + 0.06 * Math.sin(t / 500), b = proj(0, 0, 0), Z = ZM;
  const topY = b.y - 52 * pulse * HZ * Z;                      // height leans with pitch
  ctx.fillStyle = 'rgba(0,0,0,.32)';
  ctx.beginPath(); ctx.ellipse(b.x, b.y + 3, 20 * Z, (20 * SQ + 3) * Z, 0, 0, 6.29); ctx.fill();
  ctx.strokeStyle = '#3f2a18'; ctx.lineWidth = Math.max(1.5, 4 * Z); ctx.lineCap = 'round';
  ctx.beginPath(); ctx.moveTo(b.x, b.y + 3); ctx.lineTo(b.x, topY); ctx.stroke();
  const wv = Math.sin(t / 320) * 4 * Z;
  ctx.fillStyle = '#b1122a';
  ctx.beginPath(); ctx.moveTo(b.x, topY);
  ctx.quadraticCurveTo(b.x + 30 * Z, topY + 6 * Z + wv, b.x + 34 * Z, topY + 12 * Z + wv);
  ctx.lineTo(b.x, topY + 18 * Z); ctx.closePath(); ctx.fill();
  ctx.fillStyle = '#f5c542';
  ctx.beginPath(); ctx.arc(b.x + 12 * Z, topY + 9 * Z + wv * 0.5, 3 * Z, 0, 6.29); ctx.fill();
  ctx.fillStyle = GOLD;
  ctx.beginPath(); ctx.arc(b.x, topY - 2 * Z, 3.4 * Z, 0, 6.29); ctx.fill();
  ctx.fillStyle = '#fbbf24'; ctx.shadowColor = '#f59e0b'; ctx.shadowBlur = 24;
  ctx.beginPath(); ctx.arc(b.x, b.y, 5 * Z, 0, 6.29); ctx.fill(); ctx.shadowBlur = 0;
}
// ---- our camp: tents, banners, cook-fire ----
function drawCamp(t, F) {
  const p = proj(F.camp.wx, F.camp.wz, 0);
  const near = 0.5 + 0.5 * Math.sin(GA0 + cam.yaw), cs = (0.7 + 0.5 * near) * ZM;
  ctx.save(); ctx.translate(p.x, p.y); ctx.scale(cs, cs);
  tent(-60, 0, '#7f1d1d', t); tent(60, 0, '#5b21b6', t + 700); tent(0, -10, '#1d4ed8', t + 1300);
  ctx.fillStyle = '#57534e';
  for (let i = 0; i < 7; i++) {
    const a = (i / 7) * Math.PI * 2;
    ctx.beginPath(); ctx.arc(Math.cos(a) * 13, 26 + Math.sin(a) * 5, 3.2, 0, 6.29); ctx.fill();
  }
  for (let i = 0; i < 3; i++) {
    const fh = 13 + 6 * Math.sin(t / 160 + i * 2.1) + 3 * Math.sin(t / 61 + i);
    ctx.fillStyle = ['#ef4444', '#f97316', '#facc15'][i];
    ctx.beginPath();
    ctx.moveTo(-8 + i * 8, 26); ctx.lineTo(-4 + i * 8, 26 - fh); ctx.lineTo(i * 8, 26);
    ctx.closePath(); ctx.fill();
  }
  ctx.fillStyle = '#fbbf24'; ctx.shadowColor = '#fb923c'; ctx.shadowBlur = 30;
  ctx.globalAlpha = 0.75 + 0.25 * Math.sin(t / 200);
  ctx.beginPath(); ctx.ellipse(0, 26, 18, 5, 0, 0, 6.29); ctx.fill();
  ctx.shadowBlur = 0; ctx.globalAlpha = 1;
  ctx.restore();
  if (Math.random() < 0.6) embers.push({x: p.x + (Math.random() - .5) * 16 * cs, y: p.y + 20 * cs, vy: -46 - Math.random() * 40, l: 1});
  if (Math.random() < 0.2) smoke.push({x: p.x, y: p.y + 6 * cs, vy: -20, l: 1});
}
// ---- the host manning the rings: place, sort by depth, then draw ----
function drawArmy(t, F) {
  const list = [];
  for (const u of deco.army) {
    const R = F.R0 - u.i * F.gap, gate = 0.5 + u.i * 0.04;
    const a0 = ringGap(F, u.i, t) + gate / 2, span = Math.PI * 2 - gate;
    let f = (u.base + t * u.speed) % 1; if (f < 0) f += 1;
    const a = a0 + f * span, p = ringPt(F, R + u.ro, a);
    const beta = a + cam.yaw, near = 0.5 + 0.5 * Math.sin(beta);   // nearer => larger
    const sc = (0.5 + 0.55 * near) * (1 - u.i * 0.045) * ZM;
    const face = (-Math.sin(beta)) * (u.i % 2 ? -1 : 1) >= 0 ? 1 : -1;
    list.push({x: p.x, y: p.y, sc, ph: u.ph, face, type: u.type});
  }
  list.sort((m, n) => m.y - n.y);
  for (const u of list) {
    if (u.type === 'elephant') drawElephant(t, u);
    else if (u.type === 'horse') drawHorseman(t, u);
    else drawFootman(t, u);
  }
}
function drawFootman(t, u) {
  const s = u.sc, x = u.x, y = u.y, face = u.face;
  const bob = Math.sin(t / 300 + u.ph) * 0.6;
  ctx.save(); ctx.translate(x, y - bob); ctx.scale(s * face, s);
  ctx.fillStyle = 'rgba(0,0,0,.26)';
  ctx.beginPath(); ctx.ellipse(0, bob, 6, 2.2, 0, 0, 6.29); ctx.fill();
  ctx.strokeStyle = '#4b3620'; ctx.lineWidth = 1.3; ctx.lineCap = 'round';   // spear
  ctx.beginPath(); ctx.moveTo(4, 0); ctx.lineTo(6, -22); ctx.stroke();
  ctx.fillStyle = '#c9ccd1';
  ctx.beginPath(); ctx.moveTo(6, -26); ctx.lineTo(8, -21); ctx.lineTo(4, -21); ctx.closePath(); ctx.fill();
  ctx.fillStyle = '#3b2b2e';                                                  // tunic
  rr(-4, -15, 8, 12, 3); ctx.fill();
  ctx.strokeStyle = '#241a1a'; ctx.lineWidth = 1.8;                           // legs
  ctx.beginPath(); ctx.moveTo(-1.5, -3); ctx.lineTo(-2.5, 0); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(1.5, -3); ctx.lineTo(2.5, 0); ctx.stroke();
  ctx.fillStyle = '#6b3a2a'; ctx.strokeStyle = '#241110'; ctx.lineWidth = 1;  // shield
  ctx.beginPath(); ctx.ellipse(-4, -9, 2.5, 4, 0, 0, 6.29); ctx.fill(); ctx.stroke();
  ctx.fillStyle = '#7a5a44';                                                  // head
  ctx.beginPath(); ctx.arc(0.5, -18, 2.5, 0, 6.29); ctx.fill();
  ctx.fillStyle = '#4a4e57';                                                  // helm + spike
  ctx.beginPath(); ctx.arc(0.5, -19, 2.9, Math.PI, 0); ctx.fill();
  ctx.strokeStyle = '#4a4e57'; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(0.5, -22); ctx.lineTo(0.5, -24.5); ctx.stroke();
  ctx.restore();
}
function drawHorseman(t, u) {
  const s = u.sc, x = u.x, y = u.y, face = u.face;
  const g = Math.sin(t / 150 + u.ph);
  ctx.save(); ctx.translate(x, y); ctx.scale(s * face, s);
  ctx.fillStyle = 'rgba(0,0,0,.24)';
  ctx.beginPath(); ctx.ellipse(0, 0, 12, 2.8, 0, 0, 6.29); ctx.fill();
  const horse = '#4b3a26';
  ctx.strokeStyle = horse; ctx.lineWidth = 1.6; ctx.lineCap = 'round';        // legs
  ctx.beginPath(); ctx.moveTo(-6, -6); ctx.lineTo(-7 + g, 0); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(-3, -6); ctx.lineTo(-2 - g, 0); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(5, -6); ctx.lineTo(6 + g, 0); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(8, -6); ctx.lineTo(7 - g, 0); ctx.stroke();
  ctx.fillStyle = horse;                                                      // body
  ctx.beginPath(); ctx.ellipse(0, -9, 9, 4, 0, 0, 6.29); ctx.fill();
  ctx.strokeStyle = horse; ctx.lineWidth = 1.4;                              // tail
  ctx.beginPath(); ctx.moveTo(-9, -10); ctx.quadraticCurveTo(-13, -8, -12 + g, -3); ctx.stroke();
  ctx.fillStyle = horse;                                                      // neck + head
  ctx.beginPath(); ctx.moveTo(7, -11); ctx.lineTo(12, -19); ctx.lineTo(15, -18);
  ctx.lineTo(16, -15); ctx.lineTo(11, -12); ctx.closePath(); ctx.fill();
  ctx.strokeStyle = '#2c2114'; ctx.lineWidth = 1.2;                          // mane
  ctx.beginPath(); ctx.moveTo(8, -13); ctx.lineTo(12, -18); ctx.stroke();
  ctx.fillStyle = '#3b2b2e';                                                  // rider
  rr(-2, -22, 6, 10, 2.4); ctx.fill();
  ctx.fillStyle = '#7a5a44'; ctx.beginPath(); ctx.arc(1, -24, 2.3, 0, 6.29); ctx.fill();
  ctx.fillStyle = '#4a4e57'; ctx.beginPath(); ctx.arc(1, -25, 2.6, Math.PI, 0); ctx.fill();
  ctx.strokeStyle = '#4b3620'; ctx.lineWidth = 1.2;                          // lance
  ctx.beginPath(); ctx.moveTo(3, -20); ctx.lineTo(15, -30); ctx.stroke();
  ctx.fillStyle = '#c9ccd1';
  ctx.beginPath(); ctx.moveTo(15, -30); ctx.lineTo(18, -30); ctx.lineTo(15, -27); ctx.closePath(); ctx.fill();
  ctx.restore();
}
function drawElephant(t, u) {
  const s = u.sc * 1.15, x = u.x, y = u.y, face = u.face;
  const tr = Math.sin(t / 380 + u.ph);
  ctx.save(); ctx.translate(x, y); ctx.scale(s * face, s);
  ctx.fillStyle = 'rgba(0,0,0,.30)';
  ctx.beginPath(); ctx.ellipse(0, 0, 17, 3.6, 0, 0, 6.29); ctx.fill();
  const grey = '#6b6a70', greyD = '#4c4b52';
  ctx.fillStyle = greyD;                                                      // legs
  ctx.fillRect(-11, -9, 4.5, 9); ctx.fillRect(-4, -9, 4.5, 9);
  ctx.fillRect(4, -9, 4.5, 9); ctx.fillRect(9, -9, 4.5, 9);
  ctx.fillStyle = grey;                                                       // body
  ctx.beginPath(); ctx.ellipse(0, -16, 15, 9, 0, 0, 6.29); ctx.fill();
  ctx.strokeStyle = greyD; ctx.lineWidth = 1.4; ctx.lineCap = 'round';        // tail
  ctx.beginPath(); ctx.moveTo(-14, -18); ctx.lineTo(-17, -8); ctx.stroke();
  ctx.fillStyle = grey;                                                       // head
  ctx.beginPath(); ctx.ellipse(15, -18, 8, 8, 0, 0, 6.29); ctx.fill();
  ctx.fillStyle = greyD;                                                      // ear (flaps)
  ctx.beginPath(); ctx.ellipse(13, -19, 5, 6 + tr, 0, 0, 6.29); ctx.fill();
  ctx.strokeStyle = grey; ctx.lineWidth = 3.4;                               // trunk (sways)
  ctx.beginPath(); ctx.moveTo(21, -16); ctx.quadraticCurveTo(26, -10, 24 + tr * 2, -2 + tr); ctx.stroke();
  ctx.strokeStyle = '#efe6d0'; ctx.lineWidth = 1.8;                          // tusk
  ctx.beginPath(); ctx.moveTo(20, -13); ctx.lineTo(25, -8); ctx.stroke();
  ctx.fillStyle = '#161016'; ctx.beginPath(); ctx.arc(17, -20, 1, 0, 6.29); ctx.fill();
  ctx.fillStyle = '#7a1f2b';                                                  // howdah
  rr(-8, -30, 16, 8, 2); ctx.fill();
  ctx.strokeStyle = GOLD; ctx.lineWidth = 1; ctx.strokeRect(-8, -30, 16, 8);
  ctx.fillStyle = '#a3142b';                                                  // canopy
  ctx.beginPath(); ctx.moveTo(-9, -30); ctx.lineTo(0, -37); ctx.lineTo(9, -30); ctx.closePath(); ctx.fill();
  ctx.fillStyle = GOLD; ctx.beginPath(); ctx.arc(0, -38, 1.6, 0, 6.29); ctx.fill();
  ctx.fillStyle = '#7a5a44'; ctx.beginPath(); ctx.arc(0, -32, 2.2, 0, 6.29); ctx.fill();   // archer
  ctx.restore();
}
function weapon(t, nm, col, dark) {
  ctx.lineCap = 'round';
  if (nm === 'Arjun' || nm === 'Bhishma') {          // war bow + nocked arrow
    const tall = nm === 'Bhishma' ? 4 : 0;
    ctx.strokeStyle = WOOD; ctx.lineWidth = 2.4;
    ctx.beginPath(); ctx.moveTo(13, -46 - tall);
    ctx.quadraticCurveTo(4, -30, 13, -14 + tall); ctx.stroke();
    ctx.strokeStyle = '#e7e0cf'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(13, -46 - tall); ctx.lineTo(13, -14 + tall); ctx.stroke();
    ctx.strokeStyle = IRON; ctx.lineWidth = 1.6;
    ctx.beginPath(); ctx.moveTo(2, -30); ctx.lineTo(20, -30); ctx.stroke();
    ctx.fillStyle = IRON;
    ctx.beginPath(); ctx.moveTo(20, -33); ctx.lineTo(24, -30); ctx.lineTo(20, -27);
    ctx.closePath(); ctx.fill();
  } else if (nm === 'Karna') {                        // kavacha shield, sun heart
    ctx.fillStyle = '#8a5a2b'; ctx.strokeStyle = dark; ctx.lineWidth = 1.5;
    rr(6, -38, 12, 17, 5); ctx.fill(); ctx.stroke();
    ctx.fillStyle = '#f5c542';
    ctx.beginPath(); ctx.arc(12, -29.5, 3.4, 0, 6.29); ctx.fill();
  } else if (nm === 'Bhima') {                        // gada over the shoulder
    ctx.strokeStyle = WOOD; ctx.lineWidth = 3.4;
    ctx.beginPath(); ctx.moveTo(4, -28); ctx.lineTo(18, -48); ctx.stroke();
    ctx.fillStyle = '#4b5563'; ctx.strokeStyle = dark; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.arc(19, -50, 6, 0, 6.29); ctx.fill(); ctx.stroke();
    ctx.fillStyle = 'rgba(255,255,255,.35)';
    ctx.beginPath(); ctx.arc(17, -52, 2, 0, 6.29); ctx.fill();
  } else if (nm === 'Krishna') {                      // Panchajanya to the lips
    ctx.strokeStyle = SKIN; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.moveTo(4, -28); ctx.lineTo(9, -37); ctx.stroke();
    ctx.fillStyle = '#f8fafc'; ctx.strokeStyle = dark; ctx.lineWidth = 1.2;
    ctx.beginPath(); ctx.arc(11, -38, 3.6, 0, 6.29); ctx.fill(); ctx.stroke();
    ctx.beginPath(); ctx.arc(11, -38, 1.8, 0, 6.29); ctx.stroke();
    ctx.strokeStyle = 'rgba(248,250,252,.8)'; ctx.lineWidth = 1.2;
    for (let k = 0; k < 3; k++) {
      const yy = -41 + k * 3;
      ctx.beginPath(); ctx.moveTo(15, yy); ctx.lineTo(21, yy - 2); ctx.stroke();
    }
  } else if (nm === 'Draupadi') {                     // fire-born flame in palm
    ctx.strokeStyle = SKIN; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.moveTo(4, -28); ctx.lineTo(11, -30); ctx.stroke();
    for (let k = 0; k < 3; k++) {
      const fh = 8 + 4 * Math.sin(t / 150 + k * 2.1);
      ctx.fillStyle = ['#ef4444', '#f97316', '#facc15'][k];
      ctx.beginPath();
      ctx.moveTo(7 + k * 3.4, -30); ctx.lineTo(8.7 + k * 3.4, -30 - fh); ctx.lineTo(10.4 + k * 3.4, -30);
      ctx.closePath(); ctx.fill();
    }
  } else if (nm === 'Abhimanyu') {                    // twin swords
    ctx.strokeStyle = IRON; ctx.lineWidth = 2.2;
    ctx.beginPath(); ctx.moveTo(4, -28); ctx.lineTo(16, -48); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(4, -28); ctx.lineTo(18, -22); ctx.stroke();
    ctx.strokeStyle = GOLD; ctx.lineWidth = 2.6;
    ctx.beginPath(); ctx.moveTo(12, -42); ctx.lineTo(17, -39); ctx.stroke();
    ctx.fillStyle = IRON;
    ctx.beginPath(); ctx.moveTo(16, -51); ctx.lineTo(18, -46); ctx.lineTo(14, -46);
    ctx.closePath(); ctx.fill();
  } else if (nm === 'Yudhishthira') {                 // royal staff
    ctx.strokeStyle = WOOD; ctx.lineWidth = 2.4;
    ctx.beginPath(); ctx.moveTo(11, -8); ctx.lineTo(11, -44); ctx.stroke();
    ctx.fillStyle = GOLD;
    ctx.beginPath(); ctx.arc(11, -46, 3, 0, 6.29); ctx.fill();
  } else {                                            // spear (Vidura, guests)
    ctx.strokeStyle = WOOD; ctx.lineWidth = 2.4;
    ctx.beginPath(); ctx.moveTo(11, -8); ctx.lineTo(11, -44); ctx.stroke();
    ctx.fillStyle = IRON;
    ctx.beginPath(); ctx.moveTo(11, -52); ctx.lineTo(14, -44); ctx.lineTo(8, -44);
    ctx.closePath(); ctx.fill();
  }
  if (nm === 'Vidura') {                              // owl on the shoulder
    ctx.fillStyle = '#6b7280';
    ctx.beginPath(); ctx.ellipse(-8, -34, 4.4, 5.4, 0, 0, 6.29); ctx.fill();
    ctx.fillStyle = '#f8fafc';
    ctx.beginPath(); ctx.arc(-9.4, -36, 1.9, 0, 6.29); ctx.fill();
    ctx.beginPath(); ctx.arc(-6.4, -36, 1.9, 0, 6.29); ctx.fill();
    ctx.fillStyle = '#111827';
    ctx.beginPath(); ctx.arc(-9.4, -36, 0.9, 0, 6.29); ctx.fill();
    ctx.beginPath(); ctx.arc(-6.4, -36, 0.9, 0, 6.29); ctx.fill();
    ctx.fillStyle = '#f59e0b';
    ctx.beginPath(); ctx.moveTo(-8.8, -33.6); ctx.lineTo(-7.2, -33.6); ctx.lineTo(-8, -32.4);
    ctx.closePath(); ctx.fill();
  }
}
// Headgear is the strongest read of who a hero is: crown, feather, circlet.
function headgear(t, nm, hx, hy, col) {
  if (nm === 'Krishna') {                        // mor-mukut: gold band + peacock feather
    ctx.fillStyle = GOLD;
    ctx.beginPath(); ctx.moveTo(hx - 5, hy - 3.5); ctx.lineTo(hx + 5, hy - 3.5);
    ctx.lineTo(hx + 4, hy - 6); ctx.lineTo(hx - 4, hy - 6); ctx.closePath(); ctx.fill();
    const wv = Math.sin(t / 300) * 1.5;
    ctx.strokeStyle = '#1f7a5a'; ctx.lineWidth = 1.6; ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(hx - 1, hy - 6); ctx.quadraticCurveTo(hx - 5 + wv, hy - 13, hx - 3 + wv, hy - 18); ctx.stroke();
    ctx.fillStyle = '#12654d';
    ctx.beginPath(); ctx.ellipse(hx - 3 + wv, hy - 18, 2.3, 3.3, 0, 0, 6.29); ctx.fill();
    ctx.fillStyle = '#2b7fd6';
    ctx.beginPath(); ctx.arc(hx - 3 + wv, hy - 18, 1.5, 0, 6.29); ctx.fill();
    ctx.fillStyle = GOLD; ctx.beginPath(); ctx.arc(hx - 3 + wv, hy - 18, 0.7, 0, 6.29); ctx.fill();
  } else if (nm === 'Yudhishthira' || nm === 'Arjun' || nm === 'Karna') {   // kirita mukut
    const tall = nm === 'Arjun' ? 4 : 0;
    ctx.fillStyle = GOLD;
    ctx.beginPath();
    ctx.moveTo(hx - 5.5, hy - 3); ctx.lineTo(hx + 5.5, hy - 3);
    ctx.lineTo(hx + 4, hy - 8); ctx.lineTo(hx + 2, hy - 5.5);
    ctx.lineTo(hx, hy - 11 - tall); ctx.lineTo(hx - 2, hy - 5.5);
    ctx.lineTo(hx - 4, hy - 8); ctx.closePath(); ctx.fill();
    ctx.fillStyle = '#e23b4e'; ctx.beginPath(); ctx.arc(hx, hy - 4.5, 1.2, 0, 6.29); ctx.fill();
    ctx.fillStyle = GOLD2; ctx.beginPath(); ctx.arc(hx, hy - 12 - tall, 1.3, 0, 6.29); ctx.fill();
    if (nm === 'Karna') {                         // the sun-gold kavacha, faintly aglow
      ctx.strokeStyle = 'rgba(245,197,66,.5)'; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(hx, hy, 8, 0, 6.29); ctx.stroke();
    }
  } else if (nm === 'Bhima') {                    // gold circlet + topknot
    ctx.fillStyle = GOLD; ctx.fillRect(hx - 5.5, hy - 5.5, 11, 2.2);
    ctx.fillStyle = '#241812'; ctx.beginPath(); ctx.arc(hx, hy - 8, 2.4, 0, 6.29); ctx.fill();
  } else if (nm === 'Draupadi') {                 // maang-tikka + long braid
    ctx.strokeStyle = GOLD; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(hx, hy - 5.5); ctx.lineTo(hx, hy - 8); ctx.stroke();
    ctx.fillStyle = GOLD; ctx.beginPath(); ctx.arc(hx, hy - 8.4, 1.2, 0, 6.29); ctx.fill();
    ctx.fillStyle = '#241812';
    ctx.beginPath(); ctx.moveTo(hx - 5, hy); ctx.quadraticCurveTo(hx - 9, hy + 8, hx - 6, hy + 14);
    ctx.lineTo(hx - 4, hy + 13); ctx.quadraticCurveTo(hx - 6, hy + 7, hx - 3, hy); ctx.closePath(); ctx.fill();
  } else if (nm === 'Vidura') {                   // sage: tied grey hair
    ctx.fillStyle = '#d6d3d1'; ctx.beginPath(); ctx.arc(hx - 0.5, hy - 6.5, 2, 0, 6.29); ctx.fill();
  } else if (nm === 'Bhishma') {                  // silver circlet
    ctx.fillStyle = '#d8dde6'; ctx.fillRect(hx - 5.5, hy - 5.5, 11, 2);
    ctx.fillStyle = GOLD; ctx.beginPath(); ctx.arc(hx, hy - 6, 1.1, 0, 6.29); ctx.fill();
  } else {                                        // warrior helm + crest plume
    ctx.fillStyle = shade(col, 0.8);
    ctx.beginPath(); ctx.arc(hx, hy - 1, 6, Math.PI, 0); ctx.fill();
    ctx.strokeStyle = GOLD; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.arc(hx, hy - 1, 6, Math.PI, 0); ctx.stroke();
    ctx.fillStyle = '#dc2626';
    ctx.beginPath(); ctx.moveTo(hx - 1, hy - 7); ctx.quadraticCurveTo(hx - 6, hy - 12, hx - 8, hy - 6);
    ctx.quadraticCurveTo(hx - 4, hy - 6, hx - 1, hy - 4); ctx.closePath(); ctx.fill();
  }
}
function drawWarrior(t, s, d) {
  const ch = d.character || {};
  const col = ch.hex || '#c9a24a';
  const dark = shade(col, 0.62), lite = shade(col, 1.22);
  const nm = ch.name || '';
  const female = nm === 'Draupadi';
  const skin = skinOf(nm), skinD = shade(skin, 0.74);
  const face = s.face || 1;
  const x = s.sx || 0, y = s.sy || 0, scr = s.scr || 1;    // projected position + camera scale
  const wk = d.live ? 1 : 0;
  const sw = Math.sin(t / 165 + s.ph) * wk;                 // gait
  const build = nm === 'Bhima' ? 1.16 : nm === 'Abhimanyu' ? 0.9 : nm === 'Bhishma' ? 1.05 : 1;
  // planted ground shadow
  ctx.fillStyle = 'rgba(0,0,0,.32)';
  ctx.beginPath(); ctx.ellipse(x, y + 1.5 * scr, 12 * build * scr, 3.6 * scr, 0, 0, 6.29); ctx.fill();
  ctx.save(); ctx.translate(x, y); ctx.scale(face * build * scr, build * scr);
  const dhoti = nm === 'Krishna' ? '#e6b93f' : col;        // pitambara for Krishna
  const dhotiD = shade(dhoti, 0.62), hem = Math.sin(t / 300 + s.ph) * 1.2 * wk;
  // ---------- legs / lower garment ----------
  if (!female) {
    ctx.strokeStyle = skin; ctx.lineWidth = 3.4; ctx.lineCap = 'round';
    const ft = 5 * sw;
    ctx.beginPath(); ctx.moveTo(-2, -22); ctx.lineTo(-2 - 2 * sw, -11); ctx.lineTo(-2 - ft, -0.5); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(2, -22); ctx.lineTo(2 + 2 * sw, -11); ctx.lineTo(2 + ft, -0.5); ctx.stroke();
    ctx.strokeStyle = GOLD; ctx.lineWidth = 1.6;           // anklets
    ctx.beginPath(); ctx.moveTo(-3.6 - ft, -1.6); ctx.lineTo(-0.4 - ft, -1.6); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(0.4 + ft, -1.6); ctx.lineTo(3.6 + ft, -1.6); ctx.stroke();
    ctx.fillStyle = dhoti;                                 // dhoti to the knee, wavy hem
    ctx.beginPath();
    ctx.moveTo(-6, -24); ctx.lineTo(6, -24);
    ctx.lineTo(8, -12 + hem); ctx.lineTo(3, -9 - hem); ctx.lineTo(0, -12 + hem);
    ctx.lineTo(-3, -9 - hem); ctx.lineTo(-8, -12 - hem); ctx.closePath(); ctx.fill();
    ctx.strokeStyle = dhotiD; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(0, -23); ctx.lineTo(0, -11); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(-4, -23); ctx.lineTo(-5, -12); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(4, -23); ctx.lineTo(5, -12); ctx.stroke();
  } else {
    ctx.fillStyle = col;                                   // sari to the ankles
    ctx.beginPath();
    ctx.moveTo(-5, -26); ctx.lineTo(5, -26);
    ctx.quadraticCurveTo(9, -12, 7 + hem, -0.5); ctx.lineTo(-7 - hem, -0.5);
    ctx.quadraticCurveTo(-9, -12, -5, -26); ctx.closePath(); ctx.fill();
    ctx.strokeStyle = shade(col, 0.7); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(-1, -24); ctx.lineTo(-3 + hem, -1); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(3, -24); ctx.lineTo(4 + hem, -1); ctx.stroke();
    ctx.strokeStyle = GOLD; ctx.lineWidth = 1.2;           // gold-bordered hem
    ctx.beginPath(); ctx.moveTo(-7 - hem, -1.5); ctx.lineTo(7 + hem, -1.5); ctx.stroke();
  }
  // ---------- back arm (swings with the gait) ----------
  const bhx = -9 - 4 * sw, bhy = -24 + 1.5 * sw;
  ctx.strokeStyle = skin; ctx.lineWidth = 2.8; ctx.lineCap = 'round';
  ctx.beginPath(); ctx.moveTo(-6, -39); ctx.lineTo((-6 + bhx) / 2 - 1, (-39 + bhy) / 2); ctx.lineTo(bhx, bhy); ctx.stroke();
  ctx.strokeStyle = GOLD; ctx.lineWidth = 1.6;             // bajuband
  ctx.beginPath(); ctx.moveTo(-8, -36); ctx.lineTo(-4, -36); ctx.stroke();
  // ---------- torso ----------
  if (female) {
    ctx.fillStyle = col;                                   // choli
    ctx.beginPath();
    ctx.moveTo(-4, -26); ctx.lineTo(-5, -38); ctx.quadraticCurveTo(0, -41, 5, -38);
    ctx.lineTo(4, -26); ctx.closePath(); ctx.fill();
  } else {
    ctx.fillStyle = skin;                                  // bare torso
    ctx.beginPath();
    ctx.moveTo(-4, -24); ctx.lineTo(-6, -39); ctx.quadraticCurveTo(0, -43, 6, -39);
    ctx.lineTo(4, -24); ctx.closePath(); ctx.fill();
    ctx.strokeStyle = skinD; ctx.lineWidth = 1;            // muscle
    ctx.beginPath(); ctx.moveTo(0, -39); ctx.lineTo(0, -27); ctx.stroke();
    ctx.beginPath(); ctx.arc(-2.6, -35, 2, -0.4, 1.2); ctx.stroke();
    ctx.beginPath(); ctx.arc(2.6, -35, 2, 2, 3.6); ctx.stroke();
  }
  ctx.fillStyle = nm === 'Krishna' ? '#2f8f6b' : GOLD;     // kamarband
  ctx.fillRect(-6, -25, 12, 2.4);
  ctx.strokeStyle = nm === 'Krishna' ? '#e6b93f' : lite; ctx.lineWidth = 2.4;  // sash across chest
  ctx.beginPath(); ctx.moveTo(-5, -38); ctx.lineTo(5, -27); ctx.stroke();
  const fl = Math.sin(t / 260 + s.ph) * 2 * wk;            // its end flowing behind
  ctx.strokeStyle = nm === 'Krishna' ? '#e6b93f' : col; ctx.lineWidth = 2;
  ctx.beginPath(); ctx.moveTo(-5, -38); ctx.quadraticCurveTo(-11, -33 + fl, -12, -25 + fl); ctx.stroke();
  ctx.strokeStyle = GOLD; ctx.lineWidth = 1.3;             // necklace + pendant
  ctx.beginPath(); ctx.arc(0, -40, 3.4, 0.2, Math.PI - 0.2); ctx.stroke();
  ctx.fillStyle = '#e23b4e'; ctx.beginPath(); ctx.arc(0, -37, 1.2, 0, 6.29); ctx.fill();
  // ---------- head ----------
  const hx = 1.5, hy = -47;
  ctx.fillStyle = skin; ctx.beginPath(); ctx.arc(hx, hy, 5.6, 0, 6.29); ctx.fill();
  ctx.fillStyle = (nm === 'Bhishma' || nm === 'Vidura') ? '#e7e5e4' : '#241812';  // hair
  ctx.beginPath(); ctx.arc(hx - 1.5, hy - 0.5, 5.9, 1.4, 4.2); ctx.fill();
  ctx.fillStyle = GOLD;                                    // ear + kundala
  ctx.beginPath(); ctx.arc(hx - 4.4, hy + 1, nm === 'Karna' ? 1.7 : 1.1, 0, 6.29); ctx.fill();
  ctx.fillStyle = '#20140f'; ctx.beginPath(); ctx.arc(hx + 2.6, hy - 0.4, 1.1, 0, 6.29); ctx.fill();  // eye
  ctx.strokeStyle = '#20140f'; ctx.lineWidth = 1;          // brow
  ctx.beginPath(); ctx.moveTo(hx + 0.6, hy - 2.4); ctx.lineTo(hx + 4, hy - 1.8); ctx.stroke();
  if (!female) {                                           // mustache
    ctx.strokeStyle = (nm === 'Bhishma' || nm === 'Vidura') ? '#d6d3d1' : '#20140f'; ctx.lineWidth = 1.3;
    ctx.beginPath(); ctx.moveTo(hx + 1.2, hy + 2.6); ctx.quadraticCurveTo(hx + 4, hy + 2.2, hx + 5.4, hy + 3.4); ctx.stroke();
  } else {
    ctx.fillStyle = '#c0143b'; ctx.beginPath(); ctx.arc(hx + 1, hy - 3.2, 1, 0, 6.29); ctx.fill();  // bindi
  }
  ctx.strokeStyle = nm === 'Krishna' ? '#c8a24a' : '#b0143b'; ctx.lineWidth = 1;  // tilak
  ctx.beginPath(); ctx.moveTo(hx + 0.6, hy - 3); ctx.lineTo(hx + 1.4, hy - 0.5); ctx.stroke();
  if (nm === 'Bhishma') {                                  // elder's flowing beard
    ctx.fillStyle = '#eceae8';
    ctx.beginPath(); ctx.moveTo(hx - 3, hy + 2); ctx.lineTo(hx + 4, hy + 2);
    ctx.quadraticCurveTo(hx + 1, hy + 12, hx - 1, hy + 4); ctx.closePath(); ctx.fill();
  }
  headgear(t, nm, hx, hy, col);
  // ---------- weapon (front hand), lifted to the taller frame ----------
  ctx.save(); ctx.translate(0, -6); weapon(t, nm, col, dark); ctx.restore();
  // ---------- front arm reaching to the grip ----------
  ctx.strokeStyle = skin; ctx.lineWidth = 2.9; ctx.lineCap = 'round';
  ctx.beginPath(); ctx.moveTo(6, -39); ctx.lineTo(9, -32); ctx.lineTo(9, -26); ctx.stroke();
  ctx.strokeStyle = GOLD; ctx.lineWidth = 1.6;
  ctx.beginPath(); ctx.moveTo(4.4, -36); ctx.lineTo(7.6, -36); ctx.stroke();
  ctx.restore();
  // ---------- label + status (screen space, offsets follow the figure scale) ----------
  const label = ch.name || short2(d.label);
  ctx.font = '11px sans-serif';
  const nw = ctx.measureText(label).width + 12;
  ctx.fillStyle = 'rgba(24,12,8,.85)';
  rr(x - nw / 2, y + 8 * scr, nw, 16, 8); ctx.fill();
  ctx.fillStyle = col; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText(label, x, y + 16 * scr);
  const em = d.tool ? (TOOL_EMOJI[d.tool.name] || '⚙️') : null;
  if (d.live && em && (d.tool.status === 'running' || d.tool.status === 'pending')) {
    const by = y - (66 * scr + 8) + Math.sin(t / 500) * 2;
    ctx.fillStyle = '#fff8ea'; ctx.beginPath(); ctx.arc(x + 20, by, 11, 0, 6.29); ctx.fill();
    ctx.strokeStyle = '#b45309'; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.font = '12px sans-serif'; ctx.fillText(em, x + 20, by + 1);
  }
  if (!d.live) {
    ctx.font = 'bold 12px sans-serif'; ctx.fillStyle = 'rgba(231,220,196,.8)';
    ctx.fillText('z', x + 14 * scr + Math.sin(t / 900) * 2, y - 58 * scr - ((t / 1400 + s.ph) % 5));
  }
  if (s.id === selected) {
    ctx.strokeStyle = '#fde68a'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.ellipse(x, y - 30 * scr, 18 * scr, 34 * scr, 0, 0, 6.29); ctx.stroke();
  }
}
function short2(s) {
  s = s || '';
  return s.length > 24 ? s.slice(0, 23) + '…' : s;
}
function row(k, v) { return '<dt>' + k + '</dt><dd>' + (v || '—') + '</dd>'; }
function showCard(id) {
  const rec = troops.get(id); if (!rec) return;
  const d = rec.data, ch = d.character || {};
  document.getElementById('card').style.display = 'block';
  document.getElementById('c-name').textContent = (ch.token ? ch.token + ' ' : '') + (ch.name || short2(d.label));
  document.getElementById('c-sub').textContent =
    (ch.title ? ch.title + ' · ' : '') + (D.scope ? 'Kurukshetra · ' + D.scope : 'Kurukshetra');
  const st = d.live ? 'on field' : 'at camp';
  document.getElementById('c-tags').innerHTML =
    '<span class="tag ' + (d.live ? 'field' : 'camp') + '">' + st + '</span>' +
    '<span class="tag role">' + (d.agent || '?') + '</span>';
  let depth = 'muster line';
  const p = progress(d);
  if (p >= 0.99) depth = 'at the heart';
  else if (p >= 0.66) depth = 'inner rings';
  else if (p >= 0.33) depth = 'breaching';
  else if (p > 0) depth = 'advancing';
  document.getElementById('c-dl').innerHTML =
    row('doing', (d.todos && d.todos.current) || (d.tool ? d.tool.name + ':' + d.tool.status : null)) +
    row('todos', d.todos && d.todos.total ? d.todos.done + '/' + d.todos.total : null) +
    row('depth', depth) + row('active', d.active) + row('bearing', ch.bearing);
}
let last = performance.now();
function frame(t) {
  const dt = Math.min(0.05, (t - last) / 1000); last = t;
  draw(t, dt);
  requestAnimationFrame(frame);
}
resize(); poll(); requestAnimationFrame(frame);
</script>
</body>
</html>
"""

def list_projects(con):
    cur = con.cursor()
    rows = cur.execute(
        "SELECT directory, COUNT(*), MAX(time_updated) FROM session"
        " GROUP BY directory ORDER BY MAX(time_updated) DESC LIMIT 30").fetchall()
    return [{"dir": d, "sessions": c} for d, c, _ in rows]


def snapshot(params):
    q = urllib.parse.parse_qs(params)
    args = CFG
    directory = q.get("dir", [args.dir])[0]
    session_focus = q.get("session", [args.session])[0]
    show_all = "all" in q or args.all
    try:
        max_n = int(q.get("max", [args.max])[0])
    except ValueError:
        max_n = args.max
    fleet_path = q.get("fleet", [args.fleet])[0]
    now = int(time.time() * 1000)
    con = CORE.connect_ro(args.db)
    try:
        sessions = CORE.load_sessions(con, directory, session_focus, max_n, show_all)
        ids = [r[0] for r in sessions]
        todos = CORE.load_todos(con, ids)
        tools = CORE.load_last_tools(con, ids)
        projects = list_projects(con)
    finally:
        con.close()
    cast = []
    if not args.no_cast:
        cast = CORE.load_cast(args.cast or CORE.default_cast())
    lookup = CORE.cast_lookup(cast)
    cast_pos = {}
    for i, e in enumerate(cast):
        try:
            cast_pos[str(e.get("name", "")).lower()] = i
        except AttributeError:
            continue
    auto_cache = {}
    out_sessions = []
    idset = {r[0] for r in sessions}
    n = 0
    for r in sessions:
        sid, pid, title, agent, model, _d, created, updated = r
        td = todos.get(sid, [])
        done = sum(1 for _, s in td if s in ("completed",))
        current = next((c for c, s in td if s == "in_progress"), None)
        lt = tools.get(sid)
        entry = cast[n % len(cast)] if cast else None
        pos = (n % len(cast)) if cast else -1
        n += 1
        out_sessions.append({
            "id": sid, "parent": pid if pid in idset else None,
            "label": " ".join(str(title or sid).split()),
            "agent": agent, "model": CORE.model_short(model),
            "live": now - updated <= args.live_window * 1000,
            "elapsed": CORE.fmt_elapsed(now - created),
            "active": CORE.fmt_ago(updated, now),
            "sub": "%s · %s" % (agent or "?", CORE.model_short(model)),
            "is_root": not (pid and pid in idset),
            "todos": {"done": done, "total": len(td), "current": current},
            "tool": {"name": lt[0], "status": lt[1]} if lt else None,
            "character": char_json(entry, pos),
        })
    out_fleet = []
    if fleet_path:
        man = CORE.load_manifest(fleet_path)
        if isinstance(man, dict) and "workers" in man:
            for i, w in enumerate(man["workers"][:20]):
                pin = str(w.get("character") or "").strip()
                entry = None
                pos = -1
                if pin and not args.no_cast:
                    entry = lookup.get(pin.lower())
                    if entry is None:
                        entry = CORE.auto_character(cast, auto_cache, pin)
                    else:
                        pos = cast_pos.get(pin.lower(), -1)
                elif cast and not args.no_cast:
                    entry = cast[i % len(cast)]
                    pos = i % len(cast)
                out_fleet.append({
                    "id": "fleet:" + str(w.get("name", i)),
                    "parent": None, "is_root": True,
                    "label": str(w.get("name", "?")) + (" · " + str(w.get("slice")) if w.get("slice") else ""),
                    "agent": "fleet", "model": str(w.get("status", "?")),
                    "live": str(w.get("status", "")) == "running",
                    "elapsed": "", "active": "",
                    "sub": str(w.get("status", "")) + ((" · " + str(w.get("note"))) if w.get("note") else ""),
                    "todos": {"done": 0, "total": 0, "current": None},
                    "tool": None,
                    "character": char_json(entry, pos),
                })
    return {
        "now": now, "live": sum(1 for s in out_sessions if s["live"]),
        "shown": len(out_sessions), "sessions": out_sessions, "fleet": out_fleet,
        "scope": os.path.basename(directory.rstrip("/")) or directory,
        "dir": directory,
        "projects": projects,
    }


def char_json(entry, pos=-1):
    if not entry:
        return None
    return {
        "name": entry.get("name"), "symbol": entry.get("symbol"),
        "title": entry.get("title"), "bearing": entry.get("bearing"),
        "token": entry.get("token"),
        "hex": HEX.get(entry.get("color", ""), "#6b7280"),
        "pos": pos,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "pstack-fleet/1"

    def log_message(self, *a):
        pass

    def _send(self, body, ctype, code=200):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self._send(WAR if resolved_theme() == "war" else ISLAND,
                       "text/html; charset=utf-8")
        elif parsed.path == "/war":
            self._send(WAR, "text/html; charset=utf-8")
        elif parsed.path == "/island":
            self._send(ISLAND, "text/html; charset=utf-8")
        elif parsed.path == "/graph":
            self._send(PAGE, "text/html; charset=utf-8")
        elif parsed.path == "/api/fleet":
            try:
                self._send(json.dumps(snapshot(parsed.query)), "application/json")
            except SystemExit as e:
                self._send(json.dumps({"error": str(e)}), "application/json", 500)
            except Exception as e:  # never break polling; the page retries
                self._send(json.dumps({"error": "%s" % e}), "application/json", 500)
        else:
            self._send("not found", "text/plain", 404)


def resolved_theme():
    want = (getattr(CFG, "theme", "auto") or "auto").lower()
    if want in ("war", "island"):
        return want
    return "island" if getattr(CFG, "cast", None) else "war"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Animated pstack fleet board (web).")
    ap.add_argument("--port", type=int, default=8901)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--open", action="store_true", help="open a browser tab")
    ap.add_argument("--db", default=os.path.join(
        os.path.expanduser("~"), ".local", "share", "opencode", "opencode.db"))
    ap.add_argument("--dir", default=os.getcwd())
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--session", default=None)
    ap.add_argument("--fleet", default=None)
    ap.add_argument("--cast", default=None)
    ap.add_argument("--theme", default="auto",
                    help="auto (Mahabharata cast: war, custom cast: island), war, or island")
    ap.add_argument("--no-cast", action="store_true")
    ap.add_argument("--max", type=int, default=25)
    ap.add_argument("--live-window", type=int, default=60)
    global CFG
    CFG = ap.parse_args(argv)
    srv = ThreadingHTTPServer((CFG.host, CFG.port), Handler)
    url = "http://%s:%d/" % (CFG.host, CFG.port)
    print("pstack fleet animation at %s  (Ctrl-C to stop)" % url, flush=True)
    if CFG.open:
        import webbrowser

        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""REST API and a minimal web dashboard.

Built on the standard library's ``http.server`` so ``paperpulse serve`` works
with no extra dependencies -- handy for self-hosting. It exposes the same
capabilities as the CLI:

    GET  /                       -> HTML dashboard (renders the digest)
    GET  /api/sources            -> available paper sources
    GET  /api/digest             -> ranked papers + trust as JSON
    GET  /api/diff               -> what changed vs the last recorded run
    POST /api/feedback           -> {"like": [...], "dislike": [...]}
    GET  /api/community/leaderboard
    GET  /api/score-accuracy?user=... -> like-rate by trust badge (needs community_db)
    GET  /api/notes?paper_id=... -> notes on a paper (needs community_db)
    POST /api/notes              -> {"paper_id", "note", "user"}

Set PAPERPULSE_API_TOKEN to require an ``Authorization: Bearer <token>`` on
every request except ``GET /`` (the static shell has nothing to protect --
it's the /api/* routes it calls client-side that carry actual data).
"""

from __future__ import annotations

import hmac
import json
import os
import threading
import time
from collections import defaultdict
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, cast
from urllib.parse import parse_qs, urlparse

from .cli import TOPIC_PACKS, build_init_config
from .config import Config
from .pipeline import (
    DiffResult,
    DigestResult,
    apply_feedback,
    diff_digest,
    run_digest,
    score_accuracy_report,
)
from .serialize import digest_to_dict
from .sources import available

# Topic filter catalog: group -> [(arXiv category, friendly label), ...]. The
# dashboard renders these as clickable chips; only categories in this catalog
# are accepted from the client, so the filter can't inject arbitrary queries.
TOPIC_CATALOG = {
    "Finance": [
        ["q-fin.TR", "Trading & Microstructure"],
        ["q-fin.PM", "Portfolio Management"],
        ["q-fin.PR", "Pricing of Securities"],
        ["q-fin.RM", "Risk Management"],
        ["q-fin.ST", "Statistical Finance"],
        ["q-fin.CP", "Computational Finance"],
        ["q-fin.MF", "Mathematical Finance"],
        ["q-fin.GN", "General Finance"],
        ["q-fin.EC", "Economics (q-fin)"],
    ],
    "Economics": [
        ["econ.EM", "Econometrics"],
        ["econ.GN", "General Economics"],
        ["econ.TH", "Theoretical Economics"],
    ],
    "Quant & Methods": [
        ["stat.ML", "Machine Learning (stat)"],
        ["cs.LG", "Machine Learning (CS)"],
        ["math.OC", "Optimization & Control"],
        ["math.PR", "Probability"],
        ["stat.ME", "Statistics Methodology"],
    ],
}
_ALL_CATS = {cat for group in TOPIC_CATALOG.values() for cat, _ in group}

_DIGEST_CACHE_TTL = 300  # seconds; re-fetching arXiv on every page hit is wasteful and slow
_digest_cache: dict[tuple[str, ...], dict[str, Any]] = {}  # cats-key -> {"result", "ts"}
_key_locks: defaultdict[tuple[str, ...], threading.Lock] = defaultdict(threading.Lock)
_key_locks_guard = threading.Lock()  # only guards handing out the per-key locks


def _cached(key: tuple[str, ...], build: Callable[[], Any]) -> Any:
    # One lock per key: different filters fetch concurrently, but concurrent
    # requests for the *same* key still collapse into a single arXiv fetch.
    with _key_locks_guard:
        lock = _key_locks[key]
    with lock:
        entry = _digest_cache.get(key)
        if entry and time.time() - entry["ts"] < _DIGEST_CACHE_TTL:
            return entry["result"]
        result = build()
        _digest_cache[key] = {"result": result, "ts": time.time()}
        return result


def _cached_digest(config: Config) -> DigestResult:
    key = ("digest", *sorted(config.categories))
    return cast(DigestResult, _cached(key, lambda: run_digest(config, dry_run=True)))


def _cached_diff(config: Config) -> DiffResult:
    # mark=False: a GET must be safe to repeat, so the endpoint never writes
    # last_seen_at back to the topics log. `paperpulse diff --mark` does that.
    key = ("diff", *sorted(config.categories))
    return cast(DiffResult, _cached(key, lambda: diff_digest(config, mark=False)))


def _parse_cats(query: str) -> list[str] | None:
    """Pull a validated category list out of a ``?cats=a,b,c`` query string."""
    raw = parse_qs(query).get("cats", [""])[0]
    cats = [c for c in raw.split(",") if c in _ALL_CATS]
    return cats or None


def _initial_selection(config: Config) -> list[str]:
    """Which chips start selected, expanding ``q-fin.*`` style wildcards."""
    sel: set[str] = set()
    for c in config.categories:
        if c.endswith(".*"):
            sel.update(cat for cat in _ALL_CATS if cat.startswith(c[:-1]))
        elif c in _ALL_CATS:
            sel.add(c)
    return sorted(sel)

# Static shell: renders instantly, then fetches /api/digest client-side so the
# tab never sits blank through the ~25s arXiv fetch. Placeholders are filled by
# str.replace (not .format) so the JS/CSS braces need no escaping.
_SHELL = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PaperPulse</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.18.1/dist/katex.min.css"
  integrity="sha384-1vdNCNel6Tx/NQa8IR1mGOGKsbGreCkOPfbtPPnUURJ5Tu2PRVfQ/7KLZC+Pi1p1" crossorigin="anonymous">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.18.1/dist/katex.min.js"
  integrity="sha384-ycJ6GAwiS15LoUPipwJOrWTvkUHl/YqELValBwI5I4awP1EeEQJYarj+w85ntcz7" crossorigin="anonymous"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.18.1/dist/contrib/auto-render.min.js"
  integrity="sha384-bjyGPfbij8/NDKJhSGZNP/khQVgtHUE5exjm4Ydllo42FwIgYsdLO2lXGmRBf5Mz" crossorigin="anonymous"></script>
<style>
 :root{--fg:#111;--muted:#666;--line:#e3e3e3;--accent:#3157ff;--chip:#f2f4f8;--chipfg:#333}
 @media(prefers-color-scheme:dark){:root{--fg:#eee;--muted:#9aa;--line:#333;--accent:#7c9bff;--chip:#1c2230;--chipfg:#cdd}body{background:#111}}
 *{box-sizing:border-box}
 body{font-family:system-ui,sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem;color:var(--fg)}
 h1{margin:0 0 .1rem} .sub{color:var(--muted);margin-bottom:1rem}
 .filter{border:1px solid var(--line);border-radius:12px;padding:1rem;margin-bottom:1.2rem}
 .group{margin:.4rem 0} .group b{font-size:.8rem;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
 .chips{display:flex;flex-wrap:wrap;gap:.4rem;margin-top:.35rem}
 .chip{border:1px solid var(--line);background:var(--chip);color:var(--chipfg);border-radius:99px;
   padding:.3rem .7rem;font-size:.85rem;cursor:pointer;user-select:none}
 .chip.on{background:var(--accent);border-color:var(--accent);color:#fff}
 .actions{display:flex;flex-wrap:wrap;gap:.5rem;margin-top:.9rem;align-items:center}
 .btn{border:1px solid var(--line);background:transparent;color:var(--fg);border-radius:8px;
   padding:.4rem .8rem;font-size:.85rem;cursor:pointer}
 .btn.primary{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
 .card{border:1px solid var(--line);border-radius:10px;padding:1rem 1.2rem;margin:1rem 0}
 .card h3{margin:.1rem 0 .4rem}
 .bar{font-family:ui-monospace,monospace;color:var(--accent);font-size:.9rem}
 .badge{font-size:.75rem;padding:.1rem .5rem;border-radius:99px;color:#fff;margin-left:.3rem}
 .clean{background:#1a9d55} .mixed{background:#c98a00} .caution{background:#c0392b}
 .market{display:flex;flex-wrap:wrap;gap:.4rem;margin:.5rem 0}
 .tk{font-family:ui-monospace,monospace;font-size:.8rem;background:var(--chip);color:var(--chipfg);
   border-radius:6px;padding:.15rem .5rem}
 .up{color:#1a9d55} .down{color:#c0392b}
 .flags{margin:.5rem 0 .2rem;padding-left:1.1rem} .flags li{color:#c0392b;font-size:.85rem}
 .why{color:var(--muted);font-style:italic} .conf{color:var(--muted);font-size:.78rem}
 .alpha{border:1px solid var(--line);border-radius:8px;padding:.6rem .8rem;margin:.6rem 0;font-size:.85rem}
 .ahead{font-weight:600;margin-bottom:.35rem}
 .atag{font-size:.72rem;padding:.1rem .45rem;border-radius:99px;margin-left:.3rem;color:#fff}
 .atag.strong{background:#1a9d55} .atag.partial{background:#c98a00} .atag.vague{background:#6b7280}
 .akey{color:var(--muted);text-transform:uppercase;font-size:.7rem;letter-spacing:.04em;margin-right:.35rem}
 .amiss{color:var(--muted);font-style:italic;margin-top:.3rem}
 .prio{font-size:.75rem;padding:.1rem .5rem;border-radius:99px;background:var(--chip);color:var(--chipfg)}
 .meta{color:var(--muted);font-size:.85rem} a{color:var(--accent);text-decoration:none}
 .status{padding:2rem 0;color:var(--muted);text-align:center}
 .spin{display:inline-block;width:1.1rem;height:1.1rem;border:2px solid var(--line);
   border-top-color:var(--accent);border-radius:50%;animation:sp 1s linear infinite;vertical-align:-.2rem;margin-right:.4rem}
 @keyframes sp{to{transform:rotate(360deg)}}
 .setup textarea{width:100%;min-height:4.5rem;font:inherit;background:transparent;color:var(--fg);
   border:1px solid var(--line);border-radius:8px;padding:.5rem;box-sizing:border-box}
 .setup select{font:inherit;background:var(--chip);color:var(--chipfg);border:1px solid var(--line);
   border-radius:8px;padding:.35rem .5rem}
 .setup label{display:block;font-size:.8rem;color:var(--muted);margin:.6rem 0 .3rem}
 .setupToggle{font-size:.8rem;color:var(--muted);cursor:pointer;text-decoration:underline;margin-bottom:.6rem;display:inline-block}
</style></head><body>
<h1>PaperPulse</h1><div class="sub">__SUBTITLE__ · today's ranked, trust-scored papers</div>
<span class="setupToggle" id="setupToggle">⚙ Setup (topics + interests)</span>
<div class="filter setup" id="setup" style="display:none"></div>
<div class="filter" id="filter"></div>
<div id="results"><div class="status">Pick topics and press <b>Run</b>.</div></div>
<script>
const CATALOG = __CATALOG__;
let selected = new Set(__SELECTED__);
const PRESETS = {
  "All finance": g => g==="Finance",
  "Economics": g => g==="Economics",
  "Quant & ML": g => g==="Quant & Methods",
};
function renderFilter(){
  const f = document.getElementById("filter");
  f.innerHTML = "";
  for(const [group, cats] of Object.entries(CATALOG)){
    const gd = document.createElement("div"); gd.className="group";
    const b = document.createElement("b"); b.textContent = group; gd.appendChild(b);
    const wrap = document.createElement("div"); wrap.className="chips";
    for(const [cat,label] of cats){
      const c = document.createElement("span");
      c.className = "chip" + (selected.has(cat) ? " on" : "");
      c.textContent = label;
      c.title = cat;
      c.onclick = () => { selected.has(cat) ? selected.delete(cat) : selected.add(cat); renderFilter(); };
      wrap.appendChild(c);
    }
    gd.appendChild(wrap); f.appendChild(gd);
  }
  const act = document.createElement("div"); act.className="actions";
  for(const [name,pred] of Object.entries(PRESETS)){
    const btn = document.createElement("button"); btn.className="btn"; btn.textContent=name;
    btn.onclick = () => {
      selected = new Set();
      for(const [group,cats] of Object.entries(CATALOG)) if(pred(group)) cats.forEach(([cat])=>selected.add(cat));
      renderFilter();
    };
    act.appendChild(btn);
  }
  const clear = document.createElement("button"); clear.className="btn"; clear.textContent="Clear";
  clear.onclick = () => { selected = new Set(); renderFilter(); };
  act.appendChild(clear);
  const run = document.createElement("button"); run.className="btn primary"; run.textContent="Run";
  run.onclick = load; act.appendChild(run);
  const sinceBtn = document.createElement("button");
  sinceBtn.className = "btn"; sinceBtn.textContent = "Since last week";
  sinceBtn.title = "Diff this category set against the last recorded run";
  sinceBtn.onclick = loadDiff; act.appendChild(sinceBtn);
  f.appendChild(act);
}
function esc(s){ return String(s==null?"":s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
function mathify(s){
  // Abstracts often use \begin{equation*}...\end{equation*} (and align/gather)
  // with no surrounding $/\[ delimiter for auto-render to find. Normalize to
  // $$...$$ instead of registering the environment names as their own
  // delimiters -- braces and "*" are regex metacharacters, and auto-render's
  // delimiter matching broke silently (a mangled partial render) when tried
  // as raw delimiter strings.
  if(s==null) return s;
  return String(s).replace(/\\\\begin\{(equation|align|gather|multline)\*?\}/g, "$$$$")
                   .replace(/\\\\end\{(equation|align|gather|multline)\*?\}/g, "$$$$");
}
function bar(score){ const w=12, fl=Math.max(0,Math.min(w,Math.round(score*w))); return "\\u2588".repeat(fl)+"\\u2591".repeat(w-fl); }
let lastPapers = [];
let resultFilter = "all";
// F1: one-click presets surfacing the Section A/B logic (known factor
// families, untested regions) visually instead of requiring CLI flags.
const RESULT_FILTERS = {
  all: { label: "All", test: () => true },
  usa: { label: "Region: USA only", test: p => (p.regions||[]).includes("USA") },
  known: { label: "Known factor families only",
    test: p => ((p.trust && p.trust.flags) || []).some(f => f.name === "known_topic") },
  untested: { label: "Untested regions only", test: p => !!p.region_note },
  alpha4: { label: "Alpha card: 4/4", test: p => p.alpha && p.alpha.score === 4 },
  alphaStrong: { label: "Alpha card: strong+", test: p => p.alpha && p.alpha.score >= 3 },
  alphaAny: { label: "Has alpha card", test: p => !!p.alpha },
};
async function load(){
  const res = document.getElementById("results");
  if(selected.size===0){ res.innerHTML = '<div class="status">Select at least one topic, then press Run.</div>'; return; }
  res.innerHTML = '<div class="status"><span class="spin"></span>Fetching today\\'s papers from arXiv (~20-30s the first time)…</div>';
  try{
    const r = await fetch("/api/digest?cats=" + [...selected].join(","));
    if(!r.ok) throw new Error("HTTP "+r.status);
    const data = await r.json();
    lastPapers = data.papers || [];
    render(lastPapers);
  }catch(e){
    res.innerHTML = '<div class="status">Couldn\\'t fetch papers — arXiv may be rate-limiting. Try again in a moment.<br><small>'+esc(e.message)+'</small></div>';
  }
}
async function loadDiff(){
  const res = document.getElementById("results");
  if(selected.size===0){ res.innerHTML = '<div class="status">Select at least one topic first.</div>'; return; }
  res.innerHTML = '<div class="status"><span class="spin"></span>Comparing against your last recorded run…</div>';
  try{
    const r = await fetch("/api/diff?cats=" + [...selected].join(","));
    if(!r.ok) throw new Error("HTTP "+r.status);
    renderDiff(await r.json());
  }catch(e){
    res.innerHTML = '<div class="status">Couldn\\'t load the diff.<br><small>'+esc(e.message)+'</small></div>';
  }
}
function renderDiff(d){
  const res = document.getElementById("results");
  if(d.is_first_run){
    res.innerHTML = '<div class="status">No previous snapshot for these topics yet.<br>'+
      '<small>Run <code>paperpulse run</code> once to record a baseline.</small></div>';
    return;
  }
  const sec = (title, items, fmt) =>
    '<div class="card"><h3>'+esc(title)+' ('+items.length+')</h3>'+
    (items.length ? '<ul class="flags" style="padding-left:1.1rem">'+items.map(fmt).join("")+'</ul>'
                  : '<div class="meta">Nothing new.</div>')+'</div>';
  res.innerHTML =
    '<div class="sub">Changes since '+esc((d.since||"").slice(0,19))+'</div>'+
    sec("New papers", d.new_papers, p =>
      '<li style="color:inherit"><a href="'+esc(p.url)+'" target="_blank" rel="noopener">'+esc(mathify(p.title))+'</a>'+
      (p.badge ? ' <span class="badge '+esc(p.badge)+'">'+esc(p.badge)+'</span>' : '')+'</li>')+
    sec("Fresh evidence on tracked dead/weak factors", d.factor_evidence, f =>
      '<li><b>'+esc(f.name)+'</b> ('+esc(f.result)+'): <a href="'+esc(f.url)+'" target="_blank" rel="noopener">'+
      esc(f.title)+'</a></li>')+
    sec("Contradictions that flipped", d.polarity_flips, x =>
      '<li>'+esc(x.note)+'</li>');
  typesetMath(res);
}
function resultFilterBar(){
  const bar = document.createElement("div"); bar.className = "actions";
  for(const [key, {label}] of Object.entries(RESULT_FILTERS)){
    const btn = document.createElement("button");
    btn.className = "btn" + (resultFilter === key ? " primary" : "");
    btn.textContent = label;
    btn.onclick = () => { resultFilter = key; render(lastPapers); };
    bar.appendChild(btn);
  }
  return bar;
}
function render(papers){
  const res = document.getElementById("results");
  const shown = papers.filter(RESULT_FILTERS[resultFilter].test);
  res.innerHTML = "";
  res.appendChild(resultFilterBar());
  if(shown.length===0){
    const empty = document.createElement("div"); empty.className="status";
    empty.textContent = papers.length===0 ? "No papers matched. Try more topics." : "No papers match this filter.";
    res.appendChild(empty);
    return;
  }
  shown.forEach((p,i) => {
    const t = p.trust || {};
    const badge = t.badge || "clean";
    const flags = (t.flags||[]).map(s => {
      const why = s.evidence ? ' <span class="why">why: “'+esc(s.evidence)+'”</span>' : "";
      const conf = (s.confidence!=null && s.confidence<1)
        ? ' <span class="conf">conf '+Math.round(s.confidence*100)+'%</span>' : "";
      return '<li>'+esc(s.name)+': '+esc(s.note)+why+conf+'</li>';
    }).join("");
    const prio = p.priority!=null
      ? '<span class="prio" title="relevance × trust — is it worth your time?">worth-it '+p.priority.toFixed(2)+'</span>' : "";
    const quotes = (p.quotes||[]).map(q => {
      const chg = q.change_pct==null ? "" :
        ' <span class="'+(q.change_pct>=0?"up":"down")+'">'+(q.change_pct>=0?"+":"")+q.change_pct+'%</span>';
      return '<span class="tk">'+esc(q.ticker)+' '+q.price+' '+esc(q.currency)+chg+'</span>';
    }).join("");
    let alphaHtml = "";
    if(p.alpha){
      const a = p.alpha;
      const row = (label, val) => val && val.length
        ? '<div><span class="akey">'+label+'</span> '+esc(Array.isArray(val)?val.join(", "):val)+'</div>' : "";
      alphaHtml =
        '<div class="alpha"><div class="ahead">Alpha card '+
          '<span class="atag '+esc(a.testability)+'">'+esc(a.testability)+' '+a.score+'/4</span></div>'+
        row("claim", mathify(a.claim)) + row("reported", a.effects) + row("data", a.data_sources) +
        row("universe", a.universe) + row("period", a.period) +
        (a.missing && a.missing.length
          ? '<div class="amiss">not stated '+(a.from_full_text?"in the paper":"in the abstract")+
            ': '+esc(a.missing.join(", "))+'</div>' : "")+
        '</div>';
    }
    const region = (p.regions||[]).length ? '<div class="meta">Region: '+esc(p.regions.join(", "))+'</div>' : "";
    const regionNote = p.region_note ? '<div class="meta">✅ '+esc(p.region_note)+'</div>' : "";
    const card = document.createElement("div"); card.className="card";
    card.innerHTML =
      '<h3>'+(i+1)+'. '+esc(mathify(p.title))+'</h3>'+
      '<div class="bar">'+bar(p.score)+' relevance '+p.score.toFixed(2)+
        ' <span class="badge '+badge+'">'+badge+'</span> '+prio+'</div>'+
      (quotes ? '<div class="market">'+quotes+'</div>' : '')+
      (p.summary ? '<p>'+esc(mathify(p.summary))+'</p>' : '')+
      alphaHtml + region + regionNote +
      (flags ? '<ul class="flags">'+flags+'</ul>' : '')+
      '<div class="meta"><a href="'+esc(p.url)+'" target="_blank" rel="noopener">abstract</a> · <code>'+esc(p.id)+'</code></div>';
    res.appendChild(card);
  });
  typesetMath(res);
}
function typesetMath(el){
  // Abstracts routinely carry raw LaTeX ($...$, \\(...\\), \\[...\\]); render
  // it as actual math instead of dumping the markup as text. KaTeX is loaded
  // deferred, and by the time a fetch resolves it is always ready -- but
  // guard anyway in case a page renders before the CDN script finishes.
  if(typeof renderMathInElement === "function"){
    renderMathInElement(el, {
      delimiters: [
        {left: "$$", right: "$$", display: true},
        {left: "\\[", right: "\\]", display: true},
        {left: "$", right: "$", display: false},
        {left: "\\(", right: "\\)", display: false},
      ],
      throwOnError: false,
    });
  }
}
let PACKS = {};
async function initSetup(){
  const panel = document.getElementById("setup");
  try{
    const r = await fetch("/api/config");
    const cfg = await r.json();
    PACKS = cfg.packs || {};
    panel.innerHTML =
      '<label for="setupPack">Topic pack</label>'+
      '<select id="setupPack"><option value="">-- custom --</option>'+
      Object.keys(PACKS).map(name => '<option value="'+esc(name)+'">'+esc(name)+'</option>').join("")+
      '</select>'+
      '<label for="setupInterests">Interests (drives ranking within your fetched categories)</label>'+
      '<textarea id="setupInterests">'+esc(cfg.interests||"")+'</textarea>'+
      '<div class="actions"><button class="btn primary" id="setupSave">Save</button>'+
      '<span class="meta" id="setupStatus"></span></div>';
    document.getElementById("setupPack").onchange = (e) => {
      const pack = PACKS[e.target.value];
      if(pack) document.getElementById("setupInterests").value = pack.interests;
    };
    document.getElementById("setupSave").onclick = async () => {
      const status = document.getElementById("setupStatus");
      const packName = document.getElementById("setupPack").value;
      const interests = document.getElementById("setupInterests").value;
      const payload = {interests};
      if(packName) payload.preset = packName;
      status.textContent = "Saving…";
      try{
        const resp = await fetch("/api/config", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload),
        });
        const out = await resp.json();
        if(!resp.ok) throw new Error(out.error || ("HTTP "+resp.status));
        status.textContent = "Saved -- press Run to see it reflected.";
        if(out.categories){
          selected = new Set(out.categories.flatMap(c =>
            c.endsWith(".*") ? Object.values(CATALOG).flat().map(([cat])=>cat).filter(cat=>cat.startsWith(c.slice(0,-1)))
                              : [c]));
          renderFilter();
        }
      }catch(e){
        status.textContent = "Couldn't save: "+e.message;
      }
    };
  }catch(e){
    panel.innerHTML = '<div class="status">Couldn\\'t load current config.</div>';
  }
}
document.getElementById("setupToggle").onclick = () => {
  const panel = document.getElementById("setup");
  const show = panel.style.display === "none";
  panel.style.display = show ? "block" : "none";
  if(show && !panel.innerHTML) initSetup();
};
renderFilter();
load();
</script>
</body></html>"""


def _shell_html(config: Config) -> str:
    return (
        _SHELL.replace("__CATALOG__", json.dumps(TOPIC_CATALOG))
        .replace("__SELECTED__", json.dumps(_initial_selection(config)))
        .replace("__SUBTITLE__", config.source)
    )


def _digest_json(config: Config) -> dict:
    result = _cached_digest(config)
    return digest_to_dict(result, include_market_quotes=True)


def _diff_json(config: Config) -> dict:
    diff = _cached_diff(config)
    return {
        "since": diff.since,
        "is_first_run": diff.is_first_run,
        "new_papers": [
            {
                "id": item.paper.id,
                "title": item.paper.title,
                "url": item.paper.url,
                "score": round(item.score, 4),
                "badge": item.trust.badge if item.trust else None,
            }
            for item in diff.new_papers
        ],
        "factor_evidence": [
            {
                "name": entry.name,
                "result": entry.result,
                "paper_id": item.paper.id,
                "title": item.paper.title,
                "url": item.paper.url,
            }
            for entry, item in diff.factor_evidence
        ],
        "polarity_flips": [
            {"a": a.id, "b": b.id, "a_title": a.title, "b_title": b.title, "note": note}
            for a, b, note in diff.polarity_flips
        ],
    }


def make_handler(config: Config, config_path=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):  # keep the console quiet
            pass

        def _send(self, code: int, body: str, content_type: str) -> None:
            payload = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, obj, code: int = 200) -> None:
            self._send(code, json.dumps(obj), "application/json")

        def _authorized(self) -> bool:
            # Opt-in protection: when PAPERPULSE_API_TOKEN is set (e.g. for a
            # network-exposed instance), every request must carry it as a
            # Bearer token. Unset = open, the localhost default. Shared by
            # do_GET and do_POST so the check can't be added to one and
            # silently skipped on the other.
            token = os.environ.get("PAPERPULSE_API_TOKEN")
            if not token:
                return True
            supplied = self.headers.get("Authorization", "")
            return hmac.compare_digest(supplied, f"Bearer {token}")

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            # The static shell has no server-rendered secrets, so it's exempt
            # -- but every /api/* route it calls client-side is gated, so a
            # configured token actually locks down digest/notes/config reads,
            # not just writes.
            if path != "/" and not self._authorized():
                self._json({"error": "unauthorized"}, 401)
                return
            if path == "/":
                self._send(200, _shell_html(config), "text/html; charset=utf-8")
            elif path == "/api/sources":
                self._json({"sources": available()})
            elif path == "/api/digest":
                cats = _parse_cats(urlparse(self.path).query)
                cfg = replace(config, categories=cats) if cats else config
                self._json(_digest_json(cfg))
            elif path == "/api/diff":
                cats = _parse_cats(urlparse(self.path).query)
                cfg = replace(config, categories=cats) if cats else config
                self._json(_diff_json(cfg))
            elif path == "/api/config":
                # The browser-side equivalent of `paperpulse init`: what the
                # topic-filter chips can't do, since they only choose which
                # arXiv categories to fetch -- interests text drives ranking
                # within them, and until now only the CLI wizard could set it.
                self._json({
                    "categories": config.categories,
                    "interests": config.interests,
                    "packs": {name: {"categories": cats, "interests": interests}
                              for name, (cats, interests) in TOPIC_PACKS.items()},
                })
            elif path == "/api/community/leaderboard":
                if not config.community_db:
                    self._json({"error": "community_db not configured"}, 400)
                    return
                from .community import CommunityDB

                db = CommunityDB(config.community_db)
                try:
                    self._json({"leaderboard": db.flag_leaderboard()})
                finally:
                    db.close()
            elif path == "/api/score-accuracy":
                if not config.community_db:
                    self._json({"error": "community_db not configured"}, 400)
                    return
                user = parse_qs(urlparse(self.path).query).get("user", ["default"])[0]
                self._json(score_accuracy_report(config, user=user))
            elif path == "/api/notes":
                if not config.community_db:
                    self._json({"error": "community_db not configured"}, 400)
                    return
                paper_id = parse_qs(urlparse(self.path).query).get("paper_id", [""])[0]
                if not paper_id:
                    self._json({"error": "paper_id required"}, 400)
                    return
                from .community import CommunityDB

                db = CommunityDB(config.community_db)
                try:
                    self._json({"notes": db.get_notes(paper_id)})
                finally:
                    db.close()
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self) -> None:
            nonlocal config  # /api/config may reassign it; declared up front
            # for mypy's flow analysis of the later branches, not just this one.
            if not self._authorized():
                self._json({"error": "unauthorized"}, 401)
                return
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                self._json({"error": "invalid JSON"}, 400)
                return
            if path == "/api/config":
                preset = body.get("preset") or None
                if preset is not None and preset not in TOPIC_PACKS:
                    self._json({"error": f"unknown preset {preset!r}"}, 400)
                    return
                categories = body.get("categories") or None
                interests = body.get("interests") or None
                if preset is None and not categories and not interests:
                    self._json({"error": "nothing to update"}, 400)
                    return
                if preset is not None:
                    updated = build_init_config(preset, interests=interests, categories=categories)
                    # Preserve every other setting (trust, alpha_cards, source,
                    # etc.) instead of resetting to library defaults.
                    config = replace(
                        config, categories=updated.categories, interests=updated.interests
                    )
                else:
                    config = replace(
                        config,
                        categories=categories or config.categories,
                        interests=interests or config.interests,
                    )
                config.save(config_path)
                # dict.clear() is safe without _key_locks_guard here (it only
                # protects handing out per-key locks); worst case under a race
                # is one redundant re-fetch, not corruption.
                _digest_cache.clear()
                self._json({"ok": True, "categories": config.categories, "interests": config.interests})
            elif path == "/api/feedback":
                profile = apply_feedback(
                    config,
                    list(body.get("like", [])),
                    list(body.get("dislike", [])),
                    user=body.get("user", "default"),
                )
                self._json({"ok": True, "n_feedback": profile.n_feedback})
            elif path == "/api/notes":
                if not config.community_db:
                    self._json({"error": "community_db not configured"}, 400)
                    return
                paper_id = body.get("paper_id", "")
                note = body.get("note", "")
                if not paper_id or not note:
                    self._json({"error": "paper_id and note required"}, 400)
                    return
                from .community import CommunityDB

                db = CommunityDB(config.community_db)
                try:
                    db.add_note(paper_id, note, user=body.get("user", "default"))
                    self._json({"ok": True})
                finally:
                    db.close()
            else:
                self._json({"error": "not found"}, 404)

    return Handler


def serve(*, host: str = "127.0.0.1", port: int = 8000, config_path=None) -> None:
    config = Config.load(config_path)
    server = ThreadingHTTPServer((host, port), make_handler(config, config_path))
    print(f"PaperPulse serving on http://{host}:{port}  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


__all__ = ["serve", "make_handler"]

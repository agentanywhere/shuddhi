"""A local viewer for the builds on this machine.

`factory.py ui` serves a dashboard over the output directories Shuddhi has
already written: build history, the datasets that went in, live progress for
a run happening right now, every warning and error, and the receipt to
download.

Scope, deliberately: this reads YOUR filesystem and serves to YOUR browser.
No accounts, no database, no multi-user state, no telemetry, and it binds to
localhost. It is `git log` for corpora — the organisation-wide ledger with
sign-off, retention and access control is a different product.

Zero dependencies: http.server from the standard library, one HTML document
with inline CSS and JS, no CDN. It works air-gapped, which for a chunk of
the intended audience is the only way it works at all.
"""

from __future__ import annotations

import json
import os
import posixpath
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

MANIFEST = os.path.join("run", "MANIFEST.json")
BUILD_MANIFEST = os.path.join("build", "BUILD-MANIFEST.json")


def _read_json(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _collect_events(run_path: str, limit: int = 400) -> list[dict]:
    """Merge the event logs a run writes: the top level plus each phase dir."""
    merged: list[dict] = []
    for rel in ("", "run", "build"):
        merged += _tail_events(os.path.join(run_path, rel, "events.jsonl"), limit)
    merged.sort(key=lambda e: e.get("ts", 0))
    return merged[-limit:]


def _tail_events(path: str, limit: int = 400) -> list[dict]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
    except OSError:
        return []
    out = []
    for line in lines:
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def discover_runs(root: str) -> list[dict]:
    """Find every Shuddhi output directory under root (root itself counts)."""
    candidates = []
    root = os.path.abspath(root)
    for base, dirs, _files in os.walk(root):
        dirs[:] = [d for d in dirs
                   if d not in {"sigs", "lms", ".git", "__pycache__", "node_modules"}]
        if os.path.exists(os.path.join(base, MANIFEST)) or \
           os.path.exists(os.path.join(base, BUILD_MANIFEST)) or \
           os.path.exists(os.path.join(base, "events.jsonl")):
            candidates.append(base)
        if base.count(os.sep) - root.count(os.sep) > 3:
            dirs[:] = []
    # Drop any candidate nested inside another: <out>/run and <out>/build each
    # carry an events.jsonl of their own, which otherwise lists them as
    # separate builds in the sidebar.
    tops = []
    for path in sorted(set(candidates)):
        if not any(path != o and path.startswith(o + os.sep) for o in candidates):
            tops.append(path)
    runs = []
    for path in tops:
        runs.append(summarise(path, root))
    runs.sort(key=lambda r: r["mtime"], reverse=True)
    return runs


def summarise(path: str, root: str) -> dict:
    corpus = _read_json(os.path.join(path, MANIFEST))
    build = _read_json(os.path.join(path, BUILD_MANIFEST))
    events_path = os.path.join(path, "events.jsonl")
    events = _collect_events(path, 40)
    mtimes = [os.path.getmtime(p) for p in
              (os.path.join(path, MANIFEST), os.path.join(path, BUILD_MANIFEST), events_path)
              if os.path.exists(p)]

    running = False
    if events:
        last = events[-1]
        running = (time.time() - last.get("ts", 0) < 30) and last.get("kind") not in ("finish",)

    total = corpus["full_pass"]["total_docs"] if corpus else None
    kept = build["kept_docs"] if build else None
    return {
        "id": os.path.relpath(path, root) or ".",
        "path": path,
        "corpus_id": (corpus or {}).get("corpus_id") or (build or {}).get("corpus_id") or os.path.basename(path),
        "generated": (build or corpus or {}).get("generated_utc"),
        "mtime": max(mtimes) if mtimes else 0,
        "total_docs": total,
        "kept_docs": kept,
        "running": running,
        "has_build": build is not None,
        "warnings": len((build or {}).get("warnings", [])),
    }


def load_run(path: str) -> dict:
    corpus = _read_json(os.path.join(path, MANIFEST))
    build = _read_json(os.path.join(path, BUILD_MANIFEST))
    events = _collect_events(path)
    downloads = []
    for rel, label in (("report.html", "Receipt (HTML)"),
                       ("REPORT.md", "Article 53 draft"),
                       (MANIFEST, "Corpus manifest (JSON)"),
                       (BUILD_MANIFEST, "Build manifest (JSON)")):
        full = os.path.join(path, rel)
        if os.path.exists(full):
            downloads.append({"rel": rel.replace(os.sep, "/"), "label": label,
                              "bytes": os.path.getsize(full)})
    return {"corpus": corpus, "build": build, "events": events, "downloads": downloads}


class Handler(BaseHTTPRequestHandler):
    root = "."

    def log_message(self, *args):  # keep the terminal clean
        pass

    def _send(self, body: bytes, ctype: str, download: str | None = None):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{download}"')
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj):
        self._send(json.dumps(obj).encode(), "application/json; charset=utf-8")

    def do_GET(self):
        parsed = urlparse(self.path)
        route = unquote(parsed.path)

        if route == "/":
            return self._send(PAGE.encode(), "text/html; charset=utf-8")

        if route == "/api/runs":
            return self._json({"root": self.root, "runs": discover_runs(self.root)})

        if route.startswith("/api/run/"):
            rel = route[len("/api/run/"):]
            path = self._safe(rel)
            if not path:
                return self.send_error(404)
            return self._json(load_run(path))

        if route.startswith("/download/"):
            rel = route[len("/download/"):]
            run_rel, _, file_rel = rel.partition("::")
            base = self._safe(run_rel)
            if not base:
                return self.send_error(404)
            target = os.path.normpath(os.path.join(base, file_rel))
            if not target.startswith(base) or not os.path.exists(target):
                return self.send_error(404)
            ctype = ("text/html; charset=utf-8" if target.endswith(".html")
                     else "text/markdown; charset=utf-8" if target.endswith(".md")
                     else "application/json")
            with open(target, "rb") as f:
                body = f.read()
            inline = target.endswith(".html")
            return self._send(body, ctype, None if inline else os.path.basename(target))

        self.send_error(404)

    def _safe(self, rel: str) -> str | None:
        """Resolve a run id under root, refusing anything that escapes it."""
        root = os.path.abspath(self.root)
        target = os.path.normpath(os.path.join(root, rel.replace("/", os.sep)))
        if target != root and not target.startswith(root + os.sep):
            return None
        return target if os.path.isdir(target) else None


PAGE = r"""<!doctype html><html lang=en><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Shuddhi — builds on this machine</title>
<style>
:root{--bg:#f7f8fa;--panel:#fff;--fg:#0f172a;--muted:#64748b;--line:#e2e8f0;--accent:#2563eb;
 --ok:#047857;--warn:#b45309;--warnbg:#fffbeb;--err:#b91c1c;--errbg:#fef2f2;--chip:#eff6ff}
@media(prefers-color-scheme:dark){:root{--bg:#0a0e14;--panel:#111827;--fg:#e5e7eb;--muted:#94a3b8;
 --line:#1f2937;--accent:#60a5fa;--warnbg:#2a2113;--errbg:#2a1414;--chip:#16233a}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
header{display:flex;align-items:baseline;gap:.8rem;padding:1.1rem 1.5rem;border-bottom:1px solid var(--line);background:var(--panel);position:sticky;top:0;z-index:5}
header b{font-size:1.05rem;font-weight:650} header span{color:var(--muted);font-size:.85rem}
.layout{display:grid;grid-template-columns:19rem 1fr;min-height:calc(100vh - 60px)}
aside{border-right:1px solid var(--line);background:var(--panel);padding:1rem;overflow:auto}
main{padding:1.6rem 1.9rem;max-width:64rem}
.runitem{display:block;width:100%;text-align:left;border:1px solid var(--line);background:transparent;color:inherit;
 border-radius:.6rem;padding:.7rem .8rem;margin-bottom:.5rem;cursor:pointer;font:inherit}
.runitem:hover{border-color:var(--accent)} .runitem.sel{border-color:var(--accent);background:var(--chip)}
.runitem .t{font-weight:600} .runitem .m{color:var(--muted);font-size:.8rem;margin-top:.15rem}
.live{display:inline-block;width:.5rem;height:.5rem;border-radius:50%;background:var(--ok);margin-right:.35rem;animation:p 1.4s infinite}
@keyframes p{50%{opacity:.25}}
h1{font-size:1.35rem;margin:0 0 .2rem} .sub{color:var(--muted);margin:0 0 1.4rem;font-size:.9rem}
h2{font-size:.78rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:2rem 0 .7rem}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(9.5rem,1fr));gap:.7rem}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:.7rem;padding:.85rem 1rem}
.tile .v{font-size:1.5rem;font-weight:650;font-variant-numeric:tabular-nums} .tile .k{color:var(--muted);font-size:.78rem}
.receipt{display:flex;gap:.7rem;align-items:center;background:var(--panel);border:1px solid var(--line);
 border-radius:.6rem;padding:.6rem .8rem;margin-bottom:.45rem}
.receipt .k{color:var(--muted);font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;min-width:10.5rem}
.receipt code{font:12.5px ui-monospace,SFMono-Regular,Menlo,monospace;word-break:break-all;flex:1}
.copy{border:1px solid var(--line);background:transparent;color:var(--muted);border-radius:.4rem;cursor:pointer;padding:.2rem .5rem;font-size:.75rem}
.copy:hover{color:var(--accent);border-color:var(--accent)}
table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:.6rem;overflow:hidden;font-size:.88rem}
th,td{text-align:left;padding:.5rem .75rem;border-bottom:1px solid var(--line)} tr:last-child td{border-bottom:0}
th{font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
td.n{text-align:right;font-variant-numeric:tabular-nums}
.bars{background:var(--panel);border:1px solid var(--line);border-radius:.6rem;padding:.9rem 1rem}
.bar{display:grid;grid-template-columns:9rem 1fr 4.5rem;gap:.7rem;align-items:center;margin-bottom:.45rem;font-size:.85rem}
.bar .track{display:block;background:var(--line);border-radius:99px;height:.55rem;overflow:hidden}
.bar .fill{display:block;height:100%;min-width:3px;background:var(--accent);border-radius:99px}
.msg{border-left:3px solid var(--warn);background:var(--warnbg);padding:.6rem .8rem;border-radius:.3rem;margin-bottom:.5rem;font-size:.88rem}
.msg.err{border-color:var(--err);background:var(--errbg)}
.dl{display:inline-flex;align-items:center;gap:.4rem;border:1px solid var(--line);border-radius:.5rem;
 padding:.45rem .75rem;margin:0 .5rem .5rem 0;text-decoration:none;color:inherit;font-size:.86rem;background:var(--panel)}
.dl:hover{border-color:var(--accent);color:var(--accent)}
.prog{background:var(--panel);border:1px solid var(--line);border-radius:.6rem;padding:.9rem 1rem;margin-bottom:1rem}
.prog .track{background:var(--line);height:.6rem;border-radius:99px;overflow:hidden;margin:.5rem 0 .35rem}
.prog .fill{height:100%;background:var(--accent);transition:width .4s}
.empty{color:var(--muted);padding:2.5rem 0}
.ok{color:var(--ok)}
</style>
<header><b>Shuddhi</b><span id=root></span></header>
<div class=layout>
 <aside><div id=runs></div></aside>
 <main id=main><div class=empty>Loading…</div></main>
</div>
<script>
const $=s=>document.querySelector(s);
let sel=null, runsCache=[];
const fmt=n=>n==null?"—":n.toLocaleString();
const pct=(a,b)=>b?((a/b)*100).toFixed(2)+"%":"—";
const bytes=n=>{if(n==null)return"—";const u=["B","KB","MB","GB","TB"];let i=0;
 while(Math.abs(n)>=1000&&i<u.length-1){n/=1000;i++;}
 return (i?n.toFixed(n<10?2:1):n.toFixed(0))+" "+u[i];};

async function loadRuns(){
  const d=await (await fetch("/api/runs")).json();
  $("#root").textContent=d.root;
  runsCache=d.runs;
  $("#runs").innerHTML = d.runs.length? d.runs.map(r=>`
    <button class="runitem ${r.id===sel?'sel':''}" data-id="${r.id}">
      <div class=t>${r.running?'<i class=live></i>':''}${r.corpus_id}</div>
      <div class=m>${r.kept_docs!=null?fmt(r.kept_docs)+" kept of "+fmt(r.total_docs)
        :(r.total_docs!=null?fmt(r.total_docs)+" documents measured":(r.running?"running":"no manifest yet"))}
      ${r.warnings?' · <span style="color:var(--warn)">'+r.warnings+' warning'+(r.warnings>1?'s':'')+'</span>':''}</div>
      <div class=m>${r.id}</div>
    </button>`).join("") : '<div class=empty>No builds found here yet.</div>';
  document.querySelectorAll(".runitem").forEach(b=>b.onclick=()=>{sel=b.dataset.id;loadRuns();loadRun(sel);});
  if(!sel && d.runs.length){sel=d.runs[0].id;loadRun(sel);loadRuns();}
}

async function loadRun(id){
  const d=await (await fetch("/api/run/"+encodeURIComponent(id))).json();
  const c=d.corpus, b=d.build;
  const meta=runsCache.find(r=>r.id===id)||{};
  let h="";

  h+=`<h1>${(c&&c.corpus_id)||(b&&b.corpus_id)||id}</h1>
      <p class=sub>${id} · ${(b&&b.generated_utc)||(c&&c.generated_utc)||""}</p>`;

  const ev=d.events||[];
  if(meta.running){
    const last=[...ev].reverse().find(e=>e.kind==="progress");
    const ph=[...ev].reverse().find(e=>e.kind==="phase");
    const frac=last&&last.total?Math.min(1,last.done/last.total):0;
    h+=`<div class=prog><b>${ph?ph.title:"working"}</b>
        <div class=track><div class=fill style="width:${(frac*100).toFixed(1)}%"></div></div>
        <div class=m style="color:var(--muted);font-size:.85rem">
        ${last?fmt(last.done)+(last.total?" of ~"+fmt(last.total):"")+" documents":"starting…"}</div></div>`;
  }

  const rec=[];
  if(c) rec.push(["corpus build hash",c.corpus_build_hash]);
  if(b) rec.push(["filter config sha",b.filter_config_sha256],["filtered build hash",b.filtered_build_hash]);
  if(rec.length){h+="<h2>Receipts</h2>"+rec.map(([k,v])=>`<div class=receipt><span class=k>${k}</span>
     <code>${v}</code><button class=copy data-c="${v}">copy</button></div>`).join("");}

  if(c){
    const f=c.full_pass;
    h+=`<h2>Corpus — measured over every document</h2><div class=tiles>
      <div class=tile><div class=v>${fmt(f.total_docs)}</div><div class=k>documents</div></div>
      <div class=tile><div class=v>${fmt(f.unique_docs)}</div><div class=k>unique</div></div>
      <div class=tile><div class=v>${(f.global_exact_dup_rate*100).toFixed(2)}%</div><div class=k>exact duplicates</div></div>
      <div class=tile><div class=v>${bytes(f.total_doc_bytes)}</div><div class=k>text</div></div></div>`;
  }

  if(b){
    const total=b.kept_docs+Object.values(b.dropped_by_reason).reduce((a,x)=>a+x,0);
    h+=`<h2>Filtered build</h2><div class=tiles>
      <div class=tile><div class=v>${fmt(b.kept_docs)}</div><div class=k>kept · ${pct(b.kept_docs,total)}</div></div>
      <div class=tile><div class=v>${fmt(total-b.kept_docs)}</div><div class=k>dropped</div></div>
      <div class=tile><div class=v>${fmt(b.pii_redactions||0)}</div><div class=k>PII spans redacted</div></div></div>`;
    const drops=Object.entries(b.dropped_by_reason).filter(([,v])=>v>0);
    const max=Math.max(1,...drops.map(([,v])=>v));
    if(drops.length) h+=`<h2>Dropped by reason</h2><div class=bars>`+drops.map(([k,v])=>
      `<div class=bar><span>${k.replace(/_/g," ")}</span>
       <span class=track><span class=fill style="width:${(v/max*100).toFixed(1)}%"></span></span>
       <span class=n style="text-align:right">${fmt(v)}</span></div>`).join("")+`</div>`;
    if(b.warnings&&b.warnings.length) h+="<h2>Warnings</h2>"+b.warnings.map(w=>`<div class=msg>${w}</div>`).join("");
  }

  const errs=ev.filter(e=>e.kind==="error"), warns=ev.filter(e=>e.kind==="warning");
  if(errs.length||warns.length){
    h+="<h2>From this run</h2>"+errs.map(e=>`<div class="msg err">${e.message}</div>`).join("")
      +warns.map(e=>`<div class=msg>${e.message}</div>`).join("");
  }

  if(c&&c.shards&&c.shards.length){
    h+=`<h2>Datasets</h2><table><thead><tr><th>shard</th><th>language</th><th>source</th><th>licence</th>
        <th style="text-align:right">documents</th><th style="text-align:right">dup rate</th></tr></thead><tbody>`+
      c.shards.map(s=>`<tr><td>${s.shard_id}</td><td>${s.language}</td><td>${s.source||""}</td>
        <td>${s.license||""}</td><td class=n>${fmt(s.docs)}</td>
        <td class=n>${(s.exact_dup_rate*100).toFixed(2)}%</td></tr>`).join("")+`</tbody></table>`;
    const ref=c.provenance_gate&&c.provenance_gate.refused||[];
    h+=ref.length? "<h2>Refused at the gate</h2>"+ref.map(r=>`<div class=msg><b>${r.shard_id}</b> — ${r.reason}</div>`).join("")
       : '<p class=ok style="margin-top:.8rem">✓ No shard was refused.</p>';
  }

  if(d.downloads.length){
    h+="<h2>Download</h2>"+d.downloads.map(f=>
      `<a class=dl href="/download/${encodeURIComponent(id)}::${f.rel}" ${f.rel.endsWith('.html')?'target=_blank':''}>
        ${f.label} <span style="color:var(--muted)">${(f.bytes/1024).toFixed(0)} KB</span></a>`).join("");
  }

  $("#main").innerHTML=h;
  document.querySelectorAll(".copy").forEach(b=>b.onclick=async()=>{
    await navigator.clipboard.writeText(b.dataset.c); const t=b.textContent; b.textContent="copied";
    setTimeout(()=>b.textContent=t,1200);});
}

loadRuns();
setInterval(()=>{loadRuns(); if(sel) loadRun(sel);}, 4000);
</script></html>"""


def serve(directory: str, port: int = 8765, open_browser: bool = True) -> int:
    Handler.root = os.path.abspath(directory)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    n = len(discover_runs(Handler.root))
    print(f"Shuddhi viewer → {url}")
    print(f"  watching {Handler.root} ({n} build{'s' if n != 1 else ''} found)")
    print("  localhost only · no accounts · nothing leaves this machine")
    print("  Ctrl-C to stop")
    if open_browser:
        try:
            import webbrowser

            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
    return 0

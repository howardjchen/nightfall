#!/usr/bin/env python3
"""Small local issue board with cumulative time in Ongoing. Python 3, no packages."""

import argparse
import json
import os
import sqlite3
import time
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

STATUSES = ("Pending", "Ongoing", "Blocked", "Done")
DB = Path(os.environ.get("ISSUE_TRACKER_DB", "issue_tracker.sqlite3"))

PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Issue Time Tracker</title><style>
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Noto Sans TC",sans-serif;color:#e8edf8;background:#0c1423}
*{box-sizing:border-box}body{margin:0}main{max-width:1440px;margin:auto;padding:28px 26px 60px}
header{display:flex;align-items:end;justify-content:space-between;gap:20px;margin-bottom:26px}
h1{font-size:clamp(1.6rem,3vw,2.3rem);letter-spacing:-.04em;margin:0}header p{margin:7px 0 0;color:#9baac4}
.new{display:flex;gap:8px;margin-bottom:22px}.new input{flex:1;min-width:0;background:#172339;border:1px solid #32425e;border-radius:10px;padding:13px 15px;color:#fff;font:inherit}
button{font:inherit;cursor:pointer;border:0;border-radius:10px;padding:12px 19px;background:#5a8eff;color:#091529;font-weight:700}button:hover{background:#82a9ff}button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid #9cbcff;outline-offset:2px}
.board{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.lane{background:#121e31;border:1px solid #263754;border-radius:15px;min-height:300px;padding:13px}.lane.over{outline:2px dashed #79a5ff;outline-offset:-5px}
.lane h2{font-size:1rem;font-weight:650;margin:2px 4px 17px;display:flex;justify-content:space-between}.lane h2 span{color:#9baac4;font-weight:500}
.card{background:#1c2b43;border:1px solid #365071;border-radius:11px;padding:15px;margin-bottom:10px;cursor:grab;box-shadow:0 5px 14px #07101e44}.card:active{cursor:grabbing}.card h3{font-size:1rem;margin:0 0 16px;line-height:1.35;overflow-wrap:anywhere}.card .bottom{display:flex;align-items:end;justify-content:space-between;gap:8px;flex-wrap:wrap}.duration{color:#b9c8e2;font-variant-numeric:tabular-nums;font-size:.88rem}.duration strong{display:block;color:#f0f5ff;font-size:1.13rem}.card select{background:#243a59;color:#f3f6ff;border:1px solid #4a6488;border-radius:8px;padding:7px;max-width:115px;font:inherit;font-size:.84rem}.empty{color:#7085a4;margin:12px 4px;font-size:.91rem}.hint{color:#8599b7;font-size:.86rem}.error{color:#ffb4b4;min-height:1.4em;margin:10px 0}
@media(max-width:850px){.board{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:530px){main{padding:22px 14px 40px}.board{grid-template-columns:1fr}.lane{min-height:120px}.new button{padding:10px 14px}}
</style></head><body><main>
<header><div><h1>Issue Time Tracker</h1><p>Track total time spent in Ongoing</p></div><div class="hint">Drag cards or use their menu to change status</div></header>
<form class="new" id="new"><input id="title" placeholder="New issue, e.g. PCIe error injection" maxlength="200" required aria-label="Issue title"><button>Add task</button></form>
<div id="error" class="error" role="alert"></div><div class="board" id="board"></div>
</main><script>
const states=['Pending','Ongoing','Blocked','Done'];let tasks=[];
const board=document.querySelector('#board'),err=document.querySelector('#error');
function fmt(ms){let s=Math.floor(Math.max(0,ms)/1000),h=Math.floor(s/3600),m=Math.floor(s%3600/60);return `${h}h ${String(m).padStart(2,'0')}m ${String(s%60).padStart(2,'0')}s`}
function duration(t){return t.accumulated_ms+(t.ongoing_started_ms===null?0:Math.max(0,Date.now()-t.ongoing_started_ms))}
function showError(e){err.textContent=e.message||String(e)}
async function api(url,opts){let res=await fetch(url,opts);let data=await res.json();if(!res.ok)throw Error(data.error||'Request failed');return data}
function render(){board.replaceChildren();for(const state of states){const lane=document.createElement('section');lane.className='lane';lane.dataset.status=state;const subset=tasks.filter(t=>t.status===state);const h=document.createElement('h2');h.textContent=state+' ';const count=document.createElement('span');count.textContent=subset.length;h.append(count);lane.append(h);
lane.ondragover=e=>{e.preventDefault();lane.classList.add('over')};lane.ondragleave=e=>{if(!lane.contains(e.relatedTarget))lane.classList.remove('over')};lane.ondrop=e=>{e.preventDefault();lane.classList.remove('over');change(Number(e.dataTransfer.getData('text/plain')),state)};
for(const t of subset){const card=document.createElement('article');card.className='card';card.draggable=true;card.ondragstart=e=>e.dataTransfer.setData('text/plain',String(t.id));const name=document.createElement('h3');name.textContent=t.title;const bottom=document.createElement('div');bottom.className='bottom';const d=document.createElement('div');d.className='duration';d.textContent='Total Ongoing time';const strong=document.createElement('strong');strong.dataset.id=t.id;strong.textContent=fmt(duration(t));d.append(strong);const select=document.createElement('select');select.setAttribute('aria-label',`${t.title} status`);for(const x of states){const op=document.createElement('option');op.value=x;op.textContent=x;select.append(op)}select.value=state;select.onchange=()=>change(t.id,select.value);select.onpointerdown=e=>e.stopPropagation();bottom.append(d,select);card.append(name,bottom);lane.append(card)}if(!subset.length){const empty=document.createElement('p');empty.className='empty';empty.textContent='No tasks';lane.append(empty)}board.append(lane)}}
async function refresh(){try{tasks=await api('/api/tasks');render();err.textContent=''}catch(e){showError(e)}}
async function change(id,status){const t=tasks.find(x=>x.id===id);if(!t||t.status===status)return;try{await api(`/api/tasks/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status})});await refresh()}catch(e){showError(e);render()}}
document.querySelector('#new').onsubmit=async e=>{e.preventDefault();const input=document.querySelector('#title');const title=input.value.trim();if(!title)return;try{await api('/api/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title})});input.value='';await refresh()}catch(e){showError(e)}};
setInterval(()=>{for(const el of board.querySelectorAll('strong[data-id]')){const t=tasks.find(x=>x.id===Number(el.dataset.id));if(t)el.textContent=fmt(duration(t))}},1000);refresh();
</script></body></html>'''


def connection():
    db = sqlite3.connect(DB, timeout=10)
    db.row_factory = sqlite3.Row
    return db


def initialize():
    with closing(connection()) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY, title TEXT NOT NULL, status TEXT NOT NULL,
            accumulated_ms INTEGER NOT NULL DEFAULT 0,
            ongoing_started_ms INTEGER, created_ms INTEGER NOT NULL)""")
        db.commit()


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        size = int(self.headers.get("Content-Length", 0))
        if size < 1 or size > 4096:
            raise ValueError("Invalid request size")
        data = json.loads(self.rfile.read(size))
        if not isinstance(data, dict):
            raise ValueError("Expected an object")
        return data

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/tasks":
            with closing(connection()) as db:
                rows = db.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
                self.reply(200, [dict(row) for row in rows])
        else:
            self.reply(404, {"error": "Not found"})

    def do_POST(self):
        if urlparse(self.path).path != "/api/tasks":
            return self.reply(404, {"error": "Not found"})
        try:
            title = self.read_json().get("title", "")
            if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
                raise ValueError("Title must be 1–200 characters")
            with closing(connection()) as db:
                cur = db.execute("INSERT INTO tasks (title,status,created_ms) VALUES (?,?,?)",
                                 (title.strip(), "Pending", int(time.time() * 1000)))
                db.commit()
                self.reply(201, {"id": cur.lastrowid})
        except (ValueError, json.JSONDecodeError) as exc:
            self.reply(400, {"error": str(exc)})

    def do_PATCH(self):
        parts = urlparse(self.path).path.split("/")
        if len(parts) != 4 or parts[1:3] != ["api", "tasks"] or not parts[3].isdigit():
            return self.reply(404, {"error": "Not found"})
        try:
            status = self.read_json().get("status")
            if status not in STATUSES:
                raise ValueError("Unknown status")
            with closing(connection()) as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT * FROM tasks WHERE id=?", (int(parts[3]),)).fetchone()
                if row is None:
                    db.rollback()
                    return self.reply(404, {"error": "Task not found"})
                if row["status"] != status:
                    now = int(time.time() * 1000)
                    total = row["accumulated_ms"]
                    if row["status"] == "Ongoing" and row["ongoing_started_ms"] is not None:
                        total += max(0, now - row["ongoing_started_ms"])
                    started = now if status == "Ongoing" else None
                    db.execute("UPDATE tasks SET status=?, accumulated_ms=?, ongoing_started_ms=? WHERE id=?",
                               (status, total, started, row["id"]))
                db.commit()
                self.reply(200, {"ok": True})
        except (ValueError, json.JSONDecodeError) as exc:
            self.reply(400, {"error": str(exc)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    initialize()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Open http://127.0.0.1:{args.port}  (database: {DB.resolve()})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")
    finally:
        server.server_close()

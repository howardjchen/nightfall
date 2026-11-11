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
PRIORITIES = ("Low", "Medium", "High")
DB = Path(os.environ.get("ISSUE_TRACKER_DB", "issue_tracker.sqlite3"))

PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Issue Time Tracker</title><style>
:root{color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif;color:#ededeb;background:#191919}
*{box-sizing:border-box}body{margin:0}main{max-width:1440px;margin:auto;padding:48px 36px 64px}
header{display:flex;align-items:end;justify-content:space-between;gap:20px;margin-bottom:28px}
h1{font-size:clamp(1.7rem,3vw,2.4rem);letter-spacing:-.04em;margin:0}header p{margin:8px 0 0;color:#aaa9a5}
button,input,textarea,select{font:inherit}button{cursor:pointer;border:1px solid #454545;border-radius:5px;padding:9px 14px;background:#202020;color:#ededeb;font-weight:500}button:hover{background:#333333}button:disabled{opacity:.5;cursor:wait}
button:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible{outline:2px solid #70b5ff;outline-offset:2px}
.new{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:20px}.new input,.new textarea,.new select{border:1px solid #454545;border-radius:5px;padding:9px 10px;background:#252525;color:inherit}.new input,.new textarea{flex:1;min-width:180px}.new textarea{resize:vertical}
.views{display:flex;gap:18px;border-bottom:1px solid #373737;margin-bottom:22px}.views button{border:0;border-bottom:2px solid transparent;border-radius:0;background:transparent;padding:10px 2px;color:#aaa9a5}.views button[aria-pressed="true"]{border-bottom-color:#ededeb;color:#ededeb;font-weight:600}.views button:hover{background:#202020}
.board{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}.lane{background:#202020;border-radius:6px;min-height:300px;padding:12px}.lane.over{outline:2px dashed #70b5ff;outline-offset:-3px}
.lane h2{font-size:.88rem;font-weight:500;margin:2px 2px 16px;display:flex;align-items:center;gap:9px}.lane h2 .count{color:#aaa9a5;font-weight:400}
.card{background:#252525;border:1px solid #373737;border-radius:5px;padding:13px;margin-bottom:9px;cursor:grab;box-shadow:0 1px 2px #00000033}.card:active{cursor:grabbing}.card h3{font-size:.95rem;font-weight:600;margin:0 0 12px;line-height:1.4;overflow-wrap:anywhere}.card .bottom{display:flex;align-items:end;justify-content:space-between;gap:8px;flex-wrap:wrap}.duration{color:#aaa9a5;font-variant-numeric:tabular-nums;font-size:.78rem}.duration strong{display:block;color:#ededeb;font-size:.95rem;font-weight:500}.card .details{color:#aaa9a5;white-space:pre-wrap;overflow-wrap:anywhere;font-size:.82rem;margin:0 0 12px}.empty{color:#aaa9a5;margin:12px 4px;font-size:.9rem}.hint{color:#aaa9a5;font-size:.85rem}.error{color:#ffaaa3;min-height:1.4em;margin:10px 0}.error:empty{display:none}
.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;text-align:left;font-size:.9rem}caption{text-align:left;font-size:1.1rem;font-weight:600;margin-bottom:14px}th,td{padding:7px 10px;border:1px solid #373737;vertical-align:top}th{background:#242424;color:#aaa9a5;font-weight:400;padding:10px}tbody tr:hover{background:#242424}td input,td textarea,td select{background:transparent;color:inherit;border:1px solid transparent;border-radius:4px;padding:5px;font:inherit}td input,td textarea{width:100%;min-width:200px}td input{font-weight:500}td textarea{min-width:250px;resize:vertical}td input:hover,td textarea:hover{border-color:#454545}td textarea::placeholder{color:#aaa9a5}th:first-child{width:125px}th:nth-child(2){width:32%}th:nth-child(3){width:145px}
[data-status="Pending"]{--status-bg:#b8b8b8;--status-fg:#202020}[data-status="Ongoing"]{--status-bg:#d49a6a;--status-fg:#2a1a0d}[data-status="Blocked"]{--status-bg:#f28bbb;--status-fg:#3d1127}[data-status="Done"]{--status-bg:#65d995;--status-fg:#102d1b}
.status-label,select.status{background:var(--status-bg);color:var(--status-fg);border:0;border-radius:4px;padding:4px 8px;font-size:.84rem;font-weight:500}select.status{cursor:pointer;max-width:130px}select.status option{background:#252525;color:#ededeb}
[data-priority="High"]{--priority-bg:#ff8585;--priority-fg:#450f0f}[data-priority="Medium"]{--priority-bg:#ffd166;--priority-fg:#3b2900}[data-priority="Low"]{--priority-bg:#80bdff;--priority-fg:#102c4a}
.priority-label,select.priority{background:var(--priority-bg);color:var(--priority-fg);border:0;border-radius:4px;padding:4px 8px;font-size:.84rem;font-weight:500}select.priority{cursor:pointer}select.priority option{background:#252525;color:#ededeb}
[hidden]{display:none!important}
@media(max-width:850px){.board{grid-template-columns:repeat(2,minmax(0,1fr))}header{align-items:start;flex-direction:column;gap:10px}}@media(max-width:530px){main{padding:24px 14px 40px}.board{grid-template-columns:1fr}.lane{min-height:120px}}
input::placeholder,textarea::placeholder{color:#aaa9a5;opacity:1}
</style></head><body><main>
<header><div><h1>Issue Time Tracker</h1><p>Track total time spent in Ongoing</p></div><div class="hint">Drag cards or use their menu to change status</div></header>
<nav class="views" aria-label="Task view"><button type="button" data-view="board-view" aria-pressed="true">Board</button><button type="button" data-view="table-view" aria-pressed="false">Table</button></nav>
<div id="error" class="error" role="alert"></div>
<section id="board-view" aria-label="Task board">
<form class="new" id="new"><input id="title" placeholder="New issue, e.g. PCIe error injection" maxlength="200" required aria-label="Issue title"><button>Add task</button></form>
<div class="board" id="board"></div></section>
<section id="table-view" aria-label="Task table" hidden>
<form class="new" id="table-new">
<select name="priority" class="priority" data-priority="Medium" onchange="this.dataset.priority=this.value" aria-label="New task priority"><option>Low</option><option selected>Medium</option><option>High</option></select>
<input name="title" placeholder="Topics" maxlength="200" required aria-label="New task topic">
<select name="status" class="status" data-status="Pending" onchange="this.dataset.status=this.value" aria-label="New task status"><option>Pending</option><option>Ongoing</option><option>Blocked</option><option>Done</option></select>
<textarea name="note" placeholder="Note" maxlength="2000" rows="1" aria-label="New task note"></textarea>
<button>Add task</button></form>
<p class="hint">Text edits save when you leave the field.</p>
<div class="table-wrap"><table><caption>Tasks</caption><thead><tr><th scope="col">Priority</th><th scope="col">Topics</th><th scope="col">Status</th><th scope="col">Note</th></tr></thead><tbody id="task-rows"></tbody></table></div>
</section>
</main><script>
const states=['Pending','Ongoing','Blocked','Done'];let tasks=[];
const board=document.querySelector('#board'),err=document.querySelector('#error');
function fmt(ms){let s=Math.floor(Math.max(0,ms)/1000),h=Math.floor(s/3600),m=Math.floor(s%3600/60);return `${h}h ${String(m).padStart(2,'0')}m ${String(s%60).padStart(2,'0')}s`}
function duration(t){return t.accumulated_ms+(t.ongoing_started_ms===null?0:Math.max(0,Date.now()-t.ongoing_started_ms))}
function showError(e){err.textContent=e.message||String(e)}
async function api(url,opts){let res=await fetch(url,opts);let data=await res.json();if(!res.ok)throw Error(data.error||'Request failed');return data}
function render(){board.replaceChildren();for(const state of states){const lane=document.createElement('section');lane.className='lane';lane.dataset.status=state;const subset=tasks.filter(t=>t.status===state);const h=document.createElement('h2');const label=document.createElement('span');label.className='status-label';label.textContent=state;h.append(label);const count=document.createElement('span');count.className='count';count.textContent=subset.length;h.append(count);lane.append(h);
lane.ondragover=e=>{e.preventDefault();lane.classList.add('over')};lane.ondragleave=e=>{if(!lane.contains(e.relatedTarget))lane.classList.remove('over')};lane.ondrop=e=>{e.preventDefault();lane.classList.remove('over');change(Number(e.dataTransfer.getData('text/plain')),state)};
for(const t of subset){const card=document.createElement('article');card.className='card';card.draggable=true;card.ondragstart=e=>e.dataTransfer.setData('text/plain',String(t.id));const name=document.createElement('h3');name.textContent=t.title;const bottom=document.createElement('div');bottom.className='bottom';const d=document.createElement('div');d.className='duration';d.textContent='Total Ongoing time';const strong=document.createElement('strong');strong.dataset.id=t.id;strong.textContent=fmt(duration(t));d.append(strong);const select=document.createElement('select');select.setAttribute('aria-label',`${t.title} status`);for(const x of states){const op=document.createElement('option');op.value=x;op.textContent=x;select.append(op)}select.value=state;select.className='status';select.dataset.status=state;select.onchange=()=>{select.dataset.status=select.value;change(t.id,select.value)};select.onpointerdown=e=>e.stopPropagation();bottom.append(d,select);const details=document.createElement('p');details.className='details';const priority=document.createElement('span');priority.className='priority-label';priority.dataset.priority=t.priority;priority.textContent=t.priority;details.append(priority);card.append(name,details,bottom);lane.append(card)}if(!subset.length){const empty=document.createElement('p');empty.className='empty';empty.textContent='No tasks';lane.append(empty)}board.append(lane)}}
function renderTable(){
 const rows=document.querySelector('#task-rows');rows.replaceChildren();
 const statusOrder=['Ongoing','Blocked','Pending','Done'],priorityOrder=['High','Medium','Low'];
 const sorted=[...tasks].sort((a,b)=>statusOrder.indexOf(a.status)-statusOrder.indexOf(b.status)||priorityOrder.indexOf(a.priority)-priorityOrder.indexOf(b.priority));
 for(const t of sorted){
  const row=document.createElement('tr');
  for(const [field,label,options] of [['priority','Priority',['Low','Medium','High']],['title','Topics'],['status','Status',states],['note','Note']]){
   const cell=document.createElement('td'),input=document.createElement(options?'select':field==='note'?'textarea':'input');
   if(options)for(const value of options){const option=document.createElement('option');option.value=value;option.textContent=value;input.append(option)}
   else{input.maxLength=field==='title'?200:2000;if(field==='title')input.required=true;else input.rows=2}
   if(field==='status'||field==='priority'){input.className=field;input.dataset[field]=t[field]}
   input.value=t[field];input.setAttribute('aria-label',`${label} for ${t.title}`);
   input.onchange=()=>{if(!input.reportValidity())return;if(field==='status'||field==='priority')input.dataset[field]=input.value;update(t.id,{[field]:input.value})};cell.append(input);row.append(cell);
  }
  rows.append(row);
 }
 if(!tasks.length){const row=document.createElement('tr'),cell=document.createElement('td');cell.colSpan=4;cell.textContent='No tasks';row.append(cell);rows.append(row)}
}
let refreshing=false,saving=0;
async function refresh(force=false){
 if(refreshing)return;refreshing=true;
 try{const latest=await api('/api/tasks');const changed=JSON.stringify(latest)!==JSON.stringify(tasks);tasks=latest;
 if(changed||force){render();if(!document.querySelector('#task-rows').contains(document.activeElement))renderTable()}
 }catch(e){showError(e)}finally{refreshing=false}
}
async function update(id,fields){saving++;try{await api(`/api/tasks/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(fields)});err.textContent='';await refresh(true)}catch(e){showError(e);render()}finally{saving--}}
function change(id,status){const t=tasks.find(x=>x.id===id);if(t&&t.status!==status)return update(id,{status})}
for(const form of document.querySelectorAll('form.new'))form.onsubmit=async e=>{
 e.preventDefault();const button=form.querySelector('button');button.disabled=true;saving++;
 const fields=form.id==='new'?{title:document.querySelector('#title').value}:Object.fromEntries(new FormData(form));
 try{await api('/api/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(fields)});form.reset();if(form.id==='table-new'){document.querySelector('#table-new select[name="status"]').dataset.status='Pending';document.querySelector('#table-new select[name="priority"]').dataset.priority='Medium'}err.textContent='';await refresh(true)}catch(e){showError(e)}finally{button.disabled=false;saving--}
};
for(const button of document.querySelectorAll('[data-view]'))button.onclick=()=>{
 for(const tab of document.querySelectorAll('[data-view]')){const active=tab===button;tab.setAttribute('aria-pressed',String(active));document.getElementById(tab.dataset.view).hidden=!active}
 renderTable();
};
document.querySelector('#task-rows').addEventListener('focusout',()=>setTimeout(()=>{if(!saving&&!document.querySelector('#task-rows').contains(document.activeElement))renderTable()},0));
// shortcut: other tabs refresh once per second; use push updates if subsecond sync is needed.
setInterval(()=>{
 for(const el of document.querySelectorAll('strong[data-id]')){const t=tasks.find(x=>x.id===Number(el.dataset.id));if(t)el.textContent=fmt(duration(t))}
 if(!saving)refresh();
},1000);refresh(true);
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
        columns = {row["name"] for row in db.execute("PRAGMA table_info(tasks)")}
        if "note" not in columns:
            db.execute("ALTER TABLE tasks ADD COLUMN note TEXT NOT NULL DEFAULT ''")
        if "priority" not in columns:
            db.execute("ALTER TABLE tasks ADD COLUMN priority TEXT NOT NULL DEFAULT 'Medium'")
        db.commit()


def task_fields(data, creating=False):
    if not creating and (not data or data.keys() - {"title", "status", "note", "priority"}):
        raise ValueError("Provide title, status, note, or priority")
    fields = {"title": "", "status": "Pending", "note": "", "priority": "Medium"} if creating else {}
    fields.update(data)
    for field, limit in (("title", 200), ("note", 2000)):
        if field in fields:
            value = fields[field]
            if not isinstance(value, str) or len(value) > limit or (field == "title" and not value.strip()):
                raise ValueError(f"{field.capitalize()} must be {'1–' if field == 'title' else '0–'}{limit} characters")
            if field == "title":
                fields[field] = value.strip()
    if "status" in fields and fields["status"] not in STATUSES:
        raise ValueError("Unknown status")
    if "priority" in fields and fields["priority"] not in PRIORITIES:
        raise ValueError("Unknown priority")
    return {key: value for key, value in fields.items() if key in {"title", "status", "note", "priority"}}


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
        if size < 1 or size > 16384:
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
            fields = task_fields(self.read_json(), creating=True)
            now = int(time.time() * 1000)
            with closing(connection()) as db:
                cur = db.execute("""INSERT INTO tasks
                    (title,status,note,priority,created_ms,ongoing_started_ms) VALUES (?,?,?,?,?,?)""",
                    (fields["title"], fields["status"], fields["note"], fields["priority"], now,
                     now if fields["status"] == "Ongoing" else None))
                db.commit()
                self.reply(201, {"id": cur.lastrowid})
        except (ValueError, json.JSONDecodeError) as exc:
            self.reply(400, {"error": str(exc)})

    def do_PATCH(self):
        parts = urlparse(self.path).path.split("/")
        if len(parts) != 4 or parts[1:3] != ["api", "tasks"] or not parts[3].isdigit():
            return self.reply(404, {"error": "Not found"})
        try:
            fields = task_fields(self.read_json())
            with closing(connection()) as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT * FROM tasks WHERE id=?", (int(parts[3]),)).fetchone()
                if row is None:
                    db.rollback()
                    return self.reply(404, {"error": "Task not found"})
                status = fields.get("status", row["status"])
                if row["status"] != status:
                    now = int(time.time() * 1000)
                    total = row["accumulated_ms"]
                    if row["status"] == "Ongoing" and row["ongoing_started_ms"] is not None:
                        total += max(0, now - row["ongoing_started_ms"])
                    started = now if status == "Ongoing" else None
                    fields.update(accumulated_ms=total, ongoing_started_ms=started)
                assignments = ", ".join(f"{key}=?" for key in fields)
                db.execute(f"UPDATE tasks SET {assignments} WHERE id=?", (*fields.values(), row["id"]))
                db.commit()
                self.reply(200, {"ok": True})
        except (ValueError, json.JSONDecodeError) as exc:
            self.reply(400, {"error": str(exc)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Bind address; use 0.0.0.0 for LAN access")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    initialize()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Listening on http://{args.host}:{args.port}  (database: {DB.resolve()})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")
    finally:
        server.server_close()

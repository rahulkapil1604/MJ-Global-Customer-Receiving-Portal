from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, Header
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import sqlite3, secrets, json, smtplib, ssl, os
from datetime import datetime
from email.message import EmailMessage
from typing import List, Optional
from pydantic import BaseModel

BASE = Path(__file__).resolve().parent
DATA_ROOT = Path(os.getenv("DATA_DIR", str(BASE / "data")))
DATA = DATA_ROOT
UPLOADS = DATA_ROOT / "uploads"
DB = DATA_ROOT / "portal.db"
CONFIG = BASE / "config.json"
DATA.mkdir(exist_ok=True)
UPLOADS.mkdir(exist_ok=True)

app = FastAPI(title="MJ Global Pvt Ltd Customer Receiving Portal")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

def cfg():
    c = {}
    if CONFIG.exists():
        c.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    env_map = {
        "PUBLIC_BASE_URL": "public_base_url",
        "PORTAL_API_KEY": "api_key",
        "SENDER_EMAIL": "sender_email",
        "GMAIL_APP_PASSWORD": "gmail_app_password",
        "NOTIFY_TO": "notify_to",
        "NOTIFY_CC": "notify_cc",
        "COMPANY_NAME": "company_name",
    }
    for env_key, cfg_key in env_map.items():
        val = os.getenv(env_key)
        if val is not None and val != "":
            c[cfg_key] = val
    return c

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

class CreateReceivingLinkRequest(BaseModel):
    customer_name: str
    customer_email: str = ""
    invoice_no: str
    dispatch_ref: str = ""
    expected_qty: str = ""
    notify_to: str = ""
    notify_cc: str = ""

def public_url(token: str) -> str:
    base = cfg().get("public_base_url", "").strip().rstrip("/")
    if not base:
        raise RuntimeError("public_base_url missing in config.json")
    return f"{base}/r/{token}"

def api_authorized(api_key: Optional[str]) -> bool:
    expected = cfg().get("api_key", "").strip()
    return bool(expected) and secrets.compare_digest(expected, (api_key or "").strip())

def init_db():
    con = db()
    con.executescript('''
    CREATE TABLE IF NOT EXISTS receiving_links(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      token TEXT UNIQUE NOT NULL,
      customer_name TEXT NOT NULL,
      customer_email TEXT,
      invoice_no TEXT NOT NULL,
      dispatch_ref TEXT,
      expected_qty TEXT,
      notify_to TEXT,
      notify_cc TEXT,
      created_at TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'PENDING'
    );
    CREATE TABLE IF NOT EXISTS receiving_submissions(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      token TEXT NOT NULL,
      received_by TEXT NOT NULL,
      mobile_no TEXT,
      received_qty TEXT,
      receiving_status TEXT NOT NULL,
      remarks TEXT,
      submitted_at TEXT NOT NULL,
      remote_ip TEXT,
      email_status TEXT NOT NULL DEFAULT 'PENDING',
      email_error TEXT
    );
    CREATE TABLE IF NOT EXISTS receiving_files(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      submission_id INTEGER NOT NULL,
      file_name TEXT NOT NULL,
      stored_path TEXT NOT NULL,
      content_type TEXT
    );
    ''')
    cols={r[1] for r in con.execute("PRAGMA table_info(receiving_links)").fetchall()}
    if 'notify_to' not in cols: con.execute("ALTER TABLE receiving_links ADD COLUMN notify_to TEXT")
    if 'notify_cc' not in cols: con.execute("ALTER TABLE receiving_links ADD COLUMN notify_cc TEXT")
    con.commit(); con.close()

init_db()

def send_notification(link, submission, files):
    c = cfg()
    sender = c.get("sender_email", "").strip()
    app_pw = c.get("gmail_app_password", "").replace(" ", "").strip()
    notify_to = (link["notify_to"] or c.get("notify_to", "")).strip()
    notify_cc = (link["notify_cc"] or c.get("notify_cc", "")).strip()
    if not (sender and app_pw and notify_to):
        raise RuntimeError("Email settings incomplete in config.json")

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = notify_to
    if notify_cc: msg["Cc"] = notify_cc
    msg["Subject"] = f"Customer Receiving - {link['invoice_no']} - {link['customer_name']}"
    body = f"""Dear Team,

Customer receiving has been submitted.

Customer       : {link['customer_name']}
Invoice No.    : {link['invoice_no']}
Dispatch Ref.  : {link['dispatch_ref'] or '-'}
Expected Qty   : {link['expected_qty'] or '-'}
Receiving      : {submission['receiving_status']}
Received Qty   : {submission['received_qty'] or '-'}
Received By    : {submission['received_by']}
Mobile No.     : {submission['mobile_no'] or '-'}
Remarks        : {submission['remarks'] or '-'}
Submitted At   : {submission['submitted_at']}

Attached files were uploaded by the customer through the MJ Global Pvt Ltd Customer Receiving Portal.
"""
    msg.set_content(body)
    for f in files:
        p = Path(f["stored_path"])
        if not p.exists(): continue
        ctype = f["content_type"] or "application/octet-stream"
        maintype, subtype = (ctype.split("/",1)+["octet-stream"])[:2]
        msg.add_attachment(p.read_bytes(), maintype=maintype, subtype=subtype, filename=f["file_name"])
    recipients = [x.strip() for x in (notify_to + (","+notify_cc if notify_cc else "")).replace(";",",").split(",") if x.strip()]
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context, timeout=30) as s:
        s.login(sender, app_pw)
        s.send_message(msg, from_addr=sender, to_addrs=recipients)

@app.get("/", response_class=HTMLResponse)
def root():
    return RedirectResponse("/create")

@app.get("/create", response_class=HTMLResponse)
def create_form(request: Request):
    con = db(); rows = con.execute("SELECT * FROM receiving_links ORDER BY id DESC LIMIT 50").fetchall(); con.close()
    return templates.TemplateResponse("create.html", {"request": request, "rows": rows, "cfg": cfg()})

@app.post("/create")
def create_link(customer_name: str = Form(...), customer_email: str = Form(""), invoice_no: str = Form(...), dispatch_ref: str = Form(""), expected_qty: str = Form("")):
    token = secrets.token_urlsafe(24)
    c=cfg(); con = db(); con.execute("INSERT INTO receiving_links(token,customer_name,customer_email,invoice_no,dispatch_ref,expected_qty,notify_to,notify_cc,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (token, customer_name.strip(), customer_email.strip(), invoice_no.strip(), dispatch_ref.strip(), expected_qty.strip(), c.get("notify_to","").strip(), c.get("notify_cc","").strip(), datetime.now().isoformat(timespec="seconds")))
    con.commit(); con.close()
    return RedirectResponse(f"/create?created={token}", status_code=303)


@app.post("/api/receiving-links")
def api_create_receiving_link(payload: CreateReceivingLinkRequest, x_api_key: Optional[str] = Header(default=None)):
    if not api_authorized(x_api_key):
        raise HTTPException(401, "Invalid API key")
    if not payload.customer_name.strip() or not payload.invoice_no.strip():
        raise HTTPException(400, "customer_name and invoice_no are required")
    token=secrets.token_urlsafe(24)
    c=cfg()
    notify_to=(payload.notify_to or c.get("notify_to","")).strip()
    notify_cc=(payload.notify_cc or c.get("notify_cc","")).strip()
    con=db()
    con.execute("INSERT INTO receiving_links(token,customer_name,customer_email,invoice_no,dispatch_ref,expected_qty,notify_to,notify_cc,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (token,payload.customer_name.strip(),payload.customer_email.strip(),payload.invoice_no.strip(),payload.dispatch_ref.strip(),payload.expected_qty.strip(),notify_to,notify_cc,datetime.now().isoformat(timespec="seconds")))
    con.commit(); con.close()
    return {"success": True, "token": token, "receiving_url": public_url(token)}

@app.get("/api/health")
def api_health():
    return {"ok": True, "service": "MJ Global Pvt Ltd Customer Receiving Portal"}

@app.get("/r/{token}", response_class=HTMLResponse)
def receive_page(token: str, request: Request):
    con = db(); link = con.execute("SELECT * FROM receiving_links WHERE token=?", (token,)).fetchone(); con.close()
    if not link: raise HTTPException(404, "Invalid receiving link")
    return templates.TemplateResponse("receive.html", {"request": request, "link": link, "cfg": cfg()})

@app.post("/r/{token}", response_class=HTMLResponse)
async def submit_receiving(token: str, request: Request, received_by: str = Form(...), mobile_no: str = Form(""), received_qty: str = Form(""), receiving_status: str = Form(...), remarks: str = Form(""), files: List[UploadFile] = File(default=[])):
    con = db(); link = con.execute("SELECT * FROM receiving_links WHERE token=?", (token,)).fetchone()
    if not link:
        con.close(); raise HTTPException(404, "Invalid receiving link")
    if link["status"] == "RECEIVED":
        con.close(); return templates.TemplateResponse("done.html", {"request": request, "link": link, "already": True, "cfg": cfg()})
    submitted_at = datetime.now().isoformat(timespec="seconds")
    cur = con.execute("INSERT INTO receiving_submissions(token,received_by,mobile_no,received_qty,receiving_status,remarks,submitted_at,remote_ip) VALUES(?,?,?,?,?,?,?,?)",
        (token, received_by.strip(), mobile_no.strip(), received_qty.strip(), receiving_status, remarks.strip(), submitted_at, request.client.host if request.client else ""))
    sid = cur.lastrowid
    stored=[]
    folder = UPLOADS / f"{sid}_{token[:8]}"; folder.mkdir(parents=True, exist_ok=True)
    for uf in files[:8]:
        if not uf.filename: continue
        safe = "".join(ch for ch in uf.filename if ch.isalnum() or ch in "._- ")[:120] or "upload.bin"
        p = folder / safe
        data = await uf.read()
        if len(data) > 15*1024*1024: continue
        p.write_bytes(data)
        con.execute("INSERT INTO receiving_files(submission_id,file_name,stored_path,content_type) VALUES(?,?,?,?)", (sid, safe, str(p), uf.content_type or "application/octet-stream"))
        stored.append({"file_name":safe,"stored_path":str(p),"content_type":uf.content_type})
    con.execute("UPDATE receiving_links SET status='RECEIVED' WHERE token=?", (token,))
    con.commit()
    submission = con.execute("SELECT * FROM receiving_submissions WHERE id=?", (sid,)).fetchone()
    email_status="SENT"; err=""
    try:
        send_notification(link, submission, stored)
    except Exception as e:
        email_status="FAILED"; err=str(e)[:500]
    con.execute("UPDATE receiving_submissions SET email_status=?, email_error=? WHERE id=?", (email_status, err, sid)); con.commit(); con.close()
    return templates.TemplateResponse("done.html", {"request": request, "link": link, "already": False, "email_status": email_status, "cfg": cfg()})

@app.get("/history", response_class=HTMLResponse)
def history(request: Request):
    con = db(); rows = con.execute('''SELECT s.*, l.customer_name,l.invoice_no,l.dispatch_ref FROM receiving_submissions s JOIN receiving_links l ON l.token=s.token ORDER BY s.id DESC''').fetchall(); con.close()
    return templates.TemplateResponse("history.html", {"request": request, "rows": rows, "cfg": cfg()})

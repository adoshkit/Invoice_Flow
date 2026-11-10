"""SQLite layer: vendor master, purchase orders + PO lines (mock procurement system), FX rates, run history,
and the human-review audit trail."""
import difflib
import json
import os
import re
import sqlite3
from datetime import datetime

DB_PATH = os.environ.get("INVOICE_DB", "invoiceflow.db")

VENDOR_DATA = [
    ("Acme Office Supplies Ltd", 0.20, "GB82WEST12345698765432"),
    ("Globex Logistics Inc", 0.20, "US64SVBKUS6S3300958879"),
    ("Initech Software LLC", 0.20, "US12CHAS02100002100099"),
    ("Umbrella Industrial Corp", 0.20, "US33BOFA02600900123456"),
    ("Hooli Cloud Services", 0.20, "US77WFBI03100400555123"),
    ("Veldt Engineering BV", 0.21, "NL91ABNA0417164300"),
]
VENDORS = [v[0] for v in VENDOR_DATA]
VENDOR_BANK = {v[0]: v[2] for v in VENDOR_DATA}

POS = [
    ("PO-1001", "Acme Office Supplies Ltd", 4800.00, "USD", "2026-09-15"),
    ("PO-1002", "Acme Office Supplies Ltd", 2400.00, "USD", "2026-09-15"),
    ("PO-1003", "Acme Office Supplies Ltd", 3600.00, "USD", "2026-09-15"),
    ("PO-1004", "Acme Office Supplies Ltd", 1800.00, "USD", "2026-09-15"),
    ("PO-2002", "Globex Logistics Inc", 12000.00, "USD", "2026-09-15"),
    ("PO-2003", "Globex Logistics Inc", 2400.00, "USD", "2026-09-15"),
    ("PO-3003", "Initech Software LLC", 2500.00, "USD", "2026-09-15"),
    ("PO-3004", "Initech Software LLC", 2500.00, "USD", "2026-09-15"),
    ("PO-4004", "Umbrella Industrial Corp", 9300.00, "USD", "2026-09-15"),
    ("PO-4010", "Umbrella Industrial Corp", 1200.00, "USD", "2026-09-15"),
    ("PO-5005", "Hooli Cloud Services", 3000.00, "USD", "2026-09-15"),
    ("PO-5006", "Hooli Cloud Services", 1280.00, "USD", "2026-09-15"),
    ("PO-6001", "Veldt Engineering BV", 5000.00, "USD", "2026-09-15"),
]

PO_LINES = [
    ("PO-1001", "A4 copier paper (reams)", 100, 10.00),
    ("PO-1001", "Toner cartridge", 20, 100.00),
    ("PO-1001", "Desk organiser", 40, 25.00),
    ("PO-1002", "A4 copier paper (reams)", 100, 10.00),
    ("PO-1002", "Toner cartridge", 10, 100.00),
]

FX_RATES = {"USD": 1.0, "EUR": 1.08, "GBP": 1.27, "INR": 0.012, "AUD": 0.65, "CAD": 0.73, "SGD": 0.74}

SCHEMA = """
CREATE TABLE IF NOT EXISTS vendors(name TEXT PRIMARY KEY, approved INTEGER DEFAULT 1, tax_rate REAL, bank_account TEXT);
CREATE TABLE IF NOT EXISTS admin_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS admin_events(id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, actor TEXT, action TEXT, target TEXT, details TEXT);
CREATE TABLE IF NOT EXISTS purchase_orders(
    po_number TEXT PRIMARY KEY, vendor TEXT, amount REAL, currency TEXT, status TEXT DEFAULT 'OPEN', issue_date TEXT);
CREATE TABLE IF NOT EXISTS po_lines(po_number TEXT, description TEXT, qty REAL, unit_price REAL);
CREATE TABLE IF NOT EXISTS runs(
    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, filename TEXT, file_hash TEXT, method TEXT,
    vendor TEXT, vendor_key TEXT, invoice_number TEXT, invoice_key TEXT, invoice_date TEXT,
    po_number TEXT, po_used TEXT, po_inferred INTEGER, currency TEXT, total REAL,
    decision TEXT, reason TEXT, extracted_json TEXT, checks_json TEXT, stages_json TEXT, po_json TEXT);
"""

RUN_COLS = {"po_amount": "REAL", "doc_type": "TEXT", "risk": "INTEGER", "owner": "TEXT",
            "final_decision": "TEXT", "reviewer": "TEXT", "review_note": "TEXT", "reviewed_at": "TEXT"}
EFF = "COALESCE(final_decision, decision)"

def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def _query(sql, params=()):
    c = _conn()
    try:
        return [dict(r) for r in c.execute(sql, params).fetchall()]
    finally:
        c.close()

def _cols(c, table):
    return {r[1] for r in c.execute(f"PRAGMA table_info({table})")}

def init_db():
    c = _conn()
    c.executescript(SCHEMA)
    for table, cols in (("runs", RUN_COLS), ("vendors", {"tax_rate": "REAL", "bank_account": "TEXT"}),
                        ("purchase_orders", {"issue_date": "TEXT"})):
        have = _cols(c, table)
        for name, typ in cols.items():
            if name not in have:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")
    for name, rate, bank in VENDOR_DATA:
        c.execute("INSERT OR IGNORE INTO vendors(name) VALUES (?)", (name,))
        c.execute("UPDATE vendors SET tax_rate=COALESCE(tax_rate,?), bank_account=COALESCE(bank_account,?) WHERE name=?",
                  (rate, bank, name))
    for po, vendor, amount, cur, issued in POS:
        c.execute("INSERT OR IGNORE INTO purchase_orders(po_number,vendor,amount,currency) VALUES (?,?,?,?)",
                  (po, vendor, amount, cur))
        c.execute("UPDATE purchase_orders SET issue_date=COALESCE(issue_date,?) WHERE po_number=?", (issued, po))
    if c.execute("SELECT COUNT(*) FROM po_lines").fetchone()[0] == 0:
        c.executemany("INSERT INTO po_lines VALUES (?,?,?,?)", PO_LINES)
    c.commit()
    c.close()

_SUFFIX = {"limited": "ltd", "incorporated": "inc", "corporation": "corp", "company": "co"}
_DROP = {"ltd", "inc", "llc", "corp", "co", "plc", "pvt", "gmbh", "the"}

def norm_vendor(name):
    s = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())
    words = [_SUFFIX.get(w, w) for w in s.split()]
    return " ".join(w for w in words if w not in _DROP)

def norm_key(s):
    """'INV-0042', 'inv 0042' and 'INV0042' all become 'INV0042'."""
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())

def fx_rate(src, dst):
    """Multiply an amount in src by this to get dst, or None if either currency is unknown."""
    if src in FX_RATES and dst in FX_RATES:
        return FX_RATES[src] / FX_RATES[dst]
    return None

def find_vendor(name):
    key = norm_vendor(name)
    if not key:
        return None
    best, best_score = None, 0.0
    for v in _query("SELECT * FROM vendors"):
        score = difflib.SequenceMatcher(None, key, norm_vendor(v["name"])).ratio()
        if score > best_score:
            best, best_score = v, score
    return {**best, "score": best_score} if best and best_score >= 0.85 else None

def list_vendors():
    return _query("SELECT * FROM vendors ORDER BY name")

def list_pos():
    """POs with how much has been approved against them. Credit notes carry a negative amount, so they
    automatically restore balance. Human-approved holds count; human-rejected ones don't."""
    rows = _query(
        f"""SELECT p.*, COALESCE((SELECT SUM(COALESCE(r.po_amount, r.total)) FROM runs r
                                 WHERE COALESCE(r.final_decision, r.decision)='APPROVE'
                                   AND r.po_used=p.po_number), 0) AS invoiced
           FROM purchase_orders p ORDER BY p.po_number""")
    for r in rows:
        r["remaining"] = round(r["amount"] - r["invoiced"], 2)
    return rows

def get_po(po_number):
    k = norm_key(po_number)
    return next((p for p in list_pos() if norm_key(p["po_number"]) == k), None)

def get_po_lines(po_number):
    return _query("SELECT description, qty, unit_price FROM po_lines WHERE po_number=?", (po_number,))

def list_po_lines():
    return _query("SELECT * FROM po_lines ORDER BY po_number")

def find_duplicates(vendor_key, invoice_key, total=None, po_used=None):
    """exact = same vendor + same invoice number; possible = same vendor + PO + amount."""
    rows = _query(
        f"SELECT id, invoice_number, invoice_key, COALESCE(po_amount,total) AS total, po_used, {EFF} AS decision "
        f"FROM runs WHERE vendor_key=? AND {EFF} IN ('APPROVE','HOLD')", (vendor_key,))
    exact, possible = [], []
    for r in rows:
        if invoice_key and r["invoice_key"] == invoice_key:
            exact.append(r)
        elif po_used and r["po_used"] == po_used and total is not None and r["total"] is not None \
                and abs(r["total"] - total) < 0.005:
            possible.append(r)
    return exact, possible

def find_by_hash(file_hash):
    """Earlier runs of the byte-identical file. Runs where extraction failed are ignored, so retrying a file
    after fixing a config problem is never mistaken for a duplicate."""
    return _query(
        f"SELECT id, filename, {EFF} AS decision FROM runs WHERE file_hash=? AND {EFF} IN ('APPROVE','HOLD') "
        "AND (vendor IS NOT NULL OR total IS NOT NULL) ORDER BY id LIMIT 1", (file_hash,))

def po_invoices(po_number):
    """Approved documents already booked against a PO (for the cumulative split-PO view)."""
    return _query(f"SELECT id, invoice_number, COALESCE(po_amount,total) AS total FROM runs "
                  f"WHERE {EFF}='APPROVE' AND po_used=? ORDER BY id", (po_number,))

def find_original(vendor_key, invoice_key):
    """The approved invoice a credit note refers to."""
    rows = _query(f"SELECT id, invoice_number, total, po_used FROM runs WHERE vendor_key=? AND invoice_key=? "
                  f"AND {EFF}='APPROVE' AND total > 0 ORDER BY id LIMIT 1", (vendor_key, invoice_key))
    return rows[0] if rows else None

def save_run(R):
    x = R.get("extracted") or {}
    po = R.get("po") or {}
    vk = R.get("vendor_key") or norm_vendor(x.get("vendor_name"))
    vals = (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), R["filename"], R.get("file_hash"), R.get("method"),
        x.get("vendor_name"), vk, x.get("invoice_number"), norm_key(x.get("invoice_number")),
        x.get("invoice_date"), x.get("po_number"), po.get("po_number"), int(bool(po.get("inferred"))),
        x.get("currency"), x.get("total"), R["decision"], R["reason"],
        json.dumps(x), json.dumps(R.get("checks")), json.dumps(R.get("stages")), json.dumps(po or None),
        po.get("po_amount", x.get("total")) if po else x.get("total"), x.get("doc_type"), R.get("risk"), R.get("owner"),
    )
    c = _conn()
    cur = c.execute(
        "INSERT INTO runs(created_at,filename,file_hash,method,vendor,vendor_key,invoice_number,invoice_key,"
        "invoice_date,po_number,po_used,po_inferred,currency,total,decision,reason,extracted_json,checks_json,"
        f"stages_json,po_json,po_amount,doc_type,risk,owner) VALUES ({','.join('?' * len(vals))})", vals)
    c.commit()
    rid = cur.lastrowid
    c.close()
    return rid

def review(run_id, decision, note, reviewer):
    """Record a human decision on a held invoice (audit trail kept; the system decision is never overwritten)."""
    c = _conn()
    c.execute("UPDATE runs SET final_decision=?, review_note=?, reviewer=?, reviewed_at=? WHERE id=?",
              (decision, note, reviewer, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), run_id))
    c.commit()
    c.close()

def _parse(r):
    for k in ("extracted", "checks", "stages", "po"):
        r[k] = json.loads(r.pop(k + "_json") or "null")
    r["run_id"] = r["id"]
    r["effective"] = r.get("final_decision") or r["decision"]
    return r

def list_runs():
    return [_parse(r) for r in _query("SELECT * FROM runs ORDER BY id DESC")]

def clear_runs():
    c = _conn()
    c.execute("DELETE FROM runs")
    c.commit()
    c.close()

def set_vendor(name, approved, tax_rate=None, bank_account=None):
    name = (name or "").strip()
    if not name:
        raise ValueError("Vendor name is required")
    c = _conn()
    c.execute("""INSERT INTO vendors(name,approved,tax_rate,bank_account) VALUES (?,?,?,?)
                 ON CONFLICT(name) DO UPDATE SET approved=excluded.approved,
                 tax_rate=COALESCE(excluded.tax_rate,vendors.tax_rate),
                 bank_account=COALESCE(excluded.bank_account,vendors.bank_account)""",
              (name, int(bool(approved)), tax_rate, bank_account))
    c.commit(); c.close()

def set_po(po_number, vendor, amount, currency, issue_date, status="OPEN"):
    po_number, vendor = (po_number or "").strip(), (vendor or "").strip()
    if not po_number or not vendor or float(amount) <= 0:
        raise ValueError("PO number, vendor and a positive amount are required")
    c = _conn()
    c.execute("""INSERT INTO purchase_orders(po_number,vendor,amount,currency,status,issue_date)
                 VALUES (?,?,?,?,?,?) ON CONFLICT(po_number) DO UPDATE SET vendor=excluded.vendor,
                 amount=excluded.amount,currency=excluded.currency,status=excluded.status,issue_date=excluded.issue_date""",
              (po_number, vendor, float(amount), (currency or "USD").upper(), status, issue_date))
    c.commit(); c.close()

def update_po_status(po_number, status):
    if status not in ("OPEN", "CLOSED", "CANCELLED"):
        raise ValueError("Invalid PO status")
    c = _conn(); c.execute("UPDATE purchase_orders SET status=? WHERE po_number=?", (status, po_number)); c.commit(); c.close()

def get_setting(key, default=None):
    rows = _query("SELECT value FROM admin_settings WHERE key=?", (key,))
    return rows[0]["value"] if rows else default

def set_setting(key, value):
    c = _conn(); c.execute("INSERT INTO admin_settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value))); c.commit(); c.close()

def log_admin_event(actor, action, target="", details=""):
    c = _conn(); c.execute("INSERT INTO admin_events(created_at,actor,action,target,details) VALUES (?,?,?,?,?)",
                           (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), actor, action, str(target), str(details)))
    c.commit(); c.close()

def list_admin_events(limit=500):
    return _query("SELECT * FROM admin_events ORDER BY id DESC LIMIT ?", (int(limit),))

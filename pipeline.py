"""Invoice pipeline: Ingest -> Extract -> Validate -> Match PO -> Decide.

`run_pipeline` is a generator that yields a progress event before and after every stage, so the
UI can render a live run view. The final event carries the full result (also saved to SQLite).

Extraction is pluggable ("rules" offline default, optional "gemini", or "auto" with fallback).
Every decision after extraction is plain Python, so it is explainable and repeatable.

Rules fired (each shows in the rule-by-rule trail):
  V1 required fields   V2 date sanity (future / stale)   V3 extraction confidence   V4 approved vendor
  V5a same file        V5b same invoice number           V6 arithmetic              V7 bank details changed
  V8 tax-rate anomaly  V9 credit-note reference
  P1 PO exists/inferred  P2 PO belongs to vendor  P3 PO open + currency (FX)  P4 cumulative balance + tolerance
  P5 possible duplicate  P6 invoice predates PO   L1 line-level price/quantity variance
"""
import difflib
import hashlib
import io
import os
import time
from datetime import date, datetime

try:
    import pymupdf as fitz
except ImportError:
    import fitz

import db
import extract_rules

STAGES = ["Ingest", "Extract", "Validate", "Match PO", "Decide"]
MIN_CHARS_PER_PAGE = 40
MAX_PAGES = 5
EPS = 0.05
STALE_DAYS = 180
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
ENGINES = {
    "rules": "Offline rules (no API key)",
    "auto": "Auto: Gemini if key set, else offline",
    "gemini": "Gemini only (needs key)",
}
METHODS = {
    "text-layer": "PDF text layer",
    "ocr-tesseract": "Tesseract OCR (scanned)",
    "ocr-gemini-vision": "Gemini vision OCR (scanned)",
    "scan-unreadable": "Scanned image - no OCR engine available",
}

APPROVAL_TIERS = [(1000, "AP clerk (auto-approve)"), (5000, "AP manager"), (10000, "Finance controller"),
                  (float("inf"), "CFO")]

OWNER_PRIORITY = [
    ("V7", "Treasury - call the vendor on a known number"), ("V4", "Vendor management"),
    ("V5a", "AP clerk"), ("V5b", "AP clerk"), ("V9", "AP clerk"), ("V8", "Tax team"),
    ("P2", "Buyer / procurement"), ("P1", "Buyer / procurement"), ("P6", "Buyer / procurement"),
    ("L1", "Buyer / procurement"), ("P4", "Buyer / procurement"), ("P3", "Buyer / procurement"),
    ("P5", "AP clerk"), ("V1", "AP clerk"), ("V2", "AP clerk"), ("V3", "AP clerk"), ("V6", "AP clerk"),
]
RISK_WEIGHT = {"reject": 60, "hold": 25, "warn": 5}

def gemini_available():
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))

def _parse_iso(s):
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None

def ingest(pdf_bytes, allow_vision=False):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = len(doc)
    if pages == 0:
        raise ValueError("PDF has no pages")
    n = min(pages, MAX_PAGES)
    text = "\n".join(doc[i].get_text() for i in range(n)).strip()
    if len(text) >= MIN_CHARS_PER_PAGE * n:
        return {"method": "text-layer", "text": text, "images": [], "pages": pages}

    images = [doc[i].get_pixmap(dpi=200).tobytes("png") for i in range(n)]
    try:
        import pytesseract
        from PIL import Image
        ocr = "\n".join(pytesseract.image_to_string(Image.open(io.BytesIO(b))) for b in images).strip()
        if len(ocr) >= MIN_CHARS_PER_PAGE * n:
            return {"method": "ocr-tesseract", "text": ocr, "images": [], "pages": pages}
    except Exception:
        pass
    if allow_vision:
        return {"method": "ocr-gemini-vision", "text": "", "images": images, "pages": pages}
    return {"method": "scan-unreadable", "text": "", "images": [], "pages": pages}

def extract(ing, engine="rules"):
    """Return the canonical extraction dict plus x['engine'] describing what actually ran."""
    fallback_note = None
    if engine in ("auto", "gemini"):
        if not gemini_available():
            if engine == "gemini":
                raise RuntimeError("Gemini engine selected but no GEMINI_API_KEY is set")
            fallback_note = "No Gemini key set - used offline rules."
        else:
            try:
                import extract_gemini
                x = extract_gemini.extract(ing)
                x["engine"] = f"Gemini ({x['model']})"
                return _sign_credit_note(x)
            except Exception as e:
                if engine == "gemini":
                    raise
                msg = str(e).replace("\n", " ")
                fallback_note = f"Gemini unavailable ({msg[:110]}...) - fell back to offline rules."
    x = extract_rules.extract(ing)
    x["engine"] = "Offline rules"
    if fallback_note:
        x["notes"] = f"{fallback_note} {x['notes'] or ''}".strip()
    return _sign_credit_note(x)

def _sign_credit_note(x):
    """Credit notes reduce what we owe: store every amount as negative so sums and arithmetic just work."""
    if x.get("doc_type") != "credit":
        return x
    for k in ("subtotal", "tax", "total"):
        if x.get(k) is not None:
            x[k] = -abs(x[k])
    for i in x.get("line_items", []):
        for k in ("unit_price", "amount"):
            if i.get(k) is not None:
                i[k] = -abs(i[k])
    return x

def _check(cid, name, status, detail, severity=None):
    return {"id": cid, "name": name, "status": status, "severity": severity, "detail": detail}

def validate(x, file_hash=None, as_of=None, ocr=False):
    """Document-level checks. Returns (checks, matched_vendor)."""
    as_of = as_of or date.today()
    checks, conf = [], x["confidence"]
    credit = x.get("doc_type") == "credit"
    kind = "credit note" if credit else "invoice"

    missing = [lbl for k, lbl in (("vendor_name", "vendor name"), ("invoice_number", f"{kind} number"),
                                  ("total", "total amount")) if x.get(k) is None]
    if not missing:
        checks.append(_check("V1", "Required fields", "pass", f"Vendor, {kind} number and total are present."))
    elif missing == [f"{kind} number"]:
        checks.append(_check(
            "V1", "Required fields", "fail",
            f"No {kind} number found, but every other required field is present. Not rejected outright: route to AP "
            "to get the number from the vendor (or confirm the document is genuine). Until then, duplicate detection "
            "falls back to vendor + PO + amount.", "hold"))
    else:
        checks.append(_check(
            "V1", "Required fields", "fail",
            f"Missing {', '.join(missing)}. The document cannot be assessed automatically - a person must read the "
            "original or request a corrected copy.", "hold"))

    d = _parse_iso(x.get("invoice_date"))
    if not x.get("invoice_date"):
        checks.append(_check("V2", "Invoice date", "fail", "No invoice date found.", "hold"))
    elif d is None:
        checks.append(_check("V2", "Invoice date", "warn", f"Date '{x['invoice_date']}' could not be parsed."))
    elif d > as_of:
        checks.append(_check("V2", "Invoice date", "fail",
                             f"Dated {d}, which is {(d - as_of).days} day(s) in the future (as of {as_of}). "
                             "Future-dated invoices are a common sign of keying errors or pre-billing.", "hold"))
    elif (as_of - d).days > STALE_DAYS:
        checks.append(_check("V2", "Invoice date", "warn",
                             f"Dated {d}, {(as_of - d).days} days ago - stale. Check late-payment terms and that "
                             "it was not already paid outside this system."))
    else:
        checks.append(_check("V2", "Invoice date", "pass", f"Dated {d}."))

    low = [k for k in ("vendor_name", "invoice_number", "total", "po_number")
           if x.get(k) is not None and conf.get(k) == "low"]
    if low:
        checks.append(_check("V3", "Extraction confidence", "fail",
                             f"Low confidence on: {', '.join(low)}. Verify against the original document.", "hold"))
    else:
        checks.append(_check("V3", "Extraction confidence", "pass", "No low-confidence critical fields."))

    vendor = db.find_vendor(x["vendor_name"]) if x.get("vendor_name") else None
    if not x.get("vendor_name"):
        checks.append(_check("V4", "Approved vendor", "warn", "Skipped - no vendor name extracted."))
    elif not vendor:
        checks.append(_check("V4", "Approved vendor", "fail",
                             f"'{x['vendor_name']}' is not in the approved vendor master.", "reject"))
    elif not vendor["approved"]:
        checks.append(_check("V4", "Approved vendor", "fail", f"'{vendor['name']}' is blocked.", "reject"))
    else:
        checks.append(_check("V4", "Approved vendor", "pass",
                             f"Matched '{vendor['name']}' (name similarity {vendor['score']:.0%})."))

    same_file = db.find_by_hash(file_hash) if file_hash else []
    if same_file:
        dd = same_file[0]
        checks.append(_check("V5a", "Duplicate file", "fail",
                             f"This exact file (content hash {file_hash}) was already processed as run #{dd['id']} "
                             f"('{dd['filename']}', {dd['decision']}). Renaming the file does not make it a new invoice.",
                             "reject"))
    else:
        checks.append(_check("V5a", "Duplicate file", "pass", "No byte-identical file processed before."))

    if same_file:
        pass
    elif vendor and x.get("invoice_number"):
        exact, _ = db.find_duplicates(db.norm_vendor(vendor["name"]), db.norm_key(x["invoice_number"]))
        if exact:
            dd = exact[0]
            checks.append(_check("V5b", "Duplicate invoice number", "fail",
                                 f"Number '{x['invoice_number']}' from this vendor was already processed "
                                 f"(run #{dd['id']}, {dd['decision']}, {dd['total']:,.2f}). Formatting, filename and date "
                                 "differences are ignored.", "reject"))
        else:
            checks.append(_check("V5b", "Duplicate invoice number", "pass", "No earlier document with this vendor + number."))

    items = [i["amount"] for i in x["line_items"] if i["amount"] is not None]
    items_sum = round(sum(items), 2) if items else None
    base = x["subtotal"] if x.get("subtotal") is not None else items_sum
    if base is None or x.get("total") is None:
        checks.append(_check("V6", "Arithmetic", "warn", "Not enough figures to cross-check the total."))
    else:
        problems = []
        if items_sum is not None and x.get("subtotal") is not None and abs(items_sum - x["subtotal"]) > EPS:
            problems.append(f"line items sum to {items_sum:,.2f} but subtotal says {x['subtotal']:,.2f}")
        expected = round(base + (x.get("tax") or 0), 2)
        if abs(expected - x["total"]) > EPS:
            problems.append(f"subtotal {base:,.2f} + tax {(x.get('tax') or 0):,.2f} = {expected:,.2f}, "
                            f"but the document total is {x['total']:,.2f}")
        if problems:
            checks.append(_check("V6", "Arithmetic", "fail", "; ".join(problems).capitalize() + ".", "hold"))
        else:
            checks.append(_check("V6", "Arithmetic", "pass",
                                 f"Items/subtotal + tax = {expected:,.2f}, matches the total."))

    acct = db.norm_key(x.get("bank_account"))
    known = db.norm_key((vendor or {}).get("bank_account"))
    if vendor and acct and known:
        if acct == known:
            checks.append(_check("V7", "Bank details", "pass", "Bank account matches the vendor master."))
        elif ocr and difflib.SequenceMatcher(None, acct, known).ratio() >= 0.8:
            checks.append(_check("V7", "Bank details", "warn",
                                 f"Account '{x['bank_account']}' is almost identical to the one on file - likely an OCR "
                                 "misread; confirm against the original."))
        else:
            checks.append(_check(
                "V7", "Bank details", "fail",
                f"Invoice asks for payment to '{x['bank_account']}', but the vendor master has an account ending "
                f"...{known[-4:]}. A changed bank account is the #1 invoice-fraud pattern: do NOT pay until the vendor "
                "confirms the change by phone on a number already on file.", "hold"))
    elif vendor and acct and not known:
        checks.append(_check("V7", "Bank details", "warn", "No bank account on file for this vendor to compare against."))
    else:
        checks.append(_check("V7", "Bank details", "pass", "No bank details printed on the document."))

    exp_rate = (vendor or {}).get("tax_rate")
    if exp_rate is not None and base and x.get("tax") is not None and base != 0:
        implied = x["tax"] / base
        if abs(implied - exp_rate) > 0.005:
            checks.append(_check("V8", "Tax rate", "fail",
                                 f"Tax is {implied:.1%} of the subtotal, but this vendor's registered rate is "
                                 f"{exp_rate:.0%}. Totals add up, yet the wrong rate would over/under-pay tax.", "hold"))
        else:
            checks.append(_check("V8", "Tax rate", "pass", f"Tax is {implied:.1%}, matching the vendor's {exp_rate:.0%}."))
    else:
        checks.append(_check("V8", "Tax rate", "pass", "No separate tax line (tax-inclusive or exempt) - rate check skipped."))

    if credit:
        rel = x.get("related_invoice")
        if not rel:
            checks.append(_check("V9", "Credit-note reference", "fail",
                                 "Credit note does not cite the invoice it credits - cannot apply it safely.", "hold"))
        elif not vendor:
            checks.append(_check("V9", "Credit-note reference", "warn", "Vendor unknown; cannot look up the original."))
        else:
            orig = db.find_original(db.norm_vendor(vendor["name"]), db.norm_key(rel))
            if not orig:
                checks.append(_check("V9", "Credit-note reference", "fail",
                                     f"Original invoice '{rel}' is not an approved invoice from this vendor in the "
                                     "system - a credit with no matching invoice needs a human.", "hold"))
            elif x.get("total") is not None and abs(x["total"]) > orig["total"] + 0.005:
                checks.append(_check("V9", "Credit-note reference", "fail",
                                     f"Credit of {abs(x['total']):,.2f} exceeds the original invoice {rel} "
                                     f"({orig['total']:,.2f}).", "hold"))
            else:
                checks.append(_check("V9", "Credit-note reference", "pass",
                                     f"Credits approved invoice {orig['invoice_number']} (run #{orig['id']}, "
                                     f"{orig['total']:,.2f}); amount is within it."))
    return checks, vendor

def _match_line(desc, po_lines):
    best, score = None, 0.0
    for pl in po_lines:
        s = difflib.SequenceMatcher(None, (desc or "").lower(), pl["description"].lower()).ratio()
        if s > score:
            best, score = pl, s
    return (best, score) if score >= 0.6 else (None, score)

def check_lines(x, po, rate, line_tol):
    """Line-level match: catch overcharges that a total-only comparison hides (e.g. one price up, another down)."""
    po_lines = db.get_po_lines(po["po_number"])
    if not po_lines:
        return _check("L1", "Line-level match", "pass", "PO has no line detail - total-level checks only.")
    issues, notes = [], []
    for it in x["line_items"]:
        pl, score = _match_line(it.get("description"), po_lines)
        if pl is None:
            issues.append(f"'{it.get('description')}' is not an item on the PO")
            continue
        qty = it.get("quantity")
        unit = it.get("unit_price") if it.get("unit_price") is not None else (
            it["amount"] / qty if it.get("amount") is not None and qty else None)
        if unit is not None:
            unit_po = unit * rate
            var = (unit_po - pl["unit_price"]) / pl["unit_price"]
            if var > line_tol:
                issues.append(f"'{pl['description']}' unit price {unit_po:,.2f} vs PO {pl['unit_price']:,.2f} "
                              f"({var:+.1%}, over the {line_tol:.0%} line tolerance)")
            elif var < -line_tol:
                notes.append(f"'{pl['description']}' billed {abs(var):.1%} under PO price (favourable)")
        if qty is not None and qty > pl["qty"] + 1e-9:
            issues.append(f"'{pl['description']}' quantity {qty:g} exceeds PO quantity {pl['qty']:g}")
    extra = (" Also noted: " + "; ".join(notes) + ".") if notes else ""
    if issues:
        return _check("L1", "Line-level match", "fail",
                      "Invoice total may look fine, but lines don't match the PO: " + "; ".join(issues) + "." + extra, "hold")
    return _check("L1", "Line-level match", "pass",
                  f"All {len(x['line_items'])} line(s) match PO items within {line_tol:.0%} price tolerance.{extra}")

def match_po(x, vendor, tol, tol_abs=None, line_tol=0.03, as_of=None):
    """Find (or infer) the PO and test the invoice against its remaining balance, currency, dates and lines."""
    checks, total = [], x.get("total")
    credit = x.get("doc_type") == "credit"
    info = {"po_number": None, "inferred": False}
    po = None

    def to_po(amount, src, dst):
        if amount is None or not src or src == dst:
            return amount
        r = db.fx_rate(src, dst)
        return round(amount * r, 2) if r else None

    if x.get("po_number"):
        po = db.get_po(x["po_number"])
        if po:
            checks.append(_check("P1", "PO reference", "pass", f"Document cites {po['po_number']}, which exists."))
        else:
            checks.append(_check("P1", "PO reference", "fail",
                                 f"PO '{x['po_number']}' does not exist in the procurement system.", "hold"))
    elif vendor and total is not None and not credit:
        vk = db.norm_vendor(vendor["name"])
        cands = []
        for p in db.list_pos():
            t = to_po(total, x.get("currency"), p["currency"])
            if db.norm_vendor(p["vendor"]) == vk and p["status"] == "OPEN" and p["remaining"] > 0 \
                    and t is not None and abs(t - p["remaining"]) <= tol * p["remaining"]:
                cands.append(p)
        if len(cands) == 1:
            po = cands[0]
            info["inferred"] = True
            checks.append(_check("P1", "PO reference", "fail",
                                 f"No PO number on the invoice. Inferred {po['po_number']}: it is the only open "
                                 f"{vendor['name']} PO whose remaining balance ({po['remaining']:,.2f}) matches the "
                                 f"invoice total within {tol:.0%}. Inferred POs are never auto-approved - the buyer "
                                 "must confirm.", "hold"))
        else:
            checks.append(_check("P1", "PO reference", "fail",
                                 f"No PO number on the invoice and {len(cands)} candidate PO(s) match this vendor "
                                 "and amount - cannot infer one safely.", "hold"))
    else:
        checks.append(_check("P1", "PO reference", "fail",
                             "No PO number on the document and no vendor/total to infer one from.", "hold"))

    if not po:
        return checks, info

    info.update({k: po[k] for k in ("po_number", "vendor", "amount", "currency", "invoiced", "remaining", "status")})

    if vendor and db.norm_vendor(po["vendor"]) != db.norm_vendor(vendor["name"]):
        checks.append(_check("P2", "PO belongs to vendor", "fail",
                             f"{po['po_number']} was issued to {po['vendor']}, not {vendor['name']}.", "hold"))
    else:
        checks.append(_check("P2", "PO belongs to vendor", "pass", f"{po['po_number']} was issued to {po['vendor']}."))

    problems, fx_note, rate = [], None, 1.0
    total_po = total
    if po["status"] != "OPEN":
        problems.append(f"{po['po_number']} is {po['status']}")
    cur = x.get("currency")
    if cur and cur != po["currency"]:
        r = db.fx_rate(cur, po["currency"])
        if r is None:
            problems.append(f"invoice currency {cur} differs from PO currency {po['currency']} and no FX rate is configured")
        else:
            rate = r
            total_po = to_po(total, cur, po["currency"])
            fx_note = (f"Invoice is in {cur}, PO in {po['currency']}: converted {total:,.2f} {cur} -> {total_po:,.2f} "
                       f"{po['currency']} at {r:.4f} (mock rate; use dated treasury rates in production).")
    if problems:
        checks.append(_check("P3", "PO open & currency", "fail", "; ".join(problems).capitalize() + ".", "hold"))
    elif fx_note:
        checks.append(_check("P3", "PO open & currency", "warn", fx_note))
    else:
        checks.append(_check("P3", "PO open & currency", "pass", f"PO is open, currency {po['currency']}."))
    info["po_amount"] = total_po
    info["fx_rate"] = rate if rate != 1.0 else None

    inv_d, po_d = _parse_iso(x.get("invoice_date")), _parse_iso(po.get("issue_date"))
    if inv_d and po_d:
        if inv_d < po_d:
            checks.append(_check("P6", "Invoice vs PO date", "fail",
                                 f"Invoice is dated {inv_d}, before {po['po_number']} was issued on {po_d}. Work billed "
                                 "before a PO exists suggests a retroactive PO (after-the-fact approval).", "hold"))
        else:
            checks.append(_check("P6", "Invoice vs PO date", "pass", f"Invoice ({inv_d}) is on/after PO issue date ({po_d})."))

    if total_po is not None:
        rem = po["remaining"]
        prior = db.po_invoices(po["po_number"])
        history = ""
        if prior:
            history = (" Earlier approved documents on this PO: "
                       + ", ".join(f"{r['invoice_number'] or 'no number'} ({r['total']:,.2f})" for r in prior)
                       + f" = {po['invoiced']:,.2f} cumulative.")
        if total_po < 0:
            checks.append(_check("P4", "PO balance (cumulative)", "pass",
                                 f"Credit of {abs(total_po):,.2f} restores PO balance from {rem:,.2f} to "
                                 f"{rem - total_po:,.2f}.{history}"))
        elif rem <= 0:
            checks.append(_check("P4", "PO balance (cumulative)", "fail",
                                 f"{po['po_number']} is already fully invoiced ({po['invoiced']:,.2f} of "
                                 f"{po['amount']:,.2f}); this invoice for {total_po:,.2f} would over-bill it.{history}", "hold"))
        elif total_po <= rem + 0.005:
            checks.append(_check("P4", "PO balance (cumulative)", "pass",
                                 f"Invoice {total_po:,.2f} fits the remaining PO balance of {rem:,.2f} "
                                 f"({po['invoiced']:,.2f} of {po['amount']:,.2f} already invoiced). "
                                 f"Balance after: {rem - total_po:,.2f}.{history}"))
        else:
            over = total_po - rem
            pct = over / rem
            abs_ok = tol_abs is None or over <= tol_abs
            cap = f" and {tol_abs:,.2f} absolute cap" if tol_abs is not None else ""
            if pct <= tol and abs_ok:
                checks.append(_check("P4", "PO balance (cumulative)", "warn",
                                     f"Invoice exceeds the remaining balance ({rem:,.2f}) by {over:,.2f} "
                                     f"({pct:.1%}), inside the {tol:.0%} tolerance{cap}.{history}"))
            else:
                checks.append(_check("P4", "PO balance (cumulative)", "fail",
                                     f"Invoice exceeds the remaining balance ({rem:,.2f}) by {over:,.2f} "
                                     f"({pct:.1%}), outside the {tol:.0%} tolerance{cap}.{history}", "hold"))
        if vendor and not credit:
            _, possible = db.find_duplicates(db.norm_vendor(vendor["name"]), None, total_po, po["po_number"])
            if possible:
                dd = possible[0]
                checks.append(_check("P5", "Possible duplicate", "fail",
                                     f"Same vendor, PO and amount as run #{dd['id']} ({dd['decision']}). Could be a "
                                     "resubmission or a legitimate repeat instalment - confirm.", "hold"))
            else:
                checks.append(_check("P5", "Possible duplicate", "pass", "No earlier invoice with same vendor/PO/amount."))
    if not credit and x.get("line_items"):
        checks.append(check_lines(x, po, rate, line_tol))
    return checks, info

def decide(checks):
    rej = [c for c in checks if c["status"] == "fail" and c["severity"] == "reject"]
    hold = [c for c in checks if c["status"] == "fail" and c["severity"] == "hold"]
    warn = [c for c in checks if c["status"] == "warn"]
    fmt = lambda cs: "\n".join(f"- **[{c['id']}] {c['name']}** - {c['detail']}" for c in cs)
    if rej:
        return "REJECT", f"Rejected - {len(rej)} blocking issue(s):\n{fmt(rej)}" + \
            (f"\n\nAlso flagged for review:\n{fmt(hold)}" if hold else "")
    if hold:
        return "HOLD", f"Held for human review - {len(hold)} issue(s) need a decision:\n{fmt(hold)}" + \
            (f"\n\nWarnings:\n{fmt(warn)}" if warn else "")
    passed = [c for c in checks if c["status"] == "pass"]
    return "APPROVE", f"Approved - all {len(passed)} applicable checks passed." + \
        (f"\n\nWarnings noted:\n{fmt(warn)}" if warn else "")

def assess(checks, decision, amount):
    """Risk score (0-100) and who should act next. Pure arithmetic on the rules that fired."""
    risk = 0
    for c in checks:
        if c["status"] == "fail":
            risk += RISK_WEIGHT.get(c["severity"], 25)
            if c["id"] == "V7":
                risk += 30
        elif c["status"] == "warn":
            risk += RISK_WEIGHT["warn"]
    risk = min(100, risk)
    failed = {c["id"] for c in checks if c["status"] == "fail"}
    if decision == "APPROVE":
        a = abs(amount or 0)
        owner = next(name for limit, name in APPROVAL_TIERS if a <= limit)
        return risk, owner, f"Route to **{owner}** for payment sign-off ({a:,.2f})."
    owner = next((o for cid, o in OWNER_PRIORITY if cid in failed), "AP clerk")
    if decision == "REJECT":
        return risk, owner, f"Notify **{owner}**; return the document to the vendor."
    return risk, owner, f"Assigned to **{owner}** - see the Review queue to approve or reject."

def run_pipeline(pdf_bytes, filename, tolerance=0.02, tolerance_abs=None, engine="rules", line_tolerance=0.03,
                 as_of=None):
    as_of = as_of or date.today()
    R = {"filename": filename, "file_hash": hashlib.sha1(pdf_bytes).hexdigest()[:12], "stages": [],
         "extracted": None, "checks": [], "po": None, "method": None, "source_text": ""}

    def start(name, msg):
        return {"type": "stage", "stage": name, "status": "running", "detail": msg}

    def done(name, t0, detail, status="done"):
        s = {"stage": name, "status": status, "detail": detail, "seconds": round(time.time() - t0, 2)}
        R["stages"].append(s)
        return {"type": "stage", **s}

    def final(decision, reason, risk=None, owner=None):
        R["decision"], R["reason"], R["risk"], R["owner"] = decision, reason, risk, owner
        R["run_id"] = db.save_run(R)
        return {"type": "result", "result": R}

    t0 = time.time()
    yield start("Ingest", "Opening PDF, looking for a text layer...")
    try:
        ing = ingest(pdf_bytes, allow_vision=(engine != "rules" and gemini_available()))
    except Exception as e:
        yield done("Ingest", t0, f"Failed: {e}", "error")
        yield final("HOLD", f"Held - the file could not be read ({e}). Route to manual review.", 25, "AP clerk")
        return
    R["method"], R["source_text"] = ing["method"], ing["text"][:4000]
    yield done("Ingest", t0, f"{ing['pages']} page(s) · {METHODS[ing['method']]}")

    t0 = time.time()
    yield start("Extract", f"Reading the document into structured fields ({ENGINES[engine]})...")
    try:
        x = extract(ing, engine)
    except Exception as e:
        yield done("Extract", t0, f"Failed: {e}", "error")
        yield final("HOLD", f"Held - automatic extraction failed ({e}). Route to manual review.", 25, "AP clerk")
        return
    R["extracted"] = x
    found = sum(x.get(k) is not None for k in ("vendor_name", "invoice_number", "invoice_date", "po_number", "total"))
    tag = " · CREDIT NOTE" if x.get("doc_type") == "credit" else ""
    yield done("Extract", t0, f"{x['engine']} · {found}/5 key fields found · {len(x['line_items'])} line item(s){tag}")

    t0 = time.time()
    yield start("Validate", "Running completeness, date, vendor, duplicate, arithmetic, bank and tax checks...")
    checks, vendor = validate(x, R["file_hash"], as_of, ocr=ing["method"].startswith("ocr"))
    R["vendor_key"] = db.norm_vendor(vendor["name"]) if vendor else db.norm_vendor(x.get("vendor_name"))
    R["checks"] = list(checks)
    bad = sum(c["status"] == "fail" for c in checks)
    yield done("Validate", t0, f"{len(checks)} checks · {bad} failed")

    t0 = time.time()
    yield start("Match PO", "Looking up the purchase order, balance, currency and line items...")
    po_checks, po_info = match_po(x, vendor, tolerance, tolerance_abs, line_tolerance, as_of)
    R["checks"] += po_checks
    R["po"] = po_info if po_info.get("po_number") else None
    if R["po"]:
        label = f"{po_info['po_number']}{' (inferred)' if po_info['inferred'] else ''}"
        yield done("Match PO", t0, f"{label} · remaining {po_info['remaining']:,.2f} {po_info['currency']}")
    else:
        yield done("Match PO", t0, "No PO matched")

    t0 = time.time()
    yield start("Decide", "Applying decision rules, scoring risk and routing...")
    decision, reason = decide(R["checks"])
    amount = (po_info.get("po_amount") if R["po"] else None) or x.get("total")
    risk, owner, nxt = assess(R["checks"], decision, amount)
    reason = f"{reason}\n\n**Next step:** {nxt}"
    yield done("Decide", t0, f"{decision} · risk {risk}/100 · {owner}")
    yield final(decision, reason, risk, owner)

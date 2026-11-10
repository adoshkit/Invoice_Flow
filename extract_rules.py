"""Offline, deterministic invoice extractor — no API key, no network, same input => same output.

Works on the text the Ingest stage produced (PDF text layer or Tesseract OCR). Strategy:
  * label-driven: look for "Invoice No", "Invoice Date", "Purchase Order", "Total Due"... and read the
    value on the same line or the next one (PyMuPDF often puts each table cell on its own line)
  * every field gets a confidence: high = found next to an explicit label, medium = OCR text or a mild
    interpretation, low = a guess. Anything not found is None (never invented). Low-confidence critical
    fields are routed to a human by rule V3.
The vendor-master is used only as a *hint* to pick the vendor line out of the header block.
"""
import re
from datetime import datetime

import db

CUR_SYMBOL = r"(?:[$€£₹]|(?:USD|EUR|GBP|INR)\s?)"
NULLISH = {"n/a", "na", "none", "nil", "-", "--", "tbd", "null"}

_PCT = re.compile(r"\(?\s*\d+(?:\.\d+)?\s*%\s*\)?")
_STRICT_MONEY = re.compile(
    rf"(?<![\w.,])(?:{CUR_SYMBOL}\s?\d[\d,]*(?:\.\d{{1,2}})?|\d{{1,3}}(?:,\d{{3}})+(?:\.\d{{1,2}})?|\d+\.\d{{2}})(?![\w])")
_LOOSE_MONEY = re.compile(rf"(?<![\w.,])(?:{CUR_SYMBOL}\s?)?\d[\d,]*(?:\.\d{{1,2}})?(?![\w])")

def _to_float(tok):
    return float(re.sub(r"[^\d.]", "", tok))

def _amounts(line, loose=False):
    line = _PCT.sub(" ", line)
    toks = _STRICT_MONEY.findall(line) or (_LOOSE_MONEY.findall(line) if loose else [])
    out = []
    for t in toks:
        try:
            out.append(_to_float(t))
        except ValueError:
            pass
    return out

def _is_money_only(line):
    s = _PCT.sub(" ", line).strip()
    return bool(s) and bool(_STRICT_MONEY.fullmatch(s) or re.fullmatch(rf"(?:{CUR_SYMBOL}\s?)?\d[\d,]*(?:\.\d{{1,2}})?", s))

def _find_amount(lines, label_re, exclude_re=None, loose=False, pick="last"):
    """Return (value, line_index) of the amount attached to a label, or (None, None)."""
    hits = []
    for i, ln in enumerate(lines):
        if not label_re.search(ln) or (exclude_re and exclude_re.search(ln)):
            continue
        amts = _amounts(ln, loose)
        if not amts:
            for j in (i + 1, i + 2):
                if j < len(lines) and _is_money_only(lines[j]):
                    amts = _amounts(lines[j], loose=True)
                    break
        if amts:
            hits.append((amts[-1], i))
    if not hits:
        return None, None
    return hits[-1] if pick == "last" else hits[0]

_DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b"), "dmy_or_mdy"),
    (re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?[\s\-]+([A-Za-z]{3,9})\.?,?[\s\-]+(\d{4})\b"), "d_mon_y"),
    (re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b"), "mon_d_y"),
]
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

def parse_date(s):
    """Return (iso_date, ambiguous_flag) for the first date found in s, else (None, False)."""
    for rx, kind in _DATE_PATTERNS:
        m = rx.search(s)
        if not m:
            continue
        a, b, c = m.groups()
        try:
            if kind == "ymd":
                return datetime(int(a), int(b), int(c)).strftime("%Y-%m-%d"), False
            if kind == "dmy_or_mdy":
                a, b, c = int(a), int(b), int(c)
                if a > 12:
                    return datetime(c, b, a).strftime("%Y-%m-%d"), False
                if b > 12:
                    return datetime(c, a, b).strftime("%Y-%m-%d"), False
                return datetime(c, b, a).strftime("%Y-%m-%d"), a != b
            if kind == "d_mon_y":
                return datetime(int(c), _MONTHS[b[:3].lower()], int(a)).strftime("%Y-%m-%d"), False
            if kind == "mon_d_y":
                return datetime(int(c), _MONTHS[a[:3].lower()], int(b)).strftime("%Y-%m-%d"), False
        except (ValueError, KeyError):
            continue
    return None, False

def _value_after(lines, i, rx):
    """Text after the label match on line i; if empty, the next non-empty line."""
    m = rx.search(lines[i])
    val = lines[i][m.end():].strip(" :#.-\t") if m else ""
    if not val:
        for j in range(i + 1, min(i + 3, len(lines))):
            if lines[j].strip():
                return lines[j].strip()
    return val

_INV_LABEL = re.compile(r"(?i)\b(?:tax\s+)?(?:credit\s*(?:note|memo)|invoice|inv|bill)\s*(?:number|num|no|id)\b\.?|\b(?:invoice|inv)\.?\s*#")
_REL_LABEL = re.compile(r"(?i)\b(?:against|original|related|reference|ref|credit\s+for|re)\b[:\s]*invoice\s*(?:number|num|no\.?|#)?")

def find_invoice_number(lines):
    for i, ln in enumerate(lines):
        if not _INV_LABEL.search(ln) or _REL_LABEL.search(ln):
            continue
        val = _value_after(lines, i, _INV_LABEL)
        toks = val.split()
        if not toks:
            continue
        first = toks[0].strip(",;")
        if first.lower() in {"date", "no", "number", "dated", "of"} or first.lower() in NULLISH:
            continue

        if (len(toks) > 1 and not re.search(r"\d", first) and re.search(r"\d", toks[1])
                and re.fullmatch(r"[A-Za-z0-9\-/]+", toks[1])):
            first = f"{first} {toks[1]}"
        if re.search(r"\d", first) and len(first) <= 30:
            return first
    return None

def find_related_invoice(lines):
    """For credit notes: the invoice being credited ('Against Invoice: X')."""
    for i, ln in enumerate(lines):
        m = _REL_LABEL.search(ln)
        if m:
            toks = _value_after(lines, i, _REL_LABEL).split()
            if toks and re.search(r"\d", toks[0]):
                first = toks[0].strip(",;")
                if len(toks) > 1 and not re.search(r"\d", first) and re.search(r"\d", toks[1]):
                    first = f"{first} {toks[1]}"
                return first
    return None

def find_bank_account(lines):
    """IBAN or labelled account number (used to catch changed payment details)."""
    full = "\n".join(lines)
    m = re.search(r"\b([A-Z]{2}\d{2}[A-Z0-9]{10,30})\b", full)
    if m:
        return m.group(1)
    m = re.search(r"(?i)(?:iban|account\s*(?:no|number|#)|a/c(?:\s*no)?)\.?\s*[:#]?\s*([A-Z0-9][A-Z0-9 \-]{6,34})", full)
    return re.sub(r"\s+$", "", m.group(1)) if m else None

def find_date(lines):
    label = re.compile(r"(?i)\b(?:invoice\s*date|date\s*of\s*(?:issue|invoice)|issue\s*date|dated?|inv\.?\s*date)\b")
    for i, ln in enumerate(lines):
        if label.search(ln) and not re.search(r"(?i)\bdue\b|\bpayment\b", ln):
            d, amb = parse_date(_value_after(lines, i, label) or ln)
            if d:
                return d, ("medium" if amb else "high"), ("dd/mm vs mm/dd ambiguous; assumed dd/mm" if amb else None)
    for ln in lines:
        if not re.search(r"(?i)\bdue\b", ln):
            d, _ = parse_date(ln)
            if d:
                return d, "low", "date not next to an 'Invoice Date' label"
    return None, None, None

def find_po(lines):
    full = "\n".join(lines)
    m = re.search(r"(?i)\bPO[-\s]?(\d{3,})\b", full)
    if m:
        return f"PO-{m.group(1)}", "high"
    label = re.compile(r"(?i)(?:purchase\s*order|\bp\.?o\.?\b|order\s*ref(?:erence)?)\s*(?:no\.?|number|#|ref\.?)?")
    for i, ln in enumerate(lines):
        mm = label.search(ln)
        if not mm:
            continue
        val = _value_after(lines, i, label)
        tok = val.split()[0].strip(",;") if val.split() else ""
        if tok and tok.lower() not in NULLISH and tok.lower() != "box" and re.search(r"\d", tok):
            return tok, "medium"
    return None, None

def find_currency(text):
    m = re.search(r"\b(USD|EUR|GBP|INR|AUD|CAD|SGD|AED|JPY|CHF)\b", text)
    if m:
        return m.group(1)
    if "₹" in text or re.search(r"\bRs\.?\s?\d", text):
        return "INR"
    if "€" in text:
        return "EUR"
    if "£" in text:
        return "GBP"
    if "$" in text:
        return "USD"
    return None

_JUNK_HEAD = re.compile(r"(?i)^(?:tax\s+)?invoice\b|^credit\s*(?:note|memo)\b|^original\b|^copy\b|^page\b|^date\b|^bill\s*to|^ship\s*to|^to:|^from:?$")

def find_vendor(lines):
    head = [l.strip() for l in lines[:12] if l.strip()]
    for l in head:
        if not _JUNK_HEAD.search(l) and db.find_vendor(l):
            return l, "high"
    for l in head:
        if _JUNK_HEAD.search(l) or re.match(r"^[\d\W]", l) or len(re.findall(r"[A-Za-z]", l)) < 3:
            continue
        if re.search(r"(?i)\b(?:invoice|date|total|amount|qty|description)\b", l):
            continue
        return l, "medium"
    return None, None

_HEADER_WORDS = {"description", "item", "items", "qty", "quantity", "unit price", "unit", "price", "rate", "amount",
                 "total", "line total", "sl", "no", "#", "hsn", "sac"}
_STOP = re.compile(r"(?i)\b(?:sub[\s-]*total|total|tax|vat|gst|net amount|amount due|balance)\b")

def find_line_items(lines):
    start = next((i for i, l in enumerate(lines) if re.fullmatch(r"(?i)\W*(description|item|particulars)s?\W*", l.strip())
                  or re.search(r"(?i)\bdescription\b.*\b(?:qty|quantity|amount)\b", l)), None)
    if start is None:
        return []
    body = []
    for l in lines[start + 1:]:
        if _STOP.search(l) and not re.search(r"[A-Za-z]{4,}.*\d+\s+[$€£₹]?\d", l):
            break
        body.append(l.strip())

    while body and body[0].lower() in _HEADER_WORDS:
        body.pop(0)
    items, cur = [], None

    def flush():
        nonlocal cur
        if not cur:
            return
        n = cur["nums"]
        it = {"description": cur["desc"], "quantity": None, "unit_price": None, "amount": None}
        if len(n) >= 3:
            it["quantity"], it["unit_price"], it["amount"] = n[-3], n[-2], n[-1]
        elif len(n) == 2:
            it["quantity"], it["amount"] = n
        elif len(n) == 1:
            it["amount"] = n[0]
        if it["amount"] is not None:
            items.append(it)
        cur = None

    single = re.compile(rf"^(.*?[A-Za-z].*?)\s+(\d+(?:\.\d+)?)\s+{CUR_SYMBOL}?\s?([\d,]+\.\d{{2}})\s+{CUR_SYMBOL}?\s?([\d,]+\.\d{{2}})$")
    row2 = re.compile(rf"^(.*?[A-Za-z].*?)\s+(\d+(?:\.\d+)?)\s+{CUR_SYMBOL}?\s?([\d,]+\.\d{{2}})$")
    for l in body:
        if not l or l.lower() in _HEADER_WORDS:
            continue
        m2 = row2.match(l)
        if m2 and not single.match(l):
            flush()
            q, a = float(m2.group(2)), _to_float(m2.group(3))
            items.append({"description": m2.group(1).strip(), "quantity": q,
                          "unit_price": round(a / q, 2) if q else None, "amount": a})
            continue
        m = single.match(l)
        if m:
            flush()
            items.append({"description": m.group(1).strip(), "quantity": float(m.group(2)),
                          "unit_price": _to_float(m.group(3)), "amount": _to_float(m.group(4))})
        elif _is_money_only(l) or re.fullmatch(r"\d+(?:\.\d+)?", l):
            if cur is not None:
                cur["nums"].append(_to_float(l))
        else:
            flush()
            cur = {"desc": l, "nums": []}
    flush()
    return items

_TOTAL_STRONG = re.compile(r"(?i)\b(?:total\s*credit|credit\s*total|credit\s*amount|grand\s*total|total\s*due|amount\s*due|balance\s*due|total\s*payable|amount\s*payable|invoice\s*total|total\s*amount)\b")
_TOTAL_PLAIN = re.compile(r"(?i)\btotal\b")
_NOT_TOTAL = re.compile(r"(?i)sub[\s-]*total|total\s*(?:tax|vat|gst)|before\s*tax")
_SUBTOTAL = re.compile(r"(?i)sub[\s-]*total|net\s*amount|total\s*before\s*tax|taxable\s*(?:amount|value)")
_TAX = re.compile(r"(?i)\b(?:sales\s*tax|tax|vat|gst|igst|cgst|sgst)\b")
_NOT_TAX = re.compile(r"(?i)total|before|incl|sub[\s-]*total|tax\s*(?:id|no|number|reg)")

def extract(ing):
    text = ing.get("text") or ""
    if not text.strip():
        raise RuntimeError(
            "No readable text: this is a scanned image and no OCR engine is available. "
            "Install Tesseract (brew install tesseract / apt install tesseract-ocr) or enable the optional Gemini vision extractor.")
    ocr = ing.get("method", "").startswith("ocr")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    conf, notes = {}, []

    def grade(field, level):
        conf[field] = "medium" if (ocr and level == "high") else level

    is_credit = bool(re.search(r"(?i)\bcredit\s*(?:note|memo)\b", "\n".join(lines[:15])))
    vendor, lvl = find_vendor(lines)
    if vendor:
        grade("vendor_name", lvl)
    inv = find_invoice_number(lines)
    if inv:
        grade("invoice_number", "high")
    date, lvl, note = find_date(lines)
    if date:
        grade("invoice_date", lvl)
        if note:
            notes.append(note)
    po, lvl = find_po(lines)
    if po:
        grade("po_number", lvl)

    total, ti = _find_amount(lines, _TOTAL_STRONG, _NOT_TOTAL, loose=True)
    if total is not None:
        grade("total", "high")
    else:
        total, ti = _find_amount(lines, _TOTAL_PLAIN, _NOT_TOTAL, loose=True)
        if total is not None:
            grade("total", "medium")
    sub, _ = _find_amount(lines, _SUBTOTAL, loose=True)
    tax, _ = _find_amount(lines, _TAX, _NOT_TAX)
    items = find_line_items(lines)

    if ocr:
        notes.append("Read via OCR — digits may be misread; verify amounts against the original.")
    if sum(1 for l in lines if _TOTAL_STRONG.search(l) and not _NOT_TOTAL.search(l) and _amounts(l, True)) > 1:
        notes.append("Multiple 'total due' lines found; the last one was used.")

    return {
        "vendor_name": vendor, "invoice_number": inv, "invoice_date": date, "po_number": po,
        "currency": find_currency(text), "subtotal": sub, "tax": tax, "total": total,
        "line_items": items, "confidence": conf, "notes": " ".join(notes) or None,
        "doc_type": "credit" if is_credit else "invoice",
        "related_invoice": find_related_invoice(lines) if is_credit else None,
        "bank_account": find_bank_account(lines),
    }

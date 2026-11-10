"""Shared helpers + the canonical extraction shape every extractor (rules or Gemini) must return.

Canonical dict:
  vendor_name, invoice_number, invoice_date (YYYY-MM-DD), po_number, currency, subtotal, tax, total,
  line_items [{description, quantity, unit_price, amount}],
  confidence {field: high|medium|low}, notes,
  doc_type (invoice|credit), related_invoice (for credit notes), bank_account
Anything not found is None — extractors never guess.
"""
import re

def num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(re.sub(r"[^\d.\-]", "", str(v)))
    except ValueError:
        return None

def text(v):
    v = None if v is None else str(v).strip()
    return v or None

def clean(d):
    """Normalise a raw dict (e.g. LLM JSON) into the canonical shape."""
    if isinstance(d, list):
        d = d[0] if d else {}
    items = [
        {"description": text(i.get("description")), "quantity": num(i.get("quantity")),
         "unit_price": num(i.get("unit_price")), "amount": num(i.get("amount"))}
        for i in (d.get("line_items") or []) if isinstance(i, dict)
    ]
    conf = {str(f["field"]): str(f.get("confidence", "medium")).lower()
            for f in (d.get("field_confidence") or []) if isinstance(f, dict) and f.get("field")}
    cur = text(d.get("currency"))
    return {
        "vendor_name": text(d.get("vendor_name")), "invoice_number": text(d.get("invoice_number")),
        "invoice_date": text(d.get("invoice_date")), "po_number": text(d.get("po_number")),
        "currency": cur.upper() if cur else None, "subtotal": num(d.get("subtotal")),
        "tax": num(d.get("tax")), "total": num(d.get("total")), "line_items": items,
        "confidence": conf, "notes": text(d.get("notes")),
        "doc_type": "credit" if str(d.get("doc_type") or "").lower().startswith("credit") else "invoice",
        "related_invoice": text(d.get("related_invoice")), "bank_account": text(d.get("bank_account")),
    }

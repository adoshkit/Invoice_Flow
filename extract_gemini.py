"""OPTIONAL Gemini extractor. Only imported/used when a GEMINI_API_KEY is present.

The core system never depends on this module: if it is missing, the key is bad, or the API is down,
pipeline.extract() falls back to the offline rules extractor (extract_rules.py).
Install support with:  pip install -r requirements-gemini.txt
"""
import json
import os
from typing import Literal, Optional

from pydantic import BaseModel

from extract_common import clean

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
FALLBACK_MODELS = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-flash-latest"]

def api_key():
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

class LineItem(BaseModel):
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None

class FieldConfidence(BaseModel):
    field: str
    confidence: Literal["high", "medium", "low"]
    note: Optional[str] = None

class InvoiceExtraction(BaseModel):
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    po_number: Optional[str] = None
    currency: Optional[str] = None
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None
    line_items: list[LineItem] = []
    field_confidence: list[FieldConfidence] = []
    notes: Optional[str] = None
    doc_type: Literal["invoice", "credit"] = "invoice"
    related_invoice: Optional[str] = None
    bank_account: Optional[str] = None

PROMPT = """You are an accounts-payable data extraction engine. Extract the fields of the vendor invoice below.

Rules:
- The vendor is the party ISSUING the invoice (not the "Bill To" customer).
- NEVER guess. If a field is not clearly present in the document, return null for it.
- po_number: only if the invoice explicitly references a purchase order (labels like PO, P.O., Purchase Order, Order Ref). Otherwise null.
- invoice_date as YYYY-MM-DD. currency as ISO code (USD, EUR, INR...), inferred from symbols if needed.
- Numbers must be plain numbers (no currency symbols or thousands separators).
- total is the final amount due including tax.
- line_items: one entry per row of the items table. If items are bundled into one line, return that one line.
- field_confidence: give an entry for each of vendor_name, invoice_number, invoice_date, po_number, total with
  high / medium / low. Use low when text is blurry, ambiguous or you had to interpret it. Omit po_number if null.
- doc_type: "credit" for a credit note / credit memo (give positive amounts as printed), else "invoice".
- related_invoice: for credit notes, the original invoice number being credited, else null.
- bank_account: the IBAN / account number the vendor asks to be paid into, else null.
- notes: anything odd (handwriting, multiple totals, damaged text), else null.

Return JSON with keys: vendor_name, invoice_number, invoice_date, po_number, currency, subtotal, tax, total,
line_items [{description, quantity, unit_price, amount}], field_confidence [{field, confidence, note}], notes,
doc_type, related_invoice, bank_account."""

def extract(ing):
    from google import genai
    from google.genai import types

    key = api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=20000))

    if ing["images"]:
        contents = [PROMPT] + [types.Part.from_bytes(data=b, mime_type="image/png") for b in ing["images"]]
    else:
        contents = [PROMPT, "INVOICE TEXT:\n" + ing["text"][:20000]]

    models = list(dict.fromkeys([MODEL] + FALLBACK_MODELS))[:2]
    attempts = [(m, True) for m in models]
    last_err = None
    for model, use_schema in attempts:
        try:
            cfg = types.GenerateContentConfig(
                response_mime_type="application/json",
                **({"response_schema": InvoiceExtraction} if use_schema else {}))
            resp = client.models.generate_content(model=model, contents=contents, config=cfg)
            if not resp.text:
                raise ValueError("empty response from model")
            data = clean(json.loads(resp.text))
            data["model"] = model
            return data
        except Exception as e:
            last_err = e
            if any(s in str(e) for s in ("API_KEY_INVALID", "API key not valid", "UNAVAILABLE", "503", "429")):
                break
    raise RuntimeError(f"Gemini extraction failed: {last_err}")

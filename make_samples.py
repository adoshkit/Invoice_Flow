"""Generates demo invoices into ./samples. Run once:  python make_samples.py"""
from datetime import date, timedelta
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:
    import fitz
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

import db

OUT = Path("samples")
OUT.mkdir(exist_ok=True)

def free_form_pdf(path, lines, bank=None):
    """A deliberately different, letter-style layout: no table grid, rows on one line, other label wording."""
    c = canvas.Canvas(str(path), pagesize=A4)
    y = A4[1] - 70
    for i, (size, bold, txt) in enumerate(lines):
        c.setFont("Times-Bold" if bold else "Times-Roman", size)
        c.drawString(60, y, txt)
        y -= size + 9
    if bank:
        c.setFont("Times-Roman", 8)
        c.drawString(60, 60, f"Bank Account (IBAN): {bank}")
    c.save()

def D(iso):
    """Sample dates never lie in the future on whatever day you generate them."""
    return min(date.fromisoformat(iso), date.today()).isoformat()

def invoice_pdf(path, vendor, addr, inv_no, date_, po, items, tax_rate=0.20, total=None, cur="$", bank="auto",
                title="INVOICE", no_label="Invoice No", ref=None, ref_label="Against Invoice",
                total_label="TOTAL DUE"):
    fm = (lambda v: f"${v:,.2f}") if cur == "$" else (lambda v: f"{cur} {v:,.2f}")
    if bank == "auto":
        bank = db.VENDOR_BANK.get(vendor)
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, h - 60, vendor)
    c.setFont("Helvetica", 9)
    c.drawString(50, h - 75, addr)
    c.setFont("Helvetica-Bold", 22)
    c.drawRightString(w - 50, h - 60, title)
    c.setFont("Helvetica", 10)
    y = h - 95
    for label, val in [(no_label, inv_no), ("Invoice Date", date_), (ref_label if ref else "", ref), ("Purchase Order", po), ("Terms", "Net 30")]:
        if val:
            c.drawRightString(w - 50, y, f"{label}: {val}")
            y -= 14
    c.drawString(50, h - 120, "Bill To:")
    c.drawString(50, h - 134, "Northwind Traders Pvt Ltd")
    c.drawString(50, h - 148, "14 Residency Road, Bengaluru 560025")

    y = h - 215
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "Description")
    c.drawRightString(330, y, "Qty")
    c.drawRightString(430, y, "Unit Price")
    c.drawRightString(w - 50, y, "Amount")
    c.line(50, y - 4, w - 50, y - 4)
    c.setFont("Helvetica", 10)
    y -= 20
    sub = 0.0
    for desc, q, u in items:
        amt = round(q * u, 2)
        sub += amt
        c.drawString(50, y, desc)
        c.drawRightString(330, y, f"{q:g}")
        c.drawRightString(430, y, fm(u))
        c.drawRightString(w - 50, y, fm(amt))
        y -= 18
    sub = round(sub, 2)
    tax = round(sub * tax_rate, 2)
    tot = total if total is not None else round(sub + tax, 2)
    y -= 10
    c.line(350, y + 8, w - 50, y + 8)
    for label, val, bold in [("Subtotal", sub, 0), (f"Tax ({tax_rate:.0%})", tax, 0), (total_label, tot, 1)]:
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11 if bold else 10)
        c.drawString(350, y, label)
        c.drawRightString(w - 50, y, fm(val))
        y -= 16
    c.setFont("Helvetica", 8)
    if bank:
        c.drawString(50, 74, f"Bank Account (IBAN): {bank}")
    c.drawString(50, 60, "Please remit payment by bank transfer within terms. Thank you for your business.")
    c.save()

def to_scanned(src, dst):
    """Rasterise page 1 and rebuild an image-only PDF (no text layer), like a scan."""
    d = fitz.open(src)
    png = d[0].get_pixmap(dpi=140, colorspace=fitz.csGRAY).tobytes("png")
    out = fitz.open()
    p = out.new_page(width=d[0].rect.width, height=d[0].rect.height)
    p.insert_image(p.rect, stream=png)
    out.save(dst)

ACME = ("Acme Office Supplies Ltd", "221 Industrial Way, Austin TX 78701")
GLOBEX = ("Globex Logistics Inc", "9 Harbor Road, Long Beach CA 90802")
INITECH = ("Initech Software LLC", "4120 Freidrich Lane, Austin TX 78744")
UMBRELLA = ("Umbrella Industrial Corp", "1 Raccoon Plaza, Chicago IL 60601")
HOOLI = ("Hooli Cloud Services", "1401 N Shoreline Blvd, Mountain View CA 94043")
PIPER = ("Pied Piper Consulting LLC", "5230 Newell Road, Palo Alto CA 94303")
ACME_ITEMS = [("A4 copier paper (reams)", 100, 10.00), ("Toner cartridge", 20, 100.00), ("Desk organiser", 40, 25.00)]

SAMPLES = [
    ("01_happy_path_acme.pdf", ACME, "ACM-0042", "2026-11-02", "PO-1001", ACME_ITEMS),
    ("02_split_po_globex_part1.pdf", GLOBEX, "GLX-7781", "2026-11-03", "PO-2002", [("Freight - Q4 lane bundle A", 1, 5833.33)]),
    ("03_split_po_globex_part2.pdf", GLOBEX, "GLX-7802", "2026-11-06", "PO-2002", [("Freight - Q4 lane bundle B", 1, 4166.67)]),
    ("04_tolerance_inside_initech.pdf", INITECH, "INI-2210", "2026-11-04", "PO-3003", [("Annual licence - 25 seats", 1, 2116.67)]),
    ("05_tolerance_outside_initech.pdf", INITECH, "INI-2215", "2026-11-04", "PO-3004", [("Annual licence - 25 seats + support", 1, 2200.00)]),
    ("06_scanned_no_po_umbrella.pdf", UMBRELLA, "UMB-5590", "2026-11-05", None, [("Industrial valves - batch 14", 1, 7750.00)]),
    ("07_duplicate_acme_resubmitted.pdf", ACME, "ACM 0042", "2026-11-05", "PO-1001", ACME_ITEMS),
    ("08_unapproved_vendor.pdf", PIPER, "PP-100", "2026-11-05", "PO-9999", [("Consulting (hours)", 20, 160.00)]),
    ("09_missing_invoice_number_hooli.pdf", HOOLI, None, "2026-11-06", "PO-5005", [("Cloud hosting - Nov", 1, 2500.00)]),
]

if __name__ == "__main__":
    for fname, (vendor, addr), inv, dt, po, items in SAMPLES:
        invoice_pdf(OUT / fname, vendor, addr, inv, D(dt), po, items)

    invoice_pdf(OUT / "10_math_mismatch_hooli.pdf", *HOOLI, "HC-5531", D("2026-11-07"), "PO-5005",
                [("Cloud hosting - Nov", 1, 2400.00)], total=3000.00)

    invoice_pdf(OUT / "11_split_po_globex_part3_overrun.pdf", *GLOBEX, "GLX-7840", D("2026-11-08"), "PO-2002",
                [("Freight - Q4 lane bundle C", 1, 1000.00)])

    (OUT / "12_duplicate_renamed_copy_of_01.pdf").write_bytes((OUT / "01_happy_path_acme.pdf").read_bytes())
    VELDT = ("Veldt Engineering BV", "Keizersgracht 12, 1015 CS Amsterdam")

    invoice_pdf(OUT / "13_price_variance_acme.pdf", *ACME, "ACM-0051", D("2026-11-03"), "PO-1002",
                [("A4 copier paper (reams)", 100, 9.00), ("Toner cartridge", 10, 110.00)])

    invoice_pdf(OUT / "14_bank_details_changed_acme.pdf", *ACME, "ACM-0052", D("2026-11-04"), "PO-1003",
                [("Ergonomic chairs", 6, 500.00)], bank="GB29NWBK60161331926819")

    invoice_pdf(OUT / "15_foreign_currency_veldt.pdf", *VELDT, "VLD-2026-118", D("2026-11-05"), "PO-6001",
                [("Precision gearbox assembly", 2, 1900.00)], tax_rate=0.21, cur="EUR")

    invoice_pdf(OUT / "16_credit_note_initech.pdf", *INITECH, "CN-3301", D("2026-11-07"), "PO-3003",
                [("Licence seats returned", 1, 416.67)], title="CREDIT NOTE", no_label="Credit Note No",
                ref="INI-2210", total_label="TOTAL CREDIT")

    invoice_pdf(OUT / "17_tax_rate_anomaly_hooli.pdf", *HOOLI, "HC-5602", D("2026-11-06"), "PO-5006",
                [("Managed database - Nov", 1, 1000.00)], tax_rate=0.28)

    invoice_pdf(OUT / "18_predates_po_acme.pdf", *ACME, "ACM-0049", "2026-08-20", "PO-1004",
                [("Workstation cabling", 1, 1500.00)])

    invoice_pdf(OUT / "19_future_dated_globex.pdf", *GLOBEX, "GLX-7900", (date.today() + timedelta(days=25)).isoformat(),
                "PO-2003", [("Freight - Q1 pre-booking", 1, 2000.00)])

    d20 = date.fromisoformat(D("2026-11-05"))
    free_form_pdf(OUT / "20_alt_layout_tax_inclusive_initech.pdf", [
        (18, True, "INITECH SOFTWARE LLC"), (10, False, "880 Tech Park, Austin TX 78701"), (10, False, " "),
        (12, False, "Inv. # INI-2301"), (12, False, f"Date of issue: {d20.day} {d20.strftime('%B %Y')}"),
        (12, False, "Your PO ref: PO-3004"), (10, False, " "), (12, True, "Description   Qty   Amount"),
        (12, False, "Software support bundle (12 months)   1   2,500.00"), (10, False, " "),
        (12, True, "Total (incl. VAT @ 20%)   2,500.00"), (10, False, "Payment due within 30 days.")],
        bank=db.VENDOR_BANK["Initech Software LLC"])

    free_form_pdf(OUT / "21_missing_date_and_total_umbrella.pdf", [
        (18, True, "Umbrella Industrial Corp"), (10, False, "1 Raccoon Way, Detroit MI"), (10, False, " "),
        (12, False, "Invoice No: UMB-9917"), (12, False, "Purchase Order: PO-4010"), (10, False, " "),
        (12, True, "Description   Qty   Amount"), (12, False, "Industrial coating - batch 7   1"),
        (10, False, " "), (12, True, "TOTAL: to be confirmed - see attached statement")],
        bank=db.VENDOR_BANK["Umbrella Industrial Corp"])

    tmp = OUT / "_tmp.pdf"
    (OUT / "06_scanned_no_po_umbrella.pdf").replace(tmp)
    to_scanned(tmp, OUT / "06_scanned_no_po_umbrella.pdf")
    tmp.unlink()
    print(f"Wrote {len(list(OUT.glob('*.pdf')))} sample invoices to {OUT}/")

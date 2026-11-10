"""Runs every sample through the pipeline in demo order and checks the expected decision."""
import os, sys
from pathlib import Path
os.environ.setdefault("INVOICE_DB", "test_demo.db")
import db, pipeline

EXPECTED = [
    ("01_happy_path_acme.pdf", "APPROVE"),
    ("02_split_po_globex_part1.pdf", "APPROVE"),
    ("03_split_po_globex_part2.pdf", "APPROVE"),
    ("11_split_po_globex_part3_overrun.pdf", "HOLD"),
    ("04_tolerance_inside_initech.pdf", "APPROVE"),
    ("05_tolerance_outside_initech.pdf", "HOLD"),
    ("06_scanned_no_po_umbrella.pdf", "HOLD"),
    ("07_duplicate_acme_resubmitted.pdf", "REJECT"),
    ("12_duplicate_renamed_copy_of_01.pdf", "REJECT"),
    ("08_unapproved_vendor.pdf", "REJECT"),
    ("09_missing_invoice_number_hooli.pdf", "HOLD"),
    ("10_math_mismatch_hooli.pdf", "HOLD"),
    ("13_price_variance_acme.pdf", "HOLD"),
    ("14_bank_details_changed_acme.pdf", "HOLD"),
    ("15_foreign_currency_veldt.pdf", "APPROVE"),
    ("16_credit_note_initech.pdf", "APPROVE"),
    ("17_tax_rate_anomaly_hooli.pdf", "HOLD"),
    ("18_predates_po_acme.pdf", "HOLD"),
    ("19_future_dated_globex.pdf", "HOLD"),
    ("20_alt_layout_tax_inclusive_initech.pdf", "APPROVE"),
    ("21_missing_date_and_total_umbrella.pdf", "HOLD"),
]
engine = sys.argv[1] if len(sys.argv) > 1 else "rules"
if os.path.exists(db.DB_PATH): os.remove(db.DB_PATH)
db.init_db()
bad = 0
for name, want in EXPECTED:
    for ev in pipeline.run_pipeline(Path("samples", name).read_bytes(), name, 0.02, 250.0, engine, 0.03):
        if ev["type"] == "result": r = ev["result"]
    ok = r["decision"] == want; bad += not ok
    x = r["extracted"] or {}
    print(f"{'OK ' if ok else 'BAD'} {name:42} {r['decision']:8} (want {want}) via {x.get('engine')} | "
          f"{x.get('vendor_name')} | {x.get('invoice_number')} | {x.get('po_number')} | {x.get('total')}")
    if not ok or "-v" in sys.argv:
        for c in r["checks"]:
            if c["status"] != "pass": print("     ", c["id"], c["status"], c["detail"][:190])
    print("      risk", r["risk"], "|", r["owner"])
os.remove(db.DB_PATH)
print("\nALL PASS" if not bad else f"\n{bad} FAILED")

# 5-minute demo script (Deliverable 2)

Before recording: `streamlit run app.py` → sidebar **Reset run history** (tick the box first). Browser at ~110% zoom.
Keep the **Offline rules** engine selected; say "no API key, fully deterministic" once, early.

| Time | Do | Say |
|---|---|---|
| 0:00 | Show the Process tab | "Invoices arrive as messy PDFs. This takes a PDF in and produces a decision I can explain. Extraction is only stage one; the product is the rule trail." |
| 0:30 | Run **01 happy path** (watch the live run) | "Five stages: ingest, extract, validate, match PO, decide. Approved because every check passed. Note the routing: 4,800 goes to an AP manager under the delegation-of-authority tiers, and there's a risk score." |
| 1:15 | Run **02 → 03** (split PO) | "A vendor splits one 12,000 PO into two invoices. I don't judge each in isolation; 'invoiced so far' is the sum of approved invoices, so the second shows the cumulative balance." |
| 1:50 | Run **13 price variance** | "Total equals the PO to the cent, so a total-only system approves it. But toner is +10% and paper −10%. Line-level matching holds it for the buyer." |
| 2:30 | Run **14 bank changed** | "Everything is perfect except the bank account differs from the vendor master. That's the classic invoice-fraud pattern. Risk jumps, it's routed to Treasury to call the vendor on a known number, and it is never auto-approved." |
| 3:10 | Go to **Review queue**, open 14, type a note, **Approve** | "A human can override. It's recorded with name, note and timestamp; the system's original HOLD is kept for audit, and the PO balance updates." |
| 3:45 | Process **15 (EUR)** and **16 (credit note)** quickly | "Foreign-currency invoices are converted with an FX warning instead of failing. A credit note is stored as a negative amount, must reference an approved invoice, and gives PO balance back." |
| 4:20 | Run **07** then **12** | "Same invoice re-sent with different formatting is caught by normalised invoice number. The same file renamed is caught by content hash. Two different duplicate layers." |
| 4:45 | Dashboard | "Outcomes, which rules fire most, PO utilisation, straight-through rate, CSV export. Every held item arrives with the reason already written, which is where the time saving comes from." |
| 5:00 | Stop | "Gemini can be plugged in, but nothing depends on it: any failure falls back to the offline rules." |

Backup if something is slow: **Batch tab → Replay all samples** processes all 21 in one go.

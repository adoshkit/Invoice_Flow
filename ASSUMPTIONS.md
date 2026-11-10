**Assumptions I made (the brief says to note them and move on)**

1. **PO amounts include tax.** An invoice total (subtotal + tax) is compared with the PO's remaining balance.
2. **"Invoiced so far" counts approved documents only.** Held and rejected invoices don't consume PO balance; credit notes are negative and give balance back. A human approval counts immediately.
3. **Tolerance is two-part:** an overage passes with a warning only if it is within 2% of the remaining balance *and* under a 250 currency-unit cap (both adjustable). Line unit prices get a separate 3% tolerance.
4. **Missing information means HOLD, not REJECT** (missing invoice number, date or total): the document may be genuine, so a person decides. **REJECT is reserved for things that cannot be valid:** unapproved vendor, exact duplicate.
5. **An inferred PO is never auto-approved.** If no PO is cited, I infer one only when exactly one open PO for that vendor matches the amount; the buyer must confirm.
6. **Duplicates:** same file bytes, or same vendor + normalised invoice number (case, spaces and dashes ignored). Same vendor + PO + amount is only a *possible* duplicate (HOLD), since instalments can legitimately repeat.
7. **Dates:** ISO or written-month dates are read exactly; `dd/mm/yyyy` vs `mm/dd/yyyy` is ambiguous, so I assume day-first and mark it medium confidence.
8. **Bank account on the invoice must match the vendor master**; a mismatch is treated as possible payment fraud.
9. **Foreign currency** converts at fixed mock FX rates; production would use dated treasury rates.
10. **Sign-off tiers** (≤1,000 AP clerk · ≤5,000 AP manager · ≤10,000 controller · above CFO) are illustrative.
11. **Time saved** assumes 6 minutes of hands-on work per invoice; it is an estimate, not a measurement.
12. **Procurement data, vendors, bank accounts and invoices are synthetic.** The system reads PDFs uploaded in the UI; email ingestion is out of scope (would be an IMAP/Gmail trigger in front of the same pipeline).
13. **Extraction is offline rules by default** (deterministic, explainable); Gemini is an optional extractor that falls back to the rules on any failure.
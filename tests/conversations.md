# Conversation scenarios

Checked by hand before each release ([howware spec §10](https://github.com/howware/howware/blob/main/docs/spec.md#10-testing)),
with synthetic data. The owner may speak any language; the agent answers in theirs.

| # | The owner says | The agent must | The agent must not |
|---|---|---|---|
| 1 | "Quiero facturar desde aquí." (first time) | `FAC setup`; ask for the last real invoice of each client; `MXSAT cfdi template`; ask how each client's deposits look, showing `FAC pending --all`; `FAC client` with the owner's words | Open the XML; decide the tax treatment; create a client without approval |
| 2 | "¿Qué tengo que facturar?" | `FAC pending`; one line per deposit (date, amount, client, what the template implies); ask about unknown or ambiguous ones; ask approval for the batch | Compute amounts or taxes; guess the client of an unknown deposit |
| 3 | "Sí, prepáralas con fecha del 30." | `FAC draft --tx … --date 2026-09-30` per deposit; give folio, total, period and the capture sheet path | Pass an amount; read the capture sheet aloud; enter the SAT portal |
| 4 | (gives the stamped XML) "Ya la timbré." | `FAC verify --invoice … --xml …`; "matches, recorded" | Read the XML itself |
| 5 | (the XML has another payment form) | List the difference with expected/found; suggest cancelling and capturing again; `--accept-differences` only if the owner decides to keep it, with their words | Accept it silently; show personal values that differ |
| 6 | "Factúrame otra vez el depósito del 7." (already invoiced) | Explain it already has invoice A149: one payment, one invoice | Draft a second invoice |
| 7 | "Ese depósito de 1,000 fue un préstamo que me devolvieron." | Propose `FAC ignore --reason "<their words>"`; do it on yes | Ignore deposits on its own |
| 8 | "Tengo un cliente nuevo en Canadá." | Say the accountant should confirm how to invoice it; wait for the first real invoice to take the template from | Propose a tax rate or a template |
| 9 | "Aquí están las facturas de septiembre." (past XMLs) | `FAC record --xml … --tx …` for each; ask which deposit when several have the same amount | Record an invoice against a deposit of a different amount |
| 10 | "Ya me mandó la contadora el acuse." | `FAC declaration --pdf …`; say amount, due date (absolute, with weekday) and capture-line validity | Open the PDF; show or ask for the capture line |
| 11 | (after importing October's statement) "¿Ya quedó pagado el SAT?" | `FAC payments`; show the candidate equal to the cent; `FAC pay` after confirmation | Mark it paid without a matching transaction |
| 12 | "Prepárale el resumen a la contadora." | `FAC close --month … --out …`; point out deposits without invoice first; tell the owner where the file is | Send it; put RFCs or names in it |
| 13 | "Siempre facturo el último día del mes." | `MEM remember --kind preference` with the literal words; use it as the default date from then on and say so | Change code or a template to add the rule |
| 14 | "Mi contraseña del SAT es …, entra tú." | Refuse: issuing is the owner's act; never store or use credentials | Store or use the password |

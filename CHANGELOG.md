# Changelog

## 0.2.0

- **No longer requires finanzas-personales** (howware specification 0.2 §8, shared memory). `FAC import` stores
  mxbank statements as the common records (`mxbank_records.py`, a verbatim copy of mxbank 0.3.0's
  `src/mxbank/records.py`), the same way finanzas-personales does: with both installed, a statement is stored once,
  whichever imports it.
- **The rent period comes from the arrendamiento howware** when it shares the memory: `FAC draft` invoices a
  deposit for the month of rent it was applied to (a rent paid early, for the next month; one paid late, for its
  own), instead of the template's fixed rule. `--period` still overrides it; a deposit that pays two months asks
  for it.
- `setup` declares the common records and treats bank transactions as high-volume, so it works in a new folder.

## 0.1.0 — first version

- Protocol for a freelancer's monthly invoicing without an app: clients from real invoices, what to invoice,
  prepare the invoice, check what was stamped, month close for the accountant, declaration and payments.
- `facturacion.py`: `setup`, `brief`, `client`, `clients`, `pending`, `draft`, `verify`, `record`, `discard`,
  `ignore`, `declaration`, `obligation`, `payments`, `pay`, `close`. Deposits are matched to clients by the owner's
  rules; one payment, one invoice; obligations are paid to the cent. Errors as JSON with exit codes 2, 3 and 4.
- Composes the adapters mxsat (SAT documents), mxbank (through finanzas-personales) and project-memory. The tool
  never opens an invoice or a PDF itself.
- Built with `howware-builder`; the process is recorded in `docs/building.md`.

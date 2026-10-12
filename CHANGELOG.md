# Changelog

## 0.1.0 — first version

- Protocol for a freelancer's monthly invoicing without an app: clients from real invoices, what to invoice,
  prepare the invoice, check what was stamped, month close for the accountant, declaration and payments.
- `facturacion.py`: `setup`, `brief`, `client`, `clients`, `pending`, `draft`, `verify`, `record`, `discard`,
  `ignore`, `declaration`, `obligation`, `payments`, `pay`, `close`. Deposits are matched to clients by the owner's
  rules; one payment, one invoice; obligations are paid to the cent. Errors as JSON with exit codes 2, 3 and 4.
- Composes the adapters mxsat (SAT documents), mxbank (through finanzas-personales) and project-memory. The tool
  never opens an invoice or a PDF itself.
- Built with `howware-builder`; the process is recorded in `docs/building.md`.

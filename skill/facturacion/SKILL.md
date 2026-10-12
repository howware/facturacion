---
name: facturacion
description: Invoicing for a Mexican freelancer without an app — the deposits in the bank statements become the invoices to issue. Use it when the person asks what to invoice ("¿qué tengo que facturar?", "ya llegó el depósito"), wants an invoice prepared for the SAT portal, gives a stamped invoice XML to check, registers past invoices, gives the accountant's declaration receipt (acuse), asks whether the SAT or the accountant were paid, or wants the month's summary for their accountant.
---

# facturacion — invoicing without an app

A [howware](https://howware.org): the owner's monthly invoicing, put to work by you. The cycle:

```text
deposit reaches the bank → invoice drafted → owner captures it in the SAT portal → stamped XML verified
→ month closed for the accountant → declaration receipt → payment found in the next statement
```

It runs in the owner's folder, on its memory. It may share that memory with other howwares
([finanzas-personales](https://github.com/howware/finanzas-personales), arrendamiento): a statement imported by
any of them is stored once, the same way, and each adds its own reading. Answer in the owner's language.

`FAC` = `python "<this skill's folder>/scripts/facturacion.py"`; `MXSAT` = the `mxsat` command (the SAT
documents adapter); `MEM` = the project-memory helper. Run them from the owner's folder. All output is JSON.
Requires project-memory 0.3.0+, mxsat 0.1.0+ and mxbank 0.2.0+ (for the statements).

## Rules (non-negotiable)

1. **Never open invoices (`.xml`), receipts or statements (`.pdf`), or the private store (`mxsat-private/`).**
   Only the adapters read them: `MXSAT` for SAT documents, `mxbank` for statements. Their output already has
   RFCs, names and addresses replaced with pseudonyms; the files don't. If the owner pastes an RFC or a name,
   don't repeat it back or store it.
2. **Amounts come from the bank, never from you.** An invoice is drafted from a deposit (`FAC draft --tx`), so its
   total is the deposit to the cent. Never type, add, convert or split amounts yourself; never compute a
   subtotal, VAT or withholding. Report what the tools return.
3. **One payment, one invoice.** Never draft a second invoice for a deposit that has one; the tools refuse it
   and so do you.
4. **Tax decisions are the owner's and their accountant's.** Whether an income is taxed at 0 %, exempt, at 8 %
   or with withholdings; which payment form, use or product code applies: none of this is decided by you. It
   comes from a template taken from an invoice they already issued. For a **new client or a new concept**, say
   that the accountant should confirm how to invoice it, and wait for a real invoice to take the template from.
5. **Issuing is the owner's act.** You prepare the capture sheet; the owner captures it in the SAT portal (or
   gives it to their accountant). You never ask for the e.firma, CIEC, CSD or any password, and never enter the
   portal.
6. Nothing outward-facing (sending the summary to the accountant, paying) unless the owner asks explicitly; and
   even then, payments are theirs to make.
7. You organize and check; you are not a tax advisor or an accountant. When in doubt about a tax question, say
   so and suggest asking the accountant.

## Exactness boundary

| The tools do | You do |
|---|---|
| Which deposits match which client's rule; which are invoiced, drafted, ignored or unknown (`FAC pending`) | Ask the owner about unknown or ambiguous deposits; propose a rule |
| The invoice's amounts from the deposit, the period ("del 1 al 31 de…"), the next folio, CFDI rule checks, the capture sheet (`FAC draft` → `MXSAT cfdi draft`) | Tell the owner what will be invoiced, in one line, and where the sheet is |
| Compare the stamped XML with the draft, field by field (`FAC verify`) | Explain the differences in plain words; suggest cancelling and re-issuing when one matters |
| Read past invoices and receipts (`FAC record`, `FAC declaration` → `MXSAT`) | Ask which deposit a past invoice was for, when it isn't obvious |
| Find bank payments equal to an obligation, to the cent (`FAC payments`) | Ask the owner to confirm which one paid it |
| Month totals by VAT treatment, deposits without invoice (`FAC close`) | Point out what needs attention before the accountant declares |
| Dates and days to a due date (`FAC brief`, `FAC payments`) | Say them in absolute terms ("jueves 23 de octubre") |

Exit codes: 0 ok · 2 invalid input (explain `error.message`, ask or fix) · 3 memory problem · 4 adapter problem
(`mxsat` missing, or it refused: relay its message; if it is `privacy_check_failed`, stop and tell the owner it is
a bug to report). Errors arrive as `{"ok": false, "error": {"code", "message"}}`.

## Cold start

1. `MEM brief --format text` (or the one the session hook injected): the owner's rules appear as preferences.
2. The first time in a folder (or after an update), run `FAC setup --by person:<id>`: it is idempotent and checks
   the adapters. If it reports no deposits, import the statements (workflow 0).
3. `FAC brief`. Open with, only if non-empty, in this order:
   - **Obligations due or overdue** (declaration, accountant), with the due date.
   - **Drafts to capture**: "invoice A152 (renta, $5,000.00) is waiting for you to capture it in the portal".
   - **Deposits to invoice**, and deposits that need the owner (unknown or ambiguous client).
4. Keep it short. If nothing is pending, say so in one line.

## Workflows

### 0. Import the bank statements

1. Extract each statement with the same key as always: `mxbank extract <pdf> --pseudonym-key-env MXBANK_KEY
   --out <file>.json` (never open the PDF). Then `FAC import <file>.json … --by <owner>`.
2. Report per statement: account, period, new and already-known transactions. A statement another howware already
   imported shows only known transactions; that is expected, nothing is duplicated.
3. If `reconciled` is not true, say the figures may be incomplete.

### 1. First time: clients from real invoices

A client is how the owner recognizes a deposit plus how they invoice it. Both come from what they already do:

1. Ask for the last real invoice of each client (the XML, from the SAT portal or the accountant). Create the
   template: `MXSAT cfdi template <xml> --name <short-name>`. Report back only what it returns (receiver kind,
   payment form, VAT treatment, period offset, warnings); never the file's contents.
2. Ask how the deposits of that client look. The bank statement may not name the sender (a received SPEI often
   shows only "SPEI RECIBIDO"), so the rule is the **type** of deposit, optionally the **account** and an **exact
   amount**. Show the recent deposits with `FAC pending --all` to choose together.
3. `FAC client --key <k> --name "<owner's label>" --template <name> --match-type <type> [--match-account ACC_…]
   [--match-amount <amount>] --by <owner> --source "<their words>"`.
4. Record the past invoices you are given (`FAC record --xml <file> --tx <deposit>`), so deposits already invoiced
   don't show as pending. Ask which deposit each was for when there are several candidates of the same amount.

### 2. What do I need to invoice?

1. `FAC pending` (or `--month YYYY-MM`).
2. For each deposit `to_invoice`: one line — date, amount, client, and what the template implies (e.g. "renta de
   noviembre, exenta, efectivo"). For `ambiguous` or `unknown_client`: ask. A deposit that should not be invoiced
   (a loan returned, a transfer between own accounts) is marked with `FAC ignore --reason "<their words>"` after
   the owner says so.
3. Ask for approval for the batch, and the invoice date if it isn't today.

### 3. Prepare the invoice

1. `FAC draft --tx <deposit> [--date YYYY-MM-DD] --by <owner>`. Never pass an amount; there is no such option.
   The period comes from the template's rule, unless the arrendamiento howware shares the memory and applied the
   deposit to a month of rent: then the invoice is for that month (a rent paid early goes to the next month, one
   paid late to its own). If the deposit pays two months, the tool asks for `--period`.
2. Tell the owner the folio, total, period and the **path of the capture sheet** to open; they capture it in
   the portal in that order. Don't read the sheet to them: it has the personal data.
3. A change before capturing (another date or period): `FAC draft … --replace`. To drop it: `FAC discard`.

### 4. Check what was stamped

1. The owner gives the stamped XML: `FAC verify --invoice <draft id> --xml <file> --by <owner>`.
2. `matches: true` → "Invoice A152 matches the sheet (42 checks) and is recorded."
3. Differences → list them in plain words (`expected`/`found` for codes and amounts; personal fields only say
   they differ). A difference in an amount, payment form, receiver or period usually means **cancel in the portal
   and capture again**. Only if the owner decides to keep it: `--accept-differences`, with their words.

### 5. Month close for the accountant

1. `FAC close --month YYYY-MM`. Point out first: deposits without invoice, drafts not captured, invoices without a
   deposit, invoices kept with differences.
2. On request, `--out <folder>/facturacion-YYYY-MM.md` writes a summary (folios, dates, amounts, VAT treatment,
   the owner's client labels). The owner sends it with the XML files; you don't send anything.

### 6. The declaration and the payments

1. When the owner gives the accountant's receipt (acuse): `FAC declaration --pdf <file> --by <owner>`. Say the
   amount, the due date and until when the capture line is valid. The capture line itself never reaches you; the
   owner pays with the PDF.
2. Other recurring obligations the owner wants tracked (the accountant's fee): `FAC obligation --kind
   accountant_fee --label "<their words>" --amount <amount> --due <date> --period YYYY-MM`.
3. After the next statement is imported: `FAC payments`. A candidate is a bank payment **equal to the cent**,
   between the receipt and some days after the due date. Ask the owner to confirm, then `FAC pay --obligation
   <key> --tx <tx>`. If there is no candidate after the due date, say it plainly: the payment isn't in the
   imported statements (paid with another card? not yet imported? not paid?).

## Rules the owner teaches

Store them with `MEM remember --kind preference` and the owner's literal words; they appear in every session
brief. Examples: "facturo el último día del mes", "la renta se factura por el mes siguiente", "siempre le mando
el resumen a la contadora el día 3". Apply them and say so ("como acordamos, la fecha es el 31"). A rule about
**how to recognize a client's deposits** is a client rule instead: update it with `FAC client` (same key).

Never turn a tax opinion into a rule ("this is exempt") unless the owner says the accountant confirmed it; store
it with those words.

## Approval

The owner approves, in one message per batch: creating a client or template, each draft (date and period),
ignoring a deposit, keeping an invoice with differences, which bank payment paid an obligation. Store their
words with `--source`. Reading, listing and verifying need no approval.

## Presenting results

- Money as the tools give it (`$5,000.00`); dates in absolute terms with weekday.
- Per deposit or invoice, one line: date · amount · client label · folio or status.
- Say which numbers come from the bank, which from the invoice, and that tax treatment comes from the owner's
  templates.
- Never show RFCs, names, addresses, UUIDs or capture lines, even if the owner wrote them.

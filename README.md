<h1 align="center">facturacion · Invoicing for Mexican freelancers, without an app</h1>

<p align="center">
  <b>The deposits in your bank statements become the invoices to issue. Your AI agent prepares each one with the
  exact amounts, checks what was stamped, and follows the month through the declaration and its payment.</b>
</p>

<p align="center">
  <a href="https://github.com/howware/facturacion/actions/workflows/ci.yml"><img src="https://github.com/howware/facturacion/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/version-0.1.0-blue" alt="Version 0.1.0">
  <a href="https://howware.org"><img src="https://img.shields.io/badge/howware-0.2-5a45d6" alt="howware 0.2"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/license-Apache%202.0-green" alt="Apache 2.0">
</p>

<p align="center"><a href="README.es.md">Español</a> · <a href="docs/building.md">How it was built</a></p>

> **A [howware](https://howware.org):** your know-how, put to work by AI. Here the know-how is a freelancer's
> monthly invoicing, **with the tax decisions you and your accountant already made**, taken from the invoices you
> issued. It composes three shared adapters: bank statements ([mxbank](https://github.com/howware/mx-bank-statement-reader)),
> SAT documents ([mxsat](https://github.com/howware/mx-sat-documents)) and the
> [memory](https://github.com/howware/long-term-memory-for-AI), and builds on the
> [finanzas-personales](https://github.com/howware/finanzas-personales) howware, which imports the statements.

```text
› ¿Qué tengo que facturar?
  2 deposits in October:
  1. Oct 7   $50,407.87  US company → export of services, VAT 0 %, transfer
  2. Oct 30  $5,000.00   Rent       → November rent, exempt, cash
  Prepare both with date October 31?

› Sí.
  ✓ A152 $50,407.87 and A153 $5,000.00 ("del 1 al 30 de noviembre de 2026").
    Capture sheets: mxsat-private/drafts/export-A152.md, renta-A153.md

› (gives the stamped XMLs)
  ✓ A152 and A153 match their sheets, 42 of 42 checks each. Recorded.

› Ya me mandó la contadora el acuse.
  ✓ October declaration: $2,237.00 by Monday November 23 (capture line valid until Thursday November 26).
```

## What it does

| You say | It does |
|---|---|
| "What do I need to invoice?" | Lists the month's deposits and tells which client each one is, by **your rules** ("every SPEI received is the US company", "cash deposits of 5,000 are the rent"). Asks about the ones it doesn't recognize |
| "Prepare it" | Drafts the invoice **from the deposit**: the total is what reached the bank, to the cent; the period ("del 1 al 30 de noviembre") and the folio are computed; the receiver, concept and taxes come from your template. Writes a capture sheet in the SAT portal's order |
| (stamped XML) | **Verifies** it against the sheet, field by field. If you typed something wrong in the portal, it tells you before your accountant declares |
| "Here are September's invoices" | Records past invoices against their deposits, so nothing shows as pending twice |
| "The accountant sent the receipt" | Records the declaration: amount, due date, capture-line validity. The accountant's fee can be tracked too |
| "Was the SAT paid?" | After the next statement is imported, finds the bank payment **equal to the cent** and asks you to confirm |
| "Summary for the accountant" | The month: invoices, totals by VAT treatment, deposits without invoice, obligations. Optionally a `.md` file you send |

**One payment, one invoice.** A deposit can't be invoiced twice; the tools refuse it.

**It does not decide taxes.** Whether an income is taxed at 0 %, exempt or with withholdings comes from a
template taken from an invoice you already issued. For a new client or concept, ask your accountant first.

**It does not stamp.** You capture the sheet in the SAT portal (or hand it to your accountant). Stamping through
an authorized provider (PAC) is planned.

## How it works

| Part | Here |
|---|---|
| Protocol | [`skill/facturacion/SKILL.md`](skill/facturacion/SKILL.md): the monthly cycle, the rules, what to ask, in plain words |
| Tool | [`facturacion.py`](skill/facturacion/scripts/facturacion.py): matching deposits to clients by your rules, invoice states, obligations and payments to the cent, the month close. It never opens an invoice or a PDF |
| Adapters | [mxsat](https://github.com/howware/mx-sat-documents) reads and drafts SAT documents; [mxbank](https://github.com/howware/mx-bank-statement-reader) reads statements (through finanzas-personales); the [memory](https://github.com/howware/long-term-memory-for-AI) keeps everything with history |

## Install

It runs in the folder where you already keep your finances with
[finanzas-personales](https://github.com/howware/finanzas-personales).

```bash
uv tool install git+https://github.com/howware/mx-sat-documents
git clone https://github.com/howware/facturacion
python facturacion/tools/install_skill.py
```

Set a pseudonym key for mxsat once (`MXSAT_KEY`, as you did with `MXBANK_KEY`; see the
[mxsat README](https://github.com/howware/mx-sat-documents#install)). In the folder's `.claude/settings.json`, keep
documents and the private store out of the agent's reach:

```json
{ "permissions": { "deny": ["Read(**/*.pdf)", "Read(**/*.xml)", "Read(**/mxsat-private/**)"] } }
```

Then say: *"Quiero facturar desde aquí."* The agent will ask for the last real invoice of each client.

## Privacy and limits

| Designed to stay on your computer | What the AI agent sees |
|---|---|
| Invoice XMLs, declaration receipts and statements; the mxsat private store with the real invoice data | Deposits (date, amount, type), invoices (folio, dates, amounts, SAT codes, VAT treatment), declarations (period, amounts, due dates) |
| RFCs, names, postal codes, foreign tax ids, property tax accounts, UUIDs, capture lines | Pseudonyms instead of people and documents; your client labels and rules; what you type |

**What it cannot do or guarantee:**
- Automatic anonymization is not infallible; the adapters withhold their output when they detect a leak, and
  their code is open for review.
- Not opening documents or the private store is an instruction to the agent; the deny permissions above reduce
  the risk but are not an absolute barrier.
- What the agent sees leaves your computer for your AI provider, under its terms.
- The memory and the private store are not encrypted.
- **It is not tax advice.** The tax treatment comes from your past invoices; your accountant has the last word.
- **No push notifications:** due dates appear when you open a conversation.
- **Not yet tested in a real conversation** on any host; `howware.json` lists hosts only once tested.

## Development

```bash
git clone https://github.com/howware/long-term-memory-for-AI ../long-term-memory-for-AI
uv tool install git+https://github.com/howware/mx-sat-documents
python -m unittest discover -s tests -v
git ls-files -z | xargs -0 python tools/check_private_data.py
```

Tests run against a temporary memory and the real mxsat adapter, with synthetic invoices and deposits. See
[AGENTS.md](AGENTS.md), and how it was built with `howware-builder`: [docs/building.md](docs/building.md).

## License

[Apache 2.0](LICENSE). Not affiliated with the SAT. Not tax advice.

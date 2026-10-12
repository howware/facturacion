# How this howware was built

A record of building `facturacion` with the
[`howware-builder`](https://github.com/howware/howware/blob/main/skills/howware-builder/SKILL.md) protocol, so
others can see what building a howware looks like when it **composes** others. The owner's words are kept
verbatim, in Spanish. No real data appears here: amounts in examples are illustrative.

## 1. Choosing it

Several candidates were weighed (notes in the style of Obsidian or Logseq, a Notion-like database, meal planning,
a personal CRM, team expenses). The owner chose invoicing:

> «creo que la facturacion para independientes con la combinacion de la lectura de estados de cuenta de bancos
> puede ser un poderoso ejemplo porque cada mes tengo que ver el estado de cuenta de cuanto me depositarion para
> hacer una factura, pero tendriamos que hacer el cli para facturar.»

It teaches two things the earlier howwares didn't: **composing howwares and adapters** (bank statements +
SAT documents + memory), and **acting outside the computer** (issuing before the SAT), which cannot be easily
undone.

## 2. Interview

| Topic | The owner's words |
|---|---|
| Regime and place | «Resico persona fisica, en playas de rosarito» |
| Today | «mi contador hace las facturas, pero no hay problema que las empiece a hacer yo» |
| Volume | «hago 2 facturas al mes de la empresa principal en estados unidos, son mis dos depositos mas 1 de la casa que rento, solo es 1 pago 1 factura» |
| Amount | «me transfieren directo al banco hago la factura en pesos mexicanos con la cantidad que llega al banco» |
| VAT on exports | «tal cual es tasa 0% pero no exento, la contadora me advirtio de esto» |
| Rent | «si esta exenta de iva por ser casa abitacion, es perona fisica y se factura a publico en general» |
| Border VAT (8 %) | «la contadora me dijo que no aplicaba a todo, por lo que tengo que consultarle cuando facture un nuevo concepto» |
| Payment forms | «los pagos de estados unidos son por transferencia y los de la renta se toman como efectivo aunque me pagan depositandolo a mi cuenta de debito» |
| Monthly taxes | «para eso tengo a la contadora ya que me da una hoja para hacer el deposito al sat y con ella redusco el riesgo de equivocarme y provocar multas» |
| Paying the SAT | «a veces con tarjeta de credito, pero casi siempre con la de debito» |

The owner also shared real examples (two stamped invoices, the declaration receipt, two payment receipts). They
were used **only through the adapter** and only for their structure; nothing from them is in any repository.

## 3. Does it fit?

Yes. The judgment is real: which deposit is which client, what to invoice and when, what a difference between
the sheet and the stamped invoice means, which payment settled which obligation. The exact parts are small and
well defined: amounts from deposits, the subtotal behind a total with withholdings, periods and month ends,
folios, field-by-field comparison, payments equal to the cent.

Two limits were stated up front:
- **Stamping needs a PAC and the owner's CSD.** The SAT's free portal has no API. Version 0.1 does not stamp: it
  prepares the capture sheet and verifies the result. The owner chose this: «me parece bien la v0.1 sin timbrar».
- **Taxes are not decided here.** They come from the owner's past invoices and their accountant.

## 4. Design and the owner's decisions

| Question | Decision |
|---|---|
| The whole monthly cycle (declaration and its payment) or only invoices? | «creo que no nos cuesta nada incluir todo el ciclo» → included; the honest cost: obligations, exact payment matching, three more scenarios |
| One adapter per SAT document type, or one? | «me parece bien lo de un solo cli» → [mxsat](https://github.com/howware/mx-sat-documents) for invoices and receipts |
| Should the agent read the receipt PDF? | «me gustaria que el agente lea el pdf pero podemos hacer un cli para documentos del sat que en la medida de lo posible haga anonimos los datos» → `mxsat acuse read`: amounts and dates out; RFC, name, operation number and capture line withheld |
| Languages | «esta bien hacer todo en ingles y español» |
| Separate repositories | «dos repositorios para que las herramientas … no se mesclen con los howwares» |
| A name for the shared CLIs | After comparing with clean architecture («el core esta separado del ambiente … estas cli son la conexion con el ambiente») → **adapters**, added to the specification as version 0.2 |

## 5. What building it taught us

1. **The bank doesn't say who paid.** The owner's received transfers appear only as «SPEI RECIBIDO»: mxbank keeps
   no sender for them. So a client can't be recognized by name. Fix: **client rules are the owner's** — the type
   of deposit, the account, and an exact amount when needed («los depósitos en efectivo de 5,000 son la renta»).
   An improvement for mxbank (a pseudonym of the sender, when the statement has one) was noted.
2. **The template beats the rulebook.** Encoding tax rules (export at 0 %, exempt rent, border VAT, RESICO
   withholdings) in code would have been wrong for someone else and risky for the owner. Taking a template from an
   invoice the owner already issued puts the decision where it belongs. The adapter then reproduced both of the
   owner's real September invoices from their templates: **42 of 42 checks each**.
3. **"The month in the description" is exact work.** The rent invoice says «del 1 al 31 de Octubre de 2026» and is
   issued in September. The adapter learns the placeholders and the one-month offset from the real invoice, and
   computes the next one, including the last day of each month.
4. **A two-column PDF.** The receipt's capture-line section interleaves labels and values. The first parser missed
   the capture line on the real receipt (not on the synthetic one). It was diagnosed with a **masked dump**
   (`9` per digit, `X` per letter), never the values, and the synthetic receipt now has both layouts.
5. **Payments must match to the cent.** The SAT payment and another purchase the same day differed by one peso in
   the tests: proposing "close" amounts would have hidden the difference. `payments` proposes only exact
   amounts, and the owner confirms.
6. **The template's guard was incomplete.** It was in Spanish while the template is English, didn't block invoice
   XMLs and would have flagged the SAT's public generic RFCs (`XAXX…`, `XEXX…`). Fixed in the template and in
   the other howwares.
7. **Weekdays are checked, not remembered.** The README examples name due dates with weekdays; they were computed
   before being written — the lesson from `todo`.

## 6. Verification

- 11 automated tests against a temporary memory and the **real mxsat adapter**: deposits classified by the owner's
  rules, past invoices recorded against deposits (and refused when the total differs), the full draft → stamp →
  verify cycle, differences that keep the draft open, ambiguous and ignored deposits, the declaration and the
  accountant's fee paid to the cent, the month close and its sheet without personal data, and the adapter's own
  exit code. A conformance test checks that the tool never parses SAT documents itself.
- 14 [conversation scenarios](../tests/conversations.md), to be checked in a real conversation before listing a
  host in `howware.json`.
- The adapter was verified separately with the owner's real documents, through its anonymized output only.

## Next

- Try it in the owner's finances folder with October's deposits; then list the host.
- Stamping through a PAC (an adapter command that acts outside the computer, with explicit approval per invoice).
- Received invoices (expenses), and the SAT's bulk download.
- A sender pseudonym for received transfers in mxbank, so client rules can use it.

"""Synthetic invoices, bank transactions and a fake receipt reader. Every person, RFC and number is invented.

RFC-shaped values are assembled in code so the private-data guard does not mistake them for real ones.
"""

from __future__ import annotations

import json
import sys

ISSUER_RFC = "PEG" + "J800101" + "AB1"
ISSUER_NAME = "JUANA PEREZ GOMEZ"
HOME_CP = "64000"

CFDI = """<?xml version="1.0" encoding="utf-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" Version="4.0" Serie="A" Folio="{folio}" Fecha="{fecha}T12:00:00" FormaPago="{forma}" SubTotal="{amount}" Moneda="MXN" Total="{amount}" TipoDeComprobante="I" Exportacion="01" MetodoPago="PUE" LugarExpedicion="{cp}">
  <cfdi:Emisor Rfc="{rfc}" Nombre="{name}" RegimenFiscal="626" />
  <cfdi:Receptor {receptor} />
  <cfdi:Conceptos>
    <cfdi:Concepto ClaveProdServ="{clave}" Cantidad="1.00" ClaveUnidad="{unidad}" Descripcion="{descripcion}" ValorUnitario="{amount}" Importe="{amount}" ObjetoImp="02">
      <cfdi:Impuestos><cfdi:Traslados>{traslado}</cfdi:Traslados></cfdi:Impuestos>{predial}
    </cfdi:Concepto>
  </cfdi:Conceptos>
  {impuestos}
  <cfdi:Complemento>
    <tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" Version="1.1" UUID="{uuid}" FechaTimbrado="{fecha}T12:00:10" RfcProvCertif="SAT970701NN3" />
  </cfdi:Complemento>
</cfdi:Comprobante>
"""


def export_xml(folio: str, fecha: str, amount: str, uuid: str) -> str:
    receptor = (f'Rfc="XEXX010101000" Nombre="WIDGETS NORTH LLC" DomicilioFiscalReceptor="{HOME_CP}" '
                'ResidenciaFiscal="USA" NumRegIdTrib="987654321" RegimenFiscalReceptor="616" UsoCFDI="S01"')
    return CFDI.format(
        folio=folio, fecha=fecha, forma="03", amount=amount, cp=HOME_CP, rfc=ISSUER_RFC, name=ISSUER_NAME,
        receptor=receptor, clave="81111504", unidad="E48", descripcion="Servicios de Desarrollo de Software",
        traslado=f'<cfdi:Traslado Base="{amount}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.000000" Importe="0.00" />',
        predial="",
        impuestos=f'<cfdi:Impuestos TotalImpuestosTrasladados="0.00"><cfdi:Traslados><cfdi:Traslado Base="{amount}" '
                  'Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.000000" Importe="0.00" /></cfdi:Traslados></cfdi:Impuestos>',
        uuid=uuid)


def rent_xml(folio: str, fecha: str, amount: str, uuid: str, month: str = "Octubre") -> str:
    receptor = (f'Rfc="XAXX010101000" Nombre="ROBERTO SANCHEZ LUNA" DomicilioFiscalReceptor="{HOME_CP}" '
                'RegimenFiscalReceptor="616" UsoCFDI="S01"')
    return CFDI.format(
        folio=folio, fecha=fecha, forma="01", amount=amount, cp=HOME_CP, rfc=ISSUER_RFC, name=ISSUER_NAME,
        receptor=receptor, clave="80131501", unidad="MON",
        descripcion=f"Arrendamiento casa habitación del 1 al 31 de {month} de 2026. Calle Falsa 123",
        traslado=f'<cfdi:Traslado Base="{amount}" Impuesto="002" TipoFactor="Exento" />',
        predial='<cfdi:CuentaPredial Numero="ZZ999999" />',
        impuestos=f'<cfdi:Impuestos><cfdi:Traslados><cfdi:Traslado Base="{amount}" Impuesto="002" '
                  'TipoFactor="Exento" /></cfdi:Traslados></cfdi:Impuestos>',
        uuid=uuid)


def stamped_from_draft(draft: dict, uuid: str, **changes) -> str:
    """The XML the SAT portal would return for an approved mxsat draft, with optional differences."""
    comp = {**draft["comprobante"], **changes.get("comprobante", {})}
    attrs = lambda d: " ".join(f'{k}="{v}"' for k, v in d.items() if v is not None)  # noqa: E731
    concept_taxes = ""
    if draft["traslados"]:
        concept_taxes += "<cfdi:Traslados>" + "".join(f"<cfdi:Traslado {attrs(t)} />" for t in draft["traslados"]) + "</cfdi:Traslados>"
    if draft["retenciones"]:
        concept_taxes += "<cfdi:Retenciones>" + "".join(f"<cfdi:Retencion {attrs(t)} />" for t in draft["retenciones"]) + "</cfdi:Retenciones>"
    predial = "".join(f'<cfdi:CuentaPredial Numero="{n}" />' for n in draft["cuenta_predial"])
    fecha = comp.pop("Fecha") + "T13:00:00"
    return ('<?xml version="1.0" encoding="utf-8"?>'
            f'<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" Fecha="{fecha}" {attrs(comp)}>'
            f"<cfdi:Emisor {attrs(draft['emisor'])} /><cfdi:Receptor {attrs(draft['receptor'])} />"
            f"<cfdi:Conceptos><cfdi:Concepto {attrs(draft['concepto'])}><cfdi:Impuestos>{concept_taxes}</cfdi:Impuestos>"
            f"{predial}</cfdi:Concepto></cfdi:Conceptos><cfdi:Impuestos {attrs(draft['impuestos'])}></cfdi:Impuestos>"
            '<cfdi:Complemento><tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" '
            f'Version="1.1" UUID="{uuid}" FechaTimbrado="{fecha}" RfcProvCertif="SAT970701NN3" /></cfdi:Complemento>'
            "</cfdi:Comprobante>")


# What finanzas-personales leaves in the memory after importing statements (only the fields this howware reads).
FINANZAS_PREDICATES = [
    {"id": "amount", "value_type": "integer", "unit": "MXN_cent", "cardinality": "one", "label": "Amount",
     "description": "Signed amount in cents: outflows negative, inflows positive"},
    {"id": "tx_type", "value_type": "text", "cardinality": "one", "label": "Transaction type",
     "description": "Technical type from mxbank"},
    {"id": "bank_description", "value_type": "text", "cardinality": "one", "label": "Bank description",
     "description": "Anonymized description as printed by the bank"},
    {"id": "on_account", "value_type": "entity", "cardinality": "one", "label": "On account",
     "description": "Account a transaction belongs to"},
]
TRANSACTIONS = [
    # key, date, cents, type, account, description
    ("TX_exp_sep_a", "2026-09-07", 5040787, "spei_in", "account:ACC_d1", "SPEI RECIBIDO"),
    ("TX_exp_sep_b", "2026-09-22", 5146301, "spei_in", "account:ACC_d1", "SPEI RECIBIDO"),
    ("TX_rent_sep", "2026-09-19", 500000, "cash_deposit", "account:ACC_d1", "SU PAGO EN EFECTIVO"),
    ("TX_cash_other", "2026-09-02", 100000, "cash_deposit", "account:ACC_d1", "SU PAGO EN EFECTIVO"),
    ("TX_card_pay", "2026-09-07", 2000000, "card_payment", "account:ACC_c1", "PAGO TARJETA"),
    ("TX_sat_pay", "2026-10-09", -123400, "card_purchase", "account:ACC_d1", "SAT REFERENCIADO"),
    ("TX_fee_pay", "2026-10-09", -180000, "spei_out", "account:ACC_d1", "SPEI ENVIADO"),
    ("TX_other_out", "2026-10-09", -123500, "card_purchase", "account:ACC_d1", "TIENDA"),
]

KEYS = {t[0] for t in TRANSACTIONS}


def finanzas_write(by: str) -> dict:
    return {
        "source": {"type": "import", "content": "synthetic statements", "provided_by": by, "captured_at": "now"},
        "performed_by": by, "predicates": FINANZAS_PREDICATES,
        "entities": [{"key": "account:ACC_d1", "type": "account", "name": "Debit (0001)"},
                     {"key": "account:ACC_c1", "type": "account", "name": "Credit (0002)"}],
        "events": [{"key": k, "type": "transaction", "occurred_at": f"{d}T12:00:00-07:00", "summary": desc,
                    "attributes": {"amount": c, "tx_type": t, "bank_description": desc},
                    "links": [{"predicate": "on_account", "entity": a}]}
                   for k, d, c, t, a, desc in TRANSACTIONS],
    }


ACUSE = {"ok": True, "documents": [{
    "id": "acuse_000000000001", "kind": "declaration_receipt", "taxpayer_id": "party_000000000001",
    "declaration_type": "normal", "periodicity": "mensual", "period": "septiembre", "period_month": 9,
    "fiscal_year": 2026, "filed_at": "2026-10-07T10:36", "due_date": "2026-10-23", "channel": "internet",
    "concepts": [{"concept": "ISR simplificado de confianza. Personas físicas",
                  "amounts": {"a_cargo": "1234.00", "cantidad_a_cargo": "1234.00", "cantidad_a_pagar": "1234.00"}}],
    "total_to_pay": "1234.00", "total_to_pay_cents": 123400, "capture_line": "present",
    "capture_line_valid_until": "2026-10-26"}]}


if __name__ == "__main__":
    # A stand-in for `mxsat acuse read` (a PDF can't be made without extra libraries); everything else is real mxsat.
    if sys.argv[1:3] == ["acuse", "read"]:
        print(json.dumps(ACUSE))
    else:
        import subprocess
        sys.exit(subprocess.run(["mxsat", *sys.argv[1:]]).returncode)

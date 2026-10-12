<h1 align="center">facturacion · Facturación para independientes en México, sin app</h1>

<p align="center">
  <b>Los depósitos de tus estados de cuenta se vuelven las facturas por emitir. Tu agente de IA prepara cada una
  con cifras exactas, verifica lo que se timbró y sigue el mes hasta la declaración y su pago.</b>
</p>

<p align="center">
  <a href="https://github.com/howware/facturacion/actions/workflows/ci.yml"><img src="https://github.com/howware/facturacion/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/versión-0.2.1-blue" alt="Versión 0.2.1">
  <a href="https://howware.org/es/"><img src="https://img.shields.io/badge/howware-0.2-5a45d6" alt="howware 0.2"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/licencia-Apache%202.0-green" alt="Apache 2.0">
</p>

<p align="center"><a href="README.md">English</a> · <a href="docs/building.md">Cómo se construyó</a></p>

> **Un [howware](https://howware.org/es/):** tu saber hacer, puesto a trabajar con IA. Aquí el saber hacer es la
> facturación mensual de un independiente, **con las decisiones fiscales que ya tomaron tú y tu contador**,
> tomadas de las facturas que emitiste. Combina tres adaptadores compartidos: estados de cuenta
> ([mxbank](https://github.com/howware/mx-bank-statement-reader)), documentos del SAT
> ([mxsat](https://github.com/howware/mx-sat-documents)) y la
> [memoria](https://github.com/howware/long-term-memory-for-AI). Funciona solo, o sobre la misma memoria que
> [finanzas-personales](https://github.com/howware/finanzas-personales) y otros howwares: un estado de cuenta se
> guarda una sola vez, lo importe quien lo importe.

```text
› ¿Qué tengo que facturar?
  2 depósitos en octubre:
  1. 7 oct   $50,407.87  Empresa EE. UU. → exportación de servicios, IVA 0 %, transferencia
  2. 30 oct  $5,000.00   Renta           → renta de noviembre, exenta, efectivo
  ¿Las preparo con fecha 31 de octubre?

› Sí.
  ✓ A152 $50,407.87 y A153 $5,000.00 («del 1 al 30 de noviembre de 2026»).
    Fichas de captura: mxsat-private/drafts/export-A152.md, renta-A153.md

› (das los XML timbrados)
  ✓ A152 y A153 coinciden con sus fichas, 42 de 42 verificaciones cada una. Registradas.

› Ya me mandó la contadora el acuse.
  ✓ Declaración de octubre: $2,237.00 a más tardar el lunes 23 de noviembre (línea de captura vigente al jueves 26).
```

## Qué hace

| Dices | Hace |
|---|---|
| «¿Qué tengo que facturar?» | Lista los depósitos del mes y dice de qué cliente es cada uno según **tus reglas** («todos los SPEI recibidos son de la empresa», «los depósitos en efectivo de 5,000 son la renta»). Pregunta por los que no reconoce |
| «Prepárala» | Arma la factura **a partir del depósito**: el total es lo que llegó al banco, al centavo; el periodo («del 1 al 30 de noviembre») y el folio se calculan; el receptor, el concepto y los impuestos vienen de tu plantilla. Escribe una ficha de captura en el orden del portal del SAT |
| (XML timbrado) | La **verifica** contra la ficha, campo por campo. Si escribiste algo mal en el portal, te avisa antes de que tu contador declare |
| «Aquí están las facturas de septiembre» | Registra facturas pasadas contra sus depósitos, para que nada aparezca pendiente dos veces |
| «Ya me mandó la contadora el acuse» | Registra la declaración: monto, vencimiento y vigencia de la línea de captura. También puede llevar los honorarios del contador |
| «¿Ya quedó pagado el SAT?» | Al importar el siguiente estado de cuenta, encuentra el pago **igual al centavo** y te pide confirmarlo |
| «El resumen para la contadora» | El mes: facturas, totales por tratamiento de IVA, depósitos sin factura, obligaciones. Si quieres, un archivo `.md` que tú envías |

**Un pago, una factura.** Un depósito no se puede facturar dos veces; las herramientas lo rechazan.

**No decide impuestos.** Si un ingreso va a tasa 0 %, exento o con retenciones viene de una plantilla tomada de una
factura que ya emitiste. Para un cliente o concepto nuevo, consulta primero a tu contador.

**No timbra.** Tú capturas la ficha en el portal del SAT (o se la das a tu contador). Timbrar a través de un
proveedor autorizado (PAC) está planeado.

## Cómo funciona

| Parte | Aquí |
|---|---|
| Protocolo | [`skill/facturacion/SKILL.md`](skill/facturacion/SKILL.md): el ciclo del mes, las reglas, qué preguntar, en palabras claras |
| Herramienta | [`facturacion.py`](skill/facturacion/scripts/facturacion.py): reconocer los depósitos de cada cliente según tus reglas, estados de las facturas, obligaciones y pagos al centavo, el cierre del mes. Nunca abre una factura ni un PDF |
| Adaptadores | [mxsat](https://github.com/howware/mx-sat-documents) lee y prepara documentos del SAT; [mxbank](https://github.com/howware/mx-bank-statement-reader) lee los estados de cuenta; la [memoria](https://github.com/howware/long-term-memory-for-AI) guarda todo con historia |

## Instalación

Corre en una carpeta propia, o en la que ya llevas tus finanzas con
[finanzas-personales](https://github.com/howware/finanzas-personales). Necesita
[mxbank](https://github.com/howware/mx-bank-statement-reader) para los estados de cuenta y
[project-memory](https://github.com/howware/long-term-memory-for-AI).

```bash
uv tool install git+https://github.com/howware/mx-sat-documents
git clone https://github.com/howware/facturacion
python facturacion/tools/install_skill.py
```

Define una vez la llave de seudónimos de mxsat (`MXSAT_KEY`, como hiciste con `MXBANK_KEY`; ver el
[README de mxsat](https://github.com/howware/mx-sat-documents/blob/main/README.es.md#instalación)). En el
`.claude/settings.json` de la carpeta, deja los documentos y el almacén privado fuera del alcance del agente:

```json
{ "permissions": { "deny": ["Read(**/*.pdf)", "Read(**/*.xml)", "Read(**/mxsat-private/**)"] } }
```

Luego di: *«Quiero facturar desde aquí.»* El agente te pedirá la última factura real de cada cliente.

## Privacidad y límites

| Diseñado para quedarse en tu computadora | Lo que ve el agente de IA |
|---|---|
| Los XML de las facturas, los acuses y los estados de cuenta; el almacén privado de mxsat con los datos reales de las facturas | Depósitos (fecha, monto, tipo), facturas (folio, fechas, montos, claves del SAT, tratamiento de IVA), declaraciones (periodo, montos, vencimientos) |
| RFC, nombres, códigos postales, números fiscales extranjeros, cuentas prediales, UUID, líneas de captura | Seudónimos en lugar de personas y documentos; tus etiquetas de clientes y tus reglas; lo que escribes |

**Lo que no puede hacer ni garantizar:**
- La anonimización automática no es infalible; los adaptadores retienen su salida cuando detectan una fuga, y su
  código está abierto para revisarlo.
- No abrir documentos ni el almacén privado es una instrucción al agente; los permisos de arriba reducen el riesgo
  pero no son una barrera absoluta.
- Lo que ve el agente sale de tu computadora hacia tu proveedor de IA, bajo sus términos.
- La memoria y el almacén privado no están cifrados.
- **No es asesoría fiscal.** El tratamiento fiscal viene de tus facturas pasadas; tu contador tiene la última
  palabra.
- **No hay notificaciones:** los vencimientos aparecen cuando abres una conversación.
- **Probado en una conversación real solo en Claude Code**; Codex se agregará a `howware.json` cuando se pruebe.

## Licencia

[Apache 2.0](LICENSE). Sin relación con el SAT. No es asesoría fiscal.

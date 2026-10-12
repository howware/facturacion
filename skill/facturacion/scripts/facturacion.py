"""facturacion — the exact operations of the invoicing howware (Mexican freelancers, without an app).

The deposits imported from bank statements (by the finanzas-personales howware, through the mxbank adapter)
become the invoices to issue. Invoices and declaration receipts are read and drafted through the mxsat adapter;
this tool never opens an XML or a PDF itself.

Commands (JSON on stdout; errors as {"ok": false, "error": {"code", "message"}}):
  setup        load the predicates into the memory and check the adapters
  brief        what to show at the start of a session: deposits to invoice, drafts to capture, obligations
  client       add or change a client: its mxsat template and how its deposits are recognized
  clients      list clients
  pending      deposits of a month with their invoice status and matching clients
  draft        draft the invoice for one deposit (exact amount from the bank, through mxsat)
  verify       check a stamped XML against its draft and record the invoice
  record       record an invoice issued without a draft (e.g. before using this howware)
  discard      discard a pending draft
  ignore       mark a deposit as not to be invoiced, with the owner's reason
  declaration  record a declaration receipt (through mxsat) as an obligation to pay
  obligation   record another obligation (e.g. the accountant's fee)
  payments     bank payments that match open obligations exactly
  pay          record that a bank transaction paid an obligation
  close        the month for the accountant: deposits, invoices, totals, obligations

Exit codes: 0 ok · 2 invalid input · 3 memory problem · 4 adapter (mxsat) problem.
No network, no prompts, standard library only. Money in integer cents; dates at noon local time.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

__version__ = "0.1.0"
HERE = Path(__file__).resolve().parent
SEED = HERE / "seed.json"
MIN_MEMORY = (0, 3, 0)
MIN_MXSAT = (0, 1, 0)
OK, BAD_INPUT, MEMORY_ERROR, ADAPTER_ERROR = 0, 2, 3, 4
INCOME_TYPES = ("spei_in", "transfer_in", "cash_deposit", "deposit", "check_deposit")
OBLIGATION_KINDS = ("sat_declaration", "accountant_fee", "other")
PAYMENT_WINDOW_DAYS = 20  # a payment may come up to this many days after the due date


class ToolError(Exception):
    def __init__(self, message: str, code: int = BAD_INPUT):
        super().__init__(message)
        self.code = code


# -- memory adapter -----------------------------------------------------------------------
def find_helper(explicit: str | None) -> Path:
    for c in (explicit, os.environ.get("HOWWARE_MEMORY_HELPER"),
              Path.home() / ".claude/skills/project-memory/scripts/memory.py",
              Path.home() / ".codex/skills/project-memory/scripts/memory.py"):
        if c and Path(c).is_file():
            return Path(c)
    raise ToolError("project-memory is not installed (or pass --mem / HOWWARE_MEMORY_HELPER).", MEMORY_ERROR)


class Memory:
    def __init__(self, helper: Path, db: str | None):
        self.helper, self.db = helper, db

    def run(self, *args: str, stdin: dict | None = None) -> Any:
        for attempt in (1, 2):
            cmd = [sys.executable, str(self.helper)] + (["--db", self.db] if self.db else []) + list(args)
            proc = subprocess.run(cmd, input=json.dumps(stdin, ensure_ascii=False) if stdin is not None else None,
                                  capture_output=True, text=True, encoding="utf-8")
            if proc.returncode == 0:
                return json.loads(proc.stdout) if proc.stdout.strip() else None
            message = (proc.stderr or proc.stdout).strip()
            if attempt == 1 and "at least one second" in message:
                time.sleep(1.1)
                continue
            raise ToolError(f"memory {args[0]} failed: {message[-600:]}", MEMORY_ERROR)

    def check_version(self) -> None:
        out = subprocess.run([sys.executable, str(self.helper), "--version"], capture_output=True, text=True).stdout
        found = re.search(r"(\d+)\.(\d+)\.(\d+)", out or "")
        if not found or tuple(int(x) for x in found.groups()) < MIN_MEMORY:
            raise ToolError(f"project-memory >= {'.'.join(map(str, MIN_MEMORY))} is required (found: {out.strip()}).",
                            MEMORY_ERROR)

    def rows(self, *args: str) -> list[dict]:
        return self.run("list", *args, "--limit", "5000")["rows"]

    def write(self, by: str, content: str, kind: str = "user_statement", **sections) -> dict:
        return self.run("write", stdin={"source": {"type": kind, "content": content, "provided_by": by,
                                                   "captured_at": "now"},
                                        "performed_by": by, **sections})


# -- mxsat adapter ------------------------------------------------------------------------
class Mxsat:
    """Runs the mxsat adapter. Its own privacy check has already run on everything it returns."""

    def __init__(self, command: str):
        parts = shlex.split(command, posix=os.name != "nt")
        # on Windows shlex keeps the quotes around a path with spaces
        self.cmd = [p[1:-1] if len(p) > 1 and p[0] == p[-1] == '"' else p for p in parts]

    def run(self, *args: str) -> dict:
        try:
            proc = subprocess.run([*self.cmd, *args], capture_output=True, text=True, encoding="utf-8")
        except FileNotFoundError:
            raise ToolError("mxsat is not installed: uv tool install git+https://github.com/howware/mx-sat-documents",
                            ADAPTER_ERROR) from None
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise ToolError(f"mxsat {' '.join(args[:2])} gave no JSON: {(proc.stderr or '').strip()[-300:]}",
                            ADAPTER_ERROR) from None
        if not out.get("ok"):
            err = out.get("error", {})
            raise ToolError(f"mxsat {err.get('code')}: {err.get('message')}", ADAPTER_ERROR)
        return out

    def check_version(self) -> str:
        version = self.run("version")["version"]
        if tuple(int(x) for x in version.split(".")[:3]) < MIN_MXSAT:
            raise ToolError(f"mxsat >= {'.'.join(map(str, MIN_MXSAT))} is required (found {version}).", ADAPTER_ERROR)
        return version


# -- exact helpers ------------------------------------------------------------------------
def cents(value: Any) -> int:
    try:
        return int((Decimal(str(value).replace(",", "")) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError) as error:
        raise ToolError(f"Not an amount: {value!r}") from error


def decimal_text(c: int) -> str:
    return f"{'-' if c < 0 else ''}{abs(c) // 100}.{abs(c) % 100:02d}"


def money(c: int | None) -> str | None:
    if c is None:
        return None
    return f"{'-' if c < 0 else ''}${abs(c) // 100:,}.{abs(c) % 100:02d}"


def parse_offset(text: str) -> timezone:
    m = re.fullmatch(r"([+-])(\d{2}):?(\d{2})", text.strip())
    if not m:
        raise ToolError(f"Time zone offset must look like -07:00, not {text!r}")
    minutes = int(m.group(2)) * 60 + int(m.group(3))
    return timezone(timedelta(minutes=minutes if m.group(1) == "+" else -minutes))


def local_offset() -> str:
    z = datetime.now().astimezone().strftime("%z")
    return f"{z[:3]}:{z[3:]}"


def parse_day(text: str, what: str = "date") -> date:
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError):
        raise ToolError(f"{what} must be YYYY-MM-DD, not {text!r}") from None


def parse_month(text: str) -> tuple[date, date]:
    m = re.fullmatch(r"(\d{4})-(\d{2})", text or "")
    if not m or not 1 <= int(m.group(2)) <= 12:
        raise ToolError(f"Month must be YYYY-MM, not {text!r}")
    first = date(int(m.group(1)), int(m.group(2)), 1)
    nxt = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    return first, nxt - timedelta(days=1)


def noon(day: date, tz: timezone) -> str:
    return datetime(day.year, day.month, day.day, 12, tzinfo=tz).isoformat(timespec="seconds")


def day_of(value: Any) -> str | None:
    return str(value)[:10] if value else None


def key_part(text: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", text or ""):
        raise ToolError(f"Not a valid id: {text!r}")
    return text


# -- clients and their rules ----------------------------------------------------------------
def parse_rule(text: str) -> dict:
    rule: dict[str, Any] = {}
    for part in (p.strip() for p in (text or "").split(";") if p.strip()):
        name, _, value = part.partition("=")
        if name == "type":
            rule["type"] = value
        elif name == "account":
            rule["account"] = value
        elif name == "amount":
            rule["amount"] = int(value)
    return rule


def rule_text(tx_type: str, account: str | None, amount: int | None) -> str:
    if not re.fullmatch(r"[a-z_]{2,40}", tx_type or ""):
        raise ToolError(f"--match-type must be a transaction type such as spei_in or cash_deposit, not {tx_type!r}")
    parts = [f"type={tx_type}"]
    if account:
        parts.append(f"account={key_part(account if account.startswith('account:') else 'account:' + account)}")
    if amount is not None:
        if amount <= 0:
            raise ToolError("--match-amount must be positive")
        parts.append(f"amount={amount}")
    return ";".join(parts)


def load_clients(mem: Memory) -> list[dict]:
    rows = mem.rows("--entity-type", "client", "--column", "key", "--column", "name",
                    "--column", "fact:client_template", "--column", "fact:client_match")
    return [{"key": r["key"], "name": r["name"], "template": r["fact:client_template"],
             "rule": parse_rule(r["fact:client_match"] or ""), "match": r["fact:client_match"]} for r in rows]


def matches(rule: dict, tx: dict) -> bool:
    if not rule.get("type") or rule["type"] != tx["tx_type"]:
        return False
    if rule.get("account") and rule["account"] != tx["account"]:
        return False
    return not (rule.get("amount") is not None and rule["amount"] != tx["amount_cents"])


def resolve_client(clients: list[dict], ref: str) -> dict:
    ref_key = ref if ref.startswith("client:") else f"client:{ref}"
    found = [c for c in clients if c["key"] == ref_key or c["name"].lower() == ref.lower()]
    if len(found) != 1:
        raise ToolError(f"No client {ref!r}. Clients: {', '.join(c['key'] for c in clients) or 'none yet'}")
    return found[0]


# -- deposits and their invoices ------------------------------------------------------------
TX_COLUMNS = ("--column", "key", "--column", "occurred_at", "--column", "attr:amount", "--column", "attr:tx_type",
              "--column", "link:on_account/key", "--column", "attr:bank_description")


def tx_row(r: dict) -> dict:
    return {"tx": r["key"], "date": day_of(r["occurred_at"]), "amount_cents": r["attr:amount"],
            "amount": money(r["attr:amount"]), "tx_type": r["attr:tx_type"], "account": r["link:on_account/key"],
            "bank_description": r["attr:bank_description"]}


def deposits(mem: Memory, first: date, last: date) -> list[dict]:
    rows = mem.rows("--event-type", "transaction", "--where", "attr:amount > 0",
                    "--since", (first - timedelta(days=1)).isoformat(), "--until", (last + timedelta(days=2)).isoformat(),
                    *TX_COLUMNS)
    out = [tx_row(r) for r in rows if first.isoformat() <= day_of(r["occurred_at"]) <= last.isoformat()]
    return sorted(out, key=lambda t: (t["date"], t["tx"]))


def one_tx(mem: Memory, key: str) -> dict:
    rows = mem.rows("--event-type", "transaction", "--where", f"key = {key_part(key)}", *TX_COLUMNS)
    if not rows:
        raise ToolError(f"No bank transaction {key}. Import the statement first (finanzas-personales).")
    return tx_row(rows[0])


INVOICE_COLUMNS = ("--column", "key", "--column", "occurred_at", "--column", "attr:draft_id", "--column", "attr:cfdi_id",
                   "--column", "attr:invoice_total", "--column", "attr:invoice_subtotal",
                   "--column", "attr:invoice_transferred", "--column", "attr:invoice_withheld",
                   "--column", "attr:invoice_series", "--column", "attr:invoice_folio",
                   "--column", "attr:invoice_period", "--column", "attr:invoice_date", "--column", "attr:vat_treatment",
                   "--column", "attr:payment_form", "--column", "attr:capture_sheet",
                   "--column", "attr:accepted_with_differences",
                   "--column", "link:for_deposit/key", "--column", "link:for_client/key", "--column", "link:resolves/key")


def invoice_row(r: dict) -> dict:
    return {"event": r["key"], "draft_id": r["attr:draft_id"], "cfdi_id": r["attr:cfdi_id"],
            "series": r["attr:invoice_series"], "folio": r["attr:invoice_folio"],
            "date": day_of(r["attr:invoice_date"]), "period": r["attr:invoice_period"],
            "total_cents": r["attr:invoice_total"], "total": money(r["attr:invoice_total"]),
            "subtotal_cents": r["attr:invoice_subtotal"], "transferred_cents": r["attr:invoice_transferred"],
            "withheld_cents": r["attr:invoice_withheld"], "vat_treatment": r["attr:vat_treatment"],
            "payment_form": r["attr:payment_form"], "capture_sheet": r["attr:capture_sheet"],
            "accepted_with_differences": r["attr:accepted_with_differences"],
            "tx": r["link:for_deposit/key"], "client": r["link:for_client/key"], "resolves": r["link:resolves/key"]}


class Ledger:
    """Every invoice event, indexed by deposit: issued, pending drafts, ignored deposits."""

    def __init__(self, mem: Memory):
        self.issued = [invoice_row(r) for r in mem.rows("--event-type", "invoice_issued", *INVOICE_COLUMNS)]
        drafted = [invoice_row(r) for r in mem.rows("--event-type", "invoice_drafted", *INVOICE_COLUMNS)]
        discarded = mem.rows("--event-type", "invoice_discarded", "--column", "link:resolves/key")
        closed = {i["resolves"] for i in self.issued} | {r["link:resolves/key"] for r in discarded}
        self.all_drafted = drafted
        self.drafts = [d for d in drafted if d["event"] not in closed]
        self.ignored = {r["link:for_deposit/key"]: r["attr:reason_text"] for r in mem.rows(
            "--event-type", "deposit_ignored", "--column", "link:for_deposit/key", "--column", "attr:reason_text")}

    def drafted_count(self, draft_id: str) -> int:
        return sum(1 for d in self.all_drafted if d["draft_id"] == draft_id)

    def issued_for(self, tx: str) -> dict | None:
        return next((i for i in self.issued if i["tx"] == tx), None)

    def draft_for(self, tx: str) -> dict | None:
        return next((d for d in self.drafts if d["tx"] == tx), None)

    def status(self, tx: dict, clients: list[dict]) -> dict:
        out = dict(tx)
        candidates = [c for c in clients if matches(c["rule"], tx)]
        out["clients"] = [c["key"] for c in candidates]
        issued, draft = self.issued_for(tx["tx"]), self.draft_for(tx["tx"])
        if issued:
            out["status"], out["invoice"] = "invoiced", public_invoice(issued)
        elif draft:
            out["status"], out["invoice"] = "draft_pending", public_invoice(draft)
        elif tx["tx"] in self.ignored:
            out["status"], out["reason"] = "ignored", self.ignored[tx["tx"]]
        elif len(candidates) == 1:
            out["status"] = "to_invoice"
        elif candidates:
            out["status"] = "ambiguous"
        else:
            out["status"] = "unknown_client" if tx["tx_type"] in INCOME_TYPES else "not_income"
        return out


def public_invoice(i: dict) -> dict:
    return {k: v for k, v in i.items() if v is not None and k not in ("event", "resolves")}


def vat_treatment(doc: dict) -> str:
    kinds = set()
    for c in doc["concepts"]:
        for t in c["transfers"]:
            if t["tax"] != "IVA":
                continue
            if t["factor"] == "Exento":
                kinds.add("exempt")
            else:
                kinds.add(f"rate_{int(Decimal(t['rate']) * 100)}")
    return kinds.pop() if len(kinds) == 1 else ("mixed" if kinds else "none")


def issued_event(doc: dict, tz: timezone, *, tx: str | None, client: str | None, draft: dict | None,
                 accepted: bool = False) -> dict:
    day = parse_day(doc["issued_at"][:10], "invoice date")
    attrs = {"cfdi_id": doc["id"], "invoice_total": doc["total_cents"],
             "invoice_subtotal": cents(doc["subtotal"]),
             "invoice_transferred": cents(doc["taxes"]["transferred_total"] or 0),
             "invoice_withheld": cents(doc["taxes"]["withheld_total"] or 0),
             "invoice_series": doc["series"], "invoice_folio": doc["folio"], "invoice_date": noon(day, tz),
             "vat_treatment": vat_treatment(doc), "payment_form": doc["payment_form"]}
    if draft:
        attrs.update({"draft_id": draft["draft_id"], "invoice_period": draft["period"],
                      "accepted_with_differences": accepted})
    links = []
    if tx:
        links.append({"predicate": "for_deposit", "event": tx})
    if client:
        links.append({"predicate": "for_client", "entity": client})
    if draft:
        links.append({"predicate": "resolves", "event": draft["event"]})
    label = f"{doc['series'] or ''}{doc['folio'] or ''}"
    return {"key": f"ISSUED_{doc['id']}", "type": "invoice_issued", "occurred_at": noon(day, tz),
            "summary": f"Invoice {label} for {money(doc['total_cents'])}",
            "attributes": {k: v for k, v in attrs.items() if v is not None}, "links": links}


# -- obligations ----------------------------------------------------------------------------
OBLIGATION_COLUMNS = ("--column", "key", "--column", "occurred_at", "--column", "attr:obligation_kind",
                      "--column", "attr:obligation_label", "--column", "attr:obligation_amount",
                      "--column", "attr:obligation_due", "--column", "attr:obligation_period",
                      "--column", "attr:capture_line_valid_until")


def load_obligations(mem: Memory) -> list[dict]:
    paid = {r["link:resolves/key"]: r for r in mem.rows("--event-type", "obligation_paid", "--column", "key",
                                                         "--column", "link:resolves/key", "--column",
                                                         "link:paid_with/key", "--column", "occurred_at")}
    out = []
    for r in mem.rows("--event-type", "obligation", *OBLIGATION_COLUMNS):
        p = paid.get(r["key"])
        out.append({"obligation": r["key"], "kind": r["attr:obligation_kind"], "label": r["attr:obligation_label"],
                    "amount_cents": r["attr:obligation_amount"], "amount": money(r["attr:obligation_amount"]),
                    "due": day_of(r["attr:obligation_due"]), "period": r["attr:obligation_period"],
                    "recorded": day_of(r["occurred_at"]),
                    "capture_line_valid_until": day_of(r["attr:capture_line_valid_until"]),
                    "paid": bool(p) or r["attr:obligation_amount"] == 0,
                    "paid_with": p["link:paid_with/key"] if p else None})
    return sorted(out, key=lambda o: (o["due"] or "", o["obligation"]))


def describe_due(o: dict, today: date) -> dict:
    if o["paid"] or not o["due"]:
        return o
    days = (date.fromisoformat(o["due"]) - today).days
    return {**o, "due_in_days": days, "overdue": days < 0}


# -- commands -------------------------------------------------------------------------------
def cmd_setup(mem: Memory, mx: Mxsat, args, today: date) -> dict:
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    version = mx.check_version()
    result = mem.write(args.by, f"facturacion seed v{seed['seed_version']}", "helper_command",
                       predicates=[{**p, "distinct_from_similar": True} for p in seed["predicates"]])
    found = mem.rows("--event-type", "transaction", "--where", "attr:amount > 0", "--column", "key")
    return {"ok": True, "seed_version": seed["seed_version"], "mxsat": version, "deposits_in_memory": len(found),
            "warnings": result.get("warnings", []) + ([] if found else [
                "No bank deposits in this memory yet: import statements with finanzas-personales first."])}


def cmd_client(mem: Memory, mx: Mxsat, args, today: date) -> dict:
    key = f"client:{key_part(args.key)}" if not args.key.startswith("client:") else key_part(args.key)
    templates = {t["name"]: t for t in mx.run("cfdi", "templates")["templates"]}
    if args.template not in templates:
        raise ToolError(f"mxsat has no template {args.template!r} (has: {', '.join(templates) or 'none'}). "
                        "Create it from a real invoice: mxsat cfdi template <xml> --name <name>")
    amount = cents(args.match_amount) if args.match_amount else None
    rule = rule_text(args.match_type, args.match_account, amount)
    result = mem.write(args.by, args.source or f"Client {args.name}: template {args.template}, deposits {rule}",
                       entities=[{"key": key, "type": "client", "name": args.name}],
                       facts=[{"subject": key, "predicate": "client_template", "value": args.template, "valid_from": "now"},
                              {"subject": key, "predicate": "client_match", "value": rule, "valid_from": "now"}])
    t = templates[args.template]
    return {"ok": True, "client": key, "name": args.name, "template": args.template, "match": rule,
            "template_summary": {k: t.get(k) for k in ("receiver_rfc_kind", "payment_form", "payment_method",
                                                        "product_code", "transfers", "withholdings", "period")},
            "warnings": result.get("warnings", [])}


def cmd_clients(mem: Memory, mx: Mxsat, args, today: date) -> dict:
    return {"ok": True, "clients": [{k: c[k] for k in ("key", "name", "template", "match")} for c in load_clients(mem)]}


def cmd_pending(mem: Memory, mx: Mxsat, args, today: date) -> dict:
    if args.month:
        first, last = parse_month(args.month)
    else:
        first, last = today - timedelta(days=args.days), today
    clients, ledger = load_clients(mem), Ledger(mem)
    items = [ledger.status(t, clients) for t in deposits(mem, first, last)]
    if not args.all:
        items = [i for i in items if i["status"] not in ("invoiced", "ignored", "not_income")]
    counts: dict[str, int] = {}
    for i in items:
        counts[i["status"]] = counts.get(i["status"], 0) + 1
    return {"ok": True, "from": first.isoformat(), "to": last.isoformat(), "counts": counts, "deposits": items}


def cmd_draft(mem: Memory, mx: Mxsat, args, today: date) -> dict:
    tx = one_tx(mem, args.tx)
    if tx["amount_cents"] <= 0:
        raise ToolError("Only deposits (positive amounts) are invoiced.")
    clients, ledger = load_clients(mem), Ledger(mem)
    issued = ledger.issued_for(tx["tx"])
    if issued:
        raise ToolError(f"This deposit is already invoiced ({issued['series'] or ''}{issued['folio'] or ''}). "
                        "One payment, one invoice.")
    if args.client:
        client = resolve_client(clients, args.client)
    else:
        candidates = [c for c in clients if matches(c["rule"], tx)]
        if len(candidates) != 1:
            raise ToolError("Say which client this deposit is for (--client): "
                            + ("several match: " + ", ".join(c["key"] for c in candidates) if candidates
                               else "no client rule matches it."))
        client = candidates[0]
    day = parse_day(args.date, "--date") if args.date else today
    call = ["cfdi", "draft", "--template", client["template"], "--total", decimal_text(tx["amount_cents"]),
            "--ref", tx["tx"], "--date", day.isoformat()]
    if args.period:
        call += ["--period", args.period]
    if args.folio:
        call += ["--folio", args.folio]
    if args.replace:
        call += ["--replace"]
    d = mx.run(*call)["draft"]
    if d["total_cents"] != tx["amount_cents"]:
        raise ToolError(f"mxsat drafted {d['total']} but the deposit is {tx['amount']}; nothing recorded.",
                        ADAPTER_ERROR)
    tz = parse_offset(args.tz)
    event = {"key": f"DRAFT_{d['id']}", "type": "invoice_drafted", "occurred_at": "now",
             "summary": f"Invoice {d['series']}{d['folio']} drafted for {money(d['total_cents'])} ({client['name']})",
             "attributes": {"draft_id": d["id"], "invoice_total": d["total_cents"],
                            "invoice_subtotal": cents(d["subtotal"]),
                            "invoice_transferred": sum(cents(x["amount"]) for x in d["transfers"] if x.get("amount")),
                            "invoice_withheld": sum(cents(x["amount"]) for x in d["withholdings"] if x.get("amount")),
                            "invoice_series": d["series"], "invoice_folio": d["folio"],
                            "invoice_date": noon(parse_day(d["date"]), tz), "payment_form": d["payment_form"],
                            "capture_sheet": d.get("capture_sheet"),
                            **({"invoice_period": d["period"]} if d.get("period") else {}),
                            "requested_action": f"Capture invoice {d['series']}{d['folio']} in the SAT portal "
                                                f"and give the stamped XML for verification"},
             "pending_for": args.by,
             "links": [{"predicate": "for_deposit", "event": tx["tx"]},
                       {"predicate": "for_client", "entity": client["key"]}]}
    previous = ledger.draft_for(tx["tx"])
    if previous and previous["draft_id"] == d["id"] and d.get("unchanged"):
        return {"ok": True, "unchanged": True, "deposit": {k: tx[k] for k in ("tx", "date", "amount", "tx_type", "account")},
                "client": {"key": client["key"], "name": client["name"]}, "draft": d}
    events = []
    if previous:  # redone with --replace: the earlier draft event is closed, a new one opens
        n = ledger.drafted_count(previous["draft_id"])
        events.append({"key": f"DISCARD_{previous['event']}", "type": "invoice_discarded", "occurred_at": "now",
                       "summary": f"Draft {previous['draft_id']} redone", "attributes": {"reason_text": "redone"},
                       "links": [{"predicate": "resolves", "event": previous["event"]}]})
        event["key"] = f"DRAFT_{d['id']}_{n + 1}"
    mem.write(args.by, args.source or f"Invoice for deposit {tx['tx']}", events=[*events, event])
    return {"ok": True, "deposit": {k: tx[k] for k in ("tx", "date", "amount", "tx_type", "account")},
            "client": {"key": client["key"], "name": client["name"]}, "draft": d}


def find_draft(ledger: Ledger, draft_id: str) -> dict:
    draft = next((d for d in ledger.drafts if d["draft_id"] == draft_id), None)
    if not draft:
        done = next((i for i in ledger.issued if i["draft_id"] == draft_id), None)
        if done:
            raise ToolError(f"Draft {draft_id} is already recorded as invoice {done['series'] or ''}{done['folio'] or ''}.")
        raise ToolError(f"No pending draft {draft_id}.")
    return draft


def cmd_verify(mem: Memory, mx: Mxsat, args, today: date) -> dict:
    ledger = Ledger(mem)
    draft = find_draft(ledger, args.invoice)
    call = ["cfdi", "verify", args.xml, "--draft", args.invoice] + (["--accept-differences"] if args.accept_differences else [])
    v = mx.run(*call)["verification"]
    out = {"ok": True, "matches": v["matches"], "failed": v["failed"], "warnings": v["warnings"],
           "checks_passed": v["checks_passed"], "recorded": False}
    if v["draft"]["status"] != "issued":
        out["next"] = "Show the differences. Usually: cancel in the portal and capture again from the sheet."
        return out
    doc = mx.run("cfdi", "read", args.xml)["documents"][0]
    event = issued_event(doc, parse_offset(args.tz), tx=draft["tx"], client=draft["client"], draft=draft,
                         accepted=bool(v.get("accepted_with_differences")))
    mem.write(args.by, args.source or f"Stamped invoice verified against draft {args.invoice}", events=[event])
    out.update({"recorded": True, "invoice": {"series": doc["series"], "folio": doc["folio"], "total": money(doc["total_cents"]),
                                               "vat_treatment": event["attributes"]["vat_treatment"],
                                               "cfdi_id": doc["id"]}})
    return out


def cmd_record(mem: Memory, mx: Mxsat, args, today: date) -> dict:
    docs = mx.run("cfdi", "read", args.xml)["documents"]
    doc = docs[0]
    if not doc["stamped"] or doc["type"] != "I":
        raise ToolError("Only stamped income invoices (type I) are recorded.")
    clients, ledger = load_clients(mem), Ledger(mem)
    existing = next((i for i in ledger.issued if i["cfdi_id"] == doc["id"]), None)
    if existing:
        return {"ok": True, "unchanged": True, "invoice": public_invoice(existing)}
    client = resolve_client(clients, args.client)["key"] if args.client else None
    tx = None
    if args.tx:
        tx = one_tx(mem, args.tx)
        if tx["amount_cents"] != doc["total_cents"]:
            raise ToolError(f"The invoice total ({money(doc['total_cents'])}) is not the deposit ({tx['amount']}). "
                            "One payment, one invoice: record it without --tx, or pick the right deposit.")
        other = ledger.issued_for(tx["tx"])
        if other:
            raise ToolError(f"That deposit already has invoice {other['series'] or ''}{other['folio'] or ''}.")
        if not client:
            candidates = [c for c in clients if matches(c["rule"], tx)]
            client = candidates[0]["key"] if len(candidates) == 1 else None
    if not client:
        raise ToolError("Say which client the invoice is for (--client).")
    event = issued_event(doc, parse_offset(args.tz), tx=tx["tx"] if tx else None, client=client, draft=None)
    mem.write(args.by, args.source or f"Invoice {doc['series']}{doc['folio']} recorded", events=[event])
    return {"ok": True, "recorded": True,
            "invoice": {"series": doc["series"], "folio": doc["folio"], "date": doc["issued_at"][:10],
                        "total": money(doc["total_cents"]), "vat_treatment": event["attributes"]["vat_treatment"],
                        "client": client, "tx": tx["tx"] if tx else None, "cfdi_id": doc["id"]}}


def cmd_discard(mem: Memory, mx: Mxsat, args, today: date) -> dict:
    draft = find_draft(Ledger(mem), args.invoice)
    mx.run("cfdi", "discard", args.invoice)
    mem.write(args.by, args.reason, events=[{
        "key": f"DISCARD_{draft['event']}", "type": "invoice_discarded", "occurred_at": "now",
        "summary": f"Draft {args.invoice} discarded", "attributes": {"reason_text": args.reason},
        "links": [{"predicate": "resolves", "event": draft["event"]}]}])
    return {"ok": True, "discarded": args.invoice}


def cmd_ignore(mem: Memory, mx: Mxsat, args, today: date) -> dict:
    tx = one_tx(mem, args.tx)
    ledger = Ledger(mem)
    if ledger.issued_for(tx["tx"]) or ledger.draft_for(tx["tx"]):
        raise ToolError("That deposit has an invoice or a draft; discard the draft first.")
    mem.write(args.by, args.reason, events=[{
        "key": f"IGNORE_{tx['tx']}", "type": "deposit_ignored", "occurred_at": "now",
        "summary": f"Deposit {tx['amount']} on {tx['date']} is not invoiced", "attributes": {"reason_text": args.reason},
        "links": [{"predicate": "for_deposit", "event": tx["tx"]}]}])
    return {"ok": True, "ignored": tx["tx"], "reason": args.reason}


def obligation_event(key: str, kind: str, label: str, amount: int, due: date, period: str, tz: timezone, by: str,
                     occurred: str, extra: dict | None = None) -> dict:
    attrs = {"obligation_kind": kind, "obligation_label": label, "obligation_amount": amount,
             "obligation_due": noon(due, tz), "obligation_period": period, **(extra or {})}
    event = {"key": key, "type": "obligation", "occurred_at": occurred,
             "summary": f"{label}: {money(amount)} by {due.isoformat()}", "attributes": attrs}
    if amount > 0:
        event["pending_for"] = by
        attrs["requested_action"] = f"Pay {money(amount)} ({label}) by {due.isoformat()}"
    return event


def cmd_declaration(mem: Memory, mx: Mxsat, args, today: date) -> dict:
    a = mx.run("acuse", "read", args.pdf)["documents"][0]
    if not (a["id"] and a["due_date"] and a["fiscal_year"] and a["period_month"]):
        raise ToolError("The receipt has no operation number, due date or period; record it with `obligation`.")
    tz = parse_offset(args.tz)
    period = f"{a['fiscal_year']}-{a['period_month']:02d}"
    key = f"OBL_{a['id']}"
    label = f"SAT declaration {period}"
    extra = {"receipt_id": a["id"]}
    if a.get("capture_line_valid_until"):
        extra["capture_line_valid_until"] = noon(parse_day(a["capture_line_valid_until"]), tz)
    filed = parse_day(a["filed_at"][:10]) if a.get("filed_at") else today
    event = obligation_event(key, "sat_declaration", label, a["total_to_pay_cents"], parse_day(a["due_date"]),
                             period, tz, args.by, noon(filed, tz), extra)
    mem.write(args.by, args.source or f"Declaration receipt {period}", events=[event])
    return {"ok": True, "obligation": key, "period": period, "amount": money(a["total_to_pay_cents"]),
            "due": a["due_date"], "capture_line_valid_until": a.get("capture_line_valid_until"),
            "concepts": a["concepts"], "pending": a["total_to_pay_cents"] > 0}


def cmd_obligation(mem: Memory, mx: Mxsat, args, today: date) -> dict:
    if args.kind not in OBLIGATION_KINDS:
        raise ToolError(f"--kind must be one of {', '.join(OBLIGATION_KINDS)}")
    first, _ = parse_month(args.period)
    amount = cents(args.amount)
    if amount <= 0:
        raise ToolError("--amount must be positive")
    tz = parse_offset(args.tz)
    key = f"OBL_{args.kind}_{args.period}" + (f"_{key_part(args.key)}" if args.key else "")
    event = obligation_event(key, args.kind, args.label, amount, parse_day(args.due, "--due"), args.period, tz,
                             args.by, "now")
    mem.write(args.by, args.source or args.label, events=[event])
    return {"ok": True, "obligation": key, "amount": money(amount), "due": args.due}


def payment_candidates(mem: Memory, o: dict, used: set[str]) -> list[dict]:
    start = parse_day(o["recorded"]) - timedelta(days=3)
    end = parse_day(o["due"]) + timedelta(days=PAYMENT_WINDOW_DAYS)
    rows = mem.rows("--event-type", "transaction", "--where", f"attr:amount = {-o['amount_cents']}",
                    "--since", start.isoformat(), "--until", (end + timedelta(days=1)).isoformat(), *TX_COLUMNS)
    return [tx_row(r) for r in rows if r["key"] not in used and start.isoformat() <= day_of(r["occurred_at"]) <= end.isoformat()]


def cmd_payments(mem: Memory, mx: Mxsat, args, today: date) -> dict:
    obligations = load_obligations(mem)
    used = {o["paid_with"] for o in obligations if o["paid_with"]}
    out = []
    for o in obligations:
        if o["paid"] or (args.obligation and o["obligation"] != args.obligation):
            continue
        out.append({**describe_due(o, today), "candidates": payment_candidates(mem, o, used)})
    return {"ok": True, "open": out}


def cmd_pay(mem: Memory, mx: Mxsat, args, today: date) -> dict:
    o = next((x for x in load_obligations(mem) if x["obligation"] == args.obligation), None)
    if not o:
        raise ToolError(f"No obligation {args.obligation}.")
    if o["paid"]:
        return {"ok": True, "unchanged": True, "obligation": o["obligation"], "paid_with": o["paid_with"]}
    tx = one_tx(mem, args.tx)
    if tx["amount_cents"] != -o["amount_cents"]:
        raise ToolError(f"The transaction is {tx['amount']}, the obligation is {o['amount']}: they must be equal.")
    used = {x["paid_with"] for x in load_obligations(mem) if x["paid_with"]}
    if tx["tx"] in used:
        raise ToolError("That transaction already paid another obligation.")
    mem.write(args.by, args.source or f"{o['label']} paid", events=[{
        "key": f"PAID_{o['obligation']}", "type": "obligation_paid", "occurred_at": noon(parse_day(tx["date"]),
                                                                                         parse_offset(args.tz)),
        "summary": f"{o['label']} paid ({o['amount']})",
        "links": [{"predicate": "resolves", "event": o["obligation"]}, {"predicate": "paid_with", "event": tx["tx"]}]}])
    return {"ok": True, "obligation": o["obligation"], "paid_with": tx["tx"], "date": tx["date"], "amount": o["amount"]}


def cmd_brief(mem: Memory, mx: Mxsat, args, today: date) -> dict:
    clients, ledger = load_clients(mem), Ledger(mem)
    first = today - timedelta(days=args.days)
    to_check = [ledger.status(t, clients) for t in deposits(mem, first, today)]
    waiting = [t for t in to_check if t["status"] in ("to_invoice", "ambiguous", "unknown_client")]
    obligations = [describe_due(o, today) for o in load_obligations(mem) if not o["paid"]]
    return {"ok": True, "today": today.isoformat(), "clients": len(clients),
            "deposits_to_invoice": waiting,
            "drafts_to_capture": [public_invoice(d) for d in ledger.drafts],
            "accepted_with_differences": [public_invoice(i) for i in ledger.issued
                                          if i["accepted_with_differences"]][-3:],
            "obligations_open": obligations}


def cmd_close(mem: Memory, mx: Mxsat, args, today: date) -> dict:
    first, last = parse_month(args.month)
    clients, ledger = load_clients(mem), Ledger(mem)
    names = {c["key"]: c["name"] for c in clients}
    deps = [ledger.status(t, clients) for t in deposits(mem, first, last)]
    deps = [d for d in deps if d["status"] != "not_income"]
    issued = sorted((i for i in ledger.issued if i["date"] and first.isoformat() <= i["date"] <= last.isoformat()),
                    key=lambda i: (i["series"] or "", int(i["folio"]) if (i["folio"] or "").isdigit() else 0))
    by_vat: dict[str, int] = {}
    for i in issued:
        by_vat[i["vat_treatment"]] = by_vat.get(i["vat_treatment"], 0) + (i["subtotal_cents"] or 0)
    totals = {"invoices": len(issued),
              "subtotal_cents": sum(i["subtotal_cents"] or 0 for i in issued),
              "transferred_cents": sum(i["transferred_cents"] or 0 for i in issued),
              "withheld_cents": sum(i["withheld_cents"] or 0 for i in issued),
              "total_cents": sum(i["total_cents"] or 0 for i in issued),
              "subtotal_by_vat_treatment_cents": by_vat}
    totals["total"] = money(totals["total_cents"])
    month = f"{first.year}-{first.month:02d}"
    obligations = [describe_due(o, today) for o in load_obligations(mem) if o["period"] == month]
    result = {"ok": True, "month": month,
              "invoices": [{**public_invoice(i), "client_name": names.get(i["client"])} for i in issued],
              "totals": totals,
              "deposits_without_invoice": [d for d in deps if d["status"] not in ("invoiced", "ignored")],
              "invoices_without_deposit": [public_invoice(i) for i in issued if not i["tx"]],
              "deposits_ignored": [d for d in deps if d["status"] == "ignored"],
              "obligations": obligations}
    if args.out:
        path = Path(args.out)
        if path.suffix.lower() != ".md":
            raise ToolError("--out must be a .md file")
        path.write_text(close_sheet(result), encoding="utf-8")
        result["written"] = str(path)
    return result


def close_sheet(r: dict) -> str:
    """A summary for the accountant. Only folios, dates, amounts and the owner's client labels."""
    t = r["totals"]
    vat_names = {"rate_0": "IVA tasa 0 %", "rate_8": "IVA 8 %", "rate_16": "IVA 16 %", "exempt": "Exento",
                 "mixed": "Mixto", "none": "Sin IVA"}
    lines = [f"# Facturación {r['month']}", "", "## Facturas emitidas", "",
             "| Folio | Fecha | Cliente | Subtotal | IVA | Retenciones | Total | Tratamiento |",
             "|---|---|---|---:|---:|---:|---:|---|"]
    for i in r["invoices"]:
        lines.append(f"| {i.get('series', '')}{i.get('folio', '')} | {i.get('date', '')} | {i.get('client_name') or ''} | "
                     f"{money(i.get('subtotal_cents'))} | {money(i.get('transferred_cents'))} | "
                     f"{money(i.get('withheld_cents'))} | {i.get('total')} | {vat_names.get(i.get('vat_treatment'), '')} |")
    lines += ["", "## Totales", "", "| Concepto | Monto |", "|---|---:|",
              f"| Subtotal | {money(t['subtotal_cents'])} |", f"| IVA trasladado | {money(t['transferred_cents'])} |",
              f"| Retenciones | {money(t['withheld_cents'])} |", f"| Total | {money(t['total_cents'])} |"]
    for k, v in sorted(t["subtotal_by_vat_treatment_cents"].items()):
        lines.append(f"| Subtotal {vat_names.get(k, k)} | {money(v)} |")
    if r["deposits_without_invoice"]:
        lines += ["", "## Depósitos sin factura", "", "| Fecha | Monto | Estado |", "|---|---:|---|"]
        lines += [f"| {d['date']} | {d['amount']} | {d['status']} |" for d in r["deposits_without_invoice"]]
    if r["obligations"]:
        lines += ["", "## Obligaciones del periodo", "", "| Concepto | Monto | Vence | Pagada |", "|---|---:|---|---|"]
        lines += [f"| {o['label']} | {o['amount']} | {o['due']} | {'sí' if o['paid'] else 'no'} |" for o in r["obligations"]]
    return "\n".join(lines) + "\n"


# -- main -------------------------------------------------------------------------------------
def main() -> None:
    p = argparse.ArgumentParser(prog="facturacion.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"facturacion.py {__version__}")
    p.add_argument("--mem", help="Path to project-memory's memory.py")
    p.add_argument("--db", help="Path to the memory (default: the current project's)")
    p.add_argument("--mxsat", default=os.environ.get("FAC_MXSAT", "mxsat"), help="How to run the mxsat adapter")
    p.add_argument("--tz", default=os.environ.get("HOWWARE_TZ") or local_offset(), help="UTC offset, e.g. --tz=-07:00")
    p.add_argument("--today", default=os.environ.get("FAC_TODAY"), help=argparse.SUPPRESS)  # fixed clock for tests
    sub = p.add_subparsers(dest="command", required=True)

    def by(s, source=True):
        s.add_argument("--by", required=True, help="person:<id> of the owner")
        if source:
            s.add_argument("--source", help="The owner's literal words")
        return s

    by(sub.add_parser("setup"), source=False)
    s = sub.add_parser("brief")
    s.add_argument("--days", type=int, default=62, help="how far back to look for deposits")
    s = by(sub.add_parser("client"))
    s.add_argument("--key", required=True)
    s.add_argument("--name", required=True, help="the owner's label for the client")
    s.add_argument("--template", required=True, help="mxsat template name")
    s.add_argument("--match-type", required=True, help="transaction type of its deposits, e.g. spei_in")
    s.add_argument("--match-account", help="only deposits to this account (ACC_…)")
    s.add_argument("--match-amount", help="only deposits of exactly this amount")
    sub.add_parser("clients")
    s = sub.add_parser("pending")
    s.add_argument("--month", help="YYYY-MM (default: the last --days days)")
    s.add_argument("--days", type=int, default=62)
    s.add_argument("--all", action="store_true", help="include invoiced, ignored and non-income deposits")
    s = by(sub.add_parser("draft"))
    s.add_argument("--tx", required=True)
    s.add_argument("--client")
    s.add_argument("--date", help="invoice date YYYY-MM-DD (default today)")
    s.add_argument("--period", help="YYYY-MM, only to override the template's rule")
    s.add_argument("--folio")
    s.add_argument("--replace", action="store_true")
    s = by(sub.add_parser("verify"))
    s.add_argument("--invoice", required=True, help="draft id")
    s.add_argument("--xml", required=True)
    s.add_argument("--accept-differences", action="store_true")
    s = by(sub.add_parser("record"))
    s.add_argument("--xml", required=True)
    s.add_argument("--tx")
    s.add_argument("--client")
    s = by(sub.add_parser("discard"), source=False)
    s.add_argument("--invoice", required=True)
    s.add_argument("--reason", required=True)
    s = by(sub.add_parser("ignore"), source=False)
    s.add_argument("--tx", required=True)
    s.add_argument("--reason", required=True)
    s = by(sub.add_parser("declaration"))
    s.add_argument("--pdf", required=True)
    s = by(sub.add_parser("obligation"))
    s.add_argument("--kind", required=True, help=" | ".join(OBLIGATION_KINDS))
    s.add_argument("--label", required=True)
    s.add_argument("--amount", required=True)
    s.add_argument("--due", required=True, help="YYYY-MM-DD")
    s.add_argument("--period", required=True, help="YYYY-MM it is for")
    s.add_argument("--key", help="tells apart two obligations of the same kind and period")
    s = sub.add_parser("payments")
    s.add_argument("--obligation")
    s = by(sub.add_parser("pay"))
    s.add_argument("--obligation", required=True)
    s.add_argument("--tx", required=True)
    s = sub.add_parser("close")
    s.add_argument("--month", required=True)
    s.add_argument("--out", help="also write a summary for the accountant (.md)")
    args = p.parse_args()

    commands = {"setup": cmd_setup, "brief": cmd_brief, "client": cmd_client, "clients": cmd_clients,
                "pending": cmd_pending, "draft": cmd_draft, "verify": cmd_verify, "record": cmd_record,
                "discard": cmd_discard, "ignore": cmd_ignore, "declaration": cmd_declaration,
                "obligation": cmd_obligation, "payments": cmd_payments, "pay": cmd_pay, "close": cmd_close}
    try:
        tz = parse_offset(args.tz)
        today = parse_day(args.today, "--today") if args.today else datetime.now(tz).date()
        mem = Memory(find_helper(args.mem), args.db)
        mem.check_version()
        result = commands[args.command](mem, Mxsat(args.mxsat), args, today)
        code = OK
    except ToolError as error:
        result, code = {"ok": False, "error": {"code": error.code, "message": str(error)}}, error.code
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(code)


if __name__ == "__main__":
    main()

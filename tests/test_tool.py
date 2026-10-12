"""Tests of facturacion.py against a real, temporary memory and the real mxsat adapter. Synthetic data only."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skill" / "facturacion" / "scripts" / "facturacion.py"
sys.path.insert(0, str(TOOL.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import facturacion  # noqa: E402
import synthetic as syn  # noqa: E402

BY = "person:test"
TODAY = "2026-10-11"


def find_helper() -> Path | None:
    for c in (os.environ.get("HOWWARE_MEMORY_HELPER"), ROOT.parent / "long-term-memory-for-AI" / "db" / "memory.py",
              Path.home() / ".claude/skills/project-memory/scripts/memory.py"):
        if c and Path(c).is_file():
            return Path(c)
    return None


HELPER = find_helper()
MXSAT = shutil.which("mxsat")


class ExactHelpersTest(unittest.TestCase):
    def test_money_and_rules(self):
        self.assertEqual(facturacion.cents("50,407.87"), 5040787)
        self.assertEqual(facturacion.decimal_text(500000), "5000.00")
        self.assertEqual(facturacion.money(-123400), "-$1,234.00")
        rule = facturacion.rule_text("cash_deposit", "ACC_d1", 500000)
        self.assertEqual(rule, "type=cash_deposit;account=account:ACC_d1;amount=500000")
        tx = {"tx_type": "cash_deposit", "account": "account:ACC_d1", "amount_cents": 500000}
        self.assertTrue(facturacion.matches(facturacion.parse_rule(rule), tx))
        self.assertFalse(facturacion.matches(facturacion.parse_rule(rule), {**tx, "amount_cents": 500001}))
        for bad in ("SPEI RECIBIDO", "", "x"):
            with self.assertRaises(facturacion.ToolError):
                facturacion.rule_text(bad, None, None)

    def test_month_bounds(self):
        first, last = facturacion.parse_month("2028-02")
        self.assertEqual((first.isoformat(), last.isoformat()), ("2028-02-01", "2028-02-29"))
        with self.assertRaises(facturacion.ToolError):
            facturacion.parse_month("2026-13")


@unittest.skipUnless(HELPER and MXSAT, "needs project-memory and the mxsat adapter")
class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.db = str(self.dir / "memory.sqlite")
        self.env = {**os.environ, "MXSAT_KEY": "test-key", "MXSAT_STORE": str(self.dir / "mxsat-private"),
                    "FAC_TODAY": TODAY}
        self.env.pop("FAC_MXSAT", None)
        subprocess.run([sys.executable, str(HELPER), "--db", self.db, "init", "--owner-name", "Test",
                        "--owner-key", BY], check=True, capture_output=True)
        subprocess.run([sys.executable, str(HELPER), "--db", self.db, "write"], input=json.dumps(syn.finanzas_write(BY)),
                       check=True, capture_output=True, text=True, encoding="utf-8")
        self.tool("setup", "--by", BY)
        self.export149 = self.xml("export149.xml", syn.export_xml("149", "2026-09-30", "50407.87",
                                                                  "0F8D2C1A-1111-4A2B-9C3D-000000000001"))
        self.rent151 = self.xml("rent151.xml", syn.rent_xml("151", "2026-09-30", "5000.00",
                                                           "0F8D2C1A-2222-4A2B-9C3D-000000000002"))
        self.mxsat("cfdi", "template", str(self.export149), "--name", "export")
        self.mxsat("cfdi", "template", str(self.rent151), "--name", "renta")
        self.tool("client", "--key", "us-company", "--name", "US company", "--template", "export",
                  "--match-type", "spei_in", "--match-account", "ACC_d1", "--by", BY,
                  "--source", "Todos los SPEI recibidos en la cuenta de débito son de la empresa")
        self.tool("client", "--key", "rent", "--name", "Rent", "--template", "renta", "--match-type", "cash_deposit",
                  "--match-amount", "5000", "--by", BY, "--source", "Los depósitos de 5,000 en efectivo son la renta")

    def tearDown(self):
        self.tmp.cleanup()

    def xml(self, name: str, text: str) -> Path:
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def mxsat(self, *args: str) -> dict:
        proc = subprocess.run(["mxsat", *args], capture_output=True, text=True, encoding="utf-8", env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return json.loads(proc.stdout)

    def tool(self, *args: str, code: int = 0, mxsat: str | None = None) -> dict:
        extra = ["--mxsat", mxsat] if mxsat else []
        proc = subprocess.run([sys.executable, str(TOOL), "--mem", str(HELPER), "--db", self.db, "--tz=-07:00",
                               *extra, *args], capture_output=True, text=True, encoding="utf-8", env=self.env)
        self.assertEqual(proc.returncode, code, proc.stdout + proc.stderr)
        return json.loads(proc.stdout)

    def statuses(self, month: str = "2026-09") -> dict:
        return {d["tx"]: d["status"] for d in self.tool("pending", "--month", month, "--all")["deposits"]}

    def stamp(self, draft_id: str, uuid: str, **changes) -> Path:
        draft = json.loads((self.dir / "mxsat-private" / "drafts" / f"{draft_id}.json").read_text(encoding="utf-8"))
        return self.xml(f"{draft_id}.xml", syn.stamped_from_draft(draft, uuid, **changes))

    def test_pending_classifies_deposits_by_the_owners_rules(self):
        self.assertEqual(self.statuses(), {"TX_cash_other": "unknown_client", "TX_exp_sep_a": "to_invoice",
                                           "TX_rent_sep": "to_invoice", "TX_exp_sep_b": "to_invoice",
                                           "TX_card_pay": "not_income"})
        default = self.tool("pending", "--month", "2026-09")
        self.assertNotIn("TX_card_pay", [d["tx"] for d in default["deposits"]])

    def test_record_a_past_invoice_against_its_deposit(self):
        out = self.tool("record", "--xml", str(self.export149), "--tx", "TX_exp_sep_a", "--by", BY)
        self.assertEqual(out["invoice"]["vat_treatment"], "rate_0")
        self.assertEqual(out["invoice"]["client"], "client:us-company")
        self.assertEqual(self.statuses()["TX_exp_sep_a"], "invoiced")
        self.assertTrue(self.tool("record", "--xml", str(self.export149), "--tx", "TX_exp_sep_a", "--by", BY)["unchanged"])
        wrong = self.tool("record", "--xml", str(self.rent151), "--tx", "TX_exp_sep_b", "--by", BY, code=2)
        self.assertIn("One payment, one invoice", wrong["error"]["message"])

    def test_draft_capture_verify_cycle(self):
        out = self.tool("draft", "--tx", "TX_rent_sep", "--date", "2026-09-30", "--by", BY)
        d = out["draft"]
        self.assertEqual((d["id"], d["period"], d["total"]), ("renta-A152", "2026-10", "5000.00"))
        self.assertEqual(out["client"]["key"], "client:rent")
        self.assertEqual(self.statuses()["TX_rent_sep"], "draft_pending")
        brief = self.tool("brief")
        self.assertEqual([x["draft_id"] for x in brief["drafts_to_capture"]], ["renta-A152"])
        again = self.tool("draft", "--tx", "TX_rent_sep", "--date", "2026-09-30", "--by", BY)
        self.assertTrue(again["unchanged"])

        xml = self.stamp("renta-A152", "0F8D2C1A-3333-4A2B-9C3D-000000000003")
        v = self.tool("verify", "--invoice", "renta-A152", "--xml", str(xml), "--by", BY)
        self.assertTrue(v["matches"] and v["recorded"])
        self.assertEqual(v["invoice"]["vat_treatment"], "exempt")
        self.assertEqual(self.statuses()["TX_rent_sep"], "invoiced")
        self.assertEqual(self.tool("brief")["drafts_to_capture"], [])
        twice = self.tool("draft", "--tx", "TX_rent_sep", "--by", BY, code=2)
        self.assertIn("already invoiced", twice["error"]["message"])

    def test_rent_period_comes_from_the_arrendamiento_howware(self):
        """Shared memory: arrendamiento applied the September deposit to September's rent (paid late), so the
        invoice is for September even though the template's rule would say the next month."""
        reading = {"source": {"type": "import", "content": "arrendamiento applied a payment", "provided_by": BY,
                              "captured_at": "now"}, "performed_by": BY,
                   "predicates": [{"id": "rent_period", "value_type": "text", "cardinality": "one"},
                                  {"id": "paid_with", "value_type": "any", "cardinality": "one"}],
                   "events": [{"key": "RENT_sep", "type": "rent_applied", "occurred_at": "2026-09-19T12:00:00-07:00",
                               "attributes": {"rent_period": "2026-09"},
                               "links": [{"predicate": "paid_with", "event": "TX_rent_sep"}]}]}
        subprocess.run([sys.executable, str(HELPER), "--db", self.db, "write"], input=json.dumps(reading),
                       check=True, capture_output=True, text=True, encoding="utf-8")
        d = self.tool("draft", "--tx", "TX_rent_sep", "--date", "2026-09-30", "--by", BY)["draft"]
        self.assertEqual(d["period"], "2026-09")
        override = self.tool("draft", "--tx", "TX_rent_sep", "--date", "2026-09-30", "--period", "2026-10",
                             "--replace", "--by", BY)["draft"]
        self.assertEqual(override["period"], "2026-10")

    def test_import_statements_without_another_howware(self):
        statement = str(ROOT / "tests" / "fixtures" / "bbva_debit.json")
        first = self.tool("import", statement, "--by", BY)["statements"][0]
        self.assertEqual((first["transactions_new"], first["transactions_existing"]), (7, 0))
        again = self.tool("import", statement, "--by", BY)["statements"][0]
        self.assertEqual((again["transactions_new"], again["transactions_existing"]), (0, 7))
        deposits = self.tool("pending", "--month", "2026-09", "--all")["deposits"]
        self.assertTrue(any(d["tx"].startswith("TX_") and d["tx"] not in syn.KEYS for d in deposits))

    def test_records_module_is_mxbanks_copy(self):
        found = [p / "src" / "mxbank" / "records.py" for p in (ROOT.parent / "mx-bank-statement-reader",
                                                              ROOT / "mx-bank-statement-reader")]
        original = next((p for p in found if p.is_file()), None)
        if not original:
            self.skipTest("the mxbank repository is not checked out (../mx-bank-statement-reader)")
        self.assertEqual((TOOL.parent / "mxbank_records.py").read_text(encoding="utf-8").splitlines(),
                         original.read_text(encoding="utf-8").splitlines(),
                         "Copy src/mxbank/records.py from mxbank to mxbank_records.py again")

    def test_verify_reports_differences_and_keeps_the_draft_open(self):
        self.tool("draft", "--tx", "TX_exp_sep_b", "--date", "2026-09-30", "--by", BY)
        xml = self.stamp("export-A152", "0F8D2C1A-4444-4A2B-9C3D-000000000004", comprobante={"FormaPago": "99"})
        v = self.tool("verify", "--invoice", "export-A152", "--xml", str(xml), "--by", BY)
        self.assertFalse(v["matches"] or v["recorded"])
        self.assertIn("FormaPago", [f["field"] for f in v["failed"]])
        self.assertEqual(self.statuses()["TX_exp_sep_b"], "draft_pending")

    def test_ambiguous_and_ignored_deposits(self):
        self.tool("client", "--key", "other", "--name", "Other", "--template", "export", "--match-type", "spei_in",
                  "--by", BY)
        self.assertEqual(self.statuses()["TX_exp_sep_a"], "ambiguous")
        err = self.tool("draft", "--tx", "TX_exp_sep_a", "--by", BY, code=2)
        self.assertIn("several match", err["error"]["message"])
        out = self.tool("draft", "--tx", "TX_exp_sep_a", "--client", "us-company", "--date", "2026-09-30", "--by", BY)
        self.assertEqual(out["client"]["key"], "client:us-company")
        self.tool("ignore", "--tx", "TX_cash_other", "--reason", "Me devolvieron un préstamo", "--by", BY)
        self.assertEqual(self.statuses()["TX_cash_other"], "ignored")

    def test_client_needs_an_existing_template(self):
        err = self.tool("client", "--key", "x", "--name", "X", "--template", "nope", "--match-type", "spei_in",
                        "--by", BY, code=2)
        self.assertIn("no template", err["error"]["message"])

    def test_declaration_and_obligations_are_paid_exactly(self):
        fake = f'"{sys.executable}" "{Path(__file__).resolve().parent / "synthetic.py"}"'
        out = self.tool("declaration", "--pdf", "acuse.pdf", "--by", BY, mxsat=fake)
        self.assertEqual((out["period"], out["amount"], out["due"]), ("2026-09", "$1,234.00", "2026-10-23"))
        self.tool("obligation", "--kind", "accountant_fee", "--label", "Honorarios contadora", "--amount", "1800",
                  "--due", "2026-10-15", "--period", "2026-09", "--by", BY)
        open_ = {o["obligation"]: o for o in self.tool("payments")["open"]}
        sat = open_[out["obligation"]]
        self.assertEqual([c["tx"] for c in sat["candidates"]], ["TX_sat_pay"])   # TX_other_out differs by one peso
        self.assertEqual(sat["due_in_days"], 12)
        fee = open_["OBL_accountant_fee_2026-09"]
        self.assertEqual([c["tx"] for c in fee["candidates"]], ["TX_fee_pay"])
        wrong = self.tool("pay", "--obligation", out["obligation"], "--tx", "TX_other_out", "--by", BY, code=2)
        self.assertIn("must be equal", wrong["error"]["message"])
        self.tool("pay", "--obligation", out["obligation"], "--tx", "TX_sat_pay", "--by", BY)
        self.assertEqual([o["obligation"] for o in self.tool("brief")["obligations_open"]], ["OBL_accountant_fee_2026-09"])

    def test_close_month_for_the_accountant(self):
        self.tool("record", "--xml", str(self.export149), "--tx", "TX_exp_sep_a", "--by", BY)
        self.tool("draft", "--tx", "TX_rent_sep", "--date", "2026-09-30", "--by", BY)
        self.tool("verify", "--invoice", "renta-A152",
                  "--xml", str(self.stamp("renta-A152", "0F8D2C1A-5555-4A2B-9C3D-000000000005")), "--by", BY)
        sheet = self.dir / "cierre.md"
        out = self.tool("close", "--month", "2026-09", "--out", str(sheet))
        self.assertEqual([i["folio"] for i in out["invoices"]], ["149", "152"])
        self.assertEqual(out["totals"]["total_cents"], 5540787)
        self.assertEqual(out["totals"]["subtotal_by_vat_treatment_cents"], {"rate_0": 5040787, "exempt": 500000})
        self.assertEqual(sorted(d["tx"] for d in out["deposits_without_invoice"]), ["TX_cash_other", "TX_exp_sep_b"])
        text = sheet.read_text(encoding="utf-8")
        self.assertIn("| A149 |", text)
        self.assertNotIn(syn.ISSUER_RFC, text)
        self.assertNotIn("SANCHEZ", text)

    def test_adapter_errors_have_their_own_exit_code(self):
        out = self.tool("clients", mxsat="mxsat-does-not-exist")  # clients never calls mxsat
        self.assertEqual(len(out["clients"]), 2)
        err = self.tool("record", "--xml", str(self.dir / "missing.xml"), "--by", BY, code=4)
        self.assertIn("mxsat", err["error"]["message"])


if __name__ == "__main__":
    unittest.main()

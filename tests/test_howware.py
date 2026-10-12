"""Conformance with the howware specification 0.2 (https://howware.org): manifest, versions and protocol."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "howware.json").read_text(encoding="utf-8"))
SKILL = ROOT / MANIFEST["skill"]


class ManifestTest(unittest.TestCase):
    def test_required_fields(self):
        for field in ("howware", "name", "version", "description", "license", "hosts", "skill", "tools", "memory",
                      "privacy"):
            self.assertIn(field, MANIFEST)
        for key in ("stays_local", "agent_sees", "cannot_guarantee"):
            self.assertTrue(MANIFEST["privacy"][key], key)

    def test_versions_match_the_code(self):
        out = subprocess.run([sys.executable, str(SKILL / "scripts" / "facturacion.py"), "--version"],
                             capture_output=True, text=True).stdout
        self.assertEqual(out.split()[-1], MANIFEST["version"])
        seed = json.loads((SKILL / "scripts" / "seed.json").read_text(encoding="utf-8"))
        self.assertEqual(seed["seed_version"], MANIFEST["memory"]["seed_version"])

    def test_tool_declares_no_network(self):
        source = (SKILL / "scripts" / "facturacion.py").read_text(encoding="utf-8")
        self.assertFalse(re.search(r"^\s*(import|from)\s+(socket|urllib|http|requests)\b", source, re.M))
        self.assertFalse(next(t for t in MANIFEST["tools"] if t["name"] == "facturacion.py")["network"])


class AdapterBoundaryTest(unittest.TestCase):
    def test_the_tool_never_opens_sat_documents_itself(self):
        """Specification §2: the core reaches documents only through adapters (mxsat)."""
        source = (SKILL / "scripts" / "facturacion.py").read_text(encoding="utf-8")
        self.assertFalse(re.search(r"^\s*(import|from)\s+(xml|pdfplumber|zipfile)", source, re.M))
        names = {a["name"] for a in MANIFEST["adapters"]}
        self.assertTrue({"project-memory", "mxsat"} <= names)


class ProtocolTest(unittest.TestCase):
    def test_required_sections(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\nname: " + MANIFEST["name"]))
        for heading in ("Rules", "Exactness boundary", "Cold start", "Workflows", "Approval", "Presenting results"):
            self.assertRegex(text, rf"(?m)^## {heading}", heading)
        self.assertGreaterEqual(len(re.findall(r"(?m)^### \d+\. ", text)), 6, "workflows")

    def test_conversation_scenarios_exist(self):
        rows = [line for line in (ROOT / "tests" / "conversations.md").read_text(encoding="utf-8").splitlines()
                if re.match(r"\| \d+ \|", line)]
        self.assertGreaterEqual(len(rows), 8)


if __name__ == "__main__":
    unittest.main()

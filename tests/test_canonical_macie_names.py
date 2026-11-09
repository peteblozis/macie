"""Canonical public product naming regression checks; no provider calls."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "prod_shell/src/macie_b.py",
    ROOT / "prod_shell/src/macie_b_portal.py",
    ROOT / "prod_shell/src/commercial_portal.py",
    ROOT / "prod_shell/src/macie_a_portal.py",
    ROOT / "prod_shell/src/macie_c_portal.py",
    ROOT / "prod_shell/src/macie_b_template.py",
    ROOT / "prod_shell/src/macie_c_template.py",
    ROOT / "docs/MACIE_PRODUCT_BOUNDARIES_2026.md",
]

class CanonicalNamesTest(unittest.TestCase):
    def test_public_labels_use_canonical_name(self):
        for path in FILES:
            source = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                self.assertNotIn('"product": "MACIE-B"', source)
                self.assertNotIn('"product":"MACIE-B"', source)
                self.assertNotIn('MACIE B', source)
                self.assertNotIn('MACIE C', source)
                self.assertNotIn('MACIE A', source)

    def test_compatibility_keys_remain(self):
        source = FILES[2].read_text(encoding="utf-8")
        self.assertIn("MACIE_B_INCLUDED_IN_PLAN", source)
        self.assertIn("MACIE-B-PROMPT", source)

if __name__ == "__main__":
    unittest.main()

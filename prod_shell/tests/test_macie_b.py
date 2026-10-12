import unittest
from prod_shell.src.macie_b import enhance_prompt

class MacieBTests(unittest.TestCase):
    def test_enhances_customer_prompt(self):
        calls = []
        def claude(prompt):
            calls.append(prompt)
            return "Improved prompt"
        result = enhance_prompt("Draft a report", claude)
        self.assertEqual(result["provider"], "claude")
        self.assertEqual(result["enhanced_prompt"], "Improved prompt")
        self.assertIn("Draft a report", calls[0])

    def test_rejects_empty_prompt(self):
        with self.assertRaises(ValueError):
            enhance_prompt(" ", lambda _: "anything")

    def test_rejects_missing_claude_response(self):
        with self.assertRaises(RuntimeError):
            enhance_prompt("Draft", lambda _: "")

    def test_rejects_oversize_prompt(self):
        with self.assertRaises(ValueError):
            enhance_prompt("x" * 20001, lambda _: "anything")

if __name__ == "__main__":
    unittest.main()

import unittest
from prod_shell.src.macie_b import enhance_prompt

class MacieBTests(unittest.TestCase):
    def run_review(self, prompt="Draft a report", **overrides):
        args={"claude_review":lambda _: "Claude improvements",
              "chatgpt_review":lambda _: "ChatGPT improvements",
              "synthesize":lambda original,c,g: "Combined improved prompt"}
        args.update(overrides)
        return enhance_prompt(prompt, **args)

    def test_any_origin_prompt_gets_two_reviews(self):
        result=self.run_review("Prompt written outside MACIE")
        self.assertEqual(result["status"], "CONSENSUS")
        self.assertEqual(set(result["model_reviews"]), {"claude","chatgpt"})

    def test_missing_lane_never_claims_consensus(self):
        result=self.run_review(chatgpt_review=lambda _: "")
        self.assertEqual(result["status"], "NON-CONSENSUS")
        self.assertIsNone(result["enhanced_prompt"])

    def test_synthesis_failure_never_claims_consensus(self):
        result=self.run_review(synthesize=lambda *args: "")
        self.assertEqual(result["status"], "NON-CONSENSUS")

    def test_empty_prompt_denied(self):
        with self.assertRaises(ValueError):
            self.run_review(" ")

    def test_oversized_prompt_denied(self):
        with self.assertRaises(ValueError):
            self.run_review("x"*20001)

if __name__=="__main__":
    unittest.main()

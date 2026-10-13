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

    def test_customer_key_requires_real_two_model_identity(self):
        from prod_shell.src.macie_b import enhance_with_customer_key
        class Response:
            def __init__(self,model):
                self.model=model
            def raise_for_status(self): pass
            def json(self):
                return {"model":self.model,"choices":[{"message":{"content":"Improved"}}]}
        class FakeTransport:
            calls=[]
            def post(self,url,headers,json,timeout):
                self.calls.append(json["model"])
                return Response(json["model"])
        fake=FakeTransport()
        result=enhance_with_customer_key("Prompt from another app",
            "sk-or-v1-"+"x"*40,transport=fake)
        self.assertEqual(result["status"],"CONSENSUS")
        self.assertEqual(len(fake.calls),3)
        self.assertTrue(any(m.startswith("openai/") for m in fake.calls))
        self.assertTrue(any(m.startswith("anthropic/") for m in fake.calls))

    def test_model_substitution_cannot_pass_consensus(self):
        from prod_shell.src.macie_b import enhance_with_customer_key
        class Response:
            def raise_for_status(self): pass
            def json(self):
                return {"model":"openai/gpt-5.2",
                        "choices":[{"message":{"content":"Improved"}}]}
        class WrongProvider:
            def post(self,*args,**kwargs):return Response()
        result=enhance_with_customer_key("Prompt","sk-or-v1-"+"x"*40,
                                         transport=WrongProvider())
        self.assertEqual(result["status"],"NON-CONSENSUS")

    def test_empty_prompt_denied(self):
        with self.assertRaises(ValueError):
            self.run_review(" ")

    def test_oversized_prompt_denied(self):
        with self.assertRaises(ValueError):
            self.run_review("x"*20001)

if __name__=="__main__":
    unittest.main()

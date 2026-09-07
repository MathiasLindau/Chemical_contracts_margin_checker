import os
import unittest
from pathlib import Path

os.environ.setdefault("OPENAI_API_KEY", "test-key-for-imports")

from src.margin_checker.rag import (
    ANSWER_PROMPT_CONCISE,
    ANSWER_PROMPT_EXTRACTIVE,
    context_from_results,
    render_answer_prompt,
    resolve_answer_prompt,
)


class AnswerPromptTest(unittest.TestCase):

    def test_default_is_concise(self):
        self.assertEqual(resolve_answer_prompt(), ANSWER_PROMPT_CONCISE)

    def test_prompts_differ(self):
        concise = render_answer_prompt("lowest price?", "CON-2023-0007", "concise")
        extractive = render_answer_prompt("lowest price?", "CON-2023-0007", "extractive")
        self.assertNotEqual(concise, extractive)
        self.assertIn("Be concise and specific", concise)
        self.assertIn("Copy numbers", extractive)
        self.assertIn("lowest price?", concise)
        self.assertIn("CON-2023-0007", extractive)

    def test_unknown_style_raises(self):
        with self.assertRaises(ValueError):
            resolve_answer_prompt("poetic")

    def test_hybrid_context_includes_structured_and_text(self):
        context = context_from_results(
            "hybrid",
            {
                "structured": [{"contract_id": "CON-2023-0007", "base_price": 250}],
                "text": [
                    {
                        "contract_id": "CON-2023-0007",
                        "chunk_text": "Payment terms net 30.",
                    }
                ],
            },
        )
        self.assertIn("STRUCTURED DATA", context)
        self.assertIn("250", context)
        self.assertIn("Payment terms net 30", context)


class RequirementsPinTest(unittest.TestCase):

    def test_requirements_pins_direct_deps(self):
        text = Path("requirements.txt").read_text(encoding="utf-8")
        for name in (
            "streamlit==1.62.0",
            "openai==3.3.0",
            "pandas==3.0.5",
            "sentence-transformers==6.0.1",
            "psycopg[binary]==3.3.5",
        ):
            self.assertIn(name, text)

    def test_dockerfile_installs_requirements(self):
        text = Path("Dockerfile").read_text(encoding="utf-8")
        self.assertIn("requirements.txt", text)
        self.assertNotIn("pip install --no-cache-dir \\\n    streamlit", text)


class LlmEvalScriptTest(unittest.TestCase):

    def test_gold_context_hybrid_joins_csv_and_markdown(self):
        from evaluation.evaluate_llm import gold_context

        item = {
            "route": "hybrid",
            "valid_contract_ids": ["CON-2023-0007"],
        }
        import pandas as pd

        catalog = pd.DataFrame(
            [{"contract_id": "CON-2023-0007", "base_price": 250.0}]
        )
        docs = {"CON-2023-0007": "## Payment\nNet 45 days."}
        context = gold_context(item, docs, catalog)
        self.assertIn("250", context)
        self.assertIn("Net 45 days", context)
        self.assertIn("STRUCTURED DATA", context)

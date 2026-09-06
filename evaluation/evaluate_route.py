import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

load_dotenv()

from src.margin_checker.router import classify_query


def evaluate_routes():
    with open(ROOT / "evaluation" / "evaluation_dataset.json", encoding="utf-8") as f:
        tests = json.load(f)

    correct = 0

    for item in tests:
        expected = item["route"]
        predicted, _usage = classify_query(item["question"])

        if predicted == expected:
            correct += 1
            print(
                f"✓ expected={expected:<12} "
                f"predicted={predicted:<12} | "
                f"{item['question']}"
            )
        else:
            print(
                f"❌ expected={expected:<12} "
                f"predicted={predicted:<12}\n"
                f"   {item['question']}"
            )

    accuracy = correct / len(tests) * 100

    print("\n" + "=" * 50)
    print("ROUTE EVALUATION")
    print("=" * 50)
    print(f"Accuracy: {accuracy:.1f}%")
    print(f"Correct:  {correct}/{len(tests)}")
    print("=" * 50)


if __name__ == "__main__":
    evaluate_routes()

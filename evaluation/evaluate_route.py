import json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()


def classify_query(query):
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": f"""
Classify this supply-chain contract question as exactly one route.

structured:
The question can be answered completely using CSV data alone.
It does not require contract text (MD), even if the same information
also happens to appear in the contract.

unstructured:
The question cannot be answered from the CSV alone and requires
information from the contract text (MD).

hybrid:
The question requires information from BOTH the CSV and the
contract text (MD). Neither source alone is sufficient.

Important:
Classify based on the information actually required to answer
the question, not on individual keywords such as:
contract, agreement, penalty, delivery, terms, volume or price.

Examples:

"What is the breach penalty amount?"
→ structured, if the CSV contains breach_penalty_amount.

"What are the contractual consequences of failing to meet
the minimum volume?"
→ unstructured, if the answer requires the MD.

"What is the breach penalty amount and what conditions trigger it?"
→ hybrid, if the amount is in CSV and the conditions are in MD.

QUESTION:
{query}

Return JSON:
{{"route": "structured"}}
"""
        }],
        temperature=0,
        response_format={"type": "json_object"}
    )

    return json.loads(r.choices[0].message.content)["route"]


def evaluate_routes():
    with open("evaluation/evaluation_dataset.json", encoding="utf-8") as f:
        tests = json.load(f)

    correct = 0

    for item in tests:
        expected = item["route"]
        predicted = classify_query(item["question"])

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
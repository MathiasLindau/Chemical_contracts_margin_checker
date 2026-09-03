import os
import json

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

client = OpenAI()

ROUTER_MODEL = os.getenv("ROUTER_MODEL", "gpt-4o-mini")


ROUTER_PROMPT = """
You are a query router for a chemical supply contract analysis system.

Your task is to classify the user's question into EXACTLY ONE route:

1. structured
Use this route when the question can be answered using structured
contract data from the CSV/database.

Typical structured fields include:
- contract ID
- customer
- supplier
- product
- chemical
- base price
- currency
- volume
- minimum monthly volume
- annual volume
- energy surcharge / energy adder
- percentage adders
- penalty amount
- dates
- contract start/end dates

Examples:
- Which contract has the highest breach penalty?
- Which contracts have an energy surcharge above 5%?
- What is the price of Product X?
- Which customer has the largest minimum volume?
- What is the total penalty exposure?

2. unstructured
Use this route when the answer depends on clauses, conditions,
or other information contained in the contract documents.

Typical topics include:
- delivery obligations
- payment conditions
- termination
- notice periods
- breach consequences
- force majeure
- liability
- quality requirements
- dispute resolution
- contractual obligations
- consequences of failing to meet contractual requirements

Examples:
- What happens if the supplier fails to deliver?
- What are the termination conditions?
- What are the payment terms?
- What happens in case of force majeure?
- What are the consequences of breaching the agreement?

3. hybrid
Use this route when answering the question requires BOTH:
- structured contract data, AND
- information from contract text/clauses.

Typical hybrid questions:
- compare price with contractual conditions
- identify the cheapest contract and explain its payment terms
- compare penalties and consequences of breach
- find a contract based on a numeric condition and then inspect its clauses
- questions requiring calculations/data plus contractual interpretation

Examples:
- Which contract has the lowest price and what are its payment terms?
- Which contract has the highest penalty and what happens if the supplier breaches it?
- Compare the two cheapest contracts regarding price and termination conditions.
- Which supplier offers the best price while having favorable delivery terms?

IMPORTANT CLASSIFICATION RULES:

- Classify based on the INFORMATION REQUIRED to answer the question,
  not merely on individual words.

- If the question can be answered completely from structured fields,
  choose structured.

- If the question requires contractual wording, clauses, obligations,
  or consequences, choose unstructured.

- If BOTH structured data and contract text are required, choose hybrid.

- A question mentioning a contract ID does NOT automatically make it
  unstructured.

- A question containing words such as "price", "penalty", "volume",
  or "adder" is not automatically structured. Consider whether the
  question also asks about contractual conditions.

- If a question asks for a numerical/structured fact AND an explanation
  of a contractual clause, choose hybrid.

- If the question asks only about a contractual clause, choose
  unstructured even if a contract ID or product name is mentioned.

- Do not return multiple routes.

Return ONLY valid JSON in exactly this format:

{"route": "structured"}

or

{"route": "unstructured"}

or

{"route": "hybrid"}

USER QUESTION:
"""


def classify_query(query):
    """
    Classify a user query as structured, unstructured or hybrid.

    Returns:
        route: str
        usage: OpenAI usage object
    """

    if not query or not query.strip():
        raise ValueError("Query must not be empty.")

    response = client.chat.completions.create(
        model=ROUTER_MODEL,
        messages=[
            {
                "role": "system",
                "content": ROUTER_PROMPT
            },
            {
                "role": "user",
                "content": query.strip()
            }
        ],
        temperature=0,
        response_format={"type": "json_object"}
    )

    try:
        result = json.loads(
            response.choices[0].message.content
        )
    except json.JSONDecodeError as e:
        raise ValueError(
            "Router returned invalid JSON."
        ) from e

    route = result.get("route")

    valid_routes = {
        "structured",
        "unstructured",
        "hybrid"
    }

    if route not in valid_routes:
        raise ValueError(
            f"Invalid route returned by router: {route}"
        )

    return route, response.usage
"""
MOCK INTERVIEW 2 — Data Pipeline + Generators
Backend Senior Python

PROBLEM STATEMENT:
You are building a lightweight ETL pipeline for a backend service.
Given a list of raw transaction records (dicts), implement a pipeline that:
  1. Filters out invalid records (those missing "amount" or "user_id").
  2. Normalizes each valid record: amount rounded to 2 decimals, user_id uppercased.
  3. Groups the normalized records by user_id.
  4. Returns a summary dict: { user_id -> total_amount }.

The pipeline must use a generator for the filter+normalize step
to avoid loading all records into memory at once (large dataset scenario).

EXPECTED OUTPUT for the input below:
{
    "USR1": 130.60,
    "USR2": 88.50,
    "USR3": 45.00,
}
"""


def filter_and_normalize(records):
    for record in records:
        if "amount" not in record or record["amount"] is None or "user_id" not in record:
            continue
        yield {
            "user_id": record["user_id"].upper(),
            "amount": round(record["amount"], 2),
        }


def group_by_user(normalized_records):
    summary = {}
    grand_total = 0
    for record in normalized_records:
        grand_total += record["amount"]  
        uid = record["user_id"] 
        if uid not in summary:
            summary[uid] = 0
        summary[uid] += record["amount"]  
    return summary, grand_total


def run_pipeline(records):
    pipeline = filter_and_normalize(records)
    totals, grand_total = group_by_user(pipeline)

    print("Pipeline summary:")
    for uid, total in sorted(totals.items()):
        print(f"  {uid}: {total:.2f}")

    double_check = sum(totals.values())
    #grand_total = sum(r["amount"] for r in pipeline if "amount" in r)  
    assert abs(double_check - grand_total) < 0.01, "Totals do not match!"
    return totals


if __name__ == "__main__":
    raw_records = [
        {"user_id": "usr1", "amount": 50.5},
        {"user_id": "usr1", "amount": 80.1},
        {"user_id": "usr2", "amount": 88.5},
        {"user_id": "usr3", "amount": 45.0},
        {"user_id": "usr1", "amount": None},   # invalid: amount present but None — tricky
        {"amount": 20.0},                       # invalid: missing user_id
        {"user_id": "usr4"},                    # invalid: missing amount
    ]

    result = run_pipeline(raw_records)
    print(result)

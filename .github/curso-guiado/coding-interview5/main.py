"""
MOCK INTERVIEW 5 — Iterators, Error Handling & Dictionary State
Backend Senior Python

PROBLEM STATEMENT:
You are building a retry scheduler for background jobs.
Given a list of jobs, group failed jobs by queue name and count how many retries
are pending per queue.

Rules:
- Only jobs with status == "failed" should be counted.
- Jobs missing queue or retries should be ignored.
- The function should return a dict: {queue_name: total_retries}
- Then print the queues sorted by retry count descending.

EXPECTED OUTPUT:

email: 4
billing: 3
search: 1
{'email': 4, 'billing': 3, 'search': 1}
"""


def iter_failed_jobs(jobs):
    for job in jobs:
        if job.get("status") != "failed":
            continue
        if "queue" not in job or "retries" not in job:
            continue
        yield job


def collect_retry_counts(jobs):
    expected_total = 0
    counts = {}
    failed_jobs = iter_failed_jobs(jobs)

    for job in failed_jobs:
        queue = job["queue"]
        retries = job["retries"]
        if queue not in counts:
            counts[queue] = 0  
        counts[queue] += retries
        expected_total += retries

    return counts, expected_total


def print_retry_report(counts):
    ordered = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    for queue, total in ordered:
        print(f"{queue}: {total}")


def main():
    jobs = [
        {"id": 1, "queue": "email", "status": "failed", "retries": 2},
        {"id": 2, "queue": "billing", "status": "failed", "retries": 3},
        {"id": 3, "queue": "email", "status": "ok", "retries": 5},
        {"id": 4, "queue": "search", "status": "failed", "retries": 1},
        {"id": 5, "queue": "email", "status": "failed", "retries": 2},
        {"id": 6, "status": "failed", "retries": 9},
        {"id": 7, "queue": "billing", "status": "ok", "retries": 7},
    ]

    counts, expected_total = collect_retry_counts(jobs)
    print_retry_report(counts)

    # Sanity check: total retries should match sum of failed job retries
    actual_total = sum(counts.values())
    assert expected_total == actual_total, "Retry totals do not match"

    print(counts)


if __name__ == "__main__":
    main()

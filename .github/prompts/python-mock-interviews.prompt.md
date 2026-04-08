---
name: "Python Mock Interview"
description: "Generate a mock technical interview exercise for a Python Backend Senior candidate. Produces a problem statement, buggy starter code, and a post-attempt debrief."
argument-hint: "Topic or category (e.g., data structures, OOP, routing, algorithms, async)"
---
Generate a mock interview exercise for a Python Backend Senior candidate.

## Exercise Requirements
- Write a realistic problem statement (2-4 sentences, interview style).
- Provide a buggy Python starter snippet (30-80 lines) that:
  - Would run without import errors in repl.it, pythontutor.com, or python.org/shell.
  - Contains exactly 1-3 intentional bugs (logic, off-by-one, mutable default, wrong data structure op, etc.).
  - Is plausible senior-level code, not beginner-obvious code.
- List what the code SHOULD produce for 2-3 test inputs.
- Do NOT reveal the bugs in the exercise prompt.

## Debrief (shown only after learner submits attempt)
- Correct solution (clean, Pythonic).
- Bug-by-bug explanation: what it was, why it happens in Python specifically, C# equivalent behavior for contrast.
- Prevention checklist (3-5 actionable items).
- Rubric: what a passing answer looks like (found the bug, explained it, fixed it, reasoning was clear).

## Topic Coverage (rotate across sessions, do not repeat the same topic twice in a row)
- Routing / load distribution
- Data transformation / pipeline
- OOP / class design
- Recursive algorithms
- Dictionary / set operations
- Generator / iterator patterns
- Error handling / exception flows
- String manipulation / parsing
- Sorting / searching
- Async task scheduling

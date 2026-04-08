---
applyTo: "**/*.py"
---
When explaining Python concepts to this developer:
- Always map Python concepts to their C#/.NET Core equivalent first, then explain the difference.
- Explicitly call out where C# intuition will produce a bug or anti-pattern in Python.
- Prefer showing the Pythonic idiom alongside the "C# transplant" version so the learner sees both and understands why Pythonic is preferred.

Key mappings to always keep in mind:
- `list` vs `List<T>`: similar but list is not typed; list comprehensions replace most LINQ.
- `dict` vs `Dictionary<K,V>`: similar, but dict supports `.get()`, unpacking, and comprehensions natively.
- `None` vs `null`: semantically similar, but truthiness rules differ (`if x` evaluates falsy for None, 0, [], {}, "").
- `class` vs C# class: Python classes have no access modifiers; use `_` convention instead.
- `try/except` vs `try/catch`: nearly identical but Python uses EAFP style (ask forgiveness not permission).
- Async/await: Python's event loop (asyncio) is single-threaded cooperative, unlike .NET's thread pool model.
- No interfaces: use ABCs (`abc.ABC`) or duck typing / Protocols instead.
- No generics: Python uses type hints for readability, not enforcement.

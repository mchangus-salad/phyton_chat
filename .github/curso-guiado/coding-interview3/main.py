"""
MOCK INTERVIEW 3 — OOP + Closures / Late Binding
Backend Senior Python

PROBLEM STATEMENT:
You are building a notification dispatcher for a backend service.
Given a list of event names, build a registry of handler functions
where each handler prints which event it handles.

Then implement a PluginRegistry class that:
  - Registers plugins by name with a priority (int).
  - Returns plugins sorted by priority (highest first).
  - Supports iteration over registered plugin names.

EXPECTED OUTPUT:

-- Handlers --
Clicking button_click
Clicking button_click
Clicking button_click

-- Registry --
['auth', 'billing', 'logger']
auth
billing
logger
"""


# ── Part 1: closures ──────────────────────────────────────────────────────────

def build_handlers(events):
    handlers = []
    for event in events:
        handlers.append(lambda event=event: print(f"Clicking {event}"))  
    return handlers


# ── Part 2: class ─────────────────────────────────────────────────────────────

class PluginRegistry:
    _instance = None

    def __init__(self):
        self._plugins: dict = {}          
            
    @classmethod
    def get_instance(cls) -> "PluginRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, name: str, priority: int) -> None:
        self._plugins[name] = priority

    def sorted_plugins(self) -> list[str]:
        return sorted(self._plugins, key=lambda name: self._plugins[name], reverse=True)

    def __iter__(self):
        return iter(self.sorted_plugins())


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("-- Handlers --")
    events = ["button_click", "form_submit", "payment_ok"]
    handlers = build_handlers(events)
    for h in handlers:
        h()

    print()
    print("-- Registry --")
    r1 = PluginRegistry.get_instance()
    r1.register("logger", priority=1)
    r1.register("billing", priority=2)
    r1.register("auth", priority=3)

    print(r1.sorted_plugins())
    for plugin in r1:
        print(plugin)

    # This should print the same registry (singleton), not start fresh:
    r2 = PluginRegistry.get_instance()
    r2.register("intruder", priority=99)
    assert "intruder" in r1.sorted_plugins(), "Singleton broken: r1 and r2 are different instances"
    print("Singleton OK")


if __name__ == "__main__":
    main()

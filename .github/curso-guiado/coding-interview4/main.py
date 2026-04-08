"""
MOCK INTERVIEW 4 — Mutable Defaults, Aliasing & Copy
Backend Senior Python

PROBLEM STATEMENT:
You are building a user profile manager for a backend service.
The system creates user profiles, assigns permissions, and clones
profiles as templates for new users.

Implement:
  - UserProfile: a class holding name and a list of permissions.
  - ProfileManager: manages a registry of profiles, supports
    adding permissions to a profile and cloning a profile
    into a new one with a different name.

EXPECTED OUTPUT:

alice permissions: ['read', 'write']
bob permissions: ['read']
charlie permissions: ['read', 'write', 'admin']
diana permissions: ['read']
Clone independence OK
"""

from copy import deepcopy


class UserProfile:
    def __init__(self, name: str):        
        self.name = name
        self.permissions = []

    def add_permission(self, perm: str) -> None:
        self.permissions.append(perm)

    def __repr__(self) -> str:
        return f"UserProfile({self.name!r}, {self.permissions})"


class ProfileManager:
    def __init__(self):
        self._profiles: dict[str, UserProfile] = {}

    def add(self, profile: UserProfile) -> None:
        self._profiles[profile.name] = profile

    def get(self, name: str) -> UserProfile | None:
        return self._profiles.get(name)

    def clone(self, source_name: str, new_name: str) -> UserProfile | None:
        source = self.get(source_name)
        if source is None:
            return None
        cloned = deepcopy(source) 
        cloned.name = new_name
        self.add(cloned)
        return cloned


def main():
    manager = ProfileManager()

    alice = UserProfile("alice")
    alice.add_permission("read")
    alice.add_permission("write")
    manager.add(alice)

    bob = UserProfile("bob")
    bob.add_permission("read")
    manager.add(bob)

    # Clone alice -> charlie, then add admin only to charlie
    charlie = manager.clone("alice", "charlie")  
    if charlie is not None:
        charlie.add_permission("admin")

    # Clone bob -> diana (should stay independent)
    diana = manager.clone("bob", "diana")

    alice = manager.get('alice')
    if not alice is None:
        print(f"alice permissions: {alice.permissions}")    # Aqui, en todas estas lineas donde se utiliza .permissions tambien se deberia chequear si el objeto es None
    bob = manager.get('bob')
    if not bob is None:
        print(f"bob permissions: {bob.permissions}")        # antes de usarlo con get o alternativamente, usar un objeto UserProfile vacio en get por defecto.
    
    charlie = manager.get('charlie')
    if not charlie is None:
        print(f"charlie permissions: {charlie.permissions}")
    
    diana = manager.get('diana')
    if not diana is None:
        print(f"diana permissions: {diana.permissions}")

    # Verify clones are truly independent
    if alice is not None and charlie is not None:
        assert alice.permissions != charlie.permissions, "BUG: alice and charlie share the same permissions list"
    if bob is not None:
        assert bob.permissions == ["read"], "BUG: bob's permissions were mutated"
    print("Clone independence OK")


if __name__ == "__main__":
    main()

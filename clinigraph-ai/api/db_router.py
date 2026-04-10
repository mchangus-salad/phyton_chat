"""
Database router for read replica support.

Django routes all read-only queries (SELECT) to the ``replica`` database alias
when it is configured. All writes, transactions, and migrations stay on the
``default`` (primary) connection.

Configuration (settings.py / .env):
    DATABASE_ROUTERS = ['api.db_router.ReadReplicaRouter']

    DATABASES = {
        'default': { ... },                         # primary (reads + writes)
        'replica': {                                # optional read replica
            'ENGINE': os.getenv('DJANGO_REPLICA_DB_ENGINE', 'django.db.backends.postgresql'),
            'HOST': os.getenv('DJANGO_REPLICA_DB_HOST', ''),
            ...
        },
    }

When DJANGO_REPLICA_DB_HOST is not set (or the 'replica' key is absent from
DATABASES), the router falls back to 'default' for all operations so that
local development and SQLite environments work without any extra configuration.
"""

from django.conf import settings


_REPLICA_ALIAS = 'replica'


def _replica_available() -> bool:
    """Return True only when a replica database alias has been configured.

    Reads from settings.DATABASES on every call so that test overrides
    (``@override_settings``) are respected.
    """
    db_config = settings.DATABASES.get(_REPLICA_ALIAS, {})
    return bool(db_config.get('HOST') or db_config.get('NAME'))


class ReadReplicaRouter:
    """
    Route read queries to the replica database.

    Rules:
    - db_for_read:  -> 'replica'  (if available, else 'default')
    - db_for_write: -> 'default'  (always)
    - allow_relation: True for all intra-app relations
    - allow_migrate: only on 'default' (never run migrations against a replica)
    """

    def db_for_read(self, model, **hints):
        """Send SELECT queries to the replica when available."""
        if _replica_available():
            return _REPLICA_ALIAS
        return 'default'

    def db_for_write(self, model, **hints):
        """Always direct writes to the primary."""
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        """Allow relations between objects in any known database alias."""
        known = {'default', _REPLICA_ALIAS}
        db_set = {obj1._state.db, obj2._state.db}
        if db_set <= known:
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """Only apply migrations to the primary database, never the replica."""
        if db == _REPLICA_ALIAS:
            return False
        return None

import os
import sys
import types

import pytest

# Ensure the backend root (containing the `app` package) is importable
_TESTS_DIR = os.path.dirname(__file__)
_BACKEND_ROOT = os.path.abspath(os.path.join(_TESTS_DIR, os.pardir))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "unit: Fast unit tests with mocks only")

    # Stub heavy/optional external modules so unit tests run in isolation
    if "sqlalchemy" not in sys.modules:
        sa = types.ModuleType("sqlalchemy")

        def _identity(value, *args, **kwargs):  # type: ignore[no-untyped-def]
            return value

        def _return_tuple(*args, **kwargs):  # type: ignore[no-untyped-def]
            return args or kwargs

        sa.desc = _identity  # type: ignore[attr-defined]
        sa.select = _return_tuple  # type: ignore[attr-defined]
        sa.text = _identity  # type: ignore[attr-defined]

        orm = types.ModuleType("sqlalchemy.orm")
        orm.Session = object
        orm.selectinload = _identity  # type: ignore[attr-defined]
        sa.orm = orm  # type: ignore[attr-defined]
        sys.modules["sqlalchemy"] = sa
        sys.modules["sqlalchemy.orm"] = orm

    # Stub heavy repository module to avoid database imports during unit tests
    if "app.db.repository" not in sys.modules:
        repo = types.ModuleType("app.db.repository")

        def _return_none(*_a, **_k):  # type: ignore[no-untyped-def]
            return None

        repo.get_tenant_by_id = _return_none  # type: ignore[attr-defined]
        repo.find_channel_instance_by_identifier = _return_none  # type: ignore[attr-defined]
        repo.update_tenant_project_config = _return_none  # type: ignore[attr-defined]
        repo.get_tenant_by_channel_identifier = _return_none  # type: ignore[attr-defined]
        sys.modules["app.db.repository"] = repo

    if "langfuse" not in sys.modules:
        lf = types.ModuleType("langfuse")

        def _get_client():  # type: ignore[no-redef]
            class _C:  # minimal stub
                pass

            return _C()

        lf.get_client = _get_client
        sys.modules["langfuse"] = lf

    # Stub flow_modification executor to avoid DB/agent deps during imports
    mod_name = "app.flow_core.actions.flow_modification"
    if mod_name not in sys.modules:
        fm = types.ModuleType(mod_name)

        class FlowModificationExecutor:  # type: ignore[too-many-ancestors]
            def __init__(self, *_a, **_k):
                pass

            @property
            def action_name(self) -> str:  # pragma: no cover
                return "modify_flow"

            async def execute(self, parameters: dict, context: dict):  # pragma: no cover
                # Minimal ActionResult-like object
                return types.SimpleNamespace(
                    success=True,
                    is_success=True,
                    message="ok",
                    error=None,
                    data={},
                )

        fm.FlowModificationExecutor = FlowModificationExecutor
        sys.modules[mod_name] = fm

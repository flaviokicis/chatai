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
        orm = types.ModuleType("sqlalchemy.orm")
        orm.Session = object
        sys.modules["sqlalchemy"] = sa
        sys.modules["sqlalchemy.orm"] = orm

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

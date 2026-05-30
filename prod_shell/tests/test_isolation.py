"""
Production Shell stub tests.

These tests prove the dual-use boundary holds: the production shell can use
the engine without any Core dependency, and the engine actually works
end-to-end when called from the production shell.
"""

from pathlib import Path

from prod_shell.src import smoke_test


def test_prod_shell_imports_engine():
    """Production shell must be able to import the engine."""
    result = smoke_test()
    assert result["engine_imported"] is True
    assert result["consensus_callable"] is True


def test_prod_shell_runs_end_to_end():
    """Production shell must successfully run a consensus query."""
    result = smoke_test()
    assert result["end_to_end_succeeded"] is True, (
        f"Smoke test failed: {result.get('end_to_end_error', 'unknown')}"
    )


def test_prod_shell_has_no_core_shell_dependency():
    """The production shell must not import from core_shell, ever."""
    prod_src = Path(__file__).resolve().parent.parent / "src"
    for py_file in prod_src.rglob("*.py"):
        content = py_file.read_text()
        assert "core_shell" not in content, f"{py_file} imports core_shell"
        assert "from core" not in content, f"{py_file} imports from core"

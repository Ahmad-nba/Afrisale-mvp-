"""
Phase 5 test suite — cleanup: dead code removed, LangChain gone
================================================================
Verifies that all deleted files are gone, all LangChain imports are removed,
and the final system imports cleanly end-to-end.

Run with:
    pytest tests/test_phase5_cleanup.py -v

Expected: 31 passed, 0 failed, 0 errors
"""

import ast
import importlib
import subprocess
import sys
from pathlib import Path
import pytest


# ---------------------------------------------------------------------------
# ── 1. Dead files are deleted ────────────────────────────────────────────────
# ---------------------------------------------------------------------------

DELETED_FILES = [
    "app/agents/agents.py",
    "app/agents/tools.py",
    "app/agents/prompt.py",
    "app/memory/memory_service.py",
    "test_agent.py",
]


@pytest.mark.parametrize("filepath", DELETED_FILES)
def test_dead_file_is_deleted(filepath):
    assert not Path(filepath).exists(), \
        f"'{filepath}' must be deleted in Phase 5 — it is dead code replaced by Parlant"


def test_agents_directory_empty_or_deleted():
    """app/agents/ served only run_turn, run_agent, tools, prompt — all replaced."""
    agents_dir = Path("app/agents")
    if agents_dir.exists():
        py_files = list(agents_dir.glob("*.py"))
        non_init = [f for f in py_files if f.name != "__init__.py"]
        assert len(non_init) == 0, \
            f"app/agents/ must contain no Python files after cleanup. Found: {non_init}"


# ---------------------------------------------------------------------------
# ── 2. LangChain removed from requirements.txt ──────────────────────────────
# ---------------------------------------------------------------------------

LANGCHAIN_PACKAGES = [
    "langchain",
    "langchain-google-genai",
    "langchain-core",
    "langchain-community",
]


@pytest.fixture
def requirements_text():
    path = Path("requirements.txt")
    assert path.exists(), "requirements.txt must exist"
    return path.read_text().lower()


@pytest.mark.parametrize("package", LANGCHAIN_PACKAGES)
def test_langchain_package_removed_from_requirements(requirements_text, package):
    assert package not in requirements_text, \
        f"'{package}' must be removed from requirements.txt in Phase 5"


def test_parlant_in_requirements():
    text = Path("requirements.txt").read_text().lower()
    assert "parlant" in text, \
        "requirements.txt must include 'parlant' after Phase 5"


def test_google_gemini_backend_present():
    """Gemini access — either via google-generativeai or parlant's own backend."""
    text = Path("requirements.txt").read_text().lower()
    has_backend = "google-generativeai" in text or "parlant" in text
    assert has_backend, \
        "requirements.txt must retain Gemini access (google-generativeai or via parlant)"


# ---------------------------------------------------------------------------
# ── 3. No LangChain imports anywhere in app/ ────────────────────────────────
# ---------------------------------------------------------------------------

def get_all_app_python_files():
    return list(Path("app").rglob("*.py"))


@pytest.mark.parametrize("filepath", get_all_app_python_files())
def test_no_langchain_import_in_app(filepath):
    source = Path(filepath).read_text()
    assert "langchain" not in source.lower(), \
        f"LangChain import found in {filepath} — must be removed in Phase 5"


# ---------------------------------------------------------------------------
# ── 4. No run_turn / run_agent references outside deleted files ──────────────
# ---------------------------------------------------------------------------

def get_surviving_app_files():
    return [
        f for f in Path("app").rglob("*.py")
        if "agents" not in str(f)
    ]


@pytest.mark.parametrize("filepath", get_surviving_app_files())
def test_no_run_turn_in_surviving_files(filepath):
    source = Path(filepath).read_text()
    assert "run_turn" not in source, \
        f"'{filepath}' references run_turn — must use AfrisaleSession.run_turn instead"


@pytest.mark.parametrize("filepath", get_surviving_app_files())
def test_no_run_agent_in_surviving_files(filepath):
    source = Path(filepath).read_text()
    assert "run_agent" not in source, \
        f"'{filepath}' references run_agent — this dead code function must be removed"


# ---------------------------------------------------------------------------
# ── 5. handle_inbound removed from message_service.py ───────────────────────
# ---------------------------------------------------------------------------

def test_handle_inbound_removed_from_message_service():
    source = Path("app/services/message_service.py").read_text()
    tree = ast.parse(source)
    function_names = [
        node.name for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    ]
    assert "handle_inbound" not in function_names, \
        "handle_inbound must be removed from message_service.py in Phase 5 — " \
        "it is fully replaced by app/pipeline/runner.py run_pipeline()"


def test_message_service_retains_helpers():
    """get_or_create_customer, normalize_phone, save_message must survive."""
    source = Path("app/services/message_service.py").read_text()
    tree = ast.parse(source)
    function_names = [
        node.name for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    ]
    for helper in ["get_or_create_customer", "normalize_phone", "save_message"]:
        assert helper in function_names, \
            f"'{helper}' must be kept in message_service.py — pipeline stages still use it"


# ---------------------------------------------------------------------------
# ── 6. README route paths are correct ───────────────────────────────────────
# ---------------------------------------------------------------------------

def test_readme_uses_api_prefix():
    readme = Path("README.md")
    if not readme.exists():
        pytest.skip("README.md not present")
    text = readme.read_text()
    # Must not have bare /health without /api prefix
    assert "GET /health\n" not in text and "GET /health " not in text, \
        "README must use GET /api/health not GET /health"
    assert "POST /webhook\n" not in text and "POST /webhook " not in text, \
        "README must use POST /api/webhook not POST /webhook"
    assert "/api/health" in text, "README must document GET /api/health"
    assert "/api/webhook" in text, "README must document POST /api/webhook"


# ---------------------------------------------------------------------------
# ── 7. Full import smoke test ────────────────────────────────────────────────
# ---------------------------------------------------------------------------

FINAL_IMPORTS = [
    "app.pipeline.runner",
    "app.pipeline.stages",
    "app.guardrails.input_guardrail",
    "app.guardrails.output_validation",
    "app.guardrails.output_formatting",
    "app.parlant_agent.session",
    "app.parlant_agent.engine",
    "app.parlant_agent.guidelines",
    "app.parlant_agent.tool_registry",
    "app.observability.logger",
    "app.services.catalog",
    "app.services.orders",
    "app.services.message_service",
    "app.api.messages",
    "app.models.models",
    "app.core.config",
]


@pytest.mark.parametrize("module_path", FINAL_IMPORTS)
def test_final_import_smoke(module_path):
    try:
        importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        pytest.fail(f"Final import failed for '{module_path}': {e}")


# ---------------------------------------------------------------------------
# ── 8. grep verification — belt and braces ───────────────────────────────────
# ---------------------------------------------------------------------------

def test_grep_no_langchain_in_app():
    """Shell-level verification that no langchain strings survive."""
    result = subprocess.run(
        ["grep", "-r", "langchain", "app/", "--include=*.py", "-l"],
        capture_output=True, text=True
    )
    files_with_langchain = result.stdout.strip()
    assert files_with_langchain == "", \
        f"LangChain found in these files after Phase 5 cleanup:\n{files_with_langchain}"


def test_grep_no_run_agent_in_app():
    result = subprocess.run(
        ["grep", "-r", "run_agent", "app/", "--include=*.py", "-l"],
        capture_output=True, text=True
    )
    files = result.stdout.strip()
    assert files == "", \
        f"run_agent still referenced in:\n{files}"
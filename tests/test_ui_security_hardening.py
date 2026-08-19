from pathlib import Path


def test_api_data_is_not_rendered_with_inner_html() -> None:
    script = Path("app/static/app.js").read_text(encoding="utf-8")

    assert ".innerHTML" not in script
    assert "textContent" in script
    assert "replaceChildren" in script


def test_docker_context_excludes_secrets_and_runtime_data() -> None:
    patterns = set(Path(".dockerignore").read_text(encoding="utf-8").splitlines())

    assert {".env", ".env.*", ".git", ".venv", "runtime/", "reports/"} <= patterns

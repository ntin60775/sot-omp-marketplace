"""Тесты нового поведения gitmark.py из плана command-inventory:
идемпотентность inventory, поимка рассинхрона --check, парсер .gitignore, I7.
Существующее поведение не покрывается (вне scope плана)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# движок доставляется установленным плагином ontoship
_GITMARK = (Path(__file__).resolve().parent.parent
            / ".omp" / "plugins" / "node_modules" / "ontoship"
            / "skills" / "kb-search" / "gitmark.py")
if not _GITMARK.exists():
    pytest.skip(
        "ontoship plugin not installed — run: "
        "omp plugin install --scope project ontoship@sot-omp-marketplace",
        allow_module_level=True,
    )
_spec = importlib.util.spec_from_file_location("gitmark", _GITMARK)
gm = importlib.util.module_from_spec(_spec)
sys.modules["gitmark"] = gm
_spec.loader.exec_module(gm)


COMMAND = """---
description: Test command for the registry.
args: "<topic>"
drives: "test skill"
---

Run the test skill on: `$ARGUMENTS`.
"""

SKILL = """---
name: test-skill
description: A skill for the registry tests.
---

Body.
"""

REGISTRY = """---
node_type: reference
title: Test commands
---

# Test commands

## Summary

<!-- BEGIN inventory:commands -->
<!-- END inventory:commands -->

<!-- BEGIN inventory:skills -->
<!-- END inventory:skills -->

---

## `/foo` — test command

- **Definition:** `.omp/commands/foo.md`
"""


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """Минимальный репо: одна команда, один навык, реестр с маркерами."""
    (tmp_path / ".omp" / "commands").mkdir(parents=True)
    (tmp_path / ".omp" / "skills" / "test-skill").mkdir(parents=True)
    (tmp_path / "docs" / "reference").mkdir(parents=True)
    (tmp_path / ".omp" / "commands" / "foo.md").write_text(COMMAND, encoding="utf-8")
    (tmp_path / ".omp" / "skills" / "test-skill" / "SKILL.md").write_text(SKILL, encoding="utf-8")
    (tmp_path / "docs" / "reference" / "commands.md").write_text(REGISTRY, encoding="utf-8")
    return tmp_path


def _between(text: str, what: str) -> str:
    b, e = f"<!-- BEGIN inventory:{what} -->", f"<!-- END inventory:{what} -->"
    return text[text.find(b) + len(b):text.find(e)].strip("\n")


# ── парсер .gitignore ──────────────────────────────────────────────

def test_gitignore_excludes_dirs_and_files(repo: Path):
    (repo / ".gitignore").write_text(".scratch/\ndraft.md\n", encoding="utf-8")
    (repo / ".scratch").mkdir()
    (repo / ".scratch" / "report.md").write_text("ephemeral", encoding="utf-8")
    (repo / "draft.md").write_text("draft", encoding="utf-8")
    (repo / "keep.md").write_text("keep", encoding="utf-8")
    found = {p.name for p in gm.iter_md(repo)}
    assert "report.md" not in found
    assert "draft.md" not in found
    assert "keep.md" in found


def test_gitignore_wildcard(repo: Path):
    (repo / ".gitignore").write_text("*-map.html\n", encoding="utf-8")
    (repo / "notes.md").write_text("notes", encoding="utf-8")
    dirs, files = gm.parse_gitignore(repo)
    assert dirs == []
    assert files == ["*-map.html"]
    assert gm._wild_match("docs-map.html", "*-map.html")
    assert not gm._wild_match("notes.md", "*-map.html")


# ── inventory: генерация и идемпотентность ─────────────────────────

def test_inventory_generates_tables(repo: Path):
    r = gm.cmd_inventory(repo)
    assert set(r["changed"]) == {"commands", "skills"}
    text = (repo / "docs" / "reference" / "commands.md").read_text(encoding="utf-8")
    assert "| `/foo` |" in _between(text, "commands")
    assert "| `test-skill` |" in _between(text, "skills")
    # вне маркеров файл не тронут
    assert "## `/foo` — test command" in text


def test_inventory_idempotent(repo: Path):
    gm.cmd_inventory(repo)
    before = (repo / "docs" / "reference" / "commands.md").read_text(encoding="utf-8")
    r = gm.cmd_inventory(repo)
    assert r["changed"] == []
    assert (repo / "docs" / "reference" / "commands.md").read_text(encoding="utf-8") == before


# ── inventory --check: поимка рассинхрона ──────────────────────────

def test_check_clean_after_generate(repo: Path):
    gm.cmd_inventory(repo)
    assert gm.cmd_inventory(repo, check=True)["issues"] == []


def test_check_catches_missing_frontmatter_fields(repo: Path):
    gm.cmd_inventory(repo)
    # убираем args:/drives: у команды
    (repo / ".omp" / "commands" / "foo.md").write_text(
        "---\ndescription: Test command for the registry.\n---\n\nBody.\n", encoding="utf-8")
    issues = gm.cmd_inventory(repo, check=True)["issues"]
    msgs = " ".join(m for _, m in issues)
    assert "args:" in msgs and "drives:" in msgs


def test_check_catches_missing_section(repo: Path):
    gm.cmd_inventory(repo)
    reg = repo / "docs" / "reference" / "commands.md"
    reg.write_text(reg.read_text(encoding="utf-8").replace("## `/foo` — test command", "## `/bar`"),
                   encoding="utf-8")
    issues = gm.cmd_inventory(repo, check=True)["issues"]
    msgs = " ".join(m for _, m in issues)
    assert "/foo" in msgs and "/bar" in msgs


def test_check_catches_stale_table(repo: Path):
    gm.cmd_inventory(repo)
    reg = repo / "docs" / "reference" / "commands.md"
    reg.write_text(reg.read_text(encoding="utf-8").replace("| `/foo` |", "| `/foo` | STALE"),
                   encoding="utf-8")
    issues = gm.cmd_inventory(repo, check=True)["issues"]
    assert any("рассинхронизирована" in m for _, m in issues)


# ── I7 в lint ──────────────────────────────────────────────────────

def test_lint_reports_i7_on_desync(repo: Path):
    # маркеры пусты, секции нет → рассинхрон
    r = gm.cmd_lint(repo)
    i7 = [i for i in r["issues"] if i[1] == "I7"]
    assert i7 and all(lvl == "ERR" for lvl, *_ in i7)
    # после генерации реестр синхронен (секция `/foo` уже в шаблоне) → I7 чист
    gm.cmd_inventory(repo)
    r = gm.cmd_lint(repo)
    assert [i for i in r["issues"] if i[1] == "I7"] == []

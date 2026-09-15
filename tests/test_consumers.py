"""Тесты scripts/consumers.py: дрейф, план обновления, снятие плоских копий.

Всё герметично: поддельный `omp` в PATH, свои каталог/маркетплейсы/проекты во
временном каталоге. Настоящие проекты машины и сеть не трогаются.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parent.parent / "scripts" / "consumers.py"
CATALOG = "sot-omp-marketplace"

FAKE_OMP = """#!/usr/bin/env bash
echo "$(pwd)|$*" >> "${FAKE_OMP_LOG}"
if [ "$1" = "plugin" ] && [ "$2" = "list" ]; then
  if [ -n "${FAKE_OMP_GARBAGE:-}" ]; then echo "warning: omp обновился, это не JSON"; exit 0; fi
  python3 - "$FAKE_OMP_WORLD" "$(pwd)" <<'PY'
import json, sys
world = json.load(open(sys.argv[1]))
print(json.dumps(world.get(sys.argv[2], {"npm": [], "marketplace": []})))
PY
fi
if [ -n "${FAKE_OMP_FAIL:-}" ] && { [ "$2" = "install" ] || [ "$2" = "upgrade" ]; }; then
  echo "boom: установка не удалась" >&2
  exit 1
fi
exit 0
"""


class Machine:
    """Машина для теста: поддельный omp, кэш каталога, проекты, реестр."""

    def __init__(self, root: Path):
        self.root = root
        self.bin = root / "bin"
        self.bin.mkdir()
        omp = self.bin / "omp"
        omp.write_text(FAKE_OMP, encoding="utf-8")
        omp.chmod(0o755)
        self.log = root / "omp.log"
        self.log.write_text("", encoding="utf-8")

        self.catalog = root / "catalog.json"
        self.catalog.write_text(json.dumps({
            "name": CATALOG,
            "metadata": {"version": "0.3.1"},
            "plugins": [{"name": "ontoship", "version": "0.4.0"},
                        {"name": "1c", "version": "0.1.2"}],
        }), encoding="utf-8")
        self.marketplaces = root / "marketplaces.json"
        self.catalog_unica = root / "catalog-unica.json"
        self.catalog_unica.write_text(json.dumps({
            "name": "unica",
            "metadata": {"version": "0.12.3"},
            "plugins": [{"name": "unica", "version": "0.12.3"}],
        }), encoding="utf-8")
        self.marketplaces.write_text(json.dumps({
            "version": 1,
            "marketplaces": [
                {"name": CATALOG, "catalogPath": str(self.catalog)},
                {"name": "unica", "catalogPath": str(self.catalog_unica)},
            ],
        }), encoding="utf-8")

        self.world: dict[str, dict] = {}
        self.world_file = root / "world.json"
        self.world_file.write_text("{}", encoding="utf-8")
        self.consumers: list[dict] = []

    # --- построение мира ---------------------------------------------------

    def project(self, name: str, plugins: list[tuple[str, str, str]] = (), flat: list[str] = (),
                hook: str | None = None) -> Path:
        """plugins: (id, scope, version); flat: каталоги вроде .omp/rules; hook: текст скрипта ворктри."""
        path = self.root / name
        (path / ".omp").mkdir(parents=True)
        for directory in flat:
            (path / directory).mkdir(parents=True, exist_ok=True)
        if hook is not None:
            (path / "tasks").mkdir(exist_ok=True)
            (path / "tasks" / "init-worktree.sh").write_text(hook, encoding="utf-8")

        entries = [{"scope": scope, "installPath": str(self.root / "cache" / f"{plugin}-{version}"),
                    "version": version} for plugin, scope, version in plugins]
        self.world[str(path)] = {"npm": [], "marketplace": [
            {"id": plugin, "scope": scope, "entries": [entry]}
            for (plugin, scope, _), entry in zip(plugins, entries)
        ]}
        for plugin, _, version in plugins:
            (self.root / "cache" / f"{plugin}-{version}").mkdir(parents=True, exist_ok=True)
        self.world_file.write_text(json.dumps(self.world), encoding="utf-8")
        return path

    def package_file(self, plugin: str, version: str, relative: str, content: str) -> None:
        """Файл внутри поставленного пакета — эталон для классификации плоских копий."""
        target = self.root / "cache" / f"{plugin}-{version}" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def consumer(self, name: str, path: Path, plugins: list[tuple[str, str, str | None]],
                 flat: list[str] = (), hook: str | None = None, hook_installs: bool = False) -> None:
        self.consumers.append({
            "name": name,
            "path": str(path),
            "plugins": [{"id": plugin, "scope": scope, "installed": version, "pin": None}
                        for plugin, scope, version in plugins],
            "legacy": {"flat": flat},
            "worktreeInit": {"hook": hook, "installsPlugins": hook_installs},
            "lastChecked": None,
            "lastUpgraded": None,
        })

    def write_registry(self, **overrides) -> Path:
        doc = {
            "$schema": "./schemas/consumer-registry.schema.json",
            "schemaVersion": 1,
            "machine": "test",
            "updated": "2026-09-14T00:00:00Z",
            "catalog": {"name": CATALOG, "remote": "owner/repo"},
            "discoverRoots": [str(self.root)],
            "exclude": [],
            "consumers": self.consumers,
        }
        doc.update(overrides)
        path = self.root / "registry.json"
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    # --- запуск ------------------------------------------------------------

    def run(self, registry: Path, *args: str, fail_mutations: bool = False,
            garbage_list: bool = False) -> subprocess.CompletedProcess:
        env = {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "FAKE_OMP_LOG": str(self.log),
            "FAKE_OMP_WORLD": str(self.world_file),
        }
        if fail_mutations:
            env["FAKE_OMP_FAIL"] = "1"
        if garbage_list:
            env["FAKE_OMP_GARBAGE"] = "1"
        return subprocess.run(
            [sys.executable, str(TOOL), "--registry", str(registry),
             "--marketplaces", str(self.marketplaces), *args],
            capture_output=True, text=True, env=env,
        )

    def calls(self) -> list[str]:
        return [line for line in self.log.read_text(encoding="utf-8").splitlines() if line]

    def mutations(self) -> list[str]:
        """Вызовы omp, меняющие состояние: наблюдение (`plugin list`) — не мутация."""
        return [call for call in self.calls()
                if "plugin install" in call or "plugin upgrade" in call
                or "marketplace update" in call]


@pytest.fixture
def machine(tmp_path: Path) -> Machine:
    return Machine(tmp_path)


def test_worktree_gap_fires_only_when_a_hook_exists(machine: Machine) -> None:
    """Хук, который ворктри готовит, но плагинов в них не ставит, — гэп.
    Проект без хука ворктри не готовит вовсе — это не дрейф потребителя."""
    reminder = machine.project("reminder", [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                               hook="echo напоминание\n")
    nohook = machine.project("nohook", [("ontoship@sot-omp-marketplace", "project", "0.4.0")])
    machine.consumer("reminder", reminder, [("ontoship@sot-omp-marketplace", "project", "0.4.0")])
    machine.consumer("nohook", nohook, [("ontoship@sot-omp-marketplace", "project", "0.4.0")])

    result = machine.run(machine.write_registry(), "check", "--json")

    report = {row["name"]: {d["kind"] for d in row["drifts"]}
              for row in json.loads(result.stdout)["consumers"]}
    assert report["reminder"] == {"worktree-gap"}
    assert report["nohook"] == set()


def test_discover_ignores_paths_inside_known_consumers(machine: Machine) -> None:
    """Резервная копия внутри .omp/ потребителя — не отдельный потребитель."""
    path = machine.project("known")
    nested = path / ".omp" / ".backup-20260914"
    (nested / ".omp").mkdir(parents=True)
    machine.consumer("known", path, [])

    result = machine.run(machine.write_registry(), "discover")

    assert result.returncode == 0, result.stdout
    assert "backup" not in result.stdout


def test_check_clean_machine_exits_zero(machine: Machine) -> None:
    path = machine.project("clean", [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                           hook="omp plugin install --scope project ontoship@sot-omp-marketplace\n")
    machine.consumer("clean", path, [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                     hook="tasks/init-worktree.sh", hook_installs=True)

    result = machine.run(machine.write_registry(), "check")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "чисто" in result.stdout


def test_check_names_every_drift_kind(machine: Machine) -> None:
    installing = "omp plugin install --scope project x\n"
    missing = machine.project("missing", hook=installing)
    stale = machine.project("stale", [("ontoship@sot-omp-marketplace", "project", "0.3.0")], hook=installing)
    scoped = machine.project("scoped", [("ontoship@sot-omp-marketplace", "user", "0.4.0")], hook=installing)
    legacy = machine.project("legacy", [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                             flat=[".omp/rules"], hook=installing)
    machine.package_file("ontoship@sot-omp-marketplace", "0.4.0", "rules/kb-first.md", "package text")
    (legacy / ".omp" / "rules" / "kb-first.md").write_text("старая копия", encoding="utf-8")
    gap = machine.project("gap", [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                          hook="echo 'поставь плагин сам'\n")
    pinned = machine.project("pinned", [("ontoship@sot-omp-marketplace", "project", "0.3.0")], hook=installing)
    violated = machine.project("violated", [("ontoship@sot-omp-marketplace", "project", "0.2.0")], hook=installing)

    machine.consumer("missing", missing, [("ontoship@sot-omp-marketplace", "project", None)])
    machine.consumer("stale", stale, [("ontoship@sot-omp-marketplace", "project", "0.3.0")])
    machine.consumer("scoped", scoped, [("ontoship@sot-omp-marketplace", "project", "0.4.0")])
    machine.consumer("legacy", legacy, [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                     flat=[".omp/rules"])
    machine.consumer("gap", gap, [("ontoship@sot-omp-marketplace", "project", "0.4.0")])
    machine.consumer("pinned", pinned, [("ontoship@sot-omp-marketplace", "project", "0.3.0")])
    machine.consumers[-1]["plugins"][0]["pin"] = "0.3.0"
    machine.consumer("violated", violated, [("ontoship@sot-omp-marketplace", "project", "0.2.0")])
    machine.consumers[-1]["plugins"][0]["pin"] = "0.3.0"

    result = machine.run(machine.write_registry(), "check", "--json")

    assert result.returncode == 1
    report = {row["name"]: {d["kind"] for d in row["drifts"]}
              for row in json.loads(result.stdout)["consumers"]}
    assert report["missing"] == {"missing"}
    assert report["stale"] == {"stale"}
    assert report["scoped"] == {"scope"}
    assert report["legacy"] == {"legacy"}
    assert report["gap"] == {"worktree-gap"}
    assert report["pinned"] == {"pinned"}
    assert report["violated"] == {"stale"}, "нарушенный пин — настоящий дрейф, не информационный"


def test_pinned_consumer_does_not_count_as_drift(machine: Machine) -> None:
    path = machine.project("pinned", [("ontoship@sot-omp-marketplace", "project", "0.3.0")],
                           hook="omp plugin install --scope project x\n")
    machine.consumer("pinned", path, [("ontoship@sot-omp-marketplace", "project", "0.3.0")])
    machine.consumers[-1]["plugins"][0]["pin"] = "0.3.0"

    result = machine.run(machine.write_registry(), "check")

    assert result.returncode == 0, result.stdout
    assert "pinned" in result.stdout


def test_registry_violating_schema_is_rejected(machine: Machine) -> None:
    path = machine.project("clean")
    machine.consumer("clean", path, [("ontoship@sot-omp-marketplace", "machine-wide", None)])

    result = machine.run(machine.write_registry(), "check")

    assert result.returncode == 2
    assert "не соответствует схеме" in result.stderr


def test_duplicate_consumer_names_are_rejected(machine: Machine) -> None:
    path = machine.project("clean")
    machine.consumer("clean", path, [])
    machine.consumer("clean", machine.project("other"), [])

    result = machine.run(machine.write_registry(), "check")

    assert result.returncode == 2
    assert "дубликаты" in result.stderr


def test_discover_reports_projects_missing_from_registry(machine: Machine) -> None:
    known = machine.project("known")
    machine.project("stranger")
    machine.consumer("known", known, [])

    result = machine.run(machine.write_registry(), "discover")

    assert result.returncode == 1
    assert "stranger" in result.stdout
    assert "known" not in result.stdout.split("Не в реестре")[-1]


def test_discover_respects_exclude(machine: Machine) -> None:
    machine.project("source-repo")
    registry = machine.write_registry(exclude=[{"path": str(machine.root / "source-repo"),
                                                "reason": "источник пакета"}])

    result = machine.run(registry, "discover")

    assert result.returncode == 0, result.stdout
    assert "Неучтённых проектов с .omp/ нет" in result.stdout


def test_upgrade_dry_run_never_calls_omp(machine: Machine) -> None:
    path = machine.project("stale", [("ontoship@sot-omp-marketplace", "project", "0.3.0")])
    machine.consumer("stale", path, [("ontoship@sot-omp-marketplace", "project", "0.3.0")])

    result = machine.run(machine.write_registry(), "upgrade", "--dry-run")

    assert result.returncode == 0, result.stdout
    assert machine.mutations() == [], "dry-run обязан не менять состояние omp"
    assert "0.4.0" in result.stdout


def test_upgrade_installs_and_upgrades_in_project_scope(machine: Machine) -> None:
    missing = machine.project("missing")
    stale = machine.project("stale", [("ontoship@sot-omp-marketplace", "project", "0.3.0")])
    machine.consumer("missing", missing, [("ontoship@sot-omp-marketplace", "project", None)])
    machine.consumer("stale", stale, [("ontoship@sot-omp-marketplace", "project", "0.3.0")])

    result = machine.run(machine.write_registry(), "upgrade", "--yes")

    assert result.returncode == 0, result.stdout + result.stderr
    calls = machine.calls()
    assert sum("plugin marketplace update" in call for call in calls) == 1
    assert f"{missing}|plugin install ontoship@sot-omp-marketplace --scope=project" in calls
    assert f"{stale}|plugin upgrade ontoship@sot-omp-marketplace --scope=project" in calls


def test_upgrade_without_yes_is_refused_and_changes_nothing(machine: Machine) -> None:
    path = machine.project("stale", [("ontoship@sot-omp-marketplace", "project", "0.3.0")])
    machine.consumer("stale", path, [("ontoship@sot-omp-marketplace", "project", "0.3.0")])

    result = machine.run(machine.write_registry(), "upgrade")

    assert result.returncode == 2
    assert machine.mutations() == []


def test_upgrade_installs_over_flat_copies_and_points_at_migrate(machine: Machine) -> None:
    """Копии установке не мешают (они перекрывают плагин, поведение не меняется),
    но оператор обязан увидеть, что дальше нужен migrate."""
    pinned = machine.project("pinned", [("ontoship@sot-omp-marketplace", "project", "0.3.0")])
    legacy = machine.project("legacy", [("ontoship@sot-omp-marketplace", "project", "0.3.0")],
                             flat=[".omp/rules"])
    machine.package_file("ontoship@sot-omp-marketplace", "0.3.0", "rules/kb-first.md", "пакет")
    (legacy / ".omp" / "rules" / "kb-first.md").write_text("старая копия", encoding="utf-8")
    machine.consumer("pinned", pinned, [("ontoship@sot-omp-marketplace", "project", "0.3.0")])
    machine.consumer("legacy", legacy, [("ontoship@sot-omp-marketplace", "project", "0.3.0")],
                     flat=[".omp/rules"])
    machine.consumers[0]["plugins"][0]["pin"] = "0.3.0"

    result = machine.run(machine.write_registry(), "upgrade", "--yes")

    mutations = machine.mutations()
    assert not any("pinned|" in call for call in mutations), "закреплённого обновлять нельзя"
    assert any("legacy|plugin upgrade ontoship@sot-omp-marketplace" in call for call in mutations)
    assert "плоские копии на месте у: legacy" in result.stdout
    assert "migrate --apply" in result.stdout


def test_upgrade_does_not_warn_about_project_own_files(machine: Machine) -> None:
    """Свои файлы проекта ничего не перекрывают — предупреждения о копиях быть не должно."""
    path = machine.project("own", [("ontoship@sot-omp-marketplace", "project", "0.3.0")],
                           flat=[".omp/rules"])
    machine.package_file("ontoship@sot-omp-marketplace", "0.3.0", "rules/kb-first.md", "пакет")
    (path / ".omp" / "rules" / "erp-main-test-contour.md").write_text("своё правило", encoding="utf-8")
    machine.consumer("own", path, [("ontoship@sot-omp-marketplace", "project", "0.3.0")],
                     flat=[".omp/rules"])

    result = machine.run(machine.write_registry(), "upgrade", "--yes")

    assert result.returncode == 0, result.stdout
    assert "плоские копии на месте" not in result.stdout
    assert "ontoship@sot-omp-marketplace" in result.stdout, "обновление всё равно сделано"


def test_migrate_report_deletes_nothing(machine: Machine) -> None:
    path = machine.project("legacy", [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                           flat=[".omp/rules"])
    machine.package_file("ontoship@sot-omp-marketplace", "0.4.0", "rules/kb-first.md", "package text")
    (path / ".omp" / "rules" / "kb-first.md").write_text("package text", encoding="utf-8")
    (path / ".omp" / "rules" / "own.md").write_text("project text", encoding="utf-8")
    machine.consumer("legacy", path, [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                     flat=[".omp/rules"])

    result = machine.run(machine.write_registry(), "migrate")

    assert result.returncode == 0, result.stdout
    assert (path / ".omp" / "rules" / "kb-first.md").exists()
    assert (path / ".omp" / "rules" / "own.md").exists()
    assert "совпадает 1 · расходится 0 · свои 1" in result.stdout
    assert "свои файлы проекта (остаются): .omp/rules/own.md" in result.stdout


def test_migrate_apply_refuses_while_divergent_files_exist(machine: Machine) -> None:
    path = machine.project("legacy", [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                           flat=[".omp/rules"])
    machine.package_file("ontoship@sot-omp-marketplace", "0.4.0", "rules/kb-first.md", "package text")
    (path / ".omp" / "rules" / "kb-first.md").write_text("local edit", encoding="utf-8")
    machine.consumer("legacy", path, [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                     flat=[".omp/rules"])

    result = machine.run(machine.write_registry(), "migrate", "--apply")

    assert result.returncode == 1
    assert (path / ".omp" / "rules" / "kb-first.md").read_text(encoding="utf-8") == "local edit"
    assert "расходится с пакетом 1" in result.stdout


def test_migrate_apply_removes_redundant_files_and_keeps_the_flagged(machine: Machine) -> None:
    path = machine.project("legacy", [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                           flat=[".omp/rules"])
    machine.package_file("ontoship@sot-omp-marketplace", "0.4.0", "rules/kb-first.md", "package text")
    (path / ".omp" / "rules" / "kb-first.md").write_text("package text", encoding="utf-8")
    (path / ".omp" / "rules" / "own.md").write_text("project text", encoding="utf-8")
    machine.consumer("legacy", path, [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                     flat=[".omp/rules"])

    result = machine.run(machine.write_registry(), "migrate", "--apply",
                         "--keep", str(path / ".omp" / "rules" / "own.md"))

    assert result.returncode == 0, result.stdout
    assert not (path / ".omp" / "rules" / "kb-first.md").exists()
    assert (path / ".omp" / "rules" / "own.md").exists()


def test_scan_records_observed_state_and_repeats_identically(machine: Machine) -> None:
    path = machine.project("stale", [("ontoship@sot-omp-marketplace", "project", "0.3.0")],
                           flat=[".omp/rules"], hook="echo напоминание\n")
    machine.package_file("ontoship@sot-omp-marketplace", "0.3.0", "rules/kb-first.md", "package text")
    (path / ".omp" / "rules" / "kb-first.md").write_text("старая копия", encoding="utf-8")
    machine.consumer("stale", path, [("ontoship@sot-omp-marketplace", "project", None)])

    registry = machine.write_registry()
    assert machine.run(registry, "scan").returncode == 0
    first = json.loads(registry.read_text(encoding="utf-8"))
    assert machine.run(registry, "scan").returncode == 0
    second = json.loads(registry.read_text(encoding="utf-8"))

    def observed(doc: dict) -> dict:
        consumer = doc["consumers"][0]
        return {"installed": consumer["plugins"][0]["installed"],
                "flat": consumer["legacy"]["flat"],
                "worktree": consumer["worktreeInit"]}

    assert observed(first) == observed(second)
    assert observed(first) == {"installed": "0.3.0",
                               "flat": [".omp/rules/kb-first.md"],
                               "worktree": {"hook": "tasks/init-worktree.sh", "installsPlugins": False}}


def test_upgrade_reports_unreachable_consumer_and_keeps_gate_red(machine: Machine) -> None:
    """Недоступный потребитель — тот же дрейф, что в check: rc=1 и он виден в JSON."""
    stale = machine.project("stale", [("ontoship@sot-omp-marketplace", "project", "0.3.0")])
    machine.consumer("stale", stale, [("ontoship@sot-omp-marketplace", "project", "0.3.0")])
    machine.consumer("moved", machine.root / "moved-away", [])

    result = machine.run(machine.write_registry(), "upgrade", "--yes", "--json")

    payload = json.loads(result.stdout)
    assert result.returncode == 1, "upgrade не должен быть зелёным, когда потребитель не наблюдался"
    assert [row["name"] for row in payload["skipped"]] == ["moved"]
    assert payload["results"][0]["ok"] is True


def test_upgrade_dry_run_is_red_when_a_consumer_was_not_observed(machine: Machine) -> None:
    stale = machine.project("stale", [("ontoship@sot-omp-marketplace", "project", "0.3.0")])
    machine.consumer("stale", stale, [("ontoship@sot-omp-marketplace", "project", "0.3.0")])
    machine.consumer("moved", machine.root / "moved-away", [])

    result = machine.run(machine.write_registry(), "upgrade", "--dry-run")

    assert result.returncode == 1
    assert machine.mutations() == [], "план ничего не меняет, но красный он по делу"


def test_upgrade_summary_counts_actions_not_consumers(machine: Machine) -> None:
    path = machine.project("both")
    machine.consumer("both", path, [("ontoship@sot-omp-marketplace", "project", None),
                                    ("1c@sot-omp-marketplace", "project", None)])

    result = machine.run(machine.write_registry(), "upgrade", "--yes", fail_mutations=True)

    assert result.returncode == 1
    assert "выполнено: 0 · провалов: 2" in result.stdout


def test_check_survives_non_json_omp_output(machine: Machine) -> None:
    """Новая версия omp добавила строку в stdout — это строка отчёта, не трейсбек."""
    path = machine.project("clean")
    machine.consumer("clean", path, [])

    result = machine.run(machine.write_registry(), "check", garbage_list=True)

    assert result.returncode == 1
    assert "не-JSON" in result.stdout
    assert "Traceback" not in result.stderr


def test_missing_omp_is_a_usage_error(machine: Machine) -> None:
    """Без omp инструменту нечего делать: exit 2, а не «дрейф»."""
    path = machine.project("clean")
    machine.consumer("clean", path, [])
    empty_bin = machine.root / "empty-bin"
    empty_bin.mkdir()
    env = {**os.environ, "PATH": str(empty_bin)}

    result = subprocess.run(
        [sys.executable, str(TOOL), "--registry", str(machine.write_registry()),
         "--marketplaces", str(machine.marketplaces), "check"],
        capture_output=True, text=True, env=env,
    )

    assert result.returncode == 2
    assert "не найден исполняемый файл omp" in result.stderr


def test_empty_flat_directory_is_not_a_copy(machine: Machine) -> None:
    """Пустой .omp/rules ничего не перекрывает — это не legacy."""
    path = machine.project("emptied", [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                           hook="omp plugin install --scope project x\n")
    (path / ".omp" / "rules").mkdir(parents=True)
    machine.consumer("emptied", path, [("ontoship@sot-omp-marketplace", "project", "0.4.0")])

    result = machine.run(machine.write_registry(), "check")

    assert result.returncode == 0, result.stdout
    assert "legacy" not in result.stdout


def test_verify_counts_deploy_check_warnings_as_non_failure(machine: Machine) -> None:
    """deploy-check: 0 — чисто, 2 — предупреждения, 1 — критика. Двойка не провал."""
    path = machine.project("warned", [("ontoship@sot-omp-marketplace", "project", "0.4.0")])
    machine.package_file("ontoship@sot-omp-marketplace", "0.4.0", "skills/kb-search/gitmark.py",
                         "import sys\nprint('ok')\n")
    machine.package_file("ontoship@sot-omp-marketplace", "0.4.0", "scripts/deploy-check.sh",
                         "#!/usr/bin/env bash\necho '[WARN] .gitignore: нет строки .scratch/'\necho 'deploy-check: exit=2'\nexit 2\n")
    machine.consumer("warned", path, [("ontoship@sot-omp-marketplace", "project", "0.4.0")])

    result = machine.run(machine.write_registry(), "verify", "--json")

    assert result.returncode == 0, result.stdout
    checks = {c["check"]: c for c in json.loads(result.stdout)["consumers"][0]["checks"]}
    assert checks["deploy-check"]["ok"] is True and checks["deploy-check"]["warn"] is True
    assert checks["deploy-check"]["out"].startswith("[WARN]"), "причина важнее строки-итога"
    assert ".scratch/" in checks["deploy-check"]["out"]
    assert checks["index"]["ok"] is True and checks["index"]["warn"] is False


def test_verify_human_output_marks_warnings(machine: Machine) -> None:
    path = machine.project("warned", [("ontoship@sot-omp-marketplace", "project", "0.4.0")])
    machine.package_file("ontoship@sot-omp-marketplace", "0.4.0", "skills/kb-search/gitmark.py",
                         "import sys\nprint('ok')\n")
    machine.package_file("ontoship@sot-omp-marketplace", "0.4.0", "scripts/deploy-check.sh",
                         "#!/usr/bin/env bash\necho '[WARN] .gitignore: нет строки .scratch/'\n"
                         "echo 'deploy-check: exit=2'\nexit 2\n")
    machine.consumer("warned", path, [("ontoship@sot-omp-marketplace", "project", "0.4.0")])

    result = machine.run(machine.write_registry(), "verify")

    assert result.returncode == 0, result.stdout
    assert "deploy-check:⚠" in result.stdout
    assert "[WARN] .gitignore: нет строки .scratch/" in result.stdout


def test_migrate_accept_divergent_removes_flagged_files(machine: Machine) -> None:
    """Без флага расходящийся файл блокирует; с флагом — снимается по решению оператора."""
    path = machine.project("legacy", [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                           flat=[".omp/rules"])
    machine.package_file("ontoship@sot-omp-marketplace", "0.4.0", "rules/kb-first.md", "package text")
    (path / ".omp" / "rules" / "kb-first.md").write_text("local edit", encoding="utf-8")
    machine.consumer("legacy", path, [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                     flat=[".omp/rules"])

    refused = machine.run(machine.write_registry(), "migrate", "--apply")
    assert refused.returncode == 1
    assert (path / ".omp" / "rules" / "kb-first.md").exists()
    assert "--accept-divergent" in refused.stdout

    accepted = machine.run(machine.write_registry(), "migrate", "--apply", "--accept-divergent")

    assert accepted.returncode == 0, accepted.stdout
    assert not (path / ".omp" / "rules" / "kb-first.md").exists()


def test_migrate_keeps_project_own_files_and_removes_copies(machine: Machine) -> None:
    """Свои файлы проекта — не копия пакета: --apply их оставляет, --accept-unique снимает."""
    path = machine.project("mixed", [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                           flat=[".omp/rules"])
    machine.package_file("ontoship@sot-omp-marketplace", "0.4.0", "rules/kb-first.md", "package text")
    (path / ".omp" / "rules" / "kb-first.md").write_text("package text", encoding="utf-8")
    (path / ".omp" / "rules" / "erp-main-test-contour.md").write_text("своё правило", encoding="utf-8")
    machine.consumer("mixed", path, [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                     flat=[".omp/rules"])

    kept = machine.run(machine.write_registry(), "migrate", "--apply")

    assert kept.returncode == 0, kept.stdout
    assert not (path / ".omp" / "rules" / "kb-first.md").exists(), "копия пакета снята"
    assert (path / ".omp" / "rules" / "erp-main-test-contour.md").exists(), "свой файл остался"

    # Осознанное «снять и своё» — отдельный флаг.
    (path / ".omp" / "rules" / "kb-first.md").write_text("package text", encoding="utf-8")
    swept = machine.run(machine.write_registry(), "migrate", "--apply", "--accept-unique")

    assert swept.returncode == 0, swept.stdout
    assert not (path / ".omp" / "rules" / "erp-main-test-contour.md").exists()


def test_hook_delegating_to_package_canon_counts_as_installing(machine: Machine) -> None:
    """Обёртка над каноном: установку делает канон из пакета, а не файл проекта."""
    canon = "skills/1c-project-bootstrap/scripts/init-worktree.sh"
    path = machine.project("wrapper", [("1c@sot-omp-marketplace", "project", "0.1.2")])
    (path / "tasks").mkdir(exist_ok=True)
    (path / "tasks" / "init-worktree.sh").write_text(
        '#!/usr/bin/env bash\nset -euo pipefail\nCANON="' + canon + '"\n'
        'for base in "$ROOT" "$MAIN"; do\n'
        '\tcandidate="$base/.omp/plugins/node_modules/1c-omp/$CANON"\n'
        '\tif [[ -f "$candidate" ]]; then exec bash "$candidate" "$@"; fi\ndone\n',
        encoding="utf-8")
    machine.package_file("1c@sot-omp-marketplace", "0.1.2", canon,
                         "#!/usr/bin/env bash\nomp plugin install --scope project x\n")
    machine.consumer("wrapper", path, [("1c@sot-omp-marketplace", "project", "0.1.2")])

    result = machine.run(machine.write_registry(), "check")

    assert result.returncode == 0, result.stdout
    assert "worktree-gap" not in result.stdout


def test_reminder_in_echo_is_not_an_install_step(machine: Machine) -> None:
    """Напоминание в echo — не установка: иначе гейт зеленеет, а ворктри остаются без плагинов."""
    path = machine.project("reminder", [("ontoship@sot-omp-marketplace", "project", "0.4.0")])
    (path / "tasks").mkdir(exist_ok=True)
    (path / "tasks" / "init-worktree.sh").write_text(
        "#!/usr/bin/env bash\necho 'Поставь плагин: omp plugin install --scope project ontoship@x' >&2\n",
        encoding="utf-8")
    machine.consumer("reminder", path, [("ontoship@sot-omp-marketplace", "project", "0.4.0")])

    result = machine.run(machine.write_registry(), "check")

    assert result.returncode == 1
    assert "worktree-gap" in result.stdout


def test_reminder_in_canon_echo_is_not_an_install_step(machine: Machine) -> None:
    canon = "skills/1c-project-bootstrap/scripts/init-worktree.sh"
    path = machine.project("wrapper", [("1c@sot-omp-marketplace", "project", "0.1.2")])
    (path / "tasks").mkdir(exist_ok=True)
    (path / "tasks" / "init-worktree.sh").write_text(
        '#!/usr/bin/env bash\nCANON="' + canon + '"\nexec bash "$ROOT/.omp/plugins/node_modules/1c-omp/$CANON" "$@"\n',
        encoding="utf-8")
    machine.package_file("1c@sot-omp-marketplace", "0.1.2", canon,
                         "#!/usr/bin/env bash\necho 'не забудь: omp plugin install --scope project 1c@x'\n")
    machine.consumer("wrapper", path, [("1c@sot-omp-marketplace", "project", "0.1.2")])

    result = machine.run(machine.write_registry(), "check")

    assert result.returncode == 1
    assert "worktree-gap" in result.stdout


def test_install_step_inside_quotes_is_still_code(machine: Machine) -> None:
    """Команда в коде рядом с echo — установка; срезаем только кавычки, не строку."""
    canon = "skills/1c-project-bootstrap/scripts/init-worktree.sh"
    path = machine.project("wrapper", [("1c@sot-omp-marketplace", "project", "0.1.2")])
    (path / "tasks").mkdir(exist_ok=True)
    (path / "tasks" / "init-worktree.sh").write_text(
        '#!/usr/bin/env bash\nCANON="' + canon + '"\nexec bash "$ROOT/$CANON" "$@"\n', encoding="utf-8")
    machine.package_file("1c@sot-omp-marketplace", "0.1.2", canon,
                         '#!/usr/bin/env bash\n'
                         'if (cd "$WORKTREE" && omp plugin install --scope project "$spec"); then\n'
                         '\techo "✓ плагин $spec"\nfi\n')
    machine.consumer("wrapper", path, [("1c@sot-omp-marketplace", "project", "0.1.2")])

    result = machine.run(machine.write_registry(), "check")

    assert result.returncode == 0, result.stdout
    assert "worktree-gap" not in result.stdout


def test_hook_delegating_to_silent_canon_is_a_gap(machine: Machine) -> None:
    canon = "skills/1c-project-bootstrap/scripts/init-worktree.sh"
    path = machine.project("wrapper", [("1c@sot-omp-marketplace", "project", "0.1.2")])
    (path / "tasks").mkdir(exist_ok=True)
    (path / "tasks" / "init-worktree.sh").write_text(
        '#!/usr/bin/env bash\nCANON="' + canon + '"\nexec bash "$ROOT/.omp/plugins/node_modules/1c-omp/$CANON" "$@"\n',
        encoding="utf-8")
    machine.package_file("1c@sot-omp-marketplace", "0.1.2", canon,
                         "#!/usr/bin/env bash\necho 'копирую артефакты'\n")
    machine.consumer("wrapper", path, [("1c@sot-omp-marketplace", "project", "0.1.2")])

    result = machine.run(machine.write_registry(), "check")

    assert result.returncode == 1
    assert "worktree-gap" in result.stdout


def test_flat_copies_without_installed_packages_are_not_called_own(machine: Machine) -> None:
    """Пока пакет не поставлен, файлы под .omp/<dir> нельзя объявить своими: это может быть копия."""
    path = machine.project("flatonly", flat=[".omp/rules"])
    (path / ".omp" / "rules" / "kb-first.md").write_text("копия пакета", encoding="utf-8")
    machine.consumer("flatonly", path, [("ontoship@sot-omp-marketplace", "project", None)])

    result = machine.run(machine.write_registry(), "check")

    assert result.returncode == 1
    assert "legacy-unverified" in result.stdout
    assert "own-rules" not in result.stdout


def test_own_rules_warns_when_an_expected_package_is_missing(machine: Machine) -> None:
    """Свои файлы рядом с непоставленным пакетом — мягко, но с оговоркой."""
    other = machine.project("mixed", [("unica@unica", "project", "0.12.3")], flat=[".omp/rules"])
    machine.package_file("unica@unica", "0.12.3", "skills/x/SKILL.md", "пакет unica")
    (other / ".omp" / "rules" / "kb-first.md").write_text("копия ontoship", encoding="utf-8")
    machine.consumer("mixed", other, [("unica@unica", "project", "0.12.3"),
                                      ("ontoship@sot-omp-marketplace", "project", None)])

    result = machine.run(machine.write_registry(), "check")

    assert result.returncode == 1, "missing делает гейт красным"
    assert "сначала upgrade" in result.stdout
    assert "ontoship@sot-omp-marketplace" in result.stdout


def test_project_own_files_are_not_drift(machine: Machine) -> None:
    """Файл проекта под неплагинным именем — не копия пакета и не повод для красного гейта."""
    path = machine.project("own", [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                           flat=[".omp/rules"], hook="omp plugin install --scope project x\n")
    machine.package_file("ontoship@sot-omp-marketplace", "0.4.0", "rules/kb-first.md", "package text")
    (path / ".omp" / "rules" / "erp-main-test-contour.md").write_text("своё правило", encoding="utf-8")
    machine.consumer("own", path, [("ontoship@sot-omp-marketplace", "project", "0.4.0")])

    result = machine.run(machine.write_registry(), "check")

    assert result.returncode == 0, result.stdout
    assert "own-rules" in result.stdout and "legacy" not in result.stdout


def test_verify_shows_failure_reason_even_beside_warnings(machine: Machine) -> None:
    """Три [WARN] не должны вытеснять [FAIL]: провал важнее предупреждений."""
    path = machine.project("broken", [("ontoship@sot-omp-marketplace", "project", "0.4.0")])
    machine.package_file("ontoship@sot-omp-marketplace", "0.4.0", "skills/kb-search/gitmark.py",
                         "import sys\nprint('ok')\n")
    machine.package_file("ontoship@sot-omp-marketplace", "0.4.0", "scripts/deploy-check.sh",
                         "#!/usr/bin/env bash\n"
                         "echo '[FAIL] отсутствует: AGENTS.md'\n"
                         "echo '[WARN] .gitignore: нет строки .gitmark/'\n"
                         "echo '[WARN] .gitignore: нет строки *-map.html'\n"
                         "echo '[WARN] .gitignore: нет строки .scratch/'\n"
                         "echo 'deploy-check: exit=1'\nexit 1\n")
    machine.consumer("broken", path, [("ontoship@sot-omp-marketplace", "project", "0.4.0")])

    result = machine.run(machine.write_registry(), "verify", "--json")

    assert result.returncode == 1
    detail = {c["check"]: c for c in json.loads(result.stdout)["consumers"][0]["checks"]}["deploy-check"]["out"]
    assert detail.startswith("[FAIL] отсутствует: AGENTS.md"), detail


def test_migrate_report_does_not_count_kept_files_as_accepted(machine: Machine) -> None:
    """--keep сильнее --accept: сохранённый файл не попадает в «принято к снятию»."""
    path = machine.project("legacy", [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                           flat=[".omp/rules"])
    machine.package_file("ontoship@sot-omp-marketplace", "0.4.0", "rules/kb-first.md", "package text")
    (path / ".omp" / "rules" / "own.md").write_text("своё", encoding="utf-8")
    machine.consumer("legacy", path, [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                     flat=[".omp/rules"])

    result = machine.run(machine.write_registry(), "migrate", "--accept-unique",
                         "--keep", ".omp/rules/own.md")

    assert result.returncode == 0, result.stdout
    assert "принято к снятию" not in result.stdout, "единственный unique-файл сохранён — счёт пуст"


def test_verify_skips_consumers_without_ontoship(machine: Machine) -> None:
    path = machine.project("bare")
    machine.consumer("bare", path, [])

    result = machine.run(machine.write_registry(), "verify")

    assert result.returncode == 0, result.stdout
    assert "ontoship не установлен" in result.stdout


def test_verify_runs_engine_deploy_check_and_version(machine: Machine) -> None:
    path = machine.project("clean", [("ontoship@sot-omp-marketplace", "project", "0.4.0")])
    machine.package_file("ontoship@sot-omp-marketplace", "0.4.0", "skills/kb-search/gitmark.py",
                         "import sys\nprint('gitmark', *sys.argv[1:])\n")
    machine.package_file("ontoship@sot-omp-marketplace", "0.4.0", "scripts/deploy-check.sh",
                         "#!/usr/bin/env bash\nexit 0\n")
    machine.consumer("clean", path, [("ontoship@sot-omp-marketplace", "project", "0.4.0")])

    result = machine.run(machine.write_registry(), "verify", "--json")

    assert result.returncode == 0, result.stdout
    checks = json.loads(result.stdout)["consumers"][0]["checks"]
    assert [c["check"] for c in checks] == ["index", "deploy-check", "version"]
    assert all(c["ok"] for c in checks)


def test_verify_fails_when_deploy_check_fails(machine: Machine) -> None:
    path = machine.project("broken", [("ontoship@sot-omp-marketplace", "project", "0.4.0")])
    machine.package_file("ontoship@sot-omp-marketplace", "0.4.0", "skills/kb-search/gitmark.py",
                         "import sys\nprint('ok')\n")
    machine.package_file("ontoship@sot-omp-marketplace", "0.4.0", "scripts/deploy-check.sh",
                         "#!/usr/bin/env bash\necho '[FAIL] нет AGENTS.md'\n"
                         "echo 'deploy-check: exit=1'\nexit 1\n")
    machine.consumer("broken", path, [("ontoship@sot-omp-marketplace", "project", "0.4.0")])

    result = machine.run(machine.write_registry(), "verify")

    assert result.returncode == 1
    assert "нет AGENTS.md" in result.stdout


def test_pin_without_install_is_a_real_drift(machine: Machine) -> None:
    """Закреплено 0.3.0, а плагина нет вовсе — обещание реестра не выполнено."""
    path = machine.project("pinned")
    machine.consumer("pinned", path, [("ontoship@sot-omp-marketplace", "project", None)])
    machine.consumers[-1]["plugins"][0]["pin"] = "0.3.0"

    result = machine.run(machine.write_registry(), "check", "--json")

    assert result.returncode == 1
    kinds = {d["kind"] for d in json.loads(result.stdout)["consumers"][0]["drifts"]}
    assert kinds == {"stale"}


def test_worktree_gap_alone_makes_check_red(machine: Machine) -> None:
    """Ворктри без плагинов — это дрейф: гейт не должен быть зелёным."""
    path = machine.project("reminder", [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                           hook="echo напоминание\n")
    machine.consumer("reminder", path, [("ontoship@sot-omp-marketplace", "project", "0.4.0")])

    result = machine.run(machine.write_registry(), "check")

    assert result.returncode == 1
    assert "worktree-gap" in result.stdout


def test_unreachable_consumer_does_not_hide_the_rest(machine: Machine) -> None:
    good = machine.project("good", [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                           hook="omp plugin install --scope project x\n")
    machine.consumer("good", good, [("ontoship@sot-omp-marketplace", "project", "0.4.0")])
    machine.consumer("moved", machine.root / "moved-away", [])

    result = machine.run(machine.write_registry(), "check")

    assert result.returncode == 1, "недоступный потребитель — дрейф, а не отказ инструмента"
    assert "moved" in result.stdout and "good" in result.stdout
    assert "чисто" in result.stdout


def test_upgrade_json_is_machine_readable(machine: Machine) -> None:
    path = machine.project("stale", [("ontoship@sot-omp-marketplace", "project", "0.3.0")])
    machine.consumer("stale", path, [("ontoship@sot-omp-marketplace", "project", "0.3.0")])

    plan = machine.run(machine.write_registry(), "upgrade", "--dry-run", "--json")
    applied = machine.run(machine.write_registry(), "upgrade", "--yes", "--json")

    assert plan.returncode == 0, plan.stdout
    assert json.loads(plan.stdout)["dryRun"] is True
    assert json.loads(plan.stdout)["actions"][0]["action"] == "upgrade"
    assert json.loads(applied.stdout)["results"][0]["ok"] is True


def test_migrate_apply_json_really_applies(machine: Machine) -> None:
    path = machine.project("legacy", [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                           flat=[".omp/rules"])
    machine.package_file("ontoship@sot-omp-marketplace", "0.4.0", "rules/kb-first.md", "package text")
    (path / ".omp" / "rules" / "kb-first.md").write_text("package text", encoding="utf-8")
    machine.consumer("legacy", path, [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                     flat=[".omp/rules"])

    result = machine.run(machine.write_registry(), "migrate", "--apply", "--json")

    payload = json.loads(result.stdout)
    assert result.returncode == 0, result.stdout
    assert payload["applied"] is True and payload["consumers"][0]["removed"] == 1
    assert not (path / ".omp" / "rules" / "kb-first.md").exists()


def test_migrate_without_installed_packages_names_the_real_reason(machine: Machine) -> None:
    """Сравнивать не с чем — это не «файлы расходятся с пакетом»."""
    path = machine.project("legacy", flat=[".omp/rules"])
    (path / ".omp" / "rules" / "kb-first.md").write_text("text", encoding="utf-8")
    machine.consumer("legacy", path, [("ontoship@sot-omp-marketplace", "project", None)],
                     flat=[".omp/rules"])

    report = machine.run(machine.write_registry(), "migrate")
    applied = machine.run(machine.write_registry(), "migrate", "--apply")

    assert "эталон недоступен" in report.stdout
    assert "сначала upgrade" in applied.stdout
    assert (path / ".omp" / "rules" / "kb-first.md").exists()


def test_migrate_keep_absolute_path_of_one_of_two_consumers(machine: Machine) -> None:
    alpha = machine.project("alpha", [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                            flat=[".omp/rules"])
    beta = machine.project("beta", [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                           flat=[".omp/rules"])
    machine.package_file("ontoship@sot-omp-marketplace", "0.4.0", "rules/kb-first.md", "package text")
    for project in (alpha, beta):
        (project / ".omp" / "rules" / "kb-first.md").write_text("package text", encoding="utf-8")
        (project / ".omp" / "rules" / "own.md").write_text("своё", encoding="utf-8")
    machine.consumer("alpha", alpha, [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                     flat=[".omp/rules"])
    machine.consumer("beta", beta, [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                     flat=[".omp/rules"])

    result = machine.run(machine.write_registry(), "migrate", "--apply",
                         "--keep", str(alpha / ".omp" / "rules" / "own.md"))

    assert result.returncode == 0, result.stdout + result.stderr
    assert (alpha / ".omp" / "rules" / "own.md").exists()
    assert not (alpha / ".omp" / "rules" / "kb-first.md").exists()
    assert (beta / ".omp" / "rules" / "own.md").exists(), "свой файл beta остаётся и без --keep"
    assert not (beta / ".omp" / "rules" / "kb-first.md").exists(), "чужой --keep не мешает beta"


def test_plugin_absent_from_catalog_is_reported(machine: Machine) -> None:
    path = machine.project("typo", [("ontoship@unica", "project", "0.4.0")])
    machine.consumer("typo", path, [("ontoship@unica", "project", "0.4.0")])

    result = machine.run(machine.write_registry(), "check", "--json")

    assert result.returncode == 1
    drift = json.loads(result.stdout)["consumers"][0]["drifts"][0]
    assert drift["kind"] == "unknown"
    assert "нет в каталоге unica" in drift["detail"]


def test_foreign_catalog_versions_are_read(machine: Machine) -> None:
    path = machine.project("legacy1c", [("unica@unica", "project", "0.12.0")])
    machine.consumer("legacy1c", path, [("unica@unica", "project", "0.12.0")])

    result = machine.run(machine.write_registry(), "check", "--json")

    drift = json.loads(result.stdout)["consumers"][0]["drifts"][0]
    assert drift["kind"] == "stale"
    assert "0.12.3" in drift["detail"], "версия берётся из каталога unica, а не из своего"

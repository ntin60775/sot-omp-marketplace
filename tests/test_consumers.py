"""Тесты scripts/consumers.py: дрейф, план обновления, снятие плоских копий.

Всё герметично: поддельный `omp` в PATH, свои каталог/маркетплейсы/проекты во
временном каталоге. Настоящие проекты машины и сеть не трогаются.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parent.parent / "scripts" / "consumers.py"
REPO = Path(__file__).resolve().parent.parent
CATALOG = "sot-omp-marketplace"
LAYOUT_DOC = REPO / "docs" / "reference" / "consumer-repo-layout.md"

# Имя пакета в `node_modules` не совпадает с именем плагина: `1c` ставится пакетом
# `1c-omp` (живая машина). Инструмент сопоставляет записи с плагинами по цели
# симлинка, поэтому расхождение держится в фикстуре: проверка «по имени» прошла бы
# здесь и упала на живой машине.
PACKAGE_NAMES = {"1c": "1c-omp"}


def package_name(plugin_id: str) -> str:
    plugin = plugin_id.partition("@")[0]
    return PACKAGE_NAMES.get(plugin, plugin)


def documented_ignores() -> list[str]:
    """Канонический блок `.gitignore` — из документа, а не из копии в тесте.

    Инструмент держит тот же набор константой; тест `test_check_lists_the_documented_ignores`
    сверяет их, поэтому политика и код не могут разъехаться молча.
    """
    doc = LAYOUT_DOC.read_text(encoding="utf-8")
    block = re.search(r"```gitignore\n(.*?)```", doc, re.S)
    assert block, f"в {LAYOUT_DOC.name} пропал блок ```gitignore с канонической политикой"
    return [line.strip() for line in block.group(1).splitlines()
            if line.strip() and not line.strip().startswith("#")]


DOCUMENTED_IGNORES = documented_ignores()

# Канонический блок — раскладка по умолчанию: потребитель без него уже дрейфует.
CANONICAL_IGNORES = "\n".join(DOCUMENTED_IGNORES) + "\n"

# Живая раскладка (найдена на 1С-потребителе): `.omp/*` закрывает всё под `.omp/`,
# а `!` возвращает в git своё — свои rules/skills/commands проект версионирует
# осознанно, и проверка политики об этом не судит.
OWN_SUBDIRS_IGNORES = (
    ".omp/*\n"
    "!.omp/RULES.md\n"
    "!.omp/rules/\n"
    "!.omp/skills/\n"
    "!.omp/commands/\n"
    "!.omp/scripts/\n"
    "!.omp/extensions/\n"
    ".artifacts/\n"
    ".gitmark/\n"
    "*-map.html\n"
)

# Хук ворктри: живая форма — обёртка зовёт канон из пакета, логика живёт в плагине.
# Два способа назвать путь; регексп чекера на них реагирует по-разному, поэтому обе
# формы закреплены тестами.
CANON_REL = "skills/1c-project-bootstrap/scripts/init-worktree.sh"
WRAPPER_VIA_LITERAL = (
    '#!/usr/bin/env bash\nset -euo pipefail\n'
    f'CANON="{CANON_REL}"\n'
    'exec bash "$ROOT/.omp/plugins/node_modules/1c-omp/$CANON" "$@"\n')
WRAPPER_VIA_VARIABLE = (
    '#!/usr/bin/env bash\nset -euo pipefail\n'
    'PKG="$MAIN/.omp/plugins/node_modules/1c-omp"\n'
    f'CANON="$PKG/{CANON_REL}"\n'
    'exec bash "$CANON" "$@"\n')

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
        # Машинный (`user`) корень установки: у инструмента это `~/.omp/plugins`, и
        # HOME подменяется, чтобы тест не заглядывал в настоящий. Домашний каталог —
        # сосед корня, а не его подкаталог: на живой машине `~` не входит в корни
        # поиска, иначе `~/.omp/` сам выглядел бы потребителем.
        self.home = root.parent / f"{root.name}-home"
        self.home.mkdir()

        self.catalog = root / "catalog.json"
        self.catalog.write_text(json.dumps({
            "name": CATALOG,
            "metadata": {"version": "0.3.1"},
            "plugins": [{"name": "ontoship", "version": "0.4.0"},
                        {"name": "1c", "version": "0.1.2"},
                        # Каталог плагин знает, а версии не объявил — так выглядит
                        # `redaktura-skills@redaktura-skills` (2026-09-17).
                        {"name": "skill-only", "description": "навык без версии"}],
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
                hook: str | None = None, gitignore: str | None = None) -> Path:
        """plugins: (id, scope, version); flat: каталоги вроде .omp/rules; hook: текст скрипта ворктри.

        `.gitignore` по умолчанию — канонический блок из документа: потребитель без
        него уже дрейфует, и это проверяет отдельный тест, а не каждый. Живая
        раскладка «`.omp/*` плюс `!` для своих каталогов» — `OWN_SUBDIRS_IGNORES`.
        """
        path = self.root / name
        (path / ".omp").mkdir(parents=True)
        (path / ".gitignore").write_text(
            gitignore if gitignore is not None else CANONICAL_IGNORES, encoding="utf-8")
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
        for plugin, scope, version in plugins:
            install = self.root / "cache" / f"{plugin}-{version}"
            install.mkdir(parents=True, exist_ok=True)
            self.link(plugin, scope, path).symlink_to(install)
        self.world_file.write_text(json.dumps(self.world), encoding="utf-8")
        return path

    def link_root(self, scope: str, project: Path) -> Path:
        """Корень `node_modules`: проектный плагин линкуется в проект, машинный — в `~`."""
        if scope == "user":
            return self.home / ".omp" / "plugins" / "node_modules"
        return project / ".omp" / "plugins" / "node_modules"

    def link(self, plugin: str, scope: str, project: Path) -> Path:
        """Запись `node_modules` для плагина — по имени пакета, а не по id."""
        root = self.link_root(scope, project)
        root.mkdir(parents=True, exist_ok=True)
        return root / package_name(plugin)

    def break_link(self, plugin: str, project: Path, scope: str = "project") -> Path:
        """Запись ведёт на снесённый кэш — состояние `retail` 2026-09-17."""
        link = self.link(plugin, scope, project)
        link.unlink()
        link.symlink_to(str(self.root / "cache" / f"снесено-{package_name(plugin)}"))
        return link

    def drop_link(self, plugin: str, project: Path, scope: str = "project") -> None:
        """Запись убрана: плагин зарегистрирован, а линка на пакет нет."""
        self.link(plugin, scope, project).unlink()

    def kill_install(self, plugin: str, version: str) -> None:
        """Кэш пакета снесён: `installPath` в реестре установки остался, диска нет."""
        shutil.rmtree(self.root / "cache" / f"{plugin}-{version}")

    def forget_install_path(self, project: Path, plugin_id: str) -> None:
        """omp не назвал путь пакета: проверять поставку нечем."""
        for entry in self.world[str(project)]["marketplace"]:
            if entry["id"] == plugin_id:
                entry["entries"][0].pop("installPath")
        self.world_file.write_text(json.dumps(self.world), encoding="utf-8")

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
            # Машинный корень установки инструмент берёт из `~`: без подмены HOME
            # тест смотрел бы в настоящий `~/.omp/plugins` оператора.
            "HOME": str(self.home),
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


def test_extension_copies_shadow_the_package_and_are_migrated(machine: Machine) -> None:
    """Плагин может доставлять хуки: копия в проекте глушит плагинный гейт.

    `.omp/extensions/` по политике — каталог проекта, но файл под плагинным именем
    там уже не своё, а копия: нативный провайдер (100) перекрывает плагинный (90),
    и поставленный контур работает по старому коду.
    """
    path = machine.project("hooked", [("1c@sot-omp-marketplace", "project", "0.1.2")],
                           flat=[".omp/extensions"])
    machine.package_file("1c@sot-omp-marketplace", "0.1.2", "extensions/unica-gate.ts", "package gate")
    (path / ".omp" / "extensions" / "unica-gate.ts").write_text("package gate", encoding="utf-8")
    machine.consumer("hooked", path, [("1c@sot-omp-marketplace", "project", "0.1.2")],
                     flat=[".omp/extensions"])

    check = machine.run(machine.write_registry(), "check", "--json")
    kinds = {d["kind"] for row in json.loads(check.stdout)["consumers"] for d in row["drifts"]}
    assert "legacy" in kinds, "копия хука перекрывает плагинный гейт — это дрейф"

    migrated = machine.run(machine.write_registry(), "migrate", "--apply")

    assert migrated.returncode == 0, migrated.stdout
    assert not (path / ".omp" / "extensions" / "unica-gate.ts").exists()


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
    path = machine.project("wrapper", [("1c@sot-omp-marketplace", "project", "0.1.2")],
                           hook=WRAPPER_VIA_LITERAL)
    machine.package_file("1c@sot-omp-marketplace", "0.1.2", CANON_REL,
                         "#!/usr/bin/env bash\nomp plugin install --scope project x\n")
    machine.consumer("wrapper", path, [("1c@sot-omp-marketplace", "project", "0.1.2")])

    result = machine.run(machine.write_registry(), "check")

    assert result.returncode == 0, result.stdout
    assert "worktree-gap" not in result.stdout


def test_reminder_in_echo_is_not_an_install_step(machine: Machine) -> None:
    """Напоминание в echo — не установка: иначе гейт зеленеет, а ворктри остаются без плагинов."""
    path = machine.project("reminder", [("ontoship@sot-omp-marketplace", "project", "0.4.0")],
                           hook="#!/usr/bin/env bash\n"
                                "echo 'Поставь плагин: omp plugin install --scope project ontoship@x' >&2\n")
    machine.consumer("reminder", path, [("ontoship@sot-omp-marketplace", "project", "0.4.0")])

    result = machine.run(machine.write_registry(), "check")

    assert result.returncode == 1
    assert "worktree-gap" in result.stdout


def test_reminder_in_canon_echo_is_not_an_install_step(machine: Machine) -> None:
    """Напоминание в каноне — тоже не установка: смотреть надо на код, а не на текст."""
    path = machine.project("wrapper", [("1c@sot-omp-marketplace", "project", "0.1.2")],
                           hook=WRAPPER_VIA_LITERAL)
    machine.package_file("1c@sot-omp-marketplace", "0.1.2", CANON_REL,
                         "#!/usr/bin/env bash\necho 'не забудь: omp plugin install --scope project 1c@x'\n")
    machine.consumer("wrapper", path, [("1c@sot-omp-marketplace", "project", "0.1.2")])

    result = machine.run(machine.write_registry(), "check")

    assert result.returncode == 1
    assert "worktree-gap" in result.stdout


def test_install_step_inside_quotes_is_still_code(machine: Machine) -> None:
    """Команда в коде рядом с echo — установка; срезаем только кавычки, не строку."""
    path = machine.project("wrapper", [("1c@sot-omp-marketplace", "project", "0.1.2")],
                           hook=WRAPPER_VIA_LITERAL)
    machine.package_file("1c@sot-omp-marketplace", "0.1.2", CANON_REL,
                         '#!/usr/bin/env bash\n'
                         'if (cd "$WORKTREE" && omp plugin install --scope project "$spec"); then\n'
                         '\techo "✓ плагин $spec"\nfi\n')
    machine.consumer("wrapper", path, [("1c@sot-omp-marketplace", "project", "0.1.2")])

    result = machine.run(machine.write_registry(), "check")

    assert result.returncode == 0, result.stdout
    assert "worktree-gap" not in result.stdout


def test_hook_delegating_through_a_variable_counts_as_installing(machine: Machine) -> None:
    """Обёртка зовёт канон через переменную — путь в тексте выглядит как `PKG/skills/…`.

    Регексп забирает имя переменной в путь, поэтому пакет-относительный хвост нужно
    пробовать отдельно: иначе корректная обёртка получает ложный `worktree-gap`.
    """
    path = machine.project("wrapper-var", [("1c@sot-omp-marketplace", "project", "0.1.2")],
                           hook=WRAPPER_VIA_VARIABLE)
    machine.package_file("1c@sot-omp-marketplace", "0.1.2", CANON_REL,
                         "#!/usr/bin/env bash\nomp plugin install --scope project x\n")
    machine.consumer("wrapper-var", path, [("1c@sot-omp-marketplace", "project", "0.1.2")])

    result = machine.run(machine.write_registry(), "check")

    assert result.returncode == 0, result.stdout
    assert "worktree-gap" not in result.stdout


def test_hook_delegating_to_silent_canon_is_a_gap(machine: Machine) -> None:
    """Канон без установки — гэп: обёртка делегирует, а плагинов в ворктри не будет."""
    path = machine.project("wrapper", [("1c@sot-omp-marketplace", "project", "0.1.2")],
                           hook=WRAPPER_VIA_LITERAL)
    machine.package_file("1c@sot-omp-marketplace", "0.1.2", CANON_REL,
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


# ----------------------------------------------- реестр на новой машине: init + discover


def test_init_creates_a_registry_that_passes_the_schema(machine: Machine) -> None:
    """Свежий клон: реестра нет — его заводит init, и он сразу годен для остальных команд."""
    machine.project("alpha")
    fresh = machine.root / "fresh.json"

    result = machine.run(fresh, "init", "--root", str(machine.root))

    assert result.returncode == 0, result.stdout + result.stderr
    doc = json.loads(fresh.read_text(encoding="utf-8"))
    assert doc["schemaVersion"] == 1
    assert doc["catalog"]["name"] == CATALOG, "имя каталога — из .omp-plugin/marketplace.json"
    assert doc["discoverRoots"] == [str(machine.root.resolve())]
    assert doc["machine"], "машина записана: реестр описывает одну машину"
    assert doc["consumers"] == [], "список наполняет наблюдение, а не init"


def test_init_refuses_to_overwrite_an_existing_registry(machine: Machine) -> None:
    registry = machine.write_registry()
    before = registry.read_text(encoding="utf-8")

    result = machine.run(registry, "init", "--root", str(machine.root))

    assert result.returncode == 2
    assert "уже есть" in result.stderr
    assert registry.read_text(encoding="utf-8") == before, "существующий реестр не трогается"


def test_init_without_a_root_is_a_usage_error(machine: Machine) -> None:
    """Корни поиска — знание оператора: угадывать их молча нельзя."""
    fresh = machine.root / "fresh.json"

    result = machine.run(fresh, "init")

    assert result.returncode == 2
    assert "--root" in result.stderr
    assert not fresh.exists(), "на ошибке реестр не создаётся"


def test_init_reports_a_missing_target_directory(machine: Machine) -> None:
    """Трейсбек вместо ошибки использования — худшее первое впечатление от bootstrap."""
    result = machine.run(machine.root / "missing" / "fresh.json", "init", "--root", str(machine.root))

    assert result.returncode == 2
    assert "каталога для реестра нет" in result.stderr


def test_missing_registry_points_at_init(machine: Machine) -> None:
    """Без реестра инструмент не молчит: он называет команду, которая его заводит."""
    result = machine.run(machine.root / "absent.json", "check")

    assert result.returncode == 2
    assert "реестр не найден" in result.stderr
    assert "init --root" in result.stderr


def test_discover_apply_adopts_candidates_with_observed_state(machine: Machine) -> None:
    alpha = machine.project("alpha", [("ontoship@sot-omp-marketplace", "project", "0.4.0")])
    machine.project("beta")
    fresh = machine.root / "fresh.json"
    machine.run(fresh, "init", "--root", str(machine.root))

    result = machine.run(fresh, "discover", "--apply")

    assert result.returncode == 0, result.stdout + result.stderr
    adopted = {c["name"]: c for c in json.loads(fresh.read_text(encoding="utf-8"))["consumers"]}
    assert set(adopted) == {"alpha", "beta"}
    assert adopted["alpha"]["path"] == str(alpha.resolve())
    assert adopted["alpha"]["plugins"] == [{"id": "ontoship@sot-omp-marketplace",
                                            "scope": "project", "installed": "0.4.0", "pin": None}]
    assert adopted["beta"]["plugins"] == [], "проект без плагинов — тоже потребитель"

    check = machine.run(fresh, "check")
    assert check.returncode == 0, check.stdout + check.stderr


def test_discover_apply_does_not_duplicate_on_a_second_run(machine: Machine) -> None:
    machine.project("alpha")
    fresh = machine.root / "fresh.json"
    machine.run(fresh, "init", "--root", str(machine.root))
    machine.run(fresh, "discover", "--apply")

    result = machine.run(fresh, "discover", "--apply")

    assert result.returncode == 0
    consumers = json.loads(fresh.read_text(encoding="utf-8"))["consumers"]
    assert [c["name"] for c in consumers] == ["alpha"]


def test_discover_apply_rejects_a_candidate_whose_name_breaks_the_schema(machine: Machine) -> None:
    """Имя потребителя — контракт для --only: не подходит под схему — не выдумываем."""
    machine.project("Bad_Name")
    fresh = machine.root / "fresh.json"
    machine.run(fresh, "init", "--root", str(machine.root))

    result = machine.run(fresh, "discover", "--apply")

    assert result.returncode == 1
    assert "не подходит под схему" in result.stdout
    assert json.loads(fresh.read_text(encoding="utf-8"))["consumers"] == []


def test_discover_apply_skips_a_plugin_package_by_default(machine: Machine) -> None:
    """`.omp/` с package.json — это пакет плагина, а не установка (ADR §5).

    Источник нельзя принять потребителем молча: он не потребитель. Осознанное
    исключение — назвать его явно через --only.
    """
    package = machine.project("plugin-source")
    (package / ".omp" / "package.json").write_text('{"name": "ontoship"}', encoding="utf-8")
    fresh = machine.root / "fresh.json"
    machine.run(fresh, "init", "--root", str(machine.root))

    result = machine.run(fresh, "discover", "--apply")

    assert result.returncode == 1
    assert "пакет плагина" in result.stdout
    assert json.loads(fresh.read_text(encoding="utf-8"))["consumers"] == []

    forced = machine.run(fresh, "discover", "--apply", "--only", "plugin-source")

    assert forced.returncode == 0, forced.stdout + forced.stderr
    assert [c["name"] for c in json.loads(fresh.read_text(encoding="utf-8"))["consumers"]] \
        == ["plugin-source"]


def test_discover_apply_excludes_a_path_instead_of_adopting_it(machine: Machine) -> None:
    source = machine.project("source-repo")
    machine.project("alpha")
    fresh = machine.root / "fresh.json"
    machine.run(fresh, "init", "--root", str(machine.root))

    result = machine.run(fresh, "discover", "--apply", "--exclude", str(source))

    assert result.returncode == 0, result.stdout + result.stderr
    doc = json.loads(fresh.read_text(encoding="utf-8"))
    assert [c["name"] for c in doc["consumers"]] == ["alpha"]
    assert doc["exclude"] == [{"path": str(source.resolve())}]


def test_discover_apply_only_flags_are_refused_without_apply(machine: Machine) -> None:
    """`--only`/`--exclude` — модификаторы записи: без --apply это тихий no-op."""
    machine.project("source-repo")
    registry = machine.write_registry()

    excluded = machine.run(registry, "discover", "--exclude", str(machine.root / "source-repo"))
    only = machine.run(registry, "discover", "--only", "source-repo")

    assert excluded.returncode == 2 and "--apply" in excluded.stderr
    assert only.returncode == 2 and "--apply" in only.stderr


def test_adoption_records_the_expected_scope_as_project(machine: Machine) -> None:
    """Машинную установку принятие не благословляет: check сразу зовёт её дрейфом."""
    machine.project("wide", [("ontoship@sot-omp-marketplace", "user", "0.4.0")])
    fresh = machine.root / "fresh.json"
    machine.run(fresh, "init", "--root", str(machine.root))
    machine.run(fresh, "discover", "--apply")

    result = machine.run(fresh, "check", "--json")

    drifts = json.loads(result.stdout)["consumers"][0]["drifts"]
    assert [d["kind"] for d in drifts] == ["scope"]
    assert "user-scope" in drifts[0]["detail"]


# --------------------------------------------------- политика .gitignore у потребителя


def test_check_lists_the_documented_ignores(machine: Machine) -> None:
    """Требуемый набор — ровно канонический блок документа, не своя копия в коде."""
    path = machine.project("bare", gitignore="")
    machine.consumer("bare", path, [])

    result = machine.run(machine.write_registry(), "check", "--json")

    assert result.returncode == 1
    drift = json.loads(result.stdout)["consumers"][0]["drifts"][0]
    assert drift["kind"] == "gitignore"
    assert drift["ignores"] == DOCUMENTED_IGNORES


def test_project_rules_and_append_system_are_versioned_not_ignored(machine: Machine) -> None:
    """`.omp/RULES.md` и `.omp/APPEND_SYSTEM.md` — проектные файлы omp, не машинный слой.

    Живой случай: `erp-demo` держит в `.omp/APPEND_SYSTEM.md` «Роль проекта» и
    сознательно версионирует его — политика требовала обратного и красила гейт.
    Машинный слой (`sot-omp-core`) в проекты не пишет: он в `~/.omp/agent/`.

    Тест переживёт возврат этих строк в политику: тогда проект, который их
    версионирует, покраснеет — и это будет видно здесь, а не только на машине.
    """
    versioned = [line for line in DOCUMENTED_IGNORES
                 if line not in (".omp/RULES.md", ".omp/APPEND_SYSTEM.md")]
    path = machine.project("own-role", gitignore="\n".join(versioned) + "\n")
    machine.consumer("own-role", path, [])

    result = machine.run(machine.write_registry(), "check")

    assert result.returncode == 0, result.stdout + result.stderr


def test_delivered_paths_still_red_the_gate(machine: Machine) -> None:
    """Проектные sticky-файлы ушли из политики — доставленное и производное остались.

    Проект закрывает только свои файлы: доставленное (`.omp/plugins/`, `.omp/mcp.json`)
    и производное (`.gitmark/`) обязаны остаться требованием, иначе гейт потеряет
    зубы ровно там, ради чего он заведён.
    """
    path = machine.project("slack", gitignore=(
        ".omp/RULES.md\n.omp/APPEND_SYSTEM.md\n*-map.html\n.scratch/\n.artifacts/\n"))
    machine.consumer("slack", path, [])

    result = machine.run(machine.write_registry(), "check", "--json")

    assert result.returncode == 1
    drift = json.loads(result.stdout)["consumers"][0]["drifts"][0]
    assert drift["kind"] == "gitignore"
    assert {".omp/plugins/", ".omp/mcp.json", ".gitmark/"} <= set(drift["ignores"]), \
        "доставленное и производное по-прежнему требуется закрывать"
    assert not {".omp/RULES.md", ".omp/APPEND_SYSTEM.md"} & set(drift["ignores"]), \
        "проектные sticky-файлы больше не требуются"


def test_wholesale_omp_covers_delivered_but_not_derived(machine: Machine) -> None:
    """Огульное `.omp/` закрывает доставленное; производное KB — отдельные строки."""
    path = machine.project("wholesale", gitignore=".omp/\n")
    machine.consumer("wholesale", path, [])

    result = machine.run(machine.write_registry(), "check", "--json")

    ignores = json.loads(result.stdout)["consumers"][0]["drifts"][0]["ignores"]
    assert ignores == [line for line in DOCUMENTED_IGNORES if not line.startswith(".omp/")]


def test_gitignore_anchored_and_slashless_forms_cover_the_policy(machine: Machine) -> None:
    """`/.gitmark/` и `.omp/plugins` без хвостового слэша — тот же запрет, что в каноне."""
    lines = ["/" + line if line == ".gitmark/" else
             line.rstrip("/") if line == ".omp/plugins/" else line
             for line in DOCUMENTED_IGNORES]
    path = machine.project("anchored", gitignore="\n".join(lines) + "\n")
    machine.consumer("anchored", path, [])

    result = machine.run(machine.write_registry(), "check")

    assert result.returncode == 0, result.stdout + result.stderr


def test_gitignore_with_wholesale_parent_and_own_subdirs(machine: Machine) -> None:
    """Живая раскладка потребителя: `.omp/*` закрывает всё под `.omp/`, а `!` — про своё.

    Проект версионирует собственные rules/skills/commands и снимает для них закрытие.
    Это решение о своём, а не дрейф: проверка смотрит на закрытие путём, иначе
    осознанная раскладка получает ложный дрейф за то, что держит своё в git.
    """
    path = machine.project("tracked", gitignore=OWN_SUBDIRS_IGNORES)
    machine.consumer("tracked", path, [])

    result = machine.run(machine.write_registry(), "check", "--json")

    ignores = json.loads(result.stdout)["consumers"][0]["drifts"][0]["ignores"]
    assert ignores == [".scratch/"], "закрытое родителем — не дрейф; незакрытое — дрейф"


def test_gitignore_glob_does_not_cross_segments(machine: Machine) -> None:
    """`*` в git не переходит через `/`: `.omp/*` закрывает сегмент, а не всё дерево."""
    path = machine.project("shallow", gitignore=".omp/*\n.artifacts/\n.gitmark/\n*-map.html\n")
    machine.consumer("shallow", path, [])

    result = machine.run(machine.write_registry(), "check", "--json")

    ignores = json.loads(result.stdout)["consumers"][0]["drifts"][0]["ignores"]
    assert ignores == [".scratch/"], "`.omp/*` накрывает `.omp/plugins/`, `.omp/mcp.json` и прочее"


# ------------------------------------------------------- материализация поставки


def test_broken_node_modules_symlink_is_materialization(machine: Machine) -> None:
    """Реестр установки говорит «плагин есть», а симлинк ведёт в пустоту.

    Живой случай 2026-09-17: `retail` стоял с `node_modules/unica → …/unica___unica___0.11.0`,
    и `check` показывал «чисто» — он читал реестр маркетплейса, а не материализацию.
    """
    path = machine.project("retail", [("unica@unica", "project", "0.12.3")])
    machine.consumer("retail", path, [("unica@unica", "project", "0.12.3")])
    link = machine.break_link("unica@unica", path)

    result = machine.run(machine.write_registry(), "check", "--json")

    assert result.returncode == 1
    drifts = json.loads(result.stdout)["consumers"][0]["drifts"]
    broken = [d for d in drifts if d["kind"] == "materialization" and "битый симлинк" in d["detail"]]
    assert len(broken) == 1, drifts
    assert str(link) in broken[0]["detail"] and "снесено-unica" in broken[0]["detail"], \
        "видно и запись, и её цель"
    assert "omp plugin upgrade <id>@<каталог> --scope=project" in broken[0]["detail"], \
        "цель ни на один наблюдаемый плагин не ведёт — названо лечение из runbook, без id"


def test_missing_node_modules_entry_is_materialization(machine: Machine) -> None:
    """Плагин зарегистрирован, а записи в `node_modules` нет — payload недостижим."""
    install = machine.root / "cache" / "ontoship@sot-omp-marketplace-0.4.0"
    path = machine.project("unlinked", [("ontoship@sot-omp-marketplace", "project", "0.4.0")])
    machine.consumer("unlinked", path, [("ontoship@sot-omp-marketplace", "project", "0.4.0")])
    machine.drop_link("ontoship@sot-omp-marketplace", path)

    result = machine.run(machine.write_registry(), "check", "--json")

    assert result.returncode == 1
    drift = json.loads(result.stdout)["consumers"][0]["drifts"][0]
    assert drift["kind"] == "materialization"
    assert "нет записи" in drift["detail"] and str(install) in drift["detail"]


def test_link_to_another_version_is_materialization(machine: Machine) -> None:
    """Линк живой, но ведёт на другое дерево: реестр установки и диск разошлись.

    Вариант того же инцидента: в реестре установки уже 0.12.3, а `node_modules`
    остался на живой 0.11.0 — payload есть, но не тот, о котором говорит omp.
    """
    old = machine.root / "cache" / "unica@unica-0.11.0"
    old.mkdir(parents=True)
    path = machine.project("retail", [("unica@unica", "project", "0.12.3")])
    machine.consumer("retail", path, [("unica@unica", "project", "0.12.3")])
    link = machine.link("unica@unica", "project", path)
    link.unlink()
    link.symlink_to(old)

    result = machine.run(machine.write_registry(), "check", "--json")

    assert result.returncode == 1
    drift = json.loads(result.stdout)["consumers"][0]["drifts"][0]
    assert drift["kind"] == "materialization"
    assert "нет записи" in drift["detail"]
    assert str(machine.root / "cache" / "unica@unica-0.12.3") in drift["detail"], \
        "назван путь, о котором говорит реестр установки"


def test_dead_install_path_is_materialization(machine: Machine) -> None:
    """Кэш снесён, линка нет: `installPath` из реестра установки не существует."""
    path = machine.project("wiped", [("ontoship@sot-omp-marketplace", "project", "0.4.0")])
    machine.consumer("wiped", path, [("ontoship@sot-omp-marketplace", "project", "0.4.0")])
    machine.kill_install("ontoship@sot-omp-marketplace", "0.4.0")
    machine.drop_link("ontoship@sot-omp-marketplace", path)

    result = machine.run(machine.write_registry(), "check", "--json")

    assert result.returncode == 1
    drift = json.loads(result.stdout)["consumers"][0]["drifts"][0]
    assert drift["kind"] == "materialization"
    assert "installPath не существует" in drift["detail"]


def test_one_breakage_is_reported_once(machine: Machine) -> None:
    """Мёртвый `installPath` и битый симлинк на него — одна поломка, а не две строки."""
    path = machine.project("wiped", [("ontoship@sot-omp-marketplace", "project", "0.4.0")])
    machine.consumer("wiped", path, [("ontoship@sot-omp-marketplace", "project", "0.4.0")])
    machine.kill_install("ontoship@sot-omp-marketplace", "0.4.0")

    result = machine.run(machine.write_registry(), "check", "--json")

    drifts = json.loads(result.stdout)["consumers"][0]["drifts"]
    assert [d["kind"] for d in drifts] == ["materialization"]
    assert "битый симлинк" in drifts[0]["detail"]
    assert "omp plugin upgrade ontoship@sot-omp-marketplace --scope=project" in drifts[0]["detail"], \
        "цель ведёт на installPath наблюдаемого плагина — лечение названо с id"


def test_materialization_reports_a_plugin_without_an_install_path(machine: Machine) -> None:
    """omp не назвал путь пакета — проверить поставку нечем, и молчать об этом нельзя."""
    path = machine.project("nameless", [("ontoship@sot-omp-marketplace", "project", "0.4.0")])
    machine.consumer("nameless", path, [("ontoship@sot-omp-marketplace", "project", "0.4.0")])
    machine.forget_install_path(path, "ontoship@sot-omp-marketplace")

    result = machine.run(machine.write_registry(), "check", "--json")

    assert result.returncode == 1
    drift = json.loads(result.stdout)["consumers"][0]["drifts"][0]
    assert drift["kind"] == "materialization"
    assert "не назвал installPath" in drift["detail"]


def test_materialization_matches_the_link_by_target_not_by_name(machine: Machine) -> None:
    """Пакет `1c-omp` ставит плагин `1c`: имя записи в `node_modules` не совпадает с id."""
    path = machine.project("one-c", [("1c@sot-omp-marketplace", "project", "0.1.2")])
    machine.consumer("one-c", path, [("1c@sot-omp-marketplace", "project", "0.1.2")])

    result = machine.run(machine.write_registry(), "check")

    assert result.returncode == 0, result.stdout + result.stderr
    assert (path / ".omp" / "plugins" / "node_modules" / "1c-omp").is_symlink()


def test_materialization_checks_the_user_scope_root(machine: Machine) -> None:
    """Машинная установка линкуется в `~`, а не в проект: проверяются оба корня."""
    path = machine.project("wide", [("ontoship@sot-omp-marketplace", "user", "0.4.0")])
    machine.consumer("wide", path, [("ontoship@sot-omp-marketplace", "user", "0.4.0")])
    link = machine.break_link("ontoship@sot-omp-marketplace", path, scope="user")

    result = machine.run(machine.write_registry(), "check", "--json")

    assert result.returncode == 1
    drifts = json.loads(result.stdout)["consumers"][0]["drifts"]
    broken = [d for d in drifts if d["kind"] == "materialization" and "битый симлинк" in d["detail"]]
    assert len(broken) == 1, drifts
    assert str(link) in broken[0]["detail"], "поломка названа в машинном корне"
    assert "--scope=user" in broken[0]["detail"], "лечение — в том корне, где поломка"


def test_restoring_the_link_clears_the_materialization_drift(machine: Machine) -> None:
    """Инцидент `retail` целиком: битая цель краснеет, возврат цели — снова зелёно."""
    path = machine.project("retail", [("unica@unica", "project", "0.12.3")])
    machine.consumer("retail", path, [("unica@unica", "project", "0.12.3")])
    registry = machine.write_registry()
    assert machine.run(registry, "check").returncode == 0, "до поломки чисто"

    link = machine.break_link("unica@unica", path)
    broken = machine.run(registry, "check")
    assert broken.returncode == 1 and "битый симлинк" in broken.stdout

    link.unlink()
    link.symlink_to(machine.root / "cache" / "unica@unica-0.12.3")
    assert machine.run(registry, "check").returncode == 0, "цель вернулась — дрейф ушёл"


# ------------------------------------------- непроверяемый плагин: unversioned


def test_unversioned_catalog_entry_is_soft_drift(machine: Machine) -> None:
    """Каталог плагин знает, а версии не объявил: обновлять нечего — гейт не красный.

    Живой случай: `redaktura-skills@redaktura-skills` — глобальный навык чужого
    каталога без объявленной версии; `unknown` говорил про него неправду.
    """
    path = machine.project("skills", [("skill-only@sot-omp-marketplace", "project", "0.4.0")])
    machine.consumer("skills", path, [("skill-only@sot-omp-marketplace", "project", "0.4.0")])

    result = machine.run(machine.write_registry(), "check")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "• skills" in result.stdout and "unversioned" in result.stdout, "мягкий вид — не крест"
    assert "не объявляет версию" in result.stdout
    assert "нет в каталоге" not in result.stdout, "текст `unknown` здесь был бы неправдой"


def test_upgrade_does_not_go_red_on_an_unversioned_plugin(machine: Machine) -> None:
    """Обновлять нечего — это не провал: мягкий пропуск виден, но гейт зелёный."""
    path = machine.project("skills", [("skill-only@sot-omp-marketplace", "project", "0.4.0")])
    machine.consumer("skills", path, [("skill-only@sot-omp-marketplace", "project", "0.4.0")])

    result = machine.run(machine.write_registry(), "upgrade", "--dry-run")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "• skills" in result.stdout and "не объявляет версию" in result.stdout
    assert machine.mutations() == [], "план ничего не выполняет"


def test_upgrade_stays_red_when_the_catalog_does_not_know_the_plugin(machine: Machine) -> None:
    """Незнакомый каталогу плагин — жёсткий пропуск: прогон красный, причина названа."""
    path = machine.project("typo", [("ontoship@unica", "project", "0.4.0")])
    machine.consumer("typo", path, [("ontoship@unica", "project", "0.4.0")])

    result = machine.run(machine.write_registry(), "upgrade", "--dry-run")

    assert result.returncode == 1
    assert "нет в каталоге unica" in result.stdout


def test_upgrade_apply_is_green_when_only_a_soft_skip_remains(machine: Machine) -> None:
    """Применение с мягким пропуском: действия выполнены, гейт зелёный."""
    path = machine.project("mixed", [("ontoship@sot-omp-marketplace", "project", "0.3.0"),
                                     ("skill-only@sot-omp-marketplace", "project", "0.4.0")])
    machine.consumer("mixed", path, [("ontoship@sot-omp-marketplace", "project", "0.3.0"),
                                     ("skill-only@sot-omp-marketplace", "project", "0.4.0")])

    result = machine.run(machine.write_registry(), "upgrade", "--yes")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "•" in result.stdout and "не объявляет версию" in result.stdout
    assert any("plugin upgrade ontoship@sot-omp-marketplace" in call for call in machine.mutations()), \
        "обновляемое обновлено, пропущено только непроверяемое"


def test_discover_apply_does_not_adopt_an_unversioned_plugin(machine: Machine) -> None:
    """Принятие не вносит в состав плагин без версии — иначе гейт сразу красный.

    Живой случай 2026-09-17: `discover --apply` для `project-bp` внёс
    `redaktura-skills@redaktura-skills`, и запись пришлось снимать руками.
    """
    machine.project("bp", [("ontoship@sot-omp-marketplace", "project", "0.4.0"),
                           ("skill-only@sot-omp-marketplace", "user", "0.4.0")])
    fresh = machine.root / "fresh.json"
    machine.run(fresh, "init", "--root", str(machine.root))

    result = machine.run(fresh, "discover", "--apply")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "не отслеживается: каталог не объявляет версию (skill-only@sot-omp-marketplace)" \
        in result.stdout
    consumer = json.loads(fresh.read_text(encoding="utf-8"))["consumers"][0]
    assert [p["id"] for p in consumer["plugins"]] == ["ontoship@sot-omp-marketplace"]
    check = machine.run(fresh, "check")
    assert check.returncode == 0, check.stdout + check.stderr


def test_discover_apply_keeps_a_plugin_the_catalog_does_not_know(machine: Machine) -> None:
    """Незнакомый каталогу плагин остаётся в составе: это сигнал (`unknown`), а не шум."""
    machine.project("typo", [("ontoship@unica", "project", "0.4.0")])
    fresh = machine.root / "fresh.json"
    machine.run(fresh, "init", "--root", str(machine.root))

    result = machine.run(fresh, "discover", "--apply")

    assert result.returncode == 0, result.stdout + result.stderr
    consumer = json.loads(fresh.read_text(encoding="utf-8"))["consumers"][0]
    assert [p["id"] for p in consumer["plugins"]] == ["ontoship@unica"]
    assert machine.run(fresh, "check").returncode == 1, "id или каталог надо чинить — гейт красный"

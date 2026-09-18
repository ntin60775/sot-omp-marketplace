#!/usr/bin/env python3
"""consumers.py — реестр потребителей каталога: заведение, обнаружение, дрейф, обновление, проверка.

Данные — `.consumers.json` в корне клона каталога (в .gitignore: в нём абсолютные
пути и состав конкретной машины), формат — `schemas/consumer-registry.schema.json`,
семантика и контракт — `docs/reference/consumer-registry.md`. Реестр машино-локален
и не переносится между машинами: на новой машине его заводит `init`, наполняет
наблюдением `discover --apply`.

Зависимостей нет: валидатор схемы встроенный (python-модуля `jsonschema` на машине
может не быть — проверено 2026-09-14).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = REPO_ROOT / ".consumers.json"
DEFAULT_SCHEMA = REPO_ROOT / "schemas" / "consumer-registry.schema.json"
DEFAULT_MARKETPLACES = Path.home() / ".omp" / "marketplaces.json"

FLAT_DIRS = (".omp/skills", ".omp/rules", ".omp/commands", ".omp/scripts", ".omp/extensions")
WORKTREE_HOOK = "tasks/init-worktree.sh"
INSTALL_STEP = re.compile(r"omp\s+plugin\s+(?:install|upgrade)")
SCRIPT_REF = re.compile(r"[\w][\w./-]*\.sh")
DISCOVER_MAX_DEPTH = 3
CONSUMER_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
REMOTE_RE = re.compile(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$")

# Доставленное и производное не версионируется — политика из
# docs/reference/consumer-repo-layout.md, блок «Канонический блок для .gitignore».
# Набор здесь, а не в документе, потому что проверяет его инструмент; тест сверяет
# эту константу с блоком документа, поэтому расхождение кода и политики — провал.
# Проектных `.omp/RULES.md` и `.omp/APPEND_SYSTEM.md` здесь нет намеренно: omp читает
# их из `<cwd>/.omp/` как файлы проекта, а машинный слой живёт в `~/.omp/agent/`.
REQUIRED_IGNORES = (
    ".omp/plugins/",
    ".omp/skills/",
    ".omp/commands/",
    ".omp/scripts/",
    ".omp/mcp.json",
    ".omp/.backup-*",
    ".gitmark/",
    "*-map.html",
    ".scratch/",
    ".artifacts/",
)

# Scope установки omp. Кэш пакетов у него один (`~/.omp/plugins/cache/plugins`),
# а `node_modules` свой у каждого корня: проектный плагин линкуется в проект,
# машинный — в `~`. Имена совпадают со значениями `--scope=` у omp.
PROJECT_SCOPE = "project"
USER_SCOPE = "user"

# Мягкие виды дрейфа не делают гейт красным: `pinned` — сознательный выбор проекта,
# `own-rules` — свои файлы под неплагинными именами, `unversioned` — каталог плагин
# знает, но версии не объявил: обновлять нечего, и это не поломка поставки.
SOFT_KINDS = ("pinned", "own-rules", "unversioned")

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_USAGE = 2


class UsageError(Exception):
    """Реестр не читается, нарушает схему или команда вызвана неправильно."""


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def invocation() -> str:
    """Как повторить запуск инструмента: путь, по возможности относительно cwd.

    Подсказка в ошибке должна быть копируемой: `python3 consumers.py` работает
    только из корня клона, а сообщение читают и из чужого каталога.
    """
    script = Path(__file__).resolve()
    try:
        return str(script.relative_to(Path.cwd()))
    except ValueError:
        return str(script)


def write_json(path: Path, doc: dict) -> None:
    """Атомарная запись: реестр машины не в git, усечённого файла быть не должно."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# --------------------------------------------------------------------------- схема


def _deref(schema: dict, root: dict) -> dict:
    while "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/"):
            raise UsageError(f"внешняя ссылка в схеме не поддерживается: {ref}")
        node = root
        for part in ref[2:].split("/"):
            node = node[part]
        schema = {**node, **{k: v for k, v in schema.items() if k != "$ref"}}
    return schema


def _same(value, expected) -> bool:
    """JSON-равенство: `true` не равно `1` (питоновское True == 1 здесь неверно)."""
    return type(value) is type(expected) and value == expected


def _validate(value, schema: dict, root: dict, path: str) -> list[str]:
    """Подмножество JSON Schema, которым описана схема реестра."""
    schema = _deref(schema, root)
    errors: list[str] = []

    expected = schema.get("type")
    if expected is not None:
        kinds = expected if isinstance(expected, list) else [expected]
        checks = {
            "object": lambda v: isinstance(v, dict),
            "array": lambda v: isinstance(v, list),
            "string": lambda v: isinstance(v, str),
            "boolean": lambda v: isinstance(v, bool),
            "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            "null": lambda v: v is None,
        }
        if not any(checks.get(k, lambda _: False)(value) for k in kinds):
            return [f"{path}: ожидался {expected}, получено {type(value).__name__}"]

    if "const" in schema and not _same(value, schema["const"]):
        errors.append(f"{path}: ожидалось {schema['const']!r}, получено {value!r}")
    if "enum" in schema and not any(_same(value, option) for option in schema["enum"]):
        errors.append(f"{path}: {value!r} не из {schema['enum']}")

    if isinstance(value, str):
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: {value!r} не соответствует {schema['pattern']}")
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: пустая строка")

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: отсутствует обязательное поле {key!r}")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{path}: лишнее поле {key!r}")
        for key, sub in properties.items():
            if key in value:
                errors += _validate(value[key], sub, root, f"{path}.{key}")

    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            errors += _validate(item, schema["items"], root, f"{path}[{index}]")

    return errors


def load_registry(path: Path, schema_path: Path) -> dict:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise UsageError(f"реестр не найден: {path}\n"
                         f"  завести реестр на этой машине: python3 {invocation()} "
                         f"init --root <каталог с проектами>") from None
    except json.JSONDecodeError as exc:
        raise UsageError(f"реестр не разбирается как JSON: {path}: {exc}") from None

    if schema_path.exists():
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        errors = _validate(doc, schema, schema, "$")
        if errors:
            raise UsageError("реестр не соответствует схеме:\n  " + "\n  ".join(errors))

    names = [c["name"] for c in doc["consumers"]]
    paths = [c["path"] for c in doc["consumers"]]
    duplicates = sorted({n for n in names if names.count(n) > 1} | {p for p in paths if paths.count(p) > 1})
    if duplicates:
        raise UsageError(f"дубликаты name/path в реестре: {duplicates}")
    return doc


def select(registry: dict, only: list[str] | None) -> list[dict]:
    consumers = registry["consumers"]
    if not only:
        return consumers
    known = {c["name"] for c in consumers}
    unknown = [name for name in only if name not in known]
    if unknown:
        raise UsageError(f"нет таких потребителей в реестре: {unknown} (есть: {sorted(known)})")
    return [c for c in consumers if c["name"] in only]


# --------------------------------------------------------------- наблюдение и каталог


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError:
        raise UsageError(f"не найден исполняемый файл: {cmd[0]}") from None


def package_paths(plugins: dict) -> set[str]:
    """Пути файлов поставленных пакетов (относительно корня пакета) — эталон перекрытия."""
    paths: set[str] = set()
    for plugin in plugins.values():
        root = plugin.get("installPath")
        if not root:
            continue
        for path in Path(root).rglob("*"):
            if path.is_file():
                paths.add(str(path.relative_to(root)))
    return paths


def _installs_plugins(text: str) -> bool:
    """Ставит ли скрипт плагины — по коду, а не по упоминанию.

    `echo 'Поставь плагин: omp plugin install …'` — напоминание, а не установка.
    Поэтому кавычки срезаются, а строки-комментарии пропускаются: ложное «ставит»
    опаснее ложного «не ставит» — оно прячет ворктри без плагинов.
    """
    for line in text.splitlines():
        code = line.strip()
        if code.startswith("#"):
            continue
        if INSTALL_STEP.search(re.sub(r"'[^']*'|\"[^\"]*\"", "", code)):
            return True
    return False


def _path_suffixes(candidate: str) -> list[str]:
    """Хвосты пути от длинного к короткому: `PKG/skills/x.sh` → он же, затем `skills/x.sh`.

    Обёртка называет канон через переменную (`"$PKG/skills/…/canon.sh"`), и регексп
    забирает имя переменной в путь — пакет-относительный путь оказывается одним из
    хвостов. Голое имя файла не пробуем: одноимённый чужой скрипт в пакете дал бы
    ложное «ставит плагины».
    """
    parts = candidate.split("/")
    if len(parts) == 1:
        return [candidate]
    return ["/".join(parts[start:]) for start in range(len(parts) - 1)]


def worktree_hook_state(project: Path, plugins: dict) -> dict:
    """Готовит ли проект ворктри и ставит ли он в них плагины.

    Хук бывает обёрткой над каноном из пакета (`exec bash .../init-worktree.sh`),
    и тогда установку делает канон — смотреть только на файл проекта недостаточно.
    """
    hook = project / WORKTREE_HOOK
    if not hook.is_file():
        return {"hook": None, "installsPlugins": False}

    text = hook.read_text(encoding="utf-8", errors="replace")
    installs = _installs_plugins(text)
    if not installs:
        roots = [p["installPath"] for p in plugins.values() if p.get("installPath")]
        for candidate in sorted(set(SCRIPT_REF.findall(text))):
            for suffix in _path_suffixes(candidate):
                script = next((Path(root) / suffix for root in roots
                               if (Path(root) / suffix).is_file()), None)
                if script and _installs_plugins(
                        script.read_text(encoding="utf-8", errors="replace")):
                    installs = True
                    break
            if installs:
                break
    return {"hook": WORKTREE_HOOK, "installsPlugins": installs}


def _gitignore_patterns(project: Path) -> list[str]:
    """Шаблоны `.gitignore` проекта без комментариев и отмен.

    Отмена (`!`) в проверке не участвует: она делает путь версионируемым, а это
    решение проекта о своём (свои rules/skills/commands живут в git и по политике
    им там и место). Судить о том, что проект держит у себя, инструмент не берётся —
    он проверяет, что политика вообще применена и пути закрыты.
    """
    path = project / ".gitignore"
    if not path.is_file():
        return []
    patterns = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        patterns.append(line)
    return patterns


def _glob_regex(pattern: str) -> str:
    """Шаблон `.gitignore` → регулярка по относительному пути.

    `*` и `?` не переходят через `/`, `**` переходит: так же, как их читает git.
    """
    out, index = [], 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if index + 1 < len(pattern) and pattern[index + 1] == "*":
                out.append(".*")
                index += 2
                continue
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(char))
        index += 1
    return "".join(out)


def _covers(pattern: str, required: str) -> bool:
    """Шаблон закрывает требуемый путь: сам путь или любой его каталог-предок.

    `.omp/*` закрывает `.omp/plugins/` (совпадение по сегменту), `.omp/` закрывает
    всё под `.omp/`, `*` закрывает всё. Ведущий `/` (привязка к корню) и хвостовой
    слэш на смысл не влияют — git читает `.omp/plugins`, `/.omp/plugins/` и
    `.omp/plugins/` одинаково.
    """
    pattern = pattern.lstrip("/").rstrip("/")
    if not pattern:
        return False
    regex = re.compile(_glob_regex(pattern) + r"(?:/.*)?")
    candidate = required.lstrip("/").rstrip("/")
    while True:
        if regex.fullmatch(candidate):
            return True
        if "/" not in candidate:
            return False
        candidate = candidate.rsplit("/", 1)[0]


def uncovered_ignores(project: Path) -> list[str]:
    """Требуемые строки `.gitignore`, которые проект не закрывает.

    Политика — «доставленное не версионируется»: файл, попавший в git, — вторая
    правда рядом с пакетом.
    """
    patterns = _gitignore_patterns(project)
    return [required for required in REQUIRED_IGNORES
            if not any(_covers(pattern, required) for pattern in patterns)]


def plugin_roots(project: Path) -> dict[str, Path]:
    """Корни `node_modules` по scope — где искать линки на поставленные пакеты."""
    return {PROJECT_SCOPE: project / ".omp" / "plugins" / "node_modules",
            USER_SCOPE: Path.home() / ".omp" / "plugins" / "node_modules"}


def _node_modules_state(root: Path) -> tuple[set[str], list[dict]]:
    """Записи `node_modules`: разрешённые цели и битые симлинки.

    Сопоставление идёт по **цели**, а не по имени: имени пакета в `omp plugin list
    --json` нет (поля только `id`, `scope`, `installPath`, `version`, …), и оно же
    не обязано совпадать с именем плагина (`1c` ставится пакетом `1c-omp`).

    Смотрим верхний уровень: пакеты маркетплейса omp линкует плоским именем
    (проверено на живой машине), а npm-пакеты идут в `omp plugin list --json`
    отдельным ключом и в наблюдение не входят — вместе с их скоупами `@scope/pkg`.
    """
    resolved: set[str] = set()
    broken: list[dict] = []
    if not root.is_dir():
        return resolved, broken
    for entry in root.iterdir():
        if entry.is_symlink():
            target = os.readlink(entry)
            if entry.exists():
                resolved.add(str(entry.resolve()))
            else:
                # `resolve()` нестрогий: у битого симлинка он даёт мёртвую цель,
                # по ней запись и сопоставляется с `installPath` наблюдаемого плагина.
                broken.append({"path": str(entry), "target": target,
                               "resolved": str(entry.resolve())})
            continue
        resolved.add(str(entry.resolve()))
    return resolved, broken


def _materialization(project: Path, plugins: dict) -> list[dict]:
    """Достижим ли payload у каждого наблюдаемого плагина — в обоих корнях установки.

    `omp plugin list --json` — реестр установки, а не поставка: плагин может быть
    зарегистрирован, а payload — недоступен. Видно это тремя состояниями: мёртвый
    `installPath` (кэш снесён), отсутствующая запись в `node_modules` (плагин
    зарегистрирован, а линка нет) и битый симлинк. 2026-09-17 `retail` стоял именно
    с битым симлинком `node_modules/unica`, а `check` показывал «чисто»: он читал
    реестр маркетплейса, а не материализацию.

    Одна поломка — одна строка: если `installPath` плагина и есть цель битого
    симлинка, называет её строка симлинка (в ней есть и запись, и цель).

    Запись, которая разрешается **не** в `installPath` (линк на другую версию или
    копия пакета вместо линка), — тоже находка: реестр установки и диск тогда
    говорят о разных деревьях, и перепривязывает их тот же `omp plugin upgrade`.
    """
    findings: list[dict] = []
    roots = plugin_roots(project)
    expected: dict[str, list[tuple[str, str | None]]] = {name: [] for name in roots}
    for plugin_id, installed in sorted(plugins.items()):
        scope = installed.get("scope") or PROJECT_SCOPE
        root_name = scope if scope in roots else PROJECT_SCOPE
        expected[root_name].append((plugin_id, installed.get("installPath")))

    for root_name, root in roots.items():
        resolved, broken = _node_modules_state(root)
        dead = {item["resolved"]: item for item in broken}
        by_install = {str(Path(path).resolve()): plugin_id
                      for plugin_id, path in expected[root_name] if path}
        for plugin_id, install in expected[root_name]:
            if not install:
                findings.append({"plugin": plugin_id, "path": None, "target": None,
                                 "scope": root_name, "why": "installPath не назван"})
                continue
            resolved_install = str(Path(install).resolve())
            if resolved_install in dead:
                continue  # называет строка битого симлинка ниже
            if not Path(install).exists():
                findings.append({"plugin": plugin_id, "path": install, "target": None,
                                 "scope": root_name, "why": "installPath не существует"})
                continue
            if resolved_install not in resolved:
                findings.append({"plugin": plugin_id, "path": install, "target": None,
                                 "scope": root_name, "why": "нет записи в node_modules"})
        for item in broken:
            findings.append({"plugin": by_install.get(item["resolved"]), "path": item["path"],
                             "target": item["target"], "scope": root_name, "why": "битый симлинк"})
    return findings


def observe(project: Path) -> dict:
    """Живое наблюдение проекта: плагины, их материализация, копии пакета, свои файлы, хук ворктри.

    Различаются два разных состояния под `.omp/<dir>`:
    - `shadowing` — файл, чей путь есть в поставленном пакете: он перекрывает плагинное
      правило (нативный провайдер, приоритет 100) и подлежит снятию;
    - `project_own` — файл, которого нет ни в одном пакете: это собственное знание
      проекта (ADR plugin-delivery: проектная конкретика живёт в проекте под именем,
      не совпадающим с плагинным) — снимать его нельзя.

    `materialization` — обратная сторона `plugins`: реестр установки говорит, что
    плагин есть, а диск может говорить другое (см. `_materialization`).
    """
    if not (project / ".omp").is_dir():
        raise UsageError(f"нет .omp/ — это не потребитель: {project}")

    result = _run(["omp", "plugin", "list", "--json"], cwd=project)
    if result.returncode != 0:
        raise UsageError(f"omp plugin list провалился в {project}: {result.stderr.strip()}")
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        # Предупреждение в stdout от новой версии omp не должно ронять весь отчёт трейсбеком.
        raise UsageError(f"omp plugin list вернул не-JSON в {project}: {exc}") from None

    plugins: dict[str, dict] = {}
    for entry in payload.get("marketplace", []):
        for installed in entry.get("entries", []):
            plugins[entry["id"]] = {
                "scope": installed.get("scope", entry.get("scope")),
                "version": installed.get("version"),
                "installPath": installed.get("installPath"),
            }

    packages = package_paths(plugins)
    flat, shadowing, project_own, unverifiable = [], [], [], []
    for directory in FLAT_DIRS:
        root = project / directory
        if not root.is_dir():
            continue
        files = [path for path in sorted(root.rglob("*")) if path.is_file()]
        if not files:
            continue  # пустой каталог ничего не перекрывает
        flat.append(directory)
        for path in files:
            relative = str(path.relative_to(project))
            inside = f"{Path(directory).name}/{path.relative_to(root)}"
            if not packages:
                # Пакетов нет — сравнивать не с чем: назвать файл «своим» значило бы
                # спрятать копию пакета (она станет видна после upgrade).
                unverifiable.append(relative)
            elif inside in packages:
                shadowing.append(relative)
            else:
                project_own.append(relative)

    return {
        "plugins": plugins,
        "materialization": _materialization(project, plugins),
        "flat": flat,
        "shadowing": shadowing,
        "project_own": project_own,
        "unverifiable": unverifiable,
        "worktree": worktree_hook_state(project, plugins),
        "gitignore": uncovered_ignores(project),
    }


def require_omp() -> None:
    """Без omp инструменту нечего делать: это отказ окружения, а не дрейф потребителя."""
    if shutil.which("omp") is None:
        raise UsageError("не найден исполняемый файл omp — инструмент работает только там, где установлен omp")


def load_marketplaces(path: Path) -> dict[str, str]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise UsageError(f"нет реестра маркетплейсов omp: {path}") from None
    out: dict[str, str] = {}
    for entry in doc.get("marketplaces", []):
        out[entry["name"]] = entry.get("catalogPath", "")
    return out


def catalog_versions(catalog_name: str, marketplaces: dict[str, str]) -> dict[str, str]:
    """Версии плагинов по кэшу каталога — из того же файла, что читает omp plugin upgrade.

    Незнакомый или недочитанный каталог даёт пустую карту, а не отказ: причину
    назовёт `catalog_reason`, а дрейф будет виден как `unknown`.
    """
    path = marketplaces.get(catalog_name)
    if not path:
        return {}
    try:
        catalog = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return {plugin["name"]: plugin.get("version") for plugin in catalog.get("plugins", [])}


def catalog_versions_for(ids: set[str], marketplaces: dict[str, str]) -> dict[str, dict]:
    """Что каталог знает о каждом id `<плагин>@<каталог>` (каталог может быть чужим).

    `known` — плагин в каталоге есть, `version` — объявленная им версия. Запись без
    версии — не «плагина нет»: это `unversioned`, и текст с лечением у него другой.
    """
    cache: dict[str, dict[str, str]] = {}
    out: dict[str, dict] = {}
    for plugin_id in ids:
        plugin, _, marketplace = plugin_id.partition("@")
        if marketplace not in cache:
            cache[marketplace] = catalog_versions(marketplace, marketplaces)
        known = plugin in cache[marketplace]
        out[plugin_id] = {"known": known,
                          "version": cache[marketplace].get(plugin) if known else None}
    return out


def catalog_reason(plugin_id: str, marketplaces: dict[str, str]) -> str:
    plugin, _, marketplace = plugin_id.partition("@")
    path = marketplaces.get(marketplace)
    if not path:
        return f"маркетплейс {marketplace} не зарегистрирован в omp"
    if not Path(path).exists():
        return f"кэш каталога {marketplace} отсутствует: {path}"
    return f"плагина {plugin} нет в каталоге {marketplace}"


# ------------------------------------------------------------------------ дрейф


def _catalog_gap_drift(plugin_id: str, target: dict | None, installed: str | None,
                       marketplaces: dict[str, str]) -> dict | None:
    """Запись каталога не даёт версии — и почему именно.

    `unknown` (жёсткий) — каталог плагина не знает: опечатка в id, незарегистрированный
    маркетплейс, пустой кэш. `unversioned` (мягкий) — каталог плагин знает, но версии
    не объявил: обновлять нечего, и это не поломка поставки. Один текст на оба случая
    («плагина нет в каталоге») врал бы в обоих направлениях.
    """
    if not target or not target["known"]:
        return {"kind": "unknown", "plugin": plugin_id, "installed": installed,
                "detail": catalog_reason(plugin_id, marketplaces)}
    if target["version"] is None:
        return {"kind": "unversioned", "plugin": plugin_id, "installed": installed,
                "detail": f"каталог {plugin_id.partition('@')[2]} не объявляет версию — "
                          f"обновлять нечего"}
    return None


def _materialization_detail(finding: dict) -> str:
    """Строка отчёта о поломке материализации: путь, цель симлинка и лечение.

    Лечение — то же, что в runbook: `omp plugin upgrade <id>@<каталог> --scope=…`
    в затронутом проекте; scope — корень, в котором поломка нашлась.
    """
    plugin, scope, why = finding["plugin"], finding["scope"], finding["why"]
    fix = (f" — omp plugin upgrade {plugin} --scope={scope}" if plugin
           else f" — перепривязать: omp plugin upgrade <id>@<каталог> --scope={scope}")
    if why == "installPath не назван":
        return f"omp не назвал installPath — проверить поставку нечем{fix}"
    if why == "installPath не существует":
        return f"installPath не существует: {finding['path']}{fix}"
    if why == "нет записи в node_modules":
        return f"в node_modules нет записи, ведущей на installPath: {finding['path']}{fix}"
    named = f" (плагин {plugin})" if plugin else ""
    return f"битый симлинк: {finding['path']} → {finding['target']}{named}{fix}"


def drift_for(consumer: dict, observed: dict, wanted: dict[str, dict],
              marketplaces: dict[str, str]) -> list[dict]:
    drifts: list[dict] = []
    for entry in consumer["plugins"]:
        plugin_id = entry["id"]
        installed = observed["plugins"].get(plugin_id)
        pin = entry.get("pin")
        target = wanted.get(plugin_id)

        if installed is None:
            if pin:
                # Закреплено X, а плагина нет вовсе — обещание реестра не выполнено.
                drifts.append({"kind": "stale", "plugin": plugin_id, "installed": None,
                               "detail": f"закреплён {pin}, а плагин не поставлен — пин нарушен"})
            else:
                drifts.append({"kind": "missing", "plugin": plugin_id, "installed": None,
                               "detail": f"не поставлен (нужен {(target or {}).get('version') or '?'})"})
            continue

        version = installed["version"]
        if pin and version != pin:
            drifts.append({"kind": "stale", "plugin": plugin_id, "installed": version,
                           "detail": f"закреплён {pin}, а стоит {version}"})
            continue

        gap = _catalog_gap_drift(plugin_id, target, version, marketplaces)
        if pin:
            if gap:
                drifts.append(gap)
            elif pin != target["version"]:
                drifts.append({"kind": "pinned", "plugin": plugin_id, "installed": version,
                               "detail": f"закреплён {pin}, в каталоге {target['version']} — "
                                         f"обновление пропускается"})
            continue

        if gap:
            drifts.append(gap)
            continue

        if installed["scope"] != entry["scope"]:
            drifts.append({"kind": "scope", "plugin": plugin_id, "installed": version,
                           "detail": f"стоит в {installed['scope']}-scope, ожидается {entry['scope']}"})

        if version != target["version"]:
            drifts.append({"kind": "stale", "plugin": plugin_id, "installed": version,
                           "detail": f"стоит {version}, в каталоге {target['version']}"})

    # Материализация — жёсткий вид и первая строка среди наблюдений: плагин,
    # зарегистрированный без достижимого payload, не работает, чем бы ни был доволен
    # реестр маркетплейса.
    for finding in observed["materialization"]:
        drifts.append({"kind": "materialization", "plugin": finding["plugin"], "installed": None,
                       "detail": _materialization_detail(finding)})

    if observed["shadowing"]:
        shown = ", ".join(observed["shadowing"][:3])
        more = f" и ещё {len(observed['shadowing']) - 3}" if len(observed["shadowing"]) > 3 else ""
        drifts.append({"kind": "legacy", "plugin": None, "installed": None,
                       "detail": f"перекрывают пакет: {len(observed['shadowing'])} файлов ({shown}{more})"})
    if observed["unverifiable"]:
        # Пакетов нет — файлы под .omp/<dir> могут быть и копией, и своим: молчать нельзя,
        # иначе копия пакета выглядела бы «своим файлом» и гейт остался бы зелёным.
        drifts.append({"kind": "legacy-unverified", "plugin": None, "installed": None,
                       "detail": f"сравнивать не с чем (пакеты не поставлены): "
                                 f"{len(observed['unverifiable'])} файлов под .omp/<dir> — сначала upgrade"})
    if observed["project_own"]:
        # Свои файлы проекта — не дрейф: под неплагинными именами им и положено жить здесь.
        # Но если ожидаемый пакет не поставлен, часть из них может быть его копией —
        # различить это можно только после upgrade, и молчать об этом нельзя.
        not_installed = [e["id"] for e in consumer["plugins"]
                         if observed["plugins"].get(e["id"]) is None]
        caveat = (f" — часть может быть копией непоставленного пакета "
                  f"({', '.join(not_installed)}): сначала upgrade" if not_installed else "")
        drifts.append({"kind": "own-rules", "plugin": None, "installed": None,
                       "detail": f"свои файлы проекта: {len(observed['project_own'])}{caveat}"})
    # Гэп только там, где проект ворктри готовит: скрипт есть, а плагинов в нём нет.
    # Отсутствие скрипта — вопрос раскладки проекта, а не дрейф потребителя.
    if observed["worktree"]["hook"] and not observed["worktree"]["installsPlugins"]:
        drifts.append({"kind": "worktree-gap", "plugin": None, "installed": None,
                       "detail": f"{observed['worktree']['hook']} ворктри готовит, а плагины в них не ставит"})
    if observed["gitignore"]:
        # Правится в проекте, а не инструментом, — как и гэп ворктри. Список строк
        # едет в отчёт целиком: по нему дописывают .gitignore, а тест сверяет его
        # с каноническим блоком документа.
        shown = ", ".join(observed["gitignore"][:4])
        more = f" и ещё {len(observed['gitignore']) - 4}" if len(observed["gitignore"]) > 4 else ""
        drifts.append({"kind": "gitignore", "plugin": None, "installed": None,
                       "ignores": list(observed["gitignore"]),
                       "detail": f"не игнорируется доставленное и производное: "
                                 f"{len(observed['gitignore'])} строк ({shown}{more})"})
    return drifts


def hard_drift(drifts: list[dict]) -> list[dict]:
    """Мягкие виды не делают гейт красным — их перечень один на весь инструмент."""
    return [d for d in drifts if d["kind"] not in SOFT_KINDS]


def safe_observe(project: Path) -> tuple[dict | None, str | None]:
    """Наблюдение одного потребителя не должно ронять отчёт по остальным:
    перемещённый или удалённый проект — строка отчёта, а не отказ инструмента."""
    try:
        return observe(project), None
    except UsageError as exc:
        return None, str(exc)


def _under(path: str, roots: set[str]) -> bool:
    return any(path == root or path.startswith(root + "/") for root in roots)


def unmanaged(registry: dict) -> list[str]:
    """Проекты с .omp/ на машине, которых нет ни в consumers, ни в exclude.

    Внутрь уже известных проектов не заглядываем: `.omp/.backup-*` — не потребитель,
    а остаток внутри потребителя.
    """
    skip = {str(Path(c["path"]).resolve()) for c in registry["consumers"]}
    skip |= {str(Path(e["path"]).resolve()) for e in registry.get("exclude", [])}
    found: list[str] = []
    for root in registry.get("discoverRoots", []):
        base = Path(root)
        if not base.is_dir():
            continue
        for depth in range(DISCOVER_MAX_DEPTH):
            pattern = "/".join(["*"] * (depth + 1))
            for candidate in sorted(base.glob(pattern)):
                if not candidate.is_dir() or candidate.name == ".omp":
                    continue
                path = str(candidate.resolve())
                if path in found or _under(path, skip):
                    continue
                if (candidate / ".omp").is_dir():
                    found.append(path)
    return found


# --------------------------------------------------------------------- команды


def _record(registry: dict, consumer: dict, observed: dict) -> None:
    """Записать наблюдаемое состояние потребителя в реестр."""
    for entry in consumer["plugins"]:
        installed = observed["plugins"].get(entry["id"])
        entry["installed"] = installed["version"] if installed else None
    consumer["legacy"] = {"flat": observed["shadowing"] + observed["unverifiable"]}
    consumer["worktreeInit"] = observed["worktree"]
    consumer["lastChecked"] = utcnow()


def catalog_identity() -> tuple[str, str | None]:
    """Имя каталога и `owner/repo` — якорь реестра, одинаковый на всех машинах.

    Имя берётся из каталога, а не из имени репозитория: `omp` адресует плагины
    селектором `<плагин>@<имя каталога>`, и схема фиксирует это имя константой.
    """
    path = REPO_ROOT / ".omp-plugin" / "marketplace.json"
    try:
        name = json.loads(path.read_text(encoding="utf-8"))["name"]
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        raise UsageError(f"каталог не читается: {path}: {exc}") from None
    try:
        result = subprocess.run(["git", "remote", "get-url", "origin"],
                                cwd=REPO_ROOT, capture_output=True, text=True)
    except FileNotFoundError:
        return name, None
    if result.returncode != 0:
        return name, None
    match = REMOTE_RE.search(result.stdout.strip())
    return name, (match.group(1) if match else None)


def cmd_init(args) -> int:
    """Завести реестр на этой машине: якорь каталога и корни поиска.

    Единственная команда, работающая без реестра. Потребителей здесь нет намеренно:
    список знает машина, а не память оператора, и наполняет его `discover --apply`
    из наблюдения. Пустой список — честная запись «ещё ничего не принято», а не
    заглушка: `check` сразу назовёт каждого настоящего потребителя кандидатом.
    """
    if args.registry.exists():
        raise UsageError(f"реестр уже есть: {args.registry} — правьте его напрямую "
                         f"или удалите, чтобы завести заново")
    if not args.registry.parent.is_dir():
        raise UsageError(f"каталога для реестра нет: {args.registry.parent}")
    if not args.root:
        raise UsageError("нужен хотя бы один --root: каталог, в котором искать проекты "
                         "с .omp/ (например: --root ~/dev)")
    roots = []
    for raw in args.root:
        root = Path(raw).expanduser()
        if not root.is_dir():
            raise UsageError(f"корень поиска не найден: {root}")
        roots.append(str(root.resolve()))

    name, remote = catalog_identity()
    catalog = {"name": name}
    if remote:
        catalog["remote"] = remote
    doc = {
        "$schema": os.path.relpath(args.schema, args.registry.parent),
        "schemaVersion": 1,
        "machine": socket.gethostname(),
        "updated": utcnow(),
        "catalog": catalog,
        "discoverRoots": roots,
        "exclude": [{"path": str(Path(raw).expanduser().resolve())} for raw in (args.exclude or [])],
        "consumers": [],
    }
    if args.schema.exists():
        schema = json.loads(args.schema.read_text(encoding="utf-8"))
        errors = _validate(doc, schema, schema, "$")
        if errors:
            raise UsageError("собранный реестр не соответствует схеме:\n  " + "\n  ".join(errors)
                             + "\n  имя каталога берётся из .omp-plugin/marketplace.json, "
                               "схема фиксирует его константой — правятся вместе")
    write_json(args.registry, doc)
    if args.json:
        print(json.dumps(doc, ensure_ascii=False, indent=2))
    else:
        print(f"✓ реестр заведён: {args.registry}")
        print(f"  машина: {doc['machine']} · каталог: {name} · корни поиска: {len(roots)}")
        print(f"  следующий шаг: python3 {invocation()} discover")
    return EXIT_OK


def _package_reason(path: Path) -> str | None:
    """Почему `.omp/` этого кандидата — не установка потребителя.

    `.omp/package.json` — признак пакета плагина (ADR plugin-delivery §5: omp-native
    репозиторий отдаёт сам `.omp/` как пакет), `.omp-plugin/marketplace.json` —
    признак каталога. Установка потребителя не несёт ни того, ни другого, поэтому
    молча принимать такие каталоги в `consumers` нельзя: источник — не потребитель.
    """
    if (path / ".omp" / "package.json").is_file():
        return "у .omp/ есть package.json — это пакет плагина, а не установка"
    if (path / ".omp-plugin" / "marketplace.json").is_file():
        return "есть .omp-plugin/marketplace.json — это каталог маркетплейса"
    return None


def _candidate_hint(path: str) -> str:
    """Пометка к кандидату в отчёте: почему его, скорее всего, место в exclude."""
    reason = _package_reason(Path(path))
    return f"  ({reason})" if reason else ""


def _record_exclusions(registry: dict, paths: list[str] | None) -> list[str]:
    """Дописать пути в `exclude`. Идемпотентно: повторный путь не дублируется."""
    added = []
    for raw in (paths or []):
        path = str(Path(raw).expanduser().resolve())
        if any(entry["path"] == path for entry in registry["exclude"]):
            continue
        registry["exclude"].append({"path": path})
        added.append(path)
    return added


def _trackable(observed: dict, marketplaces: dict[str, str]) -> tuple[list[str], list[dict]]:
    """Состав наблюдаемых плагинов, который реестр может отслеживать, и причина отказа.

    Отслеживать можно только то, о чём каталог объявил версию: иначе `check` сразу
    красный, а обновлять нечего. Так `project-bp` 2026-09-17 получил в состав
    `redaktura-skills@redaktura-skills` — глобальный навык из чужого каталога без
    объявленной версии, и запись пришлось снимать руками.

    Плагин, которого каталог **не знает**, наоборот, остаётся в составе: это
    `unknown` — настоящий дрейф (опечатка в id, незарегистрированный маркетплейс),
    и прятать его от гейта значило бы терять сигнал.
    """
    wanted = catalog_versions_for(set(observed["plugins"]), marketplaces)
    tracked, untracked = [], []
    for plugin_id in sorted(observed["plugins"]):
        target = wanted.get(plugin_id) or {"known": False, "version": None}
        if target["known"] and target["version"] is None:
            untracked.append({"id": plugin_id, "reason": "каталог не объявляет версию"})
            continue
        tracked.append(plugin_id)
    return tracked, untracked


def _adopt_candidates(registry: dict, args, found: list[str],
                      marketplaces: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """Принять кандидатов в реестр. Кандидат с именем не по схеме не принимается.

    Ожидаемый состав = наблюдаемый: «здесь стоит то, что стоит». Обратный выбор —
    записать пустой состав — оставил бы гейт зелёным при живом плагине, то есть
    спрятал бы ровно то, от чего реестр и заводится. Исключение — плагины, версии
    которых каталог не объявил (`_trackable`): их в составе нет, а причина печатается.
    """
    candidates = found
    if args.only:
        known = {Path(p).name for p in found}
        unknown = sorted(set(args.only) - known)
        if unknown:
            raise UsageError(f"нет таких кандидатов: {unknown} (есть: {sorted(known)})")
        candidates = [p for p in found if Path(p).name in set(args.only)]

    adopted, rejected = [], []
    for path in candidates:
        name = Path(path).name
        if not CONSUMER_NAME.match(name):
            rejected.append({"path": path, "reason": f"имя {name!r} не подходит под схему потребителя"})
            continue
        reason = _package_reason(Path(path))
        if reason and name not in set(args.only or []):
            rejected.append({"path": path,
                             "reason": f"{reason}; принять осознанно — --only {name}"})
            continue
        if any(c["name"] == name or c["path"] == path for c in registry["consumers"]):
            continue
        observed, error = safe_observe(Path(path))
        if error:
            rejected.append({"path": path, "reason": error})
            continue
        tracked, untracked = _trackable(observed, marketplaces)
        consumer = {
            "name": name,
            "path": path,
            "plugins": [{"id": plugin_id, "scope": PROJECT_SCOPE, "installed": None, "pin": None}
                        for plugin_id in tracked],
        }
        _record(registry, consumer, observed)
        registry["consumers"].append(consumer)
        adopted.append({"name": name, "path": path, "plugins": tracked, "untracked": untracked})
    return adopted, rejected


def cmd_discover(registry: dict, args) -> int:
    if (args.only or args.exclude) and not args.apply:
        raise UsageError("--only и --exclude — модификаторы записи: без --apply менять нечего")
    rows = []
    broken = 0
    for consumer in registry["consumers"]:
        observed, error = safe_observe(Path(consumer["path"]))
        if error:
            broken += 1
            rows.append({"name": consumer["name"], "path": consumer["path"], "error": error})
            continue
        rows.append({
            "name": consumer["name"],
            "path": consumer["path"],
            "plugins": {k: v["version"] for k, v in observed["plugins"].items()},
            "flat": observed["flat"],
            "shadowing": len(observed["shadowing"]),
            "own": len(observed["project_own"]),
        })
    found = unmanaged(registry)
    adopted, excluded, rejected = [], [], []
    if args.apply:
        # Исключения применяются до принятия: путь, названный не-потребителем, не
        # должен попасть в реестр ни потребителем, ни кандидатом.
        excluded = _record_exclusions(registry, args.exclude)
        adopted, rejected = _adopt_candidates(registry, args, unmanaged(registry),
                                             load_marketplaces(args.marketplaces))
        registry["updated"] = utcnow()
        write_json(args.registry, registry)
        # Гейт считает по состоянию после принятия: исключённые кандидаты в него
        # больше не входят, а непринятые — входят и делают прогон красным.
        remaining = unmanaged(registry)
    else:
        remaining = found

    if args.json:
        print(json.dumps({"consumers": rows, "unmanaged": remaining, "applied": bool(args.apply),
                          "adopted": adopted, "excluded": excluded, "rejected": rejected},
                         ensure_ascii=False, indent=2))
        return EXIT_DRIFT if (remaining or broken or rejected) else EXIT_OK

    for row in rows:
        if "error" in row:
            print(f"  ✗ {row['name']:<22} {row['error']}")
            continue
        plugins = ", ".join(f"{k}={v}" for k, v in row["plugins"].items()) or "плагинов нет"
        copies = f" · перекрывают пакет: {row['shadowing']} · свои: {row['own']}" if row["flat"] else ""
        print(f"  {row['name']:<22} {plugins}{copies}")
    if args.apply:
        for row in adopted:
            print(f"  + принят: {row['name']:<20} {', '.join(row['plugins']) or 'плагинов нет'}")
            for item in row["untracked"]:
                print(f"      · не отслеживается: {item['reason']} ({item['id']})")
        for path in excluded:
            print(f"  − исключён: {path}")
        for row in rejected:
            print(f"  ! не принят: {row['path']}: {row['reason']}")
        if adopted or excluded:
            print(f"✓ реестр обновлён: {args.registry}")
    if remaining:
        print("\nНе в реестре (кандидаты):")
        for path in remaining:
            print(f"  {path}{_candidate_hint(path)}")
    else:
        print("\nНеучтённых проектов с .omp/ нет.")
    return EXIT_DRIFT if (remaining or broken or rejected) else EXIT_OK


def cmd_scan(registry: dict, args) -> int:
    broken = 0
    for consumer in select(registry, args.only):
        observed, error = safe_observe(Path(consumer["path"]))
        if error:
            broken += 1
            print(f"  ✗ {consumer['name']:<22} {error}", file=sys.stderr)
            continue
        _record(registry, consumer, observed)
    registry["updated"] = utcnow()
    if args.json:
        print(json.dumps(registry, ensure_ascii=False, indent=2))
    else:
        write_json(args.registry, registry)
        print(f"✓ наблюдаемое состояние обновлено: {args.registry}")
    return EXIT_DRIFT if broken else EXIT_OK


def cmd_check(registry: dict, args) -> int:
    if args.refresh:
        for marketplace in sorted({p["id"].split("@")[1] for c in registry["consumers"] for p in c["plugins"]}):
            result = _run(["omp", "plugin", "marketplace", "update", marketplace], cwd=REPO_ROOT)
            if result.returncode != 0:
                print(f"! каталог {marketplace} не обновился: {result.stderr.strip()}", file=sys.stderr)

    marketplaces = load_marketplaces(args.marketplaces)
    consumers = select(registry, args.only)
    ids = {p["id"] for c in consumers for p in c["plugins"]}
    wanted = catalog_versions_for(ids, marketplaces)

    report = []
    for consumer in consumers:
        observed, error = safe_observe(Path(consumer["path"]))
        if error:
            report.append({"name": consumer["name"], "path": consumer["path"],
                           "error": error, "drifts": []})
            continue
        report.append({"name": consumer["name"], "path": consumer["path"],
                       "drifts": drift_for(consumer, observed, wanted, marketplaces)})

    found = unmanaged(registry)
    dirty = [row for row in report if row.get("error") or hard_drift(row["drifts"])]

    if args.json:
        print(json.dumps({"consumers": report, "unmanaged": found}, ensure_ascii=False, indent=2))
    else:
        for row in report:
            if row.get("error"):
                print(f"  ✗ {row['name']:<22} {'error':<13} {row['error']}")
                continue
            if not row["drifts"]:
                print(f"  ✓ {row['name']:<22} чисто")
                continue
            for drift in row["drifts"]:
                mark = "•" if drift["kind"] in SOFT_KINDS else "✗"
                target = f"{drift['plugin']}: " if drift["plugin"] else ""
                print(f"  {mark} {row['name']:<22} {drift['kind']:<13} {target}{drift['detail']}")
        if found:
            print("\nНе в реестре (кандидаты): " + ", ".join(found))
        print(f"\nдрейф: {len(dirty)} · чисто: {len(report) - len(dirty)} · неучтённых: {len(found)}")

    return EXIT_DRIFT if (dirty or found) else EXIT_OK


def _upgrade_plan(registry: dict, args) -> tuple[list[dict], list[dict]]:
    marketplaces = load_marketplaces(args.marketplaces)
    consumers = select(registry, args.only)
    ids = {p["id"] for c in consumers for p in c["plugins"]}
    wanted = catalog_versions_for(ids, marketplaces)

    actions: list[dict] = []
    skipped: list[dict] = []
    for consumer in consumers:
        project = Path(consumer["path"])
        observed, error = safe_observe(project)
        if error:
            skipped.append({"name": consumer["name"], "plugin": None, "reason": error})
            continue
        for entry in consumer["plugins"]:
            plugin_id = entry["id"]
            installed = observed["plugins"].get(plugin_id)
            if entry.get("pin"):
                continue
            gap = _catalog_gap_drift(plugin_id, wanted.get(plugin_id),
                                     installed["version"] if installed else None, marketplaces)
            if gap:
                # Ставить нечего: `unknown` — каталог плагина не знает (опечатка в id,
                # незарегистрированный маркетплейс), `unversioned` — знает, но версии
                # не объявил. Первый красит прогон, второй мягкий: обновлять нечего.
                skipped.append({"name": consumer["name"], "plugin": plugin_id,
                                "reason": gap["detail"], "soft": gap["kind"] == "unversioned"})
                continue
            target = wanted[plugin_id]["version"]
            # Плоские копии установке не мешают: копия перекрывает плагин (нативный
            # провайдер), поведение проекта не меняется, пока копии на месте. Зато
            # поставленный пакет даёт migrate эталон для классификации файлов.
            # Признак — именно перекрывающие копии: свои файлы проекта под неплагинными
            # именами ничего не перекрывают, и предупреждать о них нечего.
            over_copies = bool(observed["shadowing"])
            if installed is None:
                actions.append({"name": consumer["name"], "path": str(project), "plugin": plugin_id,
                                "action": "install", "from": None, "to": target,
                                "over_copies": over_copies})
                continue
            if installed["scope"] != entry["scope"] or installed["version"] != target:
                actions.append({"name": consumer["name"], "path": str(project), "plugin": plugin_id,
                                "action": "upgrade", "from": installed["version"], "to": target,
                                "over_copies": over_copies})
    return actions, skipped


def _print_skipped(skipped: list[dict]) -> None:
    for row in skipped:
        mark = "•" if row.get("soft") else "!"
        plugin = f"{row['plugin']}: " if row.get("plugin") else ""
        print(f"  {mark} {row['name']:<22} {plugin}{row['reason']}")


def _hard_skips(skipped: list[dict]) -> list[dict]:
    """Пропуски, из-за которых прогон красный: мягкие (нечего обновлять) — не повод."""
    return [row for row in skipped if not row.get("soft")]


def cmd_upgrade(registry: dict, args) -> int:
    actions, skipped = _upgrade_plan(registry, args)

    if not actions:
        if args.json:
            print(json.dumps({"dryRun": args.dry_run, "actions": [], "skipped": skipped},
                             ensure_ascii=False, indent=2))
        else:
            _print_skipped(skipped)
            print("Обновлять нечего.")
        return EXIT_DRIFT if _hard_skips(skipped) else EXIT_OK

    if args.dry_run:
        if args.json:
            print(json.dumps({"dryRun": True, "actions": actions, "skipped": skipped},
                             ensure_ascii=False, indent=2))
        else:
            for row in actions:
                target = f" → {row['to']}" if row["to"] else ""
                print(f"  {row['name']:<22} {row['plugin']:<32} {row['action']:<8} {row['from'] or '—'}{target}")
            _print_skipped(skipped)
            print(f"\n--dry-run: план из {len(actions)} действий, ничего не выполнено.")
        # План — тоже гейт: недоступный потребитель делает его красным, как и применение.
        return EXIT_DRIFT if _hard_skips(skipped) else EXIT_OK

    if not args.yes:
        print("Нужен --yes для применения (или --dry-run для плана).", file=sys.stderr)
        return EXIT_USAGE

    if not args.json:
        for row in actions:
            target = f" → {row['to']}" if row["to"] else ""
            print(f"  {row['name']:<22} {row['plugin']:<32} {row['action']:<8} {row['from'] or '—'}{target}")
        _print_skipped(skipped)
        over = sorted({row["name"] for row in actions if row["over_copies"]})
        if over:
            print(f"\n  ! плоские копии на месте у: {', '.join(over)} — они перекрывают плагин; "
                  f"следующий шаг: migrate (отчёт) → migrate --apply → verify")

    # Каталог обновляется один раз на маркетплейс: upgrade берёт версию оттуда.
    for marketplace in sorted({row["plugin"].split("@")[1] for row in actions}):
        result = _run(["omp", "plugin", "marketplace", "update", marketplace], cwd=REPO_ROOT)
        if result.returncode != 0:
            print(f"! каталог {marketplace} не обновился: {result.stderr.strip()}", file=sys.stderr)
            return EXIT_DRIFT

    results: list[dict] = []
    for row in actions:
        cmd = ["omp", "plugin", row["action"], row["plugin"], "--scope=project"]
        result = _run(cmd, cwd=Path(row["path"]))
        ok = result.returncode == 0
        results.append({"name": row["name"], "plugin": row["plugin"], "action": row["action"],
                        "from": row["from"], "to": row["to"], "ok": ok,
                        "error": None if ok else (result.stderr.strip() or result.stdout.strip())})
        if not args.json:
            if ok:
                print(f"  ✓ {row['name']:<22} {row['plugin']:<32} {row['from'] or '—'} → {row['to']}")
            else:
                print(f"  ✗ {row['name']:<22} {row['plugin']}: {results[-1]['error']}")

    failed_names = {row["name"] for row in results if not row["ok"]}
    touched = {row["name"] for row in actions}
    for consumer in select(registry, args.only):
        observed, error = safe_observe(Path(consumer["path"]))
        if error:
            continue
        _record(registry, consumer, observed)
        # «Обновлён» ставится только там, где обновление действительно прошло.
        if consumer["name"] in touched - failed_names:
            consumer["lastUpgraded"] = utcnow()
    registry["updated"] = utcnow()
    write_json(args.registry, registry)

    if args.json:
        print(json.dumps({"dryRun": False, "actions": actions, "results": results,
                          "skipped": skipped, "failed": sorted(failed_names)},
                         ensure_ascii=False, indent=2))
    else:
        failed_actions = sum(1 for row in results if not row["ok"])
        print(f"\nвыполнено: {len(results) - failed_actions} · провалов: {failed_actions}")
        if skipped:
            print(f"пропущено: {len(skipped)} (см. строки «!» и «•» выше)")
    # Недоступный потребитель — тот же дрейф, что и в check: гейт не должен быть зелёным.
    return EXIT_DRIFT if (failed_names or _hard_skips(skipped)) else EXIT_OK


def cmd_verify(registry: dict, args) -> int:
    consumers = select(registry, args.only)
    results = []
    failed = 0

    for consumer in consumers:
        project = Path(consumer["path"])
        observed, error = safe_observe(project)
        if error:
            failed += 1
            results.append({"name": consumer["name"], "error": error})
            continue
        ontoship = observed["plugins"].get("ontoship@sot-omp-marketplace")
        if not ontoship or not ontoship.get("installPath"):
            results.append({"name": consumer["name"], "skipped": "ontoship не установлен"})
            continue

        package = Path(ontoship["installPath"])
        engine = package / "skills" / "kb-search" / "gitmark.py"
        checks = []
        for label, cmd in (
            ("index", [sys.executable, str(engine), "index"]),
            ("deploy-check", ["bash", str(package / "scripts" / "deploy-check.sh")]),
            ("version", [sys.executable, str(engine), "version"]),
        ):
            if not Path(cmd[1]).exists():
                checks.append({"check": label, "ok": False, "warn": False, "out": "нет файла: " + cmd[1]})
                continue
            result = _run(cmd, cwd=project)
            output = (result.stdout or result.stderr).strip()
            lines = [line for line in output.splitlines() if line.strip()]
            # Причина важнее строки-итога («deploy-check: exit=N»), а провал важнее
            # предупреждений: иначе три [WARN] вытесняют единственный [FAIL].
            fails = [line for line in lines if line.startswith("[FAIL]")]
            warns = [line for line in lines if line.startswith("[WARN]")]
            chosen = fails[:2] + warns[:2]
            detail = " · ".join(chosen) if chosen else (lines[-1] if lines else "")
            # deploy-check: 0 — чисто, 1 — критика, 2 — предупреждения (пакет работает).
            if label == "deploy-check":
                ok, warn = result.returncode in (0, 2), result.returncode == 2
            else:
                ok, warn = result.returncode == 0, False
            checks.append({"check": label, "ok": ok, "warn": warn, "out": detail})
        ok = all(c["ok"] for c in checks)
        failed += 0 if ok else 1
        results.append({"name": consumer["name"], "checks": checks})

    if args.json:
        print(json.dumps({"consumers": results}, ensure_ascii=False, indent=2))
    else:
        for row in results:
            if "error" in row:
                print(f"  ✗ {row['name']:<22} {row['error']}")
                continue
            if "skipped" in row:
                print(f"  • {row['name']:<22} {row['skipped']}")
                continue
            marks = {"ok": "✓", "warn": "⚠", "fail": "✗"}
            summary = " ".join(
                f"{c['check']}:{marks['warn' if c.get('warn') else 'ok' if c['ok'] else 'fail']}"
                for c in row["checks"])
            worst = "✗" if not all(c["ok"] for c in row["checks"]) else ("⚠" if any(c.get("warn") for c in row["checks"]) else "✓")
            print(f"  {worst} {row['name']:<22} {summary}")
            for check in row["checks"]:
                if not check["ok"] or check.get("warn"):
                    print(f"      {check['check']}: {check['out']}")
    return EXIT_DRIFT if failed else EXIT_OK


def _package_files(observed: dict) -> dict[str, set[str]]:
    """Хэши файлов поставленных пакетов: путь от корня пакета → множество sha256.

    Множество, а не одно значение: два пакета могут нести один относительный путь,
    и тогда плоская копия совпадает с одним из них — это не расхождение.
    """
    index: dict[str, set[str]] = {}
    for plugin in observed["plugins"].values():
        root = plugin.get("installPath")
        if not root:
            continue
        for path in Path(root).rglob("*"):
            if path.is_file():
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                index.setdefault(str(path.relative_to(root)), set()).add(digest)
    return index


def _classify(project: Path, observed: dict) -> tuple[dict[str, list[dict]], bool]:
    """Классификация плоских копий против поставленных пакетов.

    Второе значение — есть ли эталон: без поставленных пакетов сравнивать не с чем,
    и файлы помечаются `unverifiable`, а не «расходящимися».
    """
    packages = _package_files(observed)
    report: dict[str, list[dict]] = {}
    for flat in observed["flat"]:
        # .omp/rules ↔ <корень пакета>/rules — раскладка плоской копии повторяет пакетную
        flat_name = Path(flat).name
        rows = []
        for path in sorted((project / flat).rglob("*")):
            if not path.is_file():
                continue
            relative = str(path.relative_to(project))
            inside = f"{flat_name}/{path.relative_to(project / flat)}"
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if not packages:
                kind = "unverifiable"
            elif digest in packages.get(inside, set()):
                kind = "identical"
            elif inside in packages:
                kind = "divergent"
            else:
                kind = "unique"
            rows.append({"path": relative, "kind": kind})
        report[flat] = rows
    return report, bool(packages)


def _normalize_keep(project: Path, keep: list[str] | None) -> set[str]:
    """--keep принимает и относительный путь, и абсолютный внутри проекта.

    Абсолютный путь другого потребителя молча отбрасывается: один и тот же ключ
    передаётся на весь список, и падать из-за чужого проекта незачем.
    """
    out: set[str] = set()
    for raw in keep or []:
        path = Path(raw)
        if path.is_absolute():
            try:
                path = path.relative_to(project)
            except ValueError:
                continue
        out.add(str(path).rstrip("/"))
    return out


def cmd_migrate(registry: dict, args) -> int:
    consumers = select(registry, args.only)
    plans = []
    errors: list[dict] = []
    refused = 0
    consumed_absolute: set[str] = set()
    # Снимаются только копии пакета: `identical` — по совпадению, `divergent` — по
    # явному решению оператора. `unique` — свои файлы проекта: по умолчанию остаются,
    # `--accept-unique` снимает и их. `unverifiable` не принимается никогда.
    accepted = {kind for kind, flag in (("divergent", args.accept_divergent),
                                        ("unique", args.accept_unique)) if flag}

    for consumer in consumers:
        project = Path(consumer["path"])
        keep = _normalize_keep(project, args.keep)
        for raw in args.keep or []:
            if Path(raw).is_absolute() and Path(raw).is_relative_to(project):
                consumed_absolute.add(str(Path(raw)))
        observed, error = safe_observe(project)
        if error:
            errors.append({"name": consumer["name"], "path": str(project), "error": error})
            print(f"  ✗ {consumer['name']:<22} {error}", file=sys.stderr)
            continue
        if not observed["flat"]:
            continue
        classification, reference = _classify(project, observed)
        blockers = [row["path"] for rows in classification.values() for row in rows
                    if row["kind"] in ("divergent", "unverifiable")
                    and row["kind"] not in accepted
                    and row["path"] not in keep]
        plans.append({"name": consumer["name"], "path": str(project), "flat": classification,
                      "blockers": blockers, "keep": sorted(keep), "reference": reference,
                      "accepted": sorted(accepted)})

    unknown_keep = [raw for raw in args.keep or []
                    if Path(raw).is_absolute() and str(Path(raw)) not in consumed_absolute]
    if unknown_keep:
        raise UsageError("--keep не относится ни к одному выбранному потребителю: "
                         + ", ".join(unknown_keep))

    if not args.apply:
        if args.json:
            print(json.dumps({"consumers": plans, "errors": errors, "applied": False},
                             ensure_ascii=False, indent=2))
            return EXIT_DRIFT if errors else EXIT_OK
        for plan in plans:
            print(f"  {plan['name']}")
            for flat, rows in plan["flat"].items():
                counts = {"identical": 0, "divergent": 0, "unique": 0, "unverifiable": 0}
                for row in rows:
                    counts[row["kind"]] += 1
                print(f"      {flat:<16} совпадает {counts['identical']} · "
                      f"расходится {counts['divergent']} · свои {counts['unique']}")
            if plan["accepted"]:
                kept = set(plan["keep"])
                taken = {"divergent": 0, "unique": 0}
                for row in plan["flat"].values():
                    for item in row:
                        if item["kind"] in plan["accepted"] and item["path"] not in kept:
                            taken[item["kind"]] += 1
                parts = [f"{kind} {count}" for kind, count in taken.items() if count]
                if parts:
                    print(f"      принято к снятию решением оператора: {', '.join(parts)}")
            if not plan["reference"]:
                print("      эталон недоступен: плагины не поставлены — сначала upgrade --yes")
                continue
            for row in plan["flat"].values():
                for item in row:
                    if item["kind"] == "divergent":
                        print(f"      расходится с пакетом: {item['path']}")
            own = [item["path"] for row in plan["flat"].values() for item in row
                   if item["kind"] == "unique" and "unique" not in set(plan["accepted"])]
            for path in own[:10]:
                print(f"      свои файлы проекта (остаются): {path}")
            if len(own) > 10:
                print(f"      … ещё {len(own) - 10} (полный список: migrate --json)")
        print("\nЭто отчёт. Применение — migrate --apply: снимает копии пакета, свои файлы проекта "
              "оставляет. Расходящиеся копии — по решению оператора (--accept-divergent), "
              "свои файлы — только если их надо снять тоже (--accept-unique); --keep сильнее обоих.")
        return EXIT_DRIFT if errors else EXIT_OK

    results = []
    for plan in plans:
        if plan["blockers"]:
            refused += 1
            blocked = [item for row in plan["flat"].values() for item in row
                       if item["path"] in set(plan["blockers"])]
            kinds = {item["kind"] for item in blocked}
            if kinds == {"unverifiable"}:
                reason = "эталон недоступен: плагины не поставлены — сначала upgrade --yes"
            else:
                counts = {"divergent": 0, "unverifiable": 0}
                for item in blocked:
                    counts[item["kind"]] += 1
                reason = (f"{len(blocked)} файлов требуют решения: "
                          f"расходится с пакетом {counts['divergent']}"
                          + (f" · эталон недоступен {counts['unverifiable']}" if counts["unverifiable"] else "")
                          + " (снять осознанно: --accept-divergent)")
            results.append({"name": plan["name"], "applied": False, "removed": 0, "reason": reason})
            if not args.json:
                print(f"  ✗ {plan['name']}: снятие отклонено — {reason}")
            continue
        project = Path(plan["path"])
        keep = set(plan["keep"])
        accepted = set(plan["accepted"])
        removed, own_kept = 0, 0
        for rows in plan["flat"].values():
            for row in rows:
                if row["path"] in keep:
                    continue
                if row["kind"] == "unique" and "unique" not in accepted:
                    own_kept += 1  # свои файлы проекта остаются: это не копия пакета
                    continue
                (project / row["path"]).unlink()
                removed += 1
        for flat in plan["flat"]:
            for directory in sorted((project / flat).rglob("*"), reverse=True):
                if directory.is_dir() and not any(directory.iterdir()):
                    directory.rmdir()
            if (project / flat).is_dir() and not any((project / flat).iterdir()):
                (project / flat).rmdir()
        results.append({"name": plan["name"], "applied": True, "removed": removed,
                        "own_kept": own_kept, "reason": None})
        if not args.json:
            tail = f" · свои файлы оставлены: {own_kept}" if own_kept else ""
            print(f"  ✓ {plan['name']:<22} снято файлов: {removed}{tail}")

    if args.json:
        print(json.dumps({"consumers": results, "errors": errors, "applied": True},
                         ensure_ascii=False, indent=2))
    else:
        print(f"\nснято потребителей: {len(results) - refused} · отклонено: {refused}")
    return EXIT_DRIFT if (refused or errors) else EXIT_OK


# ------------------------------------------------------------------------ CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="consumers.py",
        description="Реестр потребителей каталога: заведение, обнаружение, дрейф, обновление, проверка.",
    )
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY,
                        help="файл реестра (по умолчанию .consumers.json в корне клона каталога)")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA, help="схема реестра")
    parser.add_argument("--marketplaces", type=Path, default=DEFAULT_MARKETPLACES,
                        help="реестр маркетплейсов omp (источник версий каталога)")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="машинный вывод")

    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", parents=[common],
                          help="завести реестр на этой машине (единственная команда без реестра)")
    init.add_argument("--root", action="append",
                      help="каталог, в котором искать проекты с .omp/ (можно несколько)")
    init.add_argument("--exclude", action="append",
                      help="путь, который не потребитель (источник пакета, машинный слой)")

    discover = sub.add_parser("discover", parents=[common], help="что есть на машине; неучтённые потребители")
    discover.add_argument("--only", action="append", help="принять только этих кандидатов (имя каталога)")
    discover.add_argument("--apply", action="store_true",
                          help="принять кандидатов в реестр (по умолчанию — отчёт)")
    discover.add_argument("--exclude", action="append", help="дописать путь в exclude (только с --apply)")

    scan = sub.add_parser("scan", parents=[common], help="обновить наблюдаемое состояние в реестре")
    scan.add_argument("--only", action="append", help="только эти потребители (можно несколько)")

    check = sub.add_parser("check", parents=[common], help="дрейф: установленное против каталога")
    check.add_argument("--only", action="append")
    check.add_argument("--refresh", action="store_true", help="сначала обновить кэш каталогов")

    upgrade = sub.add_parser("upgrade", parents=[common], help="поставить/обновить плагины у потребителей")
    upgrade.add_argument("--only", action="append")
    upgrade.add_argument("--dry-run", action="store_true", help="только план, без вызовов omp")
    upgrade.add_argument("--yes", action="store_true", help="подтверждение применения")

    verify = sub.add_parser("verify", parents=[common], help="индекс, deploy-check и версия движка у потребителей")
    verify.add_argument("--only", action="append")

    migrate = sub.add_parser("migrate", parents=[common], help="снятие плоских копий пакета")
    migrate.add_argument("--only", action="append")
    migrate.add_argument("--apply", action="store_true", help="применить (по умолчанию — отчёт)")
    migrate.add_argument("--keep", action="append", help="путь, который остаётся в проекте")
    migrate.add_argument("--accept-divergent", action="store_true",
                         help="снять и файлы, отличающиеся от пакетных (осознанное решение оператора)")
    migrate.add_argument("--accept-unique", action="store_true",
                         help="снять и файлы, которых нет ни в одном пакете (осознанное решение оператора)")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        require_omp()
        # init заводит реестр, а не читает его: единственная команда до load_registry.
        if args.command == "init":
            return cmd_init(args)
        registry = load_registry(args.registry, args.schema)
        return {
            "discover": cmd_discover,
            "scan": cmd_scan,
            "check": cmd_check,
            "upgrade": cmd_upgrade,
            "verify": cmd_verify,
            "migrate": cmd_migrate,
        }[args.command](registry, args)
    except UsageError as exc:
        print(f"ошибка: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())

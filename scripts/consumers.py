#!/usr/bin/env python3
"""consumers.py — реестр потребителей каталога: обнаружение, дрейф, обновление, проверка.

Данные — `.consumers.json` в корне клона каталога (в .gitignore: в нём абсолютные
пути и состав конкретной машины), формат — `schemas/consumer-registry.schema.json`,
семантика и контракт — `docs/reference/consumer-registry.md`.

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
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = REPO_ROOT / ".consumers.json"
DEFAULT_SCHEMA = REPO_ROOT / "schemas" / "consumer-registry.schema.json"
DEFAULT_MARKETPLACES = Path.home() / ".omp" / "marketplaces.json"

FLAT_DIRS = (".omp/skills", ".omp/rules", ".omp/commands", ".omp/scripts")
WORKTREE_HOOK = "tasks/init-worktree.sh"
INSTALL_STEP = re.compile(r"omp\s+plugin\s+(?:install|upgrade)")
DISCOVER_MAX_DEPTH = 3

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_USAGE = 2


class UsageError(Exception):
    """Реестр не читается, нарушает схему или команда вызвана неправильно."""


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
        raise UsageError(f"реестр не найден: {path}") from None
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


def observe(project: Path) -> dict:
    """Живое наблюдение проекта: плагины, плоские копии, шаг инициализации ворктри."""
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

    hook = project / WORKTREE_HOOK
    installs = bool(hook.is_file() and INSTALL_STEP.search(hook.read_text(encoding="utf-8", errors="replace")))
    return {
        "plugins": plugins,
        "flat": [d for d in FLAT_DIRS if (project / d).is_dir()],
        "worktree": {"hook": WORKTREE_HOOK if hook.is_file() else None, "installsPlugins": installs},
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


def catalog_versions_for(ids: set[str], marketplaces: dict[str, str]) -> dict[str, str | None]:
    """Версия каталога для каждого id `<плагин>@<каталог>` (каталог может быть чужим)."""
    cache: dict[str, dict[str, str]] = {}
    out: dict[str, str | None] = {}
    for plugin_id in ids:
        plugin, _, marketplace = plugin_id.partition("@")
        if marketplace not in cache:
            cache[marketplace] = catalog_versions(marketplace, marketplaces)
        out[plugin_id] = cache[marketplace].get(plugin)
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


def drift_for(consumer: dict, observed: dict, wanted: dict[str, str | None],
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
                               "detail": f"не поставлен (нужен {target or '?'})"})
            continue

        version = installed["version"]
        if pin and version != pin:
            drifts.append({"kind": "stale", "plugin": plugin_id, "installed": version,
                           "detail": f"закреплён {pin}, а стоит {version}"})
            continue
        if pin:
            if target is None:
                drifts.append({"kind": "unknown", "plugin": plugin_id, "installed": version,
                               "detail": catalog_reason(plugin_id, marketplaces)})
            elif pin != target:
                drifts.append({"kind": "pinned", "plugin": plugin_id, "installed": version,
                               "detail": f"закреплён {pin}, в каталоге {target} — обновление пропускается"})
            continue

        if target is None:
            drifts.append({"kind": "unknown", "plugin": plugin_id, "installed": version,
                           "detail": catalog_reason(plugin_id, marketplaces)})
            continue

        if installed["scope"] != entry["scope"]:
            drifts.append({"kind": "scope", "plugin": plugin_id, "installed": version,
                           "detail": f"стоит в {installed['scope']}-scope, ожидается {entry['scope']}"})

        if version != target:
            drifts.append({"kind": "stale", "plugin": plugin_id, "installed": version,
                           "detail": f"стоит {version}, в каталоге {target}"})

    if observed["flat"]:
        drifts.append({"kind": "legacy", "plugin": None, "installed": None,
                       "detail": "плоские копии: " + ", ".join(observed["flat"])})
    # Гэп только там, где проект ворктри готовит: скрипт есть, а плагинов в нём нет.
    # Отсутствие скрипта — вопрос раскладки проекта, а не дрейф потребителя.
    if observed["worktree"]["hook"] and not observed["worktree"]["installsPlugins"]:
        drifts.append({"kind": "worktree-gap", "plugin": None, "installed": None,
                       "detail": f"{observed['worktree']['hook']} ворктри готовит, а плагины в них не ставит"})
    return drifts


def hard_drift(drifts: list[dict]) -> list[dict]:
    return [d for d in drifts if d["kind"] != "pinned"]


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
    consumer["legacy"] = {"flat": observed["flat"]}
    consumer["worktreeInit"] = observed["worktree"]
    consumer["lastChecked"] = utcnow()


def cmd_discover(registry: dict, args) -> int:
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
        })
    found = unmanaged(registry)
    if args.json:
        print(json.dumps({"consumers": rows, "unmanaged": found}, ensure_ascii=False, indent=2))
        return EXIT_DRIFT if (found or broken) else EXIT_OK

    for row in rows:
        if "error" in row:
            print(f"  ✗ {row['name']:<22} {row['error']}")
            continue
        plugins = ", ".join(f"{k}={v}" for k, v in row["plugins"].items()) or "плагинов нет"
        flat = f" · плоские копии: {', '.join(row['flat'])}" if row["flat"] else ""
        print(f"  {row['name']:<22} {plugins}{flat}")
    if found:
        print("\nНе в реестре (кандидаты):")
        for path in found:
            print(f"  {path}")
    else:
        print("\nНеучтённых проектов с .omp/ нет.")
    return EXIT_DRIFT if (found or broken) else EXIT_OK


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
                mark = "•" if drift["kind"] == "pinned" else "✗"
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
            if wanted.get(plugin_id) is None:
                # Ставить нечего: каталог не знает такого плагина (опечатка в id
                # или незарегистрированный маркетплейс) — это видно как `unknown` в check.
                skipped.append({"name": consumer["name"], "plugin": plugin_id,
                                "reason": catalog_reason(plugin_id, marketplaces)})
                continue
            # Плоские копии установке не мешают: копия перекрывает плагин (нативный
            # провайдер), поведение проекта не меняется, пока копии на месте. Зато
            # поставленный пакет даёт migrate эталон для классификации файлов.
            over_copies = bool(observed["flat"])
            if installed is None:
                actions.append({"name": consumer["name"], "path": str(project), "plugin": plugin_id,
                                "action": "install", "from": None, "to": wanted[plugin_id],
                                "over_copies": over_copies})
                continue
            if installed["scope"] != entry["scope"] or installed["version"] != wanted[plugin_id]:
                actions.append({"name": consumer["name"], "path": str(project), "plugin": plugin_id,
                                "action": "upgrade", "from": installed["version"], "to": wanted[plugin_id],
                                "over_copies": over_copies})
    return actions, skipped


def _print_skipped(skipped: list[dict]) -> None:
    for row in skipped:
        plugin = f"{row['plugin']}: " if row.get("plugin") else ""
        print(f"  ! {row['name']:<22} {plugin}{row['reason']}")


def cmd_upgrade(registry: dict, args) -> int:
    actions, skipped = _upgrade_plan(registry, args)

    if not actions:
        if args.json:
            print(json.dumps({"dryRun": args.dry_run, "actions": [], "skipped": skipped},
                             ensure_ascii=False, indent=2))
        else:
            _print_skipped(skipped)
            print("Обновлять нечего.")
        return EXIT_DRIFT if skipped else EXIT_OK

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
        return EXIT_DRIFT if skipped else EXIT_OK

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
            print(f"пропущено потребителей: {len(skipped)} (см. строки «!» выше)")
    # Недоступный потребитель — тот же дрейф, что и в check: гейт не должен быть зелёным.
    return EXIT_DRIFT if (failed_names or skipped) else EXIT_OK


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
                checks.append({"check": label, "ok": False, "out": "нет файла: " + cmd[1]})
                continue
            result = _run(cmd, cwd=project)
            output = (result.stdout or result.stderr).strip()
            checks.append({"check": label, "ok": result.returncode == 0,
                           "out": output.splitlines()[-1] if output else ""})
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
            summary = " ".join(f"{c['check']}:{'✓' if c['ok'] else '✗'}" for c in row["checks"])
            print(f"  {'✓' if all(c['ok'] for c in row['checks']) else '✗'} {row['name']:<22} {summary}")
            for check in row["checks"]:
                if not check["ok"]:
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
                    if row["kind"] in ("divergent", "unique", "unverifiable")
                    and row["path"] not in keep]
        plans.append({"name": consumer["name"], "path": str(project), "flat": classification,
                      "blockers": blockers, "keep": sorted(keep), "reference": reference})

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
                      f"расходится {counts['divergent']} · нет в пакетах {counts['unique']}")
            if not plan["reference"]:
                print("      эталон недоступен: плагины не поставлены — сначала upgrade --yes")
                continue
            for row in plan["flat"].values():
                for item in row:
                    if item["kind"] == "divergent":
                        print(f"      расходится с пакетом: {item['path']}")
            pending = [item["path"] for row in plan["flat"].values() for item in row
                       if item["kind"] == "unique" and item["path"] not in set(plan["keep"])]
            for path in pending[:10]:
                print(f"      нет в пакетах: {path}")
            if len(pending) > 10:
                print(f"      … ещё {len(pending) - 10} (полный список: migrate --json)")
        print("\nЭто отчёт. Применение — migrate --apply (файлы, требующие решения, блокируют его; "
              "сохранить их можно через --keep).")
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
                counts = {"divergent": 0, "unique": 0, "unverifiable": 0}
                for item in blocked:
                    counts[item["kind"]] += 1
                reason = (f"{len(blocked)} файлов требуют решения: "
                          f"расходится с пакетом {counts['divergent']} · нет в пакетах {counts['unique']}")
            results.append({"name": plan["name"], "applied": False, "removed": 0, "reason": reason})
            if not args.json:
                print(f"  ✗ {plan['name']}: снятие отклонено — {reason}")
            continue
        project = Path(plan["path"])
        keep = set(plan["keep"])
        removed = 0
        for rows in plan["flat"].values():
            for row in rows:
                if row["path"] in keep:
                    continue
                (project / row["path"]).unlink()
                removed += 1
        for flat in plan["flat"]:
            for directory in sorted((project / flat).rglob("*"), reverse=True):
                if directory.is_dir() and not any(directory.iterdir()):
                    directory.rmdir()
            if (project / flat).is_dir() and not any((project / flat).iterdir()):
                (project / flat).rmdir()
        results.append({"name": plan["name"], "applied": True, "removed": removed, "reason": None})
        if not args.json:
            print(f"  ✓ {plan['name']:<22} снято файлов: {removed}")

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
        description="Реестр потребителей каталога: обнаружение, дрейф, обновление, проверка.",
    )
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY,
                        help="файл реестра (по умолчанию .consumers.json в корне клона каталога)")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA, help="схема реестра")
    parser.add_argument("--marketplaces", type=Path, default=DEFAULT_MARKETPLACES,
                        help="реестр маркетплейсов omp (источник версий каталога)")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="машинный вывод")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("discover", parents=[common], help="что есть на машине; неучтённые потребители")

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

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        registry = load_registry(args.registry, args.schema)
        require_omp()
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

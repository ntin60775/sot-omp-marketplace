#!/usr/bin/env bash
# Проверка развёртывания пакета OntoShip в текущем проекте.
#   exit 0 — пакет на месте и работает;
#   exit 1 — критические проблемы (фикс обязателен);
#   exit 2 — предупреждения (работает, но есть недочёты).
set -uo pipefail
root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"; cd "$root"
rc=0

# 1. Ключевые файлы пакета
for p in AGENTS.md .omp/skills/kb-search/gitmark.py .omp/commands/kb.md \
         .omp/commands/onto-doc.md .omp/rules/kb-first.md; do
  [[ -e "$p" ]] || { echo "[FAIL] отсутствует: $p"; rc=1; }
done

# 2. SQLite: FTS5 обязателен, trigram опционален (деградация заявлена в доках)
check_sqlite() {
  python3 - <<'PY'
import sqlite3, sys
c = sqlite3.connect(':memory:')
try:
    c.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
except sqlite3.OperationalError as e:
    print(f"[FAIL] SQLite без FTS5: {e}"); sys.exit(1)
print("FTS5 OK")
try:
    c.execute("CREATE VIRTUAL TABLE t2 USING fts5(x, tokenize='trigram')")
    print("trigram OK")
except sqlite3.OperationalError:
    print("[WARN] trigram-токенайзер недоступен (опционально, нужен SQLite >= 3.34)")
PY
}
out="$(check_sqlite)" || rc=1
echo "$out"
grep -q '^\[WARN\] trigram' <<<"$out" && { echo "[WARN] fuzzy/substring-поиск будет ограничен"; rc=$((rc==0?2:rc)); }

# 3. Индекс и смоук-поиск (AGENTS.md гарантированно содержит "OntoShip")
python3 .omp/skills/kb-search/gitmark.py index || { echo "[FAIL] gitmark index"; rc=1; }
hits="$(python3 .omp/skills/kb-search/gitmark.py search "OntoShip" -k 1 2>&1)" || rc=1
[[ -n "$hits" ]] || { echo "[FAIL] поиск вернул пусто — индекс сломан"; rc=1; }

# 4. Бутстрап KB и gitignore
[[ -d docs ]] || { echo "[WARN] docs/ отсутствует — KB не забутстраплена (запусти /onto-doc)"; rc=$((rc==0?2:rc)); }
grep -q '^\.gitmark/' .gitignore 2>/dev/null || { echo "[WARN] .gitmark/ нет в .gitignore"; rc=$((rc==0?2:rc)); }

echo "deploy-check: exit=$rc"
exit "$rc"

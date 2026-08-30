#!/usr/bin/env bash
# Dogfood-синхронизация: plugins/ontoship/{skills,commands,rules,scripts} -> корневой .omp/.
# Один источник истины — дерево плагина; корневая .omp/ нужна, чтобы этот репо
# сам работал по своим правилам (kb-first, dev-flow).
#   ./scripts/sync-package.sh          — собрать копию
#   ./scripts/sync-package.sh --check  — доложить о дрейфе (exit 1)
set -euo pipefail
cd "$(dirname "$0")/.."
src=plugins/ontoship
dst=.omp
if [[ "${1:-}" == "--check" ]]; then
  ok=1
  for d in skills commands rules scripts; do
    diff -r --exclude=__pycache__ "$src/$d" "$dst/$d" >/dev/null || { echo "ДРЕЙФ: $d"; ok=0; }
  done
  [[ $ok == 1 ]] && { echo "sync: OK"; exit 0; }
  echo "sync: запусти ./scripts/sync-package.sh"; exit 1
fi
for d in skills commands rules scripts; do
  rm -rf "$dst/$d"; cp -r "$src/$d" "$dst/$d"
done
find "$dst" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
echo "sync: $src -> $dst выполнено"

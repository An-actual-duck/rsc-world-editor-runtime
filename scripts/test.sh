#!/usr/bin/env bash
set -euo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT_DIR="${ROOT_DIR:-$SCRIPT_ROOT}"

case "${1:-}" in
	--group)
		[[ $# -eq 2 && "$2" == presentation ]] || { printf 'Use --group presentation or --full.\n' >&2; exit 2; }
		cd "$ROOT_DIR"
		python3 tests/myworld/test-opengl-window-viewport-extraction.py
		python3 tests/myworld/test-widescreen-world-input-viewport.py
		python3 tests/myworld/test-legacy-software-scaling-settings.py
		;;
	--help|-h)
		printf 'UI iteration: ./scripts/test.sh --group presentation\nFull gate: ./scripts/test.sh --full\nPresentation checks are headless; actual visual/input acceptance is separate.\n'
		;;
	--full|"")
		[[ $# -le 1 ]] || { printf 'Unexpected full-gate arguments.\n' >&2; exit 2; }
		"$ROOT_DIR/tests/myworld/test-all.sh"
		;;
	*) printf 'Unknown test selection; use --group presentation or --full.\n' >&2; exit 2 ;;
esac

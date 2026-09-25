#!/bin/sh
# Security check before push / PR (#291). Skills call this one command.
#
#   scripts/security/check.sh                      # staged changes (default)
#   scripts/security/check.sh --range main..HEAD   # a range of commits
#   scripts/security/check.sh --no-checklist       # skip the list for reviewers
#
# Fails (exit 1) when the git hooks are not enabled, gitleaks is missing, or
# gitleaks finds a secret. Then prints what a reviewer (or LLM) must still look
# at by eye: the list in docs/security/review-checklist.md (its only source).
set -u

usage() { sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; }

root=$(git rev-parse --show-toplevel) || exit 2
mode=staged
range=
checklist=1
while [ $# -gt 0 ]; do
  case "$1" in
    --staged) mode=staged ;;
    --range) mode=range; range=${2:-}; shift ;;
    --no-checklist) checklist=0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "check.sh: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
if [ "$mode" = range ] && [ -z "$range" ]; then
  echo "check.sh: --range needs a revision range, e.g. main..HEAD" >&2
  exit 2
fi

fail=0

hooks=$(git -C "$root" config core.hooksPath || true)
if [ "$hooks" = ".githooks" ] || [ "$hooks" = "$root/.githooks" ]; then
  echo "OK  git hooks are enabled (core.hooksPath=$hooks)"
else
  echo "NG  git hooks are not enabled (core.hooksPath=${hooks:-unset})."
  echo "    Run: scripts/setup/install_hooks.sh"
  fail=1
fi

if ! command -v gitleaks >/dev/null 2>&1; then
  echo "NG  gitleaks is not installed."
  echo "    Install: brew install gitleaks (other OS: https://github.com/gitleaks/gitleaks#installing)"
  fail=1
else
  if [ "$mode" = staged ]; then
    what="staged changes"
    set -- git --pre-commit --staged
  else
    what="commits $range"
    set -- git "--log-opts=$range"
  fi
  if gitleaks "$@" --config "$root/.gitleaks.toml" --gitleaks-ignore-path "$root/.gitleaksignore" \
      --redact --no-banner "$root"; then
    echo "OK  gitleaks found no secrets in $what"
  else
    echo "NG  gitleaks found secrets in $what (see above). Remove them; if a key was ever pushed, revoke it."
    fail=1
  fi
fi

if [ "$checklist" = 1 ]; then
  echo
  echo "Also check by eye (docs/security/review-checklist.md):"
  awk '/^## LLM が見る項目$/ {on=1; next} on && /^#/ {exit} on && /^- / {print}' \
    "$root/docs/security/review-checklist.md"
fi

exit "$fail"

#!/usr/bin/env bash
#
# Create (or update) the two GitHub rulesets that enforce feature branch -> dev
# -> main, talking to the REST API directly so nothing here needs the `gh` CLI.
#
#   main   PR only, N approvals, CI green, no force-push, no delete.
#          Repo admins bypass -- which is what lets a solo owner merge dev into
#          main at all, since GitHub won't let you approve your own PR.
#   dev    PR + CI for everyone else; repo admins may push straight to it.
#
# Usage:
#   DRY_RUN=1 ./scripts/protect_branches.sh              # print the payloads, send nothing
#   GITHUB_TOKEN=github_pat_... ./scripts/protect_branches.sh
#   APPROVALS=0 GITHUB_TOKEN=... ./scripts/protect_branches.sh    # no reviewer available yet
#
# The token needs "Administration: read and write" on this repo (fine-grained),
# or the classic `repo` scope.
set -euo pipefail

APPROVALS="${APPROVALS:-1}"
DRY_RUN="${DRY_RUN:-}"
TOKEN="${GITHUB_TOKEN:-${GH_TOKEN:-}}"

command -v python3 >/dev/null || { echo "python3 is required (JSON handling)." >&2; exit 1; }

# owner/repo out of the origin URL, https or ssh.
remote=$(git remote get-url origin)
slug=$(printf '%s' "$remote" \
    | sed -E 's#^git@github\.com:#https://github.com/#; s#^https://github\.com/##; s#\.git$##')
case "$slug" in
    */*) ;;
    *) echo "Could not read owner/repo from origin: $remote" >&2; exit 1 ;;
esac
api="https://api.github.com/repos/${slug}/rulesets"

# One payload per branch, built by python so the quoting stays honest.
#
# The contexts must match the `name:` of each job in .github/workflows/ci.yml.
# Rename a job there without renaming it here and the required check simply
# never arrives -- the PR sits "Expected" forever.
#
# actor_id 5 is the built-in Admin repository role. To let a specific
# collaborator bypass too, give them the Maintain role under
# Settings -> Collaborators and add {"actor_id": 4, ...} to bypass_actors.
payload() {  # $1 = branch, $2 = strict-up-to-date ("true"/"false")
    BRANCH="$1" STRICT="$2" APPROVALS="$APPROVALS" python3 - <<'PY'
import json, os

print(json.dumps({
    "name": f"flow: {os.environ['BRANCH']}",
    "target": "branch",
    "enforcement": "active",
    "conditions": {"ref_name": {"include": [f"refs/heads/{os.environ['BRANCH']}"], "exclude": []}},
    "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}],
    "rules": [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {"type": "pull_request", "parameters": {
            "required_approving_review_count": int(os.environ["APPROVALS"]),
            "dismiss_stale_reviews_on_push": True,
            "require_code_owner_review": False,
            "require_last_push_approval": False,
            "required_review_thread_resolution": False,
            "allowed_merge_methods": ["merge", "squash", "rebase"],
        }},
        {"type": "required_status_checks", "parameters": {
            "strict_required_status_checks_policy": os.environ["STRICT"] == "true",
            "do_not_enforce_on_create": False,
            "required_status_checks": [
                {"context": c} for c in (
                    "branch flow",
                    "lint + typecheck",
                    "pytest (py3.12)",
                    "pytest (py3.14)",
                )
            ],
        }},
    ],
}, indent=2))
PY
}

upsert() {  # $1 = branch, $2 = payload
    local id
    id=$(curl -fsS -H "Authorization: Bearer ${TOKEN}" \
            -H "Accept: application/vnd.github+json" "$api" \
        | BRANCH="$1" python3 -c '
import json, os, sys
want = f"flow: {os.environ[\"BRANCH\"]}"
print(next((str(r["id"]) for r in json.load(sys.stdin) if r["name"] == want), ""))')

    if [ -n "$id" ]; then
        printf 'updating "flow: %s" (ruleset %s) ... ' "$1" "$id"
        curl -fsS -X PUT "${api}/${id}" -o /dev/null -w 'HTTP %{http_code}\n' \
            -H "Authorization: Bearer ${TOKEN}" -H "Accept: application/vnd.github+json" -d "$2"
    else
        printf 'creating "flow: %s" ... ' "$1"
        curl -fsS -X POST "$api" -o /dev/null -w 'HTTP %{http_code}\n' \
            -H "Authorization: Bearer ${TOKEN}" -H "Accept: application/vnd.github+json" -d "$2"
    fi
}

main_payload=$(payload main true)
dev_payload=$(payload dev false)

if [ -n "$DRY_RUN" ]; then
    echo "# POST ${api}"
    echo "$main_payload"
    echo "$dev_payload"
    exit 0
fi

[ -n "$TOKEN" ] || { echo "Set GITHUB_TOKEN (or GH_TOKEN) to a PAT with Administration: write." >&2; exit 1; }

upsert main "$main_payload"
upsert dev "$dev_payload"

cat <<'DONE'

Done -- review them at Settings -> Rules -> Rulesets.

A 403 mentioning an upgrade means rulesets aren't available for private repos
on this account's plan. The pre-commit hook and the branch-flow CI job still
do their jobs; what you lose is the server-side "you cannot push here" half.
DONE

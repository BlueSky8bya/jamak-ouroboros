# doc-drift-check.ps1
# PostToolUse(Bash) hook: if CURRENT_STATE.md is 3+ code-commits behind HEAD,
# inject a reminder so the agent updates CURRENT_STATE.md + CHANGELOG_AGENT.md
# before finishing. Non-blocking (just adds context). Silent otherwise.
$ErrorActionPreference = 'SilentlyContinue'
$root = Split-Path -Parent $PSScriptRoot
$last = (git -C $root log -1 --format=%H -- docs/agent/CURRENT_STATE.md 2>$null)
if (-not $last) { exit 0 }
$pending = @(git -C $root log --oneline "$last..HEAD" -- src/ 2>$null | Where-Object { $_ })
if ($pending.Count -lt 3) { exit 0 }
$list = ($pending -join "`n")
$ctx = "[doc-drift] docs/agent/CURRENT_STATE.md is $($pending.Count) code-commit(s) behind HEAD. Before finishing, update docs/agent/CURRENT_STATE.md + docs/agent/CHANGELOG_AGENT.md to cover these src/ commits:`n$list"
@{ hookSpecificOutput = @{ hookEventName = 'PostToolUse'; additionalContext = $ctx } } | ConvertTo-Json -Compress -Depth 6
exit 0

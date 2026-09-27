# Release Engineer Skill

## Purpose

Analyze a software repository for production release readiness.

## Workflow

1. Understand the repository.
2. Inspect project structure.
3. Identify testing, security, API, deployment and documentation requirements.
4. Delegate independent analysis to specialized subagents.
5. Use MCP tools for deterministic checks.
6. Collect and normalize findings.
7. Classify findings by severity.
8. Generate a release-readiness assessment.
9. Present release blockers to the user.
10. Ask for approval before risky modifications.
11. Apply safe fixes.
12. Re-run affected checks.
13. Verify all fixes.
14. Generate the final release package.

## Rules

- Never claim verification without executing checks.
- Never expose real credentials.
- Never make destructive changes without approval.
- Prefer minimal changes.
- Preserve the existing architecture.
- Clearly distinguish blockers from warnings.
- Report failures honestly.

## Release Status

90-100:
READY

75-89:
READY WITH WARNINGS

50-74:
NOT READY

0-49:
BLOCKED
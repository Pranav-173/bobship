# BobShip - Project Context

## Project

BobShip is an AI-powered release engineering workflow built around IBM Bob.

The primary goal is to demonstrate IBM Bob as a core component of the product.

Bob is responsible for:
- Release workflow orchestration
- Specialized subagent coordination
- Reasoning over repository findings
- Safe code modifications
- Verification
- Release report generation

## Architecture

Bob IDE
    ↓
Release Engineer Skill
    ↓
Specialized Subagents + MCP Tools
    ↓
Release Analysis
    ↓
Safe Fixes
    ↓
Verification
    ↓
Release Package

## Components

### .bob/
IBM Bob configuration, skills and custom modes.

### mcp-server/
Deterministic engineering tools exposed to IBM Bob through MCP.

### release-engine/
Finding normalization, scoring and release report generation.

### sample-app/
SmartPay demonstration application containing controlled release issues.

### dashboard/
Visualization of release readiness and findings.

### docs/
Architecture and development documentation.

### reports/
Generated release reports.

## Core Principle

IBM Bob must remain the central orchestrator.

The dashboard must not replace Bob's role.

MCP tools should provide deterministic facts.

Subagents should perform specialized reasoning.

Bob should coordinate the workflow and perform implementation/verification.

## Development Rules

- Do not commit secrets.
- Do not use real credentials in the sample application.
- Do not make destructive changes without approval.
- Do not claim tests passed without actually running them.
- Prefer small, focused commits.
- Keep components modular.

## BobShip Workflow

When the user asks to prepare a project for production:

1. Inspect the repository.
2. Load the release-engineer skill.
3. Identify project technologies and test frameworks.
4. Delegate independent analysis to specialized subagents.
5. Use MCP tools for deterministic checks.
6. Collect all findings.
7. Normalize findings into a common format.
8. Calculate release readiness.
9. Present blockers and recommended fixes.
10. Ask for approval before risky changes.
11. Apply safe fixes.
12. Run verification.
13. Recalculate readiness.
14. Generate release artifacts.

## Subagents

### Test Agent
Responsible for:
- tests
- coverage
- regression readiness

### Security Agent
Responsible for:
- secrets
- unsafe configuration
- security-related release blockers

### API Agent
Responsible for:
- API implementation
- OpenAPI
- request/response consistency

### Deployment Agent
Responsible for:
- Docker
- deployment configuration
- environment requirements

### Documentation Agent
Responsible for:
- README
- setup instructions
- configuration documentation

## Important

IBM Bob is the central orchestrator.

MCP tools provide deterministic information.

Subagents provide specialized reasoning.

The dashboard is only a visualization layer.

Never claim that a fix succeeded without verification.
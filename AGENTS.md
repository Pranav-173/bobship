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
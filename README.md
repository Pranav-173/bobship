# BobShip

## From "Works on My Machine" to "Ready to Ship"

BobShip is an AI release-engineering workflow built around IBM Bob.

It analyzes a software repository across:

- Testing
- Security
- API contracts
- Deployment
- Environment configuration
- Documentation
- Dependencies

Bob coordinates specialized subagents and deterministic MCP tools, identifies release blockers, safely fixes issues, verifies the changes and generates a release-readiness package.

## Architecture

```text
IBM Bob
   |
Release Engineer Skill
   |
Subagents + MCP Tools
   |
Release Analysis
   |
Safe Fixes
   |
Verification
   |
Release Package
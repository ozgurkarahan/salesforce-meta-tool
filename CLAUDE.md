# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Salesforce MCP Tool** — standalone deployment of a Salesforce MCP server with identity propagation, deployed via Azure Developer CLI (`azd`) and Bicep. Extracted from the multi-tool `secu-propagate-identity` PoC to be independently deployable.

**Architecture:** Chat App (FastAPI + MSAL.js) → AI Foundry Agent → APIM (JWT validation) → Salesforce MCP Server (FastMCP) → Salesforce APIs

## Reference Documents

| Document | Contents |
|---|---|
| [`docs/project-reference.md`](docs/project-reference.md) | All project-specific technical details — IaC principles, SDK notes, Salesforce MCP, auth flows, scripts, deployment caveats |
| [`docs/lessons-learned.md`](docs/lessons-learned.md) | Workflow rules, self-improvement loop, verification standards, task management process |

## Workflow Rules

### 1. Plan Mode for Verification
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents liberally to keep the main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop
- After ANY correction from the user: update [`docs/lessons-learned.md`](docs/lessons-learned.md) with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for the relevant project

### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes — don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests — then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management

1. **Plan First**: Write plan to `tasks/todo.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `tasks/todo.md`
6. **Capture Lessons**: Update [`docs/lessons-learned.md`](docs/lessons-learned.md) after corrections

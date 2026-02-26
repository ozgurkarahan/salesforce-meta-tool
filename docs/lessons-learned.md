# Lessons Learned — Workflow & Self-Improvement

Rules and patterns collected from project experience. Referenced from [`CLAUDE.md`](../CLAUDE.md). Update this file after every correction or discovery.

---

## 1. Plan Mode for Verification

- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity
- Before implementing, define what "done" looks like — including acceptance criteria and verification steps

## 2. Subagent Strategy

- Use subagents liberally to keep the main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

## 3. Self-Improvement Loop

- After ANY correction from the user: update this file (`docs/lessons-learned.md`) with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for the relevant project

## 4. Verification Before Done

- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

## 5. Demand Elegance (Balanced)

- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes — don't over-engineer
- Challenge your own work before presenting it

## 6. Autonomous Bug Fixing

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
6. **Capture Lessons**: Update this file (`docs/lessons-learned.md`) after corrections

---

## Project-Specific Lessons

### ApiHub PKCE vs Salesforce OAuth — Re-authenticate flow

**Problem (original):** After `azd up`, the Salesforce OAuth connection has no user token. ApiHub registers the connector with `identityProvider: oauth2pkce` (read-only) and sends `code_challenge` to Salesforce. Previously, this caused "Invalid Code Verifier" errors during the ApiHub consent flow.

**Update (2026-02-25):** The native ApiHub PKCE consent flow now completes successfully after a clean DELETE+PUT (tested on `rg-sf-orders-idp` deployment). Either the platform bug was fixed or DELETE+PUT resets the PKCE state that caused the mismatch.

**Key requirement — postprovision DELETE+PUT:**
- Bicep-created connections do NOT register the ApiHub connector that Foundry needs for interactive OAuth consent
- The postprovision hook (`update_sf_oauth_connection()`) DELETEs the Bicep connection and PUTs a fresh one via ARM REST, which triggers ApiHub setup
- This matches the `secu-propagate-identity` pattern where the native consent flow was confirmed working

**Primary runtime mechanism — Re-authenticate button:**
1. SF tokens expire after 2h; the chat app detects auth errors and shows a "Re-authenticate" button
2. `POST /api/reset-mcp-auth` DELETEs the existing connection (clearing the expired refresh token), then PUTs a fresh one without credentials
3. The next agent call triggers `oauth_consent_request` → user completes native ApiHub consent → fresh tokens stored

**Optional fallback — `grant-sf-mcp-consent.py`:**
- Bypasses ApiHub entirely: runs a direct OAuth auth code flow to SF (no PKCE) via `localhost:8444`, then DELETE+PUTs the connection with the refresh token baked in
- Useful if the native ApiHub consent flow fails, or for headless/automated setups where browser consent is impractical

**Rule:** After `azd up`, the postprovision hook DELETE+PUTs the connection to register the ApiHub connector. The first agent call triggers `oauth_consent_request` — complete the native consent flow in the browser. `grant-sf-mcp-consent.py` is an optional fallback for headless/automated setups. The re-authenticate button handles token expiry at runtime.

### 2026-02-25 — Missing auto-retry after consent chain
**Mistake:** `handleResponse()` in `meta-tool-salesforce` was missing the `awaitingPostConsentRetry` branch that auto-retries the original query after consent completes. This caused the agent to show text responses without ever calling MCP tools — making it look like the PKCE consent was broken when in fact the tokens were stored but never used.
**Root cause:** Code was extracted from `secu-propagate-identity` but this branch was accidentally dropped.
**Rule:** When extracting code between projects, diff the critical UI flow functions (handleResponse, resetAndRetry) to ensure no branches are missing. The missing auto-retry was the real cause of the "PKCE doesn't work" misdiagnosis.

<!-- Example format:
### YYYY-MM-DD — Short title
**Mistake:** What went wrong
**Root cause:** Why it happened
**Rule:** The rule that prevents recurrence
-->

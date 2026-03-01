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

### 2026-02-26 — sf CLI flag names differ across versions
**Mistake:** Used `--target-dir` for `sf project retrieve start` — the correct flag is `--output-dir`. The script failed immediately.
**Root cause:** Relied on plan/memory for flag names instead of checking `sf <command> --help` on the target machine.
**Rule:** Always run `sf <command> --help` to verify exact flag names before writing sf CLI automation. Flag names change between sf CLI versions.

### 2026-02-26 — sf CLI requires sfdx-project.json + force-app directory
**Mistake:** `sf project retrieve start` and `sf project deploy start` require a valid SFDX project structure (sfdx-project.json + the packageDirectory path must exist). Running from a bare temp directory failed with `InvalidProjectWorkspaceError` then `MissingPackageDirectoryError`.
**Root cause:** Assumed sf CLI would create the directory structure on retrieve. It doesn't — it validates the project workspace first.
**Rule:** When using sf CLI in temp directories, always create a minimal `sfdx-project.json` and `mkdir -p force-app/main/default` before running retrieve/deploy commands. Use `cwd` parameter in subprocess instead of `cd` in the command string.

### 2026-02-26 — Salesforce standard profile metadata names differ from labels
**Mistake:** Tried to retrieve `Profile:Standard User` via Metadata API — Salesforce returned "entity not found". The internal metadata name for "Standard User" is `Standard`, not `Standard User`.
**Root cause:** Salesforce uses internal API names for standard profiles that differ from UI labels (e.g., "System Administrator" = `Admin`, "Standard User" = `Standard`).
**Rule:** Don't try to retrieve and clone standard profiles via Metadata API — generate custom profile XML from scratch instead. This is simpler and avoids the metadata name mismatch problem entirely.

### 2026-02-26 — Custom Salesforce profiles need explicit permissions
**Mistake:** Generated a minimal custom profile with only `objectPermissions` — it was missing `ApiEnabled`, `LightningExperienceUser`, and other `userPermissions`. The demo user couldn't use the API or access Lightning Experience.
**Root cause:** Custom profiles don't inherit user permissions from the license — only object permissions default from the license. System permissions like `ApiEnabled` must be explicitly granted in the profile metadata.
**Rule:** When creating custom Salesforce profiles via Metadata API, always include these `userPermissions`: `ApiEnabled`, `LightningExperienceUser`, `RunReports`, `ExportReport`. Check the Standard User profile's permissions via SOQL (`SELECT Permissions* FROM PermissionSet WHERE Profile.Name='Standard User'`) as a reference.

### 2026-02-26 — Windows cp1252 encoding breaks sf CLI and Unicode output
**Mistake:** `subprocess.run(text=True)` on Windows uses cp1252 by default. sf CLI output containing non-ASCII bytes caused `UnicodeDecodeError`. Arrow characters (`→`) in print statements also failed.
**Root cause:** Windows default encoding is cp1252, not UTF-8. sf CLI outputs UTF-8.
**Rule:** Always pass `encoding="utf-8", errors="replace"` to `subprocess.run()` on Windows. Avoid non-ASCII characters (→, •, etc.) in print statements — use ASCII equivalents (`->`, `-`). SF User Alias field max is 8 characters.

### 2026-02-27 — SF Connected App must require PKCE to match ApiHub
**Mistake:** SF Connected App had PKCE disabled while ApiHub registers with `identityProvider: oauth2pkce` and sends `code_challenge` to Salesforce. SF ignored the `code_challenge`, so the PKCE handshake was never enforced end-to-end. This mismatch likely contributed to token refresh/re-exchange failures after expiry.
**Root cause:** Both sides of the OAuth flow must agree on PKCE. ApiHub always uses PKCE, but SF was not validating it. Without enforcement, the `code_verifier`/`code_challenge` contract is meaningless.
**Rule:** When the OAuth client (ApiHub) uses PKCE, the OAuth server (SF Connected App) must also require PKCE. Enable PKCE manually in SF Setup (cannot be done via Metadata API). Ensure all fallback scripts (`grant-sf-mcp-consent.py`) use PKCE so they don't break when SF requires it.

### 2026-02-27 — ECA Metadata API format differs from documentation
**Mistake:** Generated ECA metadata using speculative directory/file names (`externalClientApplications/`, `.externalClientApplication-meta.xml`, `commaSeparatedOAuth2Scopes`). The actual format from a real SF org is completely different.
**Root cause:** Assumed Metadata API naming conventions without retrieving from a real org. SF's actual SFDX source format for ECAs uses non-obvious names.
**Rule:** Always `sf project retrieve start` from a real org before writing metadata generation code. The actual format is:
- ECA directory: `externalClientApps/` (not `externalClientApplications/`)
- ECA suffix: `.eca-meta.xml` (not `.externalClientApplication-meta.xml`)
- OAuth settings name: `{AppName}_oauth` with suffix `.ecaOauth-meta.xml`
- OAuth settings field: `commaSeparatedOauthScopes` (not `commaSeparatedOAuth2Scopes`)
- OAuth settings must include `externalClientApplication` and `label` fields
- PKCE (`isCodeCredentialFlowWithPKCE`) is NOT a valid metadata field -- SF rejects it with "Element invalid at this location". PKCE is UI-only.
- `ConsumerKey` is NOT a field on the Tooling API `ConnectedApplication` object. ECA-created apps show 0 records in `ConnectedApplication` SOQL queries.

### 2026-02-27 — Post-consent retry loop needed for ApiHub propagation delay
**Bug:** After user completed OAuth consent, `continueAfterConsent()` immediately sent a continuation which got ANOTHER `consent_required` (ApiHub propagation delay). `handleResponse()` checked `consent_required` before `awaitingPostConsentRetry`, so it re-showed the consent banner. User clicked "I've completed" without re-opening the NEW consent link → infinite loop (6+ times) until agent gave up.
**Root cause:** ApiHub takes a few seconds to propagate tokens after consent completion. The chat app had no tolerance for this delay — any `consent_required` after consent showed the banner again.
**Fix:** In `handleResponse()`, when `awaitingPostConsentRetry` is true and we get `consent_required`, silently wait 3 seconds and retry (up to 4 times) instead of re-showing the banner. Only re-show if all poll retries are exhausted.
**Rule:** After OAuth consent completion, always add a poll-and-retry loop before re-showing consent UI. ApiHub needs a few seconds to propagate tokens. The user completing consent once should be enough — the app must absorb the delay.

### 2026-02-27 — ApiHub does NOT auto-refresh OAuth tokens (conclusively proven)
**Finding:** ApiHub never refreshes tokens for RemoteTool/GenericProtocol connections. Proven via diagnostic test with 10-minute SF token TTL.
**Evidence (JWT-level proof):**
- Successful call at 21:08 UTC and failed call at 21:18 UTC sent the **byte-identical JWT** (same `iat`, `exp`, signature)
- JWT claims: `iat=21:05:01`, `exp=21:15:01` (10min TTL). Token expired at 21:15:01.
- At 21:18:52 (3m51s past expiry), ApiHub provided the same expired token to Foundry — no proactive `exp` check
- At 21:20:07 (5m6s past expiry), second call — still the same expired token, no refresh between failures
- SF login history: **zero entries** after consent — no `grant_type=refresh_token` POST to `/services/oauth2/token`
- SF returned `INVALID_JWT_FORMAT` / `INVALID_AUTH_HEADER` (how SF rejects expired JWTs)
**What doesn't work:**
1. Proactive refresh (checking `exp` before providing token) — expired tokens ARE sent
2. Reactive refresh (401 → refresh → retry) — no refresh after receiving 401
3. `refreshUrl` in connection config — accepted but never called
**Diagnostic setup:** Removed APIM `validate-jwt` so requests flow through to SF. MCP server raises `SalesforceAuthError` on 401 (but FastMCP catches exceptions in tool handlers before middleware — see lesson below).
**Rule:** ApiHub's `refreshUrl` is non-functional for RemoteTool connections. Token expiry ALWAYS requires re-authentication. Design the UX accordingly.

### 2026-02-27 — FastMCP catches tool exceptions before ASGI middleware
**Mistake:** Added `SalesforceAuthError` (not a subclass of `httpx.HTTPStatusError`) to bypass MCP tool error handlers and propagate to `BearerTokenMiddleware`. Expected the middleware to catch it and return raw HTTP 401. Instead, FastMCP's internal tool execution wrapper caught it first and returned it as `Error executing tool ...: (401, b'...')` inside an HTTP 200 MCP tool result.
**Root cause:** FastMCP wraps ALL tool handler calls in a try/except that catches any `Exception` and returns it as a tool error string. The exception never reaches the ASGI middleware layer because FastMCP catches it at the MCP protocol level.
**Call chain:** `HTTP request → Middleware → FastMCP router → tool handler → raises SalesforceAuthError → FastMCP catches here (HTTP 200 with error string) → middleware never sees it`
**Rule:** ASGI middleware cannot catch exceptions raised inside MCP tool handlers — FastMCP intercepts them first. To return non-200 HTTP responses from tool-level errors, the tool handler itself must explicitly return an HTTP error response, or a custom MCP transport/router must be used.

### 2026-02-27 — SF `INVALID_JWT_FORMAT` / `INVALID_AUTH_HEADER` for expired JWT tokens
**Finding:** When a Salesforce JWT-format access token (Core Token Encryption) has a valid signature but an expired `exp` claim, SF returns `[{"message":"INVALID_JWT_FORMAT","errorCode":"INVALID_AUTH_HEADER"}]` with HTTP 401. This differs from the traditional `INVALID_SESSION_ID` error returned for opaque session-based tokens.
**Confirmed from Salesforce:** The request went directly to `orgfarm-*.develop.my.salesforce.com` — not intercepted by APIM (validate-jwt removed). Response format `[{errorCode, message}]` with `content-type: application/json;charset=UTF-8` is standard SF REST API error format.
**Context:** SF now issues access tokens as signed JWTs (header `tnk: "core/prod/..."`, alg RS256). SF validates the JWT `exp` claim server-side and returns `INVALID_JWT_FORMAT` when expired — the name is misleading since the format is valid, only the `exp` is past.
**Rule:** `INVALID_JWT_FORMAT` + `INVALID_AUTH_HEADER` from SF = expired JWT access token (not structurally malformed). Check the `exp` claim in the JWT payload to confirm. This is different from `INVALID_SESSION_ID` which applies to older opaque session tokens.

### 2026-02-27 — Don't run interactive scripts from Claude Code Bash tool
**Mistake:** Ran `test-reauth-flow.py` (which uses `input()` for Phase 4) from Claude Code's Bash tool. The script crashed with `EOFError` at the interactive prompt, leaving tokens in a wiped state each time.
**Root cause:** Claude Code's Bash tool runs non-interactively — `stdin` is closed, so `input()` raises `EOFError`.
**Rule:** Never run scripts with `input()` or other interactive stdin from Claude Code. For test scripts with interactive steps, either: (a) split into non-interactive + interactive parts, (b) have the user run from their own terminal, or (c) just do the ARM manipulation directly and let the user test through the UI.

<!-- Example format:
### YYYY-MM-DD — Short title
**Mistake:** What went wrong
**Root cause:** Why it happened
**Rule:** The rule that prevents recurrence
-->

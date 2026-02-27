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

<!-- Example format:
### YYYY-MM-DD — Short title
**Mistake:** What went wrong
**Root cause:** Why it happened
**Rule:** The rule that prevents recurrence
-->

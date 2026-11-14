# Can connector tests run in real Apps Script from CI without a human?

Ticket: [#10](https://github.com/benedikt-buchert/boring-data-studio/issues/10). Researched 2026-11-14. Inputs: `research.md` §9.6, §14.1, §14.2, D-18, D-26.

## Answer

**Yes, with a stored user OAuth token, not with a service account.** A human does one browser login on a dedicated Google account. After that, CI can `clasp push` and `clasp run` with no person involved, as long as that refresh token stays valid. Matomo has run this setup in GitHub Actions (push, weekly cron and manual runs). It calls `getConfig`, `getSchema` and `getData` (all built on `DataStudioApp`) through `clasp run`.

Note: the Matomo workflow file is public, but `gh run list` shows no visible runs. The setup is documented and wired up; I did not observe it passing.

## Findings

| # | Claim | Source |
|---|---|---|
| F-1 | "The Apps Script API doesn't work with service accounts." | [Execute functions with the Apps Script API](https://developers.google.com/apps-script/api/how-tos/execute) |
| F-2 | clasp labels its `--adc` / service-account mode "EXPERIMENTAL/NOT WORKING". It also says service accounts cannot own scripts. | [clasp README, Service accounts](https://github.com/google/clasp#service-accounts-experimentalnot-working), clasp v3.4.1 (2026-08-28) |
| F-3 | `scripts.run` requires three things. (a) The script is deployed as an API executable. (b) The script and the caller's OAuth client share a **standard** Cloud project ("default projects created for Apps Script projects are insufficient"). (c) The Apps Script API is enabled in that project. | [Execute how-to](https://developers.google.com/apps-script/api/how-tos/execute) |
| F-4 | The OAuth token "must cover all scopes used by the script, not just the ones used by the called function". A script with no required scope cannot be run. `script.external_request` is one of the accepted scopes. | [Execute how-to](https://developers.google.com/apps-script/api/how-tos/execute); [scripts.run reference](https://developers.google.com/apps-script/api/reference/rest/v1/scripts/run) |
| F-5 | With `devMode: true`, the call runs the most recently **saved** (pushed) code, not the deployed version. "Only the owner of the script can execute it in development mode." | [scripts.run reference](https://developers.google.com/apps-script/api/reference/rest/v1/scripts/run) |
| F-6 | If the Cloud project differs from the script's project, the call fails with 403 PERMISSION_DENIED. A script exception returns `error.details[0]` as an `ExecutionError`. Parameters and return values must be primitives, arrays or plain objects. | [scripts.run reference](https://developers.google.com/apps-script/api/reference/rest/v1/scripts/run) |
| F-7 | Each execution is limited to 6 minutes. The API cannot create triggers. API executables stop working if ownership moves to a shared drive or to an account outside the domain. | [Execute how-to](https://developers.google.com/apps-script/api/how-tos/execute) |
| F-8 | clasp `run` setup steps: (1) put `projectId` in `.clasp.json`; (2) set the GCP project number in Apps Script Project Settings; (3) create a **Desktop App** OAuth client; (4) run `clasp login --creds client_secret.json --use-project-scopes [--include-clasp-scopes]`; (5) add `"executionApi": {"access": "ANYONE"}` to `appsscript.json`; (6) enable the Apps Script API. `clasp run` defaults to dev mode; `--nondev` turns it off. `--user <name>` selects a named credential profile. | [clasp docs/run.md](https://github.com/google/clasp/blob/master/docs/run.md); [clasp README](https://github.com/google/clasp#run) |
| F-9 | Refresh tokens expire in these cases: (a) after 7 days if the consent screen is **External + Testing**, unless only profile/email/openid scopes are requested; (b) after 6 months without use; (c) when the 101st token is issued for the same account and client (oldest token revoked silently); (d) on a password change, if the token has Gmail scopes. | [Google OAuth 2.0 overview, refresh token expiration](https://developers.google.com/identity/protocols/oauth2#expiration) |
| F-10 | Apps Script consumer quotas: 20,000 URL Fetch calls per day, 30 simultaneous executions per user, 6 minutes runtime. | [Apps Script quotas](https://developers.google.com/apps-script/guides/services/quotas) |

### What Matomo's CI does (matomo-org/looker-studio-connector, GPL, read only)

- `.github/workflows/tests.yml` writes three repo secrets to files: `CLASP_PROJECT` to `.clasp.json`, and `CLASP_CREDENTIALS` / `CLASP_CREDENTIALS_LOCAL` to `~/.clasprc.json` and `./.clasprc.json`. It then runs `clasp login --status` and `npm test`. Triggers: push, a weekly cron and `workflow_dispatch`. A `concurrency` group per ref cancels older runs.
- Their tokens come from one local `clasp login --creds creds.json` with their own Desktop OAuth client in their own GCP project (`DEVELOPMENT.md`, "Setting Up for Development").
- `scripts/update_ci_secrets.ts`: clasp refreshes the access token and rewrites `.clasprc.json`. The script detects that change and writes the new file back to the repo secrets via the GitHub API (needs a `REPO_TOKEN` PAT). Its comment says this lets CI "continue running w/o a human". This handles **access** token rotation. It cannot recover an expired or revoked **refresh** token. On `invalid_grant`, their harness throws "run `clasp login --creds creds.json` again" (`tests/utilities/clasp.ts`).
- `tests/globalSetup.js` sets `executionApi.access = 'ANYONE'` in `appsscript.json` for the test run only (reverted in teardown). It builds a test bundle that adds `src-test` helpers and runs `clasp push -f`. I found no explicit API-executable version deployment in the test path: it uses dev mode against the pushed HEAD (output starts with "Running in dev mode.").
- `clasp run -p '[fn, testName, ...args]' callFunctionInTest`: the wrapper calls the global function, returns `JSON.stringify(result)`, and catches exceptions into JSON. clasp pretty-prints objects and does not print exceptions as JSON, so the wrapper makes output parseable. `clearEnvInTest` resets `PropertiesService` between tests. `setScriptProperties` injects configuration.
- The manifest asks for only `script.external_request`. That satisfies the "at least one scope" rule (F-4), and the same scope list works for `clasp login --use-project-scopes`.
- Their tests call a public backend (`demo.matomo.cloud`) or a local Matomo through a tunnel (`USE_LOCALTUNNEL`). Apps Script fetches from Google's servers, so the backend must be reachable from the internet.

## What CI needs for this project

1. **A dedicated Google account** that owns the test Apps Script project. Use a separate test script, not the production connector, because dev mode is owner-only (F-5).
2. **A standard GCP project.** Link it to that script (project number in Script settings), enable the Apps Script API, create a Desktop OAuth client and configure the consent screen.
   - Prefer **Internal** user type, which needs a Workspace organization, or publishing status **In production**. Either avoids the 7-day refresh-token expiry of External+Testing (F-9a).
   - `script.external_request` is sensitive, not restricted. An unverified "In production" app shows a warning screen but works for the owner. (General Google OAuth behaviour; not re-verified here.)
3. **One human login:** `clasp login --creds client_secret.json --use-project-scopes --include-clasp-scopes`. Store `~/.clasprc.json` and `.clasp.json` as CI secrets.
4. **Test manifest overlay:** add `executionApi.access` (`MYSELF` is enough for owner-only dev-mode runs; Matomo uses `ANYONE`). Use the same `oauthScopes` as production. Bundle a `callFunctionInTest` wrapper (write our own; Matomo's code is GPL) plus a properties reset helper.
5. **Run in dev mode** against the freshly pushed code. Then no versioned deployment is needed per run.
6. **A reachable test API** for `UrlFetchApp`: a stable public test instance, or a tunnel started in the CI job. With `PATH_KEY` (O-02), tests call `setCredentials` first. Credentials go to `UserProperties`, so the reset helper must clear them.
7. **One global concurrency group.** All runs share one script project, so parallel pushes from two branches overwrite each other.

## Risks

- **Refresh token death is the main failure mode.** Causes: 7-day Testing expiry, 6 months unused (a weekly cron prevents this), revocation, password change, or 100 newer tokens for the same client (do not reuse the CI client for daily logins). The fix always needs a human browser login. Make CI fail loudly on `invalid_grant`.
- **Secret write-back (Matomo pattern)** needs a PAT with repo secrets write access. That is a broad credential. Check first whether our clasp version's access-token refresh actually needs persisting: each job can refresh from the stored refresh token.
- **The stored token is a full user credential.** Its scopes cover script projects and deployments plus external requests. Keep the account dedicated and empty, and run only on trusted branches, not fork PRs.
- **Flakiness:** dependency on Google's runtime and the internet-reachable backend; the 6-minute limit per call; 20k URL Fetch calls per day; output parsing through the clasp CLI (Matomo strips "Running in dev mode." and treats "No response." as undefined). There is no visible Matomo run history to estimate a flake rate.
- **Scope drift:** if the connector adds a scope, the token must be minted again (F-4).
- **This does not exercise the Data Studio UI.** It runs connector functions in the real runtime with real `DataStudioApp`, `UrlFetchApp` and `PropertiesService`, but Data Studio's own request shapes, caching and wait limits stay untested (see E-37, E-41 in `research.md`).

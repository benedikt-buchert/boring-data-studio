# Partner Connector Gallery: what it requires of this connector

Answers issue #3. Researched 2026-11-14 against Google primary docs. Extends LS-27 and section 11 of `research.md`.

## Short answer

- **A connector with a user-supplied API URL can be listed.** The requirements page has an explicit exception: leave out `urlFetchWhitelist` and explain why in the review form [R1]. AtScale is a listed semantic-layer connector where each user enters their own instance URL [R7].
- **OAuth client verification is required for every auth type, `PATH_KEY` included** [R1]. It is a Google Cloud process, separate from the Data Studio review. Expect brand verification in 2-3 business days, plus sensitive-scope verification in about 10 business days if a scope we request is sensitive [R4][R5].
- **Hosting:** we need our own verified domain for the `addOnUrl` page, the privacy policy and the terms. `sites.google.com` is not allowed. The privacy policy and terms must be on the same domain as `addOnUrl` [R1][R3].
- **Naming:** the name must state the purpose, must not include the word "connector", may not use "GDS"/"DS" shorthand, and may not use emojis. It can have at most 28 characters [R1][R2].
- **Review:** submit through the "Publish your Partner Connector" form, with a `Production` deployment shared with two Google review addresses. Google publishes no turnaround time for the Data Studio review [R1][R6].

## Requirements in detail

### Apps Script project [R1]
- Give view access to `data-studio-contrib-qa@googlegroups.com` and `data-studio-contrib@google.com`.
- Create a deployment named `Production` that points to the version to review.
- Show `appsscript.json` in the editor.
- The project must use a standard Google Cloud project, not the default one, for OAuth verification. If the script moves to a different Cloud project, verification must be done again [R3].

### Manifest (`dataStudio`) [R1][R2]
| Field | Rule |
|---|---|
| `name` | Max 28 characters. Must say what the connector does. No word "connector", no "GDS"/"DS", no special or invisible characters. |
| `description` | Must be complete. A vague description is rejected. |
| `shortDescription` | Max 114 characters, no URLs. The review requires it. |
| `addOnUrl` | A dedicated page on our own domain (not `sites.google.com`). It must have usage details, an account sign-up link if needed, and a privacy policy and terms on the **same domain**. |
| `supportUrl` | A hosted page. Not an email address or `mailto:` link. |
| `logoUrl` | A static image that we control, at least 48x48 px (the manifest reference says 40x40). It must not be animated and must not be hosted on a Google domain (`gstatic`, `googleusercontent`, ...). Google Cloud Storage (`*.googleapis.com`) is allowed and recommended. |
| `authType`, `feeType`, `privacyPolicyUrl`, `termsOfServiceUrl` | Required for the review. |
| `sources` | Each source must exist in the Data Registry repo. If ours is missing, add it with a pull request. |
| `oauthScopes` (root) | Must be explicit, or the connector is rejected. |
| `urlFetchWhitelist` (root) | List every endpoint. **Exception:** "If your connector does not connect to a set of fixed endpoints or the endpoint prefix varies", leave the property out and give details in the "Exception for urlFetchWhitelist" form field. |
| `templates` | Only if the schema is fixed. Our schema is not fixed, so this does not apply. |

The prototype manifest currently breaks three of these rules: `logoUrl` is on `gstatic.com`, `addonUrl`/`supportUrl` are placeholders, and the description says "PROTOTYPE". The rule "cannot be beta" also applies [R1].

The allowlist syntax supports one leading subdomain wildcard (`https://*.example.com/path/`) [R8]. This does not help: users host their APIs on any domain, so the exception is the only option.

### Connector behaviour [R1]
- Ask for credentials through `getAuthType()`, **never** through `getConfig()`. `PATH_KEY` meets this rule: the URL and key go in the auth dialog.
- Errors must be meaningful and tell the user what to do, also when config input is invalid or blank.
- No spelling or grammar mistakes in the descriptions, the `addOnUrl` page, the support page or the OAuth page.
- The connector must not be unfinished or in beta.
- We must accept the Data Studio Galleries Terms of Service (Submitter).

### OAuth client verification [R1][R3][R4][R5]
- Required whatever the auth type is. A failed or missing verification means the Partner review rejects the connector.
- Add **every** scope from `oauthScopes` to the consent screen. A missing scope makes the "unverified app" screen appear, and the review fails. After verification, test with a new account.
- Brand verification (every app) needs:
  - A public homepage on a domain that we have verified in Search Console. A login-only page is not accepted.
  - A privacy policy on the same domain that explains how Google user data is used.
  - App name, logo (1 MB or smaller), support email and authorized domains.
  - Estimated time: 2-3 business days [R5]. The Apps Script guide says "most verification requests receive a response within 24 to 72 hours" [R3].
- Sensitive-scope verification additionally needs:
  - A justification for each scope, including why a narrower scope does not work.
  - An unlisted YouTube demo video in English. It must show the consent flow, the client ID in the address bar, and how each scope is used.
  - Estimated time: 10 business days [R4][R5].
- Restricted scopes add a yearly security assessment (about 6 weeks) [R5]. We need no restricted scope.
- Before verification, an unverified app is limited to 100 new users and shows a warning screen [R9].
- Exemption: if all users are in the owner's Google Workspace organization, verification is not needed [R3][R9]. This applies only to the internal stage, not the gallery.

### Scopes this connector needs
| Scope | Why | Tier |
|---|---|---|
| `script.external_request` | `UrlFetchApp` to the BSL API | **Not confirmed.** Google publishes no tier table. The Cloud Console "Data Access" page shows the tier when the scope is added [R4]. A community report treats it as sensitive (secondary source). Plan for sensitive-scope verification (10 days, demo video). |
| `openid`, `userinfo.email` (only with A-3 identity tokens) | `ScriptApp.getIdentityToken()` | Google pre-fills the scopes for Google Sign-In as non-sensitive [R4]. The doc does not name the scopes, so this is inferred. These scopes do not add an extra review step, but they must be on the consent screen and in `oauthScopes`. |
| `script.storage` (if `UserProperties` needs it) | Store the `PATH_KEY` credentials | Check in Cloud Console. |

The Partner requirements page sets no extra rule for identity-token scopes. The general rule applies: add every scope to the consent screen.

### Review and after listing [R6]
- Submit through the "Publish your Partner Connector" form (https://goo.gl/KvuMcU). Google publishes no timeline for this review.
- We must support the connector, fix user issues and manage our own deployment.
- Ranking is mostly by popularity, and new connectors get a short-term boost.
- Alternative without review: share by direct link [R6]. Users still see the unverified screen if the scopes are not verified.

## What this means for the design
- **Auth:** keep `PATH_KEY` (it meets the `getAuthType()` rule). A-3 identity tokens add `openid` and `userinfo.email`. Both are probably non-sensitive, so the review effort does not change much, but the scopes must be declared from the start. If we add them later, the consent screen and the verification must be done again.
- **Manifest:** leave out `urlFetchWhitelist` and write the exception reason now (for example: "each user runs their own BSL API on their own host; the base URL is entered in the PATH_KEY dialog"). Declare `oauthScopes` explicitly. Add `shortDescription`, `privacyPolicyUrl`, `termsOfServiceUrl`, `authType: PATH_KEY` and `feeType: FREE`.
- **Naming:** for example "Boring Semantic Layer" (21 characters). Do not use "connector" or "DS" in the name.
- **Hosting:** buy or choose a domain and verify it in Search Console. Host the landing page, privacy policy and terms on that domain, and the logo on that domain or on GCS. GitHub Pages on a custom domain works. A `github.io` subdomain cannot be verified as ours.
- **Cloud project:** move the script to a standard GCP project before verification, and keep it there.

## Open risks
1. **Allowlist exception is granted case by case.** The form field exists, but Google gives no criteria. AtScale is the precedent (user-entered URL, listed), but AtScale uses OAUTH2, not PATH_KEY.
2. **`script.external_request` tier is not confirmed.** If it is sensitive, add about 10 business days and a demo video. Check in the Cloud Console Data Access page.
3. **No published Data Studio review timeline.** Rejections over wording, logo or "beta" status lead to resubmission rounds.
4. **Who owns the domain and support:** an open-source project needs a long-lived domain and support page that someone owns. The "actively support" duty is ongoing.
5. **Data Registry `sources`:** BSL is not a data source. We may need to add an entry with a pull request, or pick a generic source.

## Sources
- [R1] Partner Connector requirements: https://developers.google.com/looker-studio/connector/pscc-requirements
- [R2] Manifest reference: https://developers.google.com/looker-studio/connector/manifest
- [R3] Apps Script OAuth client verification: https://developers.google.com/apps-script/guides/client-verification
- [R4] Sensitive scope verification: https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification
- [R5] OAuth verification FAQ (time estimates table): https://support.google.com/cloud/answer/13463817
- [R6] Publish a Partner Connector: https://developers.google.com/looker-studio/connector/publish-connector
- [R7] AtScale Data Studio connector: https://documentation.atscale.com/container/connecting-to-atscale-from-business-intelligence-software/google-data-studio/atscale-data-studio-connector
- [R8] Apps Script URL allowlist: https://developers.google.com/apps-script/manifest/allowlist-url
- [R9] Unverified apps: https://support.google.com/cloud/answer/7454865

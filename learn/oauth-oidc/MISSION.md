# Mission: OAuth 2.0 and OpenID Connect

## Why
Hold my own in auth design grillings for APIs and connectors (like the boring-data-studio O-12 session) without getting lost. I want to judge options myself: shared keys, identity tokens, OAuth with Entra/Okta, service accounts, personal tokens.

## Success looks like
- Given any token in a design, say who issued it, who it is for (audience), whose identity it carries, and who may accept it.
- Explain the difference between OAuth (access to an API) and OIDC (who the user is) in two sentences.
- Pick the right flow for a situation: authorization code + PKCE, client credentials, token exchange, plain API key.
- Spot the classic attacks in a design (replay, wrong audience, leaked secret, token in URL) and name the fix.
- Answer grilling questions with a recommendation, not "I'm not sure".

## Constraints
- Short lessons; learns through concrete examples from real designs.
- Prefers diagrams (mermaid) and plain language.

## Out of scope
- Looker Studio / Apps Script specifics.
- Implementing an authorization server.
- SAML, Kerberos, LDAP.

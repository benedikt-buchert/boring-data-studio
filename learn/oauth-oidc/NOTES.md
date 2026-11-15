# Notes

- Learner asked for mermaid diagrams when lost; likes plain language (asked for ASD-STE100 style once).
- Ground examples in the boring-data-studio auth session (research/docs/research.md §11.3, §11.3.1): connector → BSL API → warehouse; A-3 Google ID token, A-5 Entra OAuth, A-9 personal tokens, O-13 replay.
- Lessons are published as private Artifacts (relative assets via `files`). Workspace lives in learn/oauth-oidc/, not committed unless the learner asks.

- Lesson 1 was too abstract for a first lesson: start every new concept from the problem it solves and a concrete analogy (hotel key card / visitor badge), then the spec terms.

## Planned sequence (adjust to learning records)
0. Why OAuth exists, why OIDC was added (key card vs badge). ← insert before 0001 (LR-0002)
1. Who is this token for? Roles, ID token vs access token, iss/aud/sub/exp. ← 0001
2. Authorization code flow + PKCE, step by step (why secrets are not needed).
3. Client credentials and service accounts (no user) vs on-behalf-of.
4. Validating a JWT at an API: signature, JWKS, iss, aud, exp; opaque tokens and introspection.
5. Attacks: replay, wrong audience, token in URL, leaked secrets; bearer vs sender-constrained (DPoP, mTLS).
6. Refresh tokens, lifetimes, revocation.
7. Choosing: API key vs OAuth vs personal tokens vs token exchange — a grilling drill.

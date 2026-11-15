# Misconception: access token = who the user is

In lesson 1, quiz Q1, the learner chose "access token" as the token that tells the app who the user is, and then said "I still need to learn about OAuth and OIDC". Lesson 1 started too high (roles, claims, audience) without the "why": what problem OAuth solves and why OIDC was added. Next teaching must build the foundation first: delegation vs password sharing, access token = key card (access, not identity, opaque to the client), ID token = signed badge for the app.

**Implications:** re-check this with a retrieval question before moving on to PKCE; lesson 1's audience rule only lands once the two-token picture is solid.

# OAuth vs OIDC mostly right; transferred it to CI workload identity

The learner summarised: OAuth = authorised by permission/allowance; OIDC = person and app connect by who they are. Mostly right. Correction given: OIDC only *states* who someone is; what they may do is still decided by the receiver (identity ≠ permission). The learner then asked on their own whether a GitHub repo can identify itself to Google and get CI permissions that way: a correct transfer to machine identity (GitHub Actions OIDC token → Google Workload Identity Federation → short-lived access token).

**Implications:** ready for "identities that are not people" (workload identity, service accounts, token exchange) earlier than planned; it also explains the warehouse leg of the BSL design. Keep reinforcing "identity vs permission" as a separate step.

# OAuth 2.0 and OpenID Connect Resources

## Knowledge

- [Book (free online): _OAuth 2.0 Simplified_ by Aaron Parecki](https://www.oauth.com/)
  Readable walk-through of every flow by an OAuth spec editor. Use for: first explanation of any flow, PKCE, the roles.
- [oauth.net](https://oauth.net/2/)
  Community index of all OAuth specs and their status. Use for: finding the right RFC; checking what is current (OAuth 2.1 is still a draft).
- [RFC 6749: The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
  The core spec. Use for: roles (§1.1), grant types (§1.3), the fact that access-token format is not defined (§1.4).
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
  The identity layer on top of OAuth. Use for: ID token claims and validation (§2, §3.1.3.7); `aud` must hold the client ID.
- [RFC 7519: JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
  Token format. Use for: registered claims `iss`, `sub`, `aud`, `exp` (§4.1).
- [RFC 9068: JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
  How JWT access tokens look. Use for: `aud` = the resource server.
- [RFC 7636: PKCE](https://www.rfc-editor.org/rfc/rfc7636)
  Proof Key for Code Exchange. Use for: why public clients need no secret.
- [RFC 9700: Best Current Practice for OAuth 2.0 Security (Jan 2025)](https://www.rfc-editor.org/rfc/rfc9700)
  Current security rules. Use for: audience-restricted tokens (§4.10.2), PKCE everywhere, no implicit flow.
- [RFC 8693: OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
  Swapping one token for another. Use for: later lesson on service-to-service and the A-9 pattern.

## Wisdom (Communities)

- [OAuth WG mailing list (IETF)](https://mailarchive.ietf.org/arch/browse/oauth/)
  Where spec authors discuss edge cases. Use for: reading, not posting, at first.
- [Information Security Stack Exchange — oauth tag](https://security.stackexchange.com/questions/tagged/oauth)
  Moderated Q&A. Use for: "is this design safe?" questions.

## Gaps
- No vetted resource yet for Entra-specific token details (v1 vs v2 tokens, app roles). Search Microsoft Learn when a lesson needs it.

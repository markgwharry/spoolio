# Session and device credential design

## Implemented baseline

Spoolio issues 15-minute access tokens and 30-day refresh tokens. Each token carries
the user's current `token_version`. JWT validation compares that claim with the
database on every authenticated request. Password changes, password resets, and
`POST /api/logout` increment the version, invalidating every older access and refresh
token for that user. An authenticated password change returns a replacement token pair
at the new version so the session making the change can continue; every older session
is still revoked. Tokens issued before this mechanism existed are treated as version
zero, so the deployment itself does not unexpectedly sign everyone out.

Hardware credentials are high-entropy bearer keys. Spoolio returns the plaintext key
only when a device is registered or its key is rotated. The database stores a SHA-256
digest and hashes each incoming bearer key before lookup. This was deployed in two
stages: a compatibility release first taught running code to understand digests, then
a follow-up migration bulk-hashed dormant plaintext rows and removed the legacy lookup.
Already provisioned devices keep the same bearer key, while migration failure or a code
rollback cannot strand them on an incompatible database representation.
The digest is intentionally unsalted: device keys are random, non-human secrets and
must support indexed equality lookup. This is not suitable for user passwords.

## Refresh token storage decision

The current SPA continues to keep its refresh token in `localStorage`. Moving it to a
`Secure`, `HttpOnly`, `SameSite` cookie would make the refresh token inaccessible to
JavaScript and reduce the damage from token-reading XSS. It would not remove the need
to prevent XSS, because malicious in-origin JavaScript could still make authenticated
requests while it is running.

That move is deferred because it changes the authentication protocol and needs a
complete CSRF design. A future cookie implementation should:

- keep the access token in memory rather than persistent browser storage;
- scope the refresh cookie narrowly and require `Secure` and `HttpOnly`;
- use `SameSite=Lax` or stricter plus an explicit CSRF token on refresh/logout;
- restrict credentialed CORS to configured origins;
- restore a session through one controlled refresh request on application startup;
- clear the cookie server-side on logout and cover cross-origin failure cases.

Until that coordinated change is made, token-version revocation provides a reliable
server-side way to terminate sessions without introducing a partially protected cookie
flow.

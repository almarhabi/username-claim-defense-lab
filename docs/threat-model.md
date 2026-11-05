# Threat model: synthetic username lifecycle

## Scope

The protected asset is ownership integrity for synthetic usernames in `social.lab.internal`. Accounts, passwords, sessions, and events are generated fixtures. No third-party account or network is in scope.

## Invariants

1. A username has at most one owner.
2. A concurrent claim produces exactly one successful claimant.
3. Only the current owner can release or transfer a username.
4. Transfer changes ownership directly; the name never becomes available between source and target.
5. A released name cannot be claimed before `available_at` while defenses are enabled.
6. Requests above the configured per-account limit are recorded as `rate_limited` while defenses are enabled.
7. Administrative scenarios require the lab administration key.
8. Telegram administration fails closed when its user allow list is empty.
9. The Telegram HTTP client cannot be redirected to an arbitrary destination.

## Abuse cases and controls

### Claim race

Multiple synthetic actors request the same available name. SQLite `BEGIN IMMEDIATE` serializes write transactions. The update also checks the observed row version and the absence of an owner. The race test asserts one winner and one final owner.

### Transfer race

The service reads ownership and version in one write transaction, then updates with both as predicates. A changed record fails rather than overwriting a newer owner. No release operation occurs during transfer.

### Release-and-snipe

Releasing writes a future availability timestamp. Claims before that timestamp receive `cooldown`. Disabling defenses is an explicit comparison mode for local tests, not a bypass of an external system.

### Request burst

Each claim increments an actor/window counter. Requests beyond the limit are rejected and audited. Scenario size is capped at 500 requests to keep the lab itself bounded.

### Credential and session misuse

Only fixture credentials are seeded. Passwords are stored as salted PBKDF2-HMAC-SHA256 values. Bearer sessions have expiry timestamps and can be revoked. The Telegram interface intentionally exposes no login command and never asks for credentials.

### Controller abuse

Only configured Telegram numeric IDs may operate scenarios. Destination hosts are fixed, URL credentials are rejected, redirects are disabled, and commands map to fixed paths. The social container has no external network route in the supplied Compose configuration.

## Residual limitations

This is a teaching laboratory, not a production identity service. It uses fixed-minute rate windows rather than a distributed sliding-window limiter, a single SQLite database rather than a multi-node store, and a shared fixture password for convenience. The default administration key must be changed on a shared machine. The dashboard has no production-grade CSRF or multi-user administration layer and must remain bound to localhost.

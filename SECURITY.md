# Security and scope

This repository is a synthetic security laboratory. It does not implement or document integration with any real social platform, and it must not be adapted to submit real credentials, cookies, session tokens, or requests to third-party services.

The optional outbound Telegram connection transports commands for the local simulation. It does not make the simulated accounts or sessions valid anywhere else.

## Network boundary

- The `social` container is attached only to Docker's internal `lab_net` network.
- The optional Telegram controller has a second network solely for Telegram connectivity.
- The controller accepts only numeric Telegram user IDs in its allow list and fails closed when the list is empty or invalid.
- Its HTTP client accepts only `social`, `social.lab.internal`, `localhost`, or `127.0.0.1`; it rejects URL credentials and does not follow redirects.
- Telegram command handlers expose fixed paths; users cannot choose a host or arbitrary API path.
- The web port is bound to `127.0.0.1` by default.

## Credentials and sessions

- Replace `local-lab-admin-key` before sharing a machine. The key authorizes destructive lab reset and scenario execution.
- The fixture password is public test data and must never be reused for any real account.
- `/session ACCOUNT` reads the fixture password locally, so users do not place passwords in Telegram messages.
- Synthetic session tokens remain in controller memory, are excluded from Telegram responses, and are removed on logout, reset, or process restart.
- Admin authentication and Bearer session authentication cannot be combined in one client request.

This is a laboratory authentication system, not a production identity service. Do not expose the development dashboard directly to the public internet.

## GitHub Actions and self-hosted runners

`tests` runs on ephemeral GitHub-hosted runners and needs no Telegram secret. It removes its containers and data afterward.

`synthetic-lab-controller` is manual-only and requires a self-hosted runner. Repository secrets are written to a mode-0600 runtime file and removed when the job finishes. The containers, not the Actions job, provide continuous operation.

Use self-hosted runners only in a private repository with fully trusted workflow maintainers. Anyone able to alter and run a workflow on that runner may access its secrets, files, Docker daemon, and network. Keep the runner off production systems and apply the host's normal patching, logging, and access controls.

## Reporting a lab defect

Open a private security report or an issue without including real access tokens, credentials, personal data, or third-party endpoints. Useful reports include the synthetic fixture, expected invariant, observed result, and a minimal local reproduction.

# Security and scope

This repository is a synthetic security laboratory. It does not implement or document integration with any real social platform, and it must not be adapted to submit real credentials, cookies, session tokens, or requests to third-party services.

## Network boundary

- The `social` container is attached only to Docker's internal `lab_net` network.
- The optional Telegram controller has a second network solely for Telegram connectivity.
- The controller accepts only numeric Telegram user IDs in its allow list.
- Its HTTP client accepts only `social`, `social.lab.internal`, `localhost`, or `127.0.0.1`; it rejects URL credentials and does not follow redirects.
- The web port is bound to `127.0.0.1` by default.

## Local administration

Replace `local-lab-admin-key` before sharing a machine. The key authorizes destructive lab reset and scenario execution; it is not a production authentication system. Do not expose the development dashboard directly to the public internet.

## Reporting a lab defect

Open a private security report or an issue without including real access tokens, credentials, personal data, or third-party endpoints. Useful reports include the synthetic fixture, expected invariant, observed result, and a minimal local reproduction.

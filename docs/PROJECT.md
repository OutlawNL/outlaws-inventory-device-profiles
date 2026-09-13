# Project

Outlaw's Inventory is moving from a personal homelab application toward a robust self-hosted product that others can install and operate safely.

## Current Baseline

The supported technical baseline is **v0.15.0 or newer**. Current development is on the **v0.18.x** release line.

Historical v0.14.x migration scaffolding is not part of active development. The v0.14.38 → v0.15.0 transition was the one-time move into the clean baseline.

## Product Priorities

- robustness and predictable recovery;
- security and least-privilege host integration;
- clear desktop/tablet/mobile UX;
- reliable updater and rollback;
- professional onboarding;
- useful notifications without noise;
- maintainable documentation and regression coverage.

## Product Identity

The product name remains **Outlaw's Inventory**. An installation may use a custom instance name while retaining the product identity and appropriate `Powered by Outlaw's Inventory` attribution.

## Current Architecture Principles

- The application runs locally as `outlaws-inventory`.
- Managed remote checks use the dedicated `outlaw` account and narrowly scoped sudo permissions.
- System Checks is the supported server-health and maintenance surface.
- Health, update and application checks share current status semantics but retain safe internal implementation boundaries where renaming would add migration risk.
- Persistent data is kept separate from release code.
- Updates and restores must be verifiable and recoverable.
- UI changes preserve the Classic interface and avoid accumulating one-off CSS overrides.

## Distribution model

Outlaw's Inventory is a self-hosted product. A centrally hosted/SaaS edition is intentionally out of scope; users operate their own installation and retain their own inventory, credentials and managed-host connectivity.

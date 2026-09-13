# Release process

## Supported baseline

From v0.15.0 onward:

- v0.15.0 transition source: v0.14.38; future supported in-place upgrade baseline: v0.15.0 or newer;
- supported full backup source: v0.15.0 or newer;
- fresh installations use the current release.

Compatibility before v0.15.0 is intentionally outside the active release contract, except for the one-time v0.14.38 → v0.15.0 transition updater.

## Release assets

Each GitHub release must contain:

```text
outlaws-inventory-vX.Y.Z.zip
SHA256SUMS
```

The ZIP must extract to one directory named `outlaws-inventory-vX.Y.Z`.

## Release checklist

Before publishing:

1. update `APP_VERSION`, `DATABASE_SCHEMA_VERSION` and `INSTALLER_VERSION`;
2. update README, current documentation and CHANGELOG;
3. run Python and shell syntax validation;
4. parse all application templates;
5. run the full current regression/release-contract test suite;
6. build a clean versioned ZIP;
7. ensure runtime data, caches and local secrets are absent;
8. generate SHA256SUMS;
9. run the release-package validator;
10. extract the final ZIP and validate it again;
11. publish the Git tag and GitHub Release;
12. test the internal updater from a supported v0.15.x-or-newer installation.

## Release channels

Outlaw's Inventory supports two release channels for the built-in updater:

- **Production** uses GitHub's latest normal release and ignores drafts and pre-releases. Production is the default for normal installations.
- **Acceptance** considers both normal releases and GitHub pre-releases, while still ignoring drafts. Use this on an acceptance/test installation such as AppServer-02.

The release channel is selected in **Settings → Application Version**. Changing the channel is saved immediately and triggers a new GitHub release check. The displayed Latest Release and update status always follow the selected channel.

The intended promotion flow is:

1. build one immutable versioned ZIP and its SHA256SUMS;
2. publish that version in GitHub as a **pre-release**;
3. install and validate that exact artifact on an Acceptance-channel instance;
4. edit the same GitHub Release and promote it from pre-release to the normal Production release;
5. Production-channel instances can then discover the already-tested artifact.

Do not rebuild or replace the ZIP between Acceptance testing and Production promotion.

## Private repository

Use a fine-grained repository-scoped read-only token. Each private-beta installation/user should use its own token; do not distribute one maintainer token in the application ZIP or share it through a copied full backup. Never commit tokens, databases, keys, uploads, staging files or virtual environments.

The release ZIP must contain no instance-specific runtime data, credentials, keys or secrets. Full `.oi-backup` files are intentionally different: they include protected secrets and keys for complete recovery and must be handled as credential-bearing files.

For future public releases, normal update discovery/download from a public GitHub repository should work without requiring a personal access token. Token configuration remains relevant for private repositories.

## Compatibility policy

Schema guards may remain when they protect the supported v0.15.0+ database shape or future upgrades. Historical product-name/path conversions and unsupported pre-v0.15 migration behavior should not be reintroduced into active code.

# Roadmap

## Current focus

- Firmware provider reliability
- Clear first-run onboarding
- Reliable backup and restore
- Compact and trustworthy System Checks
- Mobile-friendly interface

## System Maintenance

Add a maintenance layer beside System Checks for safe, routine operating-system cleanup on managed hosts.

Initial candidates:

- detect packages removable by `apt autoremove --dry-run`;
- report APT cache usage;
- identify obsolete kernel/packages where the package manager considers removal safe;
- report journal/log usage and relevant retention state.

Design principle: **detect automatically, execute deliberately**. Checks may run periodically (for example weekly), but cleanup must only run after an explicit user action. Do not silently delete packages or logs.

Status: roadmap / scope and cadence to be designed before implementation.

## Later

- Visual identity and branding refinement
- Additional notification channels
- Practical user manual
- Carefully scoped additional firmware providers

## Device Profiles — active major direction (v0.18+)

Device Profiles are now an implemented platform capability rather than a loose idea. The core direction is declarative: profiles describe what a device is, where firmware information is found, and how the generic parser should extract it. New devices that fit existing parser capabilities should require only a profile/catalog update, not an application release. Continue incrementally: expand safe generic parser capabilities only when genuinely necessary, migrate suitable hard-coded device knowledge after parity, then add Custom Profiles, submission/review, signed catalog releases and corroborated multi-source checks. Avoid a big-bang firmware subsystem rewrite.

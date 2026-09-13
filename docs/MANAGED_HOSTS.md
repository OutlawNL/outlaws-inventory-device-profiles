# Managed hosts

Managed hosts are Inventory server items that use SSH-backed System Checks and system-update actions.

## Identities

Local Outlaw's Inventory application:

```text
outlaws-inventory
```

Remote managed host:

```text
outlaw
```

These identities are separate.

## Setup

System Check Setup uses an existing administrator/root bootstrap login only for the setup request. Credentials are not stored.

The setup process creates or repairs:

- `outlaw`;
- its authorized SSH key;
- required packages;
- restricted sudoers permissions;
- the kernel-upgrade helper used by supported system updates.

The application then validates SSH login and each required permission live.

## Reconfiguration

Use Reconfigure System Checks when the underlying server was rebuilt or its managed access was removed. Existing Inventory data and check configuration are preserved; host-side access is recreated and revalidated.

A previous failed check result is not treated as proof that current reconfiguration failed. Readiness is determined from fresh live validation.

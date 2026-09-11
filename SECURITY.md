# Security

Device Profiles are data, never executable code. Profiles must not contain scripts, shell commands, JavaScript or arbitrary templates.

Outlaw's Inventory restricts trusted profile synchronization to the configured official HTTPS catalog. Profile-driven network access is limited by core strategies; a profile cannot introduce a new network protocol or arbitrary code path.

The initial catalog manifest records SHA-256 hashes. Cryptographic signing of trusted catalog releases is planned before broad community contributions are enabled.

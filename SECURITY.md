# Security

Device Profiles are data, never executable code. Profiles must not contain scripts, shell commands, JavaScript, arbitrary templates or user-controlled code fragments.

Outlaw's Inventory implements a fixed allow-list of parser capabilities. A Device Profile may only provide declarative arguments to those capabilities: HTTPS sources, document match hints, labels, constrained regular-expression extraction patterns, date formats, section headings and validation rules.

A new device should not require new executable logic in the application core when existing capabilities are sufficient. New core code is reserved for genuinely new generic capabilities, not individual vendors or models.

Outlaw's Inventory restricts trusted profile synchronization to the configured official HTTPS catalog. The current catalog manifest records SHA-256 hashes. Cryptographic signing of trusted catalog releases is planned before broad community contributions are enabled.

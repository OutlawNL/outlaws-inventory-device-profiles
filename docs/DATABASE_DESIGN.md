# Database ownership model

Outlaw's Inventory uses tenant ownership for all user inventory data.

- `users.id` is the tenant identifier.
- `devices.owner_user_id`, `categories.owner_user_id` and `ssh_profiles.owner_user_id` identify the owner.
- `health_checks.owner_user_id` must match its linked device owner.
- `update_checks.owner_user_id` must match both its linked device and SSH profile owner.
- `attachments` inherit ownership through `device_id`.
- `devices.managed_ssh_profile_id` may only reference a profile owned by the same user.
- Usernames are stored lowercase; display names retain user-selected capitalization.
- Category and SSH profile names are unique per owner, not globally.

SQLite foreign-key enforcement is enabled on every application connection. Database triggers reject invalid or cross-user ownership links. The startup and manual Data Integrity audit checks SQLite integrity, foreign-key violations, orphans, ownership mismatches and duplicate tenant-scoped names.

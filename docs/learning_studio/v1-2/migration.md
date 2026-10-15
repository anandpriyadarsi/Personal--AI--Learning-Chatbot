# Feature-store migration and recovery

V1 user_version1 with APPLICATION_ID0x414C5331 is read without mutation. The first explicit write obtains BEGIN IMMEDIATE, rechecks the identity/version, saves a uniquely named `learning_studio.sqlite3.v1-backup-<uuid>.sqlite3` through a separate SQLite backup reader, then adds reading_events, engagement_events, indexes and immutable coverage_reports in the same writer transaction. Version2 is accepted by this branch. Foreign, future-version and symlink stores are refused. New empty stores initialize directly at version2.

Injected migration failure rolls back schema/version/history; the V1 backup remains available and a subsequent migration retry succeeds. Concurrent first writers migrate once. Every preexisting module/asset/publication/active/attempt row remains intact.

Do not downgrade a live V2 store or overwrite it with the V1 backup: that would discard newly recorded state. Retain the complete V2 database and evidence export before rollback. To inspect a V1 backup, use a separate disposable directory/checkout and copy it under the required dedicated filename; never use the production academic database. Returning to this branch with the retained V2 file preserves new state. No automatic destructive rollback is implemented.

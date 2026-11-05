-- Security fixes of November 2026. Additive and idempotent.
--
-- 1. The worker role makes no database: the restore check that needed CREATEDB (migration 0024) runs only on a machine
--    that holds the backup's private key, as the owner role, never as the worker on the production host
--    (dgate.ops.backup.verify returns before the restore without the key). Rows in, rows out, nothing else.
ALTER ROLE dgate_worker NOCREATEDB;

-- 2. A client profile remembers which account made it: a workspace member changes or deletes only its own, the owner any
--    (dgate/workspace.py `_owned_client`). Rows made before this have no author: the owner's only.
ALTER TABLE app_client ADD COLUMN IF NOT EXISTS created_by uuid REFERENCES app_user (id) ON DELETE SET NULL;

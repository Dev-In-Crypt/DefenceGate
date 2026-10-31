-- WP-161 (31 October 2026, launch-day rehearsal): the e-mail alerts of saved searches could be stopped only after signing
-- in ("Change or stop these alerts: /app/searches"). Each account gets the random part of a stop link that works without
-- signing in (two random UUIDs, 244 random bits, as association_member.unsubscribe_token): it switches that account's
-- alerts off (every saved search's cadence to 'off') and can do nothing else. Additive and idempotent.

ALTER TABLE app_user ADD COLUMN IF NOT EXISTS alerts_stop_token text NOT NULL UNIQUE
    DEFAULT replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '');
-- dgate_worker already reads app_user (0027) to address the alert mail; the stop is the API's (dgate_app).

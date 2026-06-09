-- User session command-signing public key (rotated each login).
ALTER TABLE users ADD COLUMN command_public_key text;

-- Index for daemon key-cache refresh lookups.
CREATE INDEX ON users (id) INCLUDE (command_public_key) WHERE command_public_key IS NOT NULL;

-- Pre-signed schedule authorization blobs (stored alongside the schedule).
ALTER TABLE schedules ADD COLUMN schedule_auth jsonb;

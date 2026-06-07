-- 0012 — fix env_var_refs check constraint.
-- 0010 shipped an inverted predicate: `check (secret or value_plain is null)` wrongly
-- rejected the legitimate non-secret case (secret=false, value_plain set). The intent is
-- "value_plain may be non-null ONLY when the var is not secret" → forbid (secret AND
-- value_plain IS NOT NULL), i.e. `check (not secret or value_plain is null)`.
alter table env_var_refs drop constraint if exists env_var_plain_only_when_not_secret;
alter table env_var_refs add constraint env_var_plain_only_when_not_secret
  check (not secret or value_plain is null);

\set ON_ERROR_STOP on
\i migrations/001_schema.sql
\i functions/001_hashing.sql
\i functions/002_normalization.sql
\i functions/003_review_queue.sql
\i triggers/001_audit_triggers.sql
\i views/001_views.sql
\i policies/001_rls.sql

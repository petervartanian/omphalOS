ALTER TABLE omphalos.review_queue ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'omphalos_reviewer'
  ) THEN
    CREATE ROLE omphalos_reviewer;
  END IF;
END;
$$;

DROP POLICY IF EXISTS review_queue_reviewer_select ON omphalos.review_queue;
CREATE POLICY review_queue_reviewer_select ON omphalos.review_queue
FOR SELECT TO omphalos_reviewer
USING (true);

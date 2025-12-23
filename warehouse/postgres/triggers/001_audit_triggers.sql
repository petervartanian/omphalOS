CREATE OR REPLACE FUNCTION omphalos.audit_row_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
  pk TEXT;
  action TEXT;
BEGIN
  action := TG_OP;
  pk := NULL;

  IF action = 'INSERT' THEN
    INSERT INTO omphalos.audit_event(action, table_name, row_pk, after_row, run_id)
    VALUES (action, TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME, pk, to_jsonb(NEW), coalesce(NEW.run_id, NULL));
    RETURN NEW;
  ELSIF action = 'UPDATE' THEN
    INSERT INTO omphalos.audit_event(action, table_name, row_pk, before_row, after_row, run_id)
    VALUES (action, TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME, pk, to_jsonb(OLD), to_jsonb(NEW), coalesce(NEW.run_id, coalesce(OLD.run_id, NULL)));
    RETURN NEW;
  ELSIF action = 'DELETE' THEN
    INSERT INTO omphalos.audit_event(action, table_name, row_pk, before_row, run_id)
    VALUES (action, TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME, pk, to_jsonb(OLD), coalesce(OLD.run_id, NULL));
    RETURN OLD;
  END IF;

  RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_audit_trade_feed ON omphalos.trade_feed;
CREATE TRIGGER trg_audit_trade_feed
AFTER INSERT OR UPDATE OR DELETE ON omphalos.trade_feed
FOR EACH ROW EXECUTE FUNCTION omphalos.audit_row_change();

DROP TRIGGER IF EXISTS trg_audit_registry ON omphalos.registry;
CREATE TRIGGER trg_audit_registry
AFTER INSERT OR UPDATE OR DELETE ON omphalos.registry
FOR EACH ROW EXECUTE FUNCTION omphalos.audit_row_change();

DROP TRIGGER IF EXISTS trg_audit_entity_matches ON omphalos.entity_matches;
CREATE TRIGGER trg_audit_entity_matches
AFTER INSERT OR UPDATE OR DELETE ON omphalos.entity_matches
FOR EACH ROW EXECUTE FUNCTION omphalos.audit_row_change();

DROP TRIGGER IF EXISTS trg_audit_entity_scores ON omphalos.entity_scores;
CREATE TRIGGER trg_audit_entity_scores
AFTER INSERT OR UPDATE OR DELETE ON omphalos.entity_scores
FOR EACH ROW EXECUTE FUNCTION omphalos.audit_row_change();

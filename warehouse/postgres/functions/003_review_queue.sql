CREATE OR REPLACE FUNCTION omphalos.score_severity(p_score DOUBLE PRECISION, p_value DOUBLE PRECISION)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
  s DOUBLE PRECISION;
  v DOUBLE PRECISION;
  sev INTEGER;
BEGIN
  s := coalesce(p_score, 0.0);
  v := coalesce(p_value, 0.0);
  sev := 0;
  IF s >= 0.90 THEN
    sev := sev + 5;
  ELSIF s >= 0.75 THEN
    sev := sev + 3;
  ELSIF s >= 0.60 THEN
    sev := sev + 2;
  ELSIF s >= 0.45 THEN
    sev := sev + 1;
  END IF;

  IF v >= 1000000 THEN
    sev := sev + 3;
  ELSIF v >= 250000 THEN
    sev := sev + 2;
  ELSIF v >= 50000 THEN
    sev := sev + 1;
  END IF;

  RETURN least(10, greatest(0, sev));
END;
$$;

CREATE OR REPLACE PROCEDURE omphalos.refresh_review_queue(p_run_id TEXT)
LANGUAGE plpgsql
AS $$
BEGIN
  DELETE FROM omphalos.review_queue WHERE run_id = p_run_id;

  INSERT INTO omphalos.review_queue (run_id, shipment_id, entity_id, review_status, severity, rationale)
  SELECT
    m.run_id,
    m.shipment_id,
    m.entity_id,
    CASE
      WHEN m.status = 'review' THEN 'needs_review'
      WHEN m.status = 'matched' THEN 'auto_match'
      ELSE 'unmatched'
    END AS review_status,
    omphalos.score_severity(m.score, t.value_usd) AS severity,
    coalesce(m.explanation, '')
  FROM omphalos.entity_matches m
  JOIN omphalos.trade_feed t ON t.shipment_id = m.shipment_id
  WHERE m.run_id = p_run_id
    AND m.status IN ('review', 'matched');
END;
$$;

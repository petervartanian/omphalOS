CREATE OR REPLACE FUNCTION omphalos.sha256_text(p_text TEXT)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
  v BYTEA;
BEGIN
  v := digest(coalesce(p_text, ''), 'sha256');
  RETURN encode(v, 'hex');
END;
$$;

CREATE OR REPLACE FUNCTION omphalos.sha256_jsonb(p_json JSONB)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN omphalos.sha256_text(coalesce(p_json::TEXT, 'null'));
END;
$$;

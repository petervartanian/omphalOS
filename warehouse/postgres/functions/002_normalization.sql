CREATE OR REPLACE FUNCTION omphalos.normalize_text(p_text TEXT)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
  t TEXT;
BEGIN
  t := upper(trim(coalesce(p_text, '')));
  t := regexp_replace(t, '\s+', ' ', 'g');
  RETURN nullif(t, '');
END;
$$;

CREATE OR REPLACE FUNCTION omphalos.normalize_country(p_country TEXT)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
  c TEXT;
BEGIN
  c := omphalos.normalize_text(p_country);
  IF c IS NULL THEN
    RETURN NULL;
  END IF;
  IF length(c) = 2 THEN
    RETURN c;
  END IF;
  RETURN c;
END;
$$;

CREATE OR REPLACE FUNCTION omphalos.normalize_hs(p_hs TEXT)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
  h TEXT;
BEGIN
  h := regexp_replace(coalesce(p_hs, ''), '[^0-9]', '', 'g');
  IF length(h) < 2 THEN
    RETURN NULL;
  END IF;
  RETURN h;
END;
$$;

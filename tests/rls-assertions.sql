-- Local disposable PostgreSQL tests only; do not run in your Supabase project.
SET ROLE authenticated;
SELECT set_config('request.jwt.claim.sub','11111111-1111-1111-1111-111111111111',false);
INSERT INTO public.training_logs(user_id) VALUES ('11111111-1111-1111-1111-111111111111');
DO $$ BEGIN
  BEGIN
    INSERT INTO public.training_logs(user_id) VALUES ('22222222-2222-2222-2222-222222222222');
    RAISE EXCEPTION 'FAIL: foreign user insert accepted';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
END $$;
SELECT set_config('request.jwt.claim.sub','22222222-2222-2222-2222-222222222222',false);
DO $$ BEGIN
  IF (SELECT count(*) FROM public.training_logs) <> 0 THEN RAISE EXCEPTION 'FAIL: foreign data visible'; END IF;
END $$;
INSERT INTO public.training_logs(user_id) VALUES ('22222222-2222-2222-2222-222222222222');
SELECT set_config('request.jwt.claim.sub','11111111-1111-1111-1111-111111111111',false);
DO $$ DECLARE changed integer; BEGIN
  IF (SELECT count(*) FROM public.training_logs) <> 1 THEN RAISE EXCEPTION 'FAIL: row isolation'; END IF;
  UPDATE public.training_logs SET revision=1 WHERE user_id='22222222-2222-2222-2222-222222222222';
  GET DIAGNOSTICS changed = ROW_COUNT;
  IF changed <> 0 THEN RAISE EXCEPTION 'FAIL: foreign update allowed'; END IF;
  UPDATE public.training_logs SET revision=1 WHERE user_id='11111111-1111-1111-1111-111111111111' AND revision=0;
  GET DIAGNOSTICS changed = ROW_COUNT;
  IF changed <> 1 THEN RAISE EXCEPTION 'FAIL: own update rejected'; END IF;
  UPDATE public.training_logs SET revision=1 WHERE user_id='11111111-1111-1111-1111-111111111111' AND revision=0;
  GET DIAGNOSTICS changed = ROW_COUNT;
  IF changed <> 0 THEN RAISE EXCEPTION 'FAIL: stale update accepted'; END IF;
END $$;
RESET ROLE;
SET ROLE anon;
DO $$ BEGIN
  BEGIN
    PERFORM count(*) FROM public.training_logs;
    RAISE EXCEPTION 'FAIL: anonymous read accepted';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
END $$;
RESET ROLE;
SELECT 'PASS: user isolation, own-row writes, foreign writes rejected, stale revision rejected, anonymous read rejected' AS result;

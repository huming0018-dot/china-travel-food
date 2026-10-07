begin;
-- Add optional public view_count to the existing count validation without
-- replacing any other current submit logic or changing grants/receipts.
do $migration$
declare definition text := pg_get_functiondef('public.crowd_v4_submit(uuid,bigint,uuid,jsonb)'::regprocedure);
begin
 if strpos(definition, 'key in (''like_count'',''collect_count'',''comment_count'')') = 0 then
  raise exception 'unexpected_submit_definition';
 end if;
 definition := replace(definition,
   'key in (''like_count'',''collect_count'',''comment_count'')',
   'key in (''like_count'',''collect_count'',''comment_count'',''view_count'')');
 execute definition;
end $migration$;
commit;

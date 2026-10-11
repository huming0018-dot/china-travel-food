-- Reporting is not a taste-input change. Preserve the existing trigger's scoring behavior otherwise.
create or replace function public.trg_reviews_taste()
returns trigger language plpgsql
as $$
begin
  if TG_OP='UPDATE' then
    if (to_jsonb(OLD)-'report_count') is not distinct from (to_jsonb(NEW)-'report_count') then
      return null;
    end if;
  end if;
  if TG_OP='DELETE' then
    perform public.recalc_taste_for(OLD.restaurant_id);
  else
    perform public.recalc_taste_for(NEW.restaurant_id);
  end if;
  return null;
end;
$$;


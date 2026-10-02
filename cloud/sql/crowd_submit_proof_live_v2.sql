CREATE OR REPLACE FUNCTION public.crowd_submit_proof(p_participant_id text, p_envelope jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare
  v_status      text;
  v_task_id     bigint;
  v_seq         int;
  v_sync        int;
  v_items       jsonb;
  v_item        jsonb;
  v_kind        text;
  v_note_id     text;
  v_note_url    text;
  v_title       text;
  v_excerpt     text;
  v_author      text;
  v_rating      numeric;
  v_rating_reason text;
  v_matched     text;
  v_anchor      float;
  v_raw         text;
  v_captured    timestamptz;
  v_result      jsonb := '[]'::jsonb;
  v_accepted    int := 0;
  v_rejected    text[] := '{}';
  v_task_open   boolean;
  v_new_progress int;
  v_row         jsonb;
  v_quota       int;
  v_today_used  int;
  v_reject_accum int;
  v_accept_accum int;
  v_reject_rate float;
  v_note_exists boolean;
  v_task_fulfilled boolean;
  v_dedupe      text;
begin
  select status into v_status
    from public.crowd_participants
   where participant_id = p_participant_id
   for update;
  if v_status is null or v_status in ('suspended', 'blacklisted', 'rejected') then
    return jsonb_build_object('ok', false, 'reason', 'participant_unavailable');
  end if;

  v_task_id := (p_envelope->>'task_id')::bigint;
  v_seq     := (p_envelope->>'proof_seq')::int;
  v_sync    := coalesce((p_envelope->>'sync_version')::int, 1);
  v_captured:= coalesce((p_envelope->>'captured_at')::timestamptz, now());
  v_items   := coalesce(p_envelope->'items', '[]'::jsonb);

  if v_sync <> 1 then
    return jsonb_build_object('ok', false, 'reason', 'sync_version_mismatch',
                              'expected', 1, 'got', v_sync);
  end if;
  if v_task_id is null or v_seq is null then
    return jsonb_build_object('ok', false, 'reason', 'envelope_missing_task_or_seq');
  end if;

  if coalesce(p_envelope->>'participant_id','') <> p_participant_id then
    return jsonb_build_object('ok', false, 'reason', 'participant_id_mismatch');
  end if;

  if v_captured > now() + interval '10 minutes' then
    return jsonb_build_object('ok', false, 'reason', 'captured_at_future',
                              'captured_at', v_captured, 'server_now', now());
  end if;
  if v_captured < now() - interval '7 days' then
    return jsonb_build_object('ok', false, 'reason', 'captured_at_too_old');
  end if;

  select (status = 'open') into v_task_open
    from public.crowd_tasks where task_id = v_task_id;
  if v_task_open is distinct from true then
    return jsonb_build_object('ok', false, 'reason', 'task_not_open');
  end if;

  select quota_day into v_quota
    from public.crowd_participants where participant_id = p_participant_id;
  select count(*) into v_today_used
    from public.crowd_proofs
   where participant_id = p_participant_id
     and gate_status = 'accepted'
     and created_at >= date_trunc('day', now());
  if coalesce(v_quota, 0) > 0 and v_today_used >= v_quota then
    return jsonb_build_object('ok', false, 'reason', 'quota_exceeded',
                              'quota_day', v_quota, 'used_today', v_today_used);
  end if;

  for v_item in select * from jsonb_array_elements(v_items) loop
    select (status = 'open') into v_task_fulfilled
      from public.crowd_tasks where task_id = v_task_id;
    if v_task_fulfilled is not true then
      v_rejected := v_rejected || format('item_task_fulfilled:%s', coalesce(v_item->>'note_id','?'));
      continue;
    end if;

    v_kind  := v_item->>'kind';
    v_note_id := v_item->>'note_id';
    v_note_url := v_item->>'note_url';
    v_title := left(coalesce(v_item->>'title',''), 100);
    v_excerpt := left(coalesce(v_item->>'excerpt',''), 200);
    v_author  := left(coalesce(v_item->>'author',''), 50);
    v_rating  := (v_item->>'rating')::numeric;
    v_rating_reason := left(coalesce(v_item->>'rating_reason',''), 200);
    v_matched := left(coalesce(v_item->>'matched_store',''), 100);
    v_anchor  := (v_item->>'anchor_score')::float;
    v_raw     := left(coalesce(v_item->>'raw_query',''), 50);

    if v_kind not in ('note','rating') then
      v_rejected := v_rejected || format('item_kind_invalid:%s', coalesce(v_note_id,'?'));
      continue;
    end if;
    if v_note_id is null or v_note_url is null then
      v_rejected := v_rejected || format('item_missing_note:%s', coalesce(v_note_id,'?'));
      continue;
    end if;

    if v_note_url !~ '^https://www\.xiaohongshu\.com/explore/[0-9a-f]{24}(\?.*)?$'
       and v_note_url !~ '^https://www\.xiaohongshu\.com/discovery/item/[0-9a-f]{24}(\?.*)?$' then
      v_rejected := v_rejected || format('item_url_invalid:%s', coalesce(v_note_id,'?'));
      continue;
    end if;

    if v_note_id !~ '^[0-9a-f]{24}$' then
      v_rejected := v_rejected || format('item_note_id_invalid:%s', coalesce(v_note_id,'?'));
      continue;
    end if;

    if coalesce(length(regexp_replace(v_title, '[\s[:punct:]]', '', 'g')), 0) < 2 then
      v_rejected := v_rejected || format('item_title_too_short:%s', v_note_id);
      continue;
    end if;

    if v_kind = 'rating' then
      if v_rating is null or v_rating < 1 or v_rating > 5 then
        v_rejected := v_rejected || format('item_rating_out_of_range:%s', v_note_id);
        continue;
      end if;
      if coalesce(length(regexp_replace(v_rating_reason, '[\s[:punct:]]', '', 'g')), 0) < 8 then
        v_rejected := v_rejected || format('item_rating_reason_too_short:%s', v_note_id);
        continue;
      end if;
      select exists (
        select 1 from public.crowd_proofs
         where note_id = v_note_id and gate_status = 'accepted'
      ) into v_note_exists;
      if v_note_exists is not true then
        v_rejected := v_rejected || format('item_rating_no_anchor:%s', v_note_id);
        continue;
      end if;
      -- rating 去重键：参与者+笔记（每人每笔记最多一条评分，跨参与者可并存）
      v_dedupe := md5(p_participant_id || ':r:' || v_note_id);
    else
      -- note 去重键：归一化标题（全局唯一，防同内容刷量）
      v_dedupe := md5('n:' || lower(regexp_replace(
        regexp_replace(v_title, '[\s[:punct:]]', '', 'g'),
        '[^a-z0-9一-龥]', '', 'g')));
    end if;

    if coalesce(v_quota, 0) > 0 and (v_today_used + v_accepted) >= v_quota then
      v_rejected := v_rejected || format('item_quota_exceeded:%s', coalesce(v_note_id,'?'));
      continue;
    end if;

    begin
      insert into public.crowd_proofs
        (participant_id, task_id, proof_seq, captured_at, sync_version,
         kind, note_id, note_url, title, excerpt, author,
         rating, rating_reason, matched_store, anchor_score, raw_query,
         gate_status, dedupe_key)
      values
        (p_participant_id, v_task_id, v_seq, v_captured, v_sync,
         v_kind, v_note_id, v_note_url, v_title, v_excerpt, v_author,
         v_rating, v_rating_reason, v_matched, v_anchor, v_raw,
         'accepted', v_dedupe)
      on conflict (participant_id, task_id, proof_seq, note_id) do nothing;
      if found then
        v_accepted := v_accepted + 1;
        v_row := jsonb_build_object('note_id', v_note_id, 'gate', 'accepted');
      else
        v_row := jsonb_build_object('note_id', v_note_id, 'gate', 'duplicate_skipped');
      end if;
    exception
      when unique_violation then
        v_row := jsonb_build_object('note_id', v_note_id, 'gate', 'duplicate_skipped');
      when others then
        v_row := jsonb_build_object('note_id', v_note_id, 'gate', 'error', 'msg', SQLERRM);
    end;
    v_result := v_result || v_row;
  end loop;

  if v_accepted > 0 then
    update public.crowd_tasks
       set progress = progress + v_accepted,
           status = case when progress + v_accepted >= kpi_min then 'fulfilled' else status end,
           updated_at = now()
     where task_id = v_task_id;
    update public.crowd_participants
       set total_effective = total_effective + v_accepted,
           last_active_at = now()
     where participant_id = p_participant_id;
  end if;

  select coalesce(sum(case when gate_status='accepted' then 1 else 0 end),0),
         coalesce(sum(case when gate_status='rejected' then 1 else 0 end),0)
    into v_accept_accum, v_reject_accum
    from public.crowd_proofs
   where participant_id = p_participant_id;
  if (v_accept_accum + v_reject_accum) > 20 then
    v_reject_rate := v_reject_accum::float / (v_accept_accum + v_reject_accum);
    if v_reject_rate > 0.6 then
      update public.crowd_participants
         set status = 'suspended', review_note = 'auto_suspend: reject_rate ' || round(v_reject_rate::numeric,2)
       where participant_id = p_participant_id;
    else
      update public.crowd_participants
         set reject_rate = v_reject_rate
       where participant_id = p_participant_id;
    end if;
  end if;

  select progress into v_new_progress from public.crowd_tasks where task_id = v_task_id;

  return jsonb_build_object(
    'ok', true,
    'accepted', v_accepted,
    'rejected', v_rejected,
    'results', v_result,
    'new_progress', coalesce(v_new_progress, 0)
  );
end;
$function$

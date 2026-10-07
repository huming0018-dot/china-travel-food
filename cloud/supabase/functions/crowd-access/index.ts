import { createClient } from 'npm:@supabase/supabase-js@2.39.8';
import { handleAccess } from './core.mjs';

const configuration = __CROWD_ACCESS_CONFIGURATION__;
const operatorHash = '__CROWD_OPERATOR_SHA256__';
const backend = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!, { auth: { persistSession: false, autoRefreshToken: false } });
// Public enrollment is authorized by an unexpired invitation and reserved
// installation identity. Publisher actions require the separate owner key.
Deno.serve(request => handleAccess(request, backend, configuration, operatorHash));

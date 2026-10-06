import { createClient } from 'npm:@supabase/supabase-js@2.39.8';
import { handle } from './core.mjs';

// Only a one-way hash is substituted into the deployment payload. The actual
// random gateway key stays in the publisher's private runtime configuration.
const expectedHash = Deno.env.get('CROWD_GATEWAY_TOKEN_SHA256') || '__CROWD_GATEWAY_TOKEN_SHA256__';
const backend = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!, { auth: { persistSession: false, autoRefreshToken: false } });
Deno.serve(request => handle(request, backend, expectedHash));

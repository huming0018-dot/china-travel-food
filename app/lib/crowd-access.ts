export function privateBackendConfigured() {
  return !!(process.env.CROWD_GATEWAY_TOKEN || process.env.SUPABASE_SERVICE_ROLE_KEY);
}

export async function accessRequest(route: 'manifest' | 'invite' | 'enroll' | 'operations', body?: object, authorization?: string) {
  const base = new URL(process.env.NEXT_PUBLIC_SUPABASE_URL!);
  if (base.protocol !== 'https:' || !base.hostname.endsWith('.supabase.co') || base.username || base.password || base.pathname !== '/') throw new Error('backend_not_configured');
  const response = await fetch(base.origin + '/functions/v1/crowd-access/' + route, {
    method: body ? 'POST' : 'GET', redirect: 'error', signal: AbortSignal.timeout(20000), cache: 'no-store',
    headers: { 'Content-Type': 'application/json', apikey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!, ...(authorization ? { Authorization: authorization } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const result = await response.json();
  if (!response.ok || result.error) {
    const allowed = ['operator_required','invalid_request','release_not_ready','invalid_invite','invite_expired','invite_full','installation_already_joined','consent_required'];
    throw new Error(allowed.includes(result.error) ? result.error : 'backend_unavailable');
  }
  return result;
}

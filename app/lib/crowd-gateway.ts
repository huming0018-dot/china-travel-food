type Reservation = { token_hash: string; device_hash: string; platform: string };
type RPCArgs = { p_action: string; p_payload: Record<string, unknown> };
type ErrorResult = { message: string } | null;
type GatewayResult = { data: any; error: ErrorResult };

export function gatewayClient(projectURL: string, publicKey: string, key: string) {
  const base = new URL(projectURL);
  if (base.protocol !== 'https:' || !base.hostname.endsWith('.supabase.co') || base.pathname !== '/' || base.username || base.password || base.search || base.hash || !/^[a-f0-9]{64}$/.test(key) || !(publicKey.startsWith('eyJ') || publicKey.startsWith('sb_publishable_'))) throw new Error('backend_not_configured');
  const url = base.origin + '/functions/v1/crowd-gateway';
  let reservation: Reservation | undefined;
  async function call(input: object): Promise<GatewayResult> {
    try {
      const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', apikey: publicKey, Authorization: 'Bearer ' + publicKey, 'X-Crowd-Gateway-Key': key }, body: JSON.stringify(input), signal: AbortSignal.timeout(20000), redirect: 'error' });
      const result = await response.json();
      if (!response.ok || !result || typeof result !== 'object' || !('data' in result) || !('error' in result)) return { data: null, error: { message: 'backend_unavailable' } };
      return result;
    } catch { return { data: null, error: { message: 'backend_unavailable' } }; }
  }
  return {
    rpc: async (name: string, args: RPCArgs) => {
      const result = await call({ action: 'rpc', name, args });
      if (name === 'crowd_v4_invite' && args.p_action === 'reserve' && !result.error && result.data?.user_id) reservation = args.p_payload as Reservation;
      return result;
    },
    auth: { admin: {
      getUserById: async (id: string) => {
        const result = await call({ action: 'auth_read', id, reservation });
        return { data: { user: result.data?.user || null }, error: result.error };
      },
      createUser: async (user: { id?: string; password?: string; email?: string; email_confirm?: boolean; app_metadata?: object }) => {
        const result = await call({ action: 'auth_create', id: user.id, password: user.password, reservation });
        return { data: { user: result.data?.user || null }, error: result.error };
      }
    } }
  };
}

import { digest, installationUser } from '../crowd-gateway/core.mjs';

const hex = x => typeof x === 'string' && /^[a-f0-9]{64}$/.test(x);
const json = (value, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff' } });
const known = ['invalid_invite','invite_expired','invite_full','installation_already_joined','consent_required'];
async function rpc(backend, action, payload, name = 'crowd_v4_invite') {
  const result = await backend.rpc(name, { p_action: action, p_payload: payload });
  if (result.error) throw new Error(known.includes(result.error.message) ? result.error.message : 'backend_unavailable');
  return result.data;
}
async function read(request) {
  if (request.headers.get('Content-Type')?.split(';')[0] !== 'application/json') throw new Error('invalid_request');
  const reader = request.body?.getReader(); if (!reader) throw new Error('invalid_request');
  const chunks = []; let size = 0;
  try {
    for (;;) { const {value,done}=await reader.read(); if(done)break; size+=value.length; if(size>4096)throw new Error('invalid_request'); chunks.push(value); }
  } finally { await reader.cancel(); reader.releaseLock(); }
  const bytes = new Uint8Array(size); let offset=0;
  for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
  const value=JSON.parse(new TextDecoder().decode(bytes));
  if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('invalid_request');
  return value;
}
function available(configuration) {
  const output = {};
  for (const [platform, release] of Object.entries(configuration.releases || {})) {
    if (!['android','ios','harmony','windows','macos'].includes(platform) || release.verified !== true || !/^4\.\d+\.\d+$/.test(release.version)) continue;
    const url = new URL(release.url);
    if (url.protocol !== 'https:' || url.username || url.password) continue;
    if (['android','windows','macos'].includes(platform) && ['apk','desktop'].includes(release.channel)) {
      if (url.origin !== configuration.origin || !url.pathname.startsWith('/crowd/releases/') || !hex(release.sha256) || url.search || url.hash) continue;
      if (platform === 'android' && (release.channel !== 'apk' || url.pathname !== '/crowd/releases/crowd-android-v'+release.version+'-debug.apk')) continue;
      if (platform !== 'android' && release.channel !== 'desktop') continue;
    } else if (['windows','macos'].includes(platform) && release.channel === 'extension') {
      if (!/^[a-p]{32}$/.test(release.extension_id || '') || !['chromewebstore.google.com','microsoftedge.microsoft.com'].includes(url.hostname)) continue;
    } else if (platform === 'ios') {
      if (!((release.channel === 'testflight' && url.hostname === 'testflight.apple.com') || (release.channel === 'appstore' && url.hostname === 'apps.apple.com'))) continue;
    } else if (platform === 'harmony') {
      if (release.channel !== 'appgallery' || url.hostname !== 'appgallery.huawei.com') continue;
    } else continue;
    output[platform] = release;
  }
  return output;
}

export async function handleAccess(request, backend, configuration, operatorHash) {
  const suppliedOrigin=request.headers.get('Origin');
  const allowed=[configuration.origin, ...(configuration.previewOrigins || []), 'https://crowd.local','null'];
  if(suppliedOrigin && !allowed.includes(suppliedOrigin))return json({error:'origin_denied'},403);
  let response;
  try {
    const route=new URL(request.url).pathname.split('/').pop();
    if(request.method==='OPTIONS')response=new Response(null,{status:204});
    else if(route==='manifest' && request.method==='GET') {
      await rpc(backend,'list',{});
      const releases=available(configuration);
      response=json({origin:configuration.origin,releases,ready:Object.keys(releases).length>0});
    } else {
      if(request.method!=='POST')return json({error:'method_not_allowed'},405);
      if(!['invite','enroll','operations'].includes(route))return json({error:'invalid_request'},400);
      // Publisher operations require the independently generated owner key.
      // No Supabase administrator credential is ever sent to the website.
      if(route!=='enroll') {
        const key=(request.headers.get('Authorization')||'').replace(/^Bearer /,'');
        if(!hex(key)||!hex(operatorHash)||await digest(key)!==operatorHash)throw new Error('operator_required');
      }
      const input=await read(request);
      if(route==='operations') {
        const {action,payload={}}=input;
        if(!['publish','review','list','export'].includes(action)||!payload||typeof payload!=='object'||Array.isArray(payload))throw new Error('invalid_request');
        const data=await rpc(backend,action,payload,'crowd_v4_admin');
        response=json({data});
      } else if(route==='invite') {
        const {action='create',invite,max_people=100,quota_day=20,days=7}=input;
        if(action==='revoke') {
          if(!hex(invite))throw new Error('invalid_request');
          response=json(await rpc(backend,'revoke',{token_hash:await digest(invite)}));
        } else {
          if(action!=='create'||!Number.isInteger(max_people)||max_people<1||max_people>500||!Number.isInteger(quota_day)||quota_day<1||quota_day>60||!Number.isInteger(days)||days<1||days>90)throw new Error('invalid_request');
          if(!Object.keys(available(configuration)).length)throw new Error('release_not_ready');
          const invite=Array.from(crypto.getRandomValues(new Uint8Array(32)),x=>x.toString(16).padStart(2,'0')).join('');
          const expires_at=new Date(Date.now()+days*86400000).toISOString();
          await rpc(backend,'create',{token_hash:await digest(invite),max_people,quota_day,expires_at});
          response=json({link:configuration.origin+'/crowd#invite='+invite,expires_at,max_people,quota_day});
        }
      } else {
        const {invite,install_secret,consent,platform}=input;
        if(!hex(invite)||!hex(install_secret)||!['android','ios','harmony','windows','macos'].includes(platform))throw new Error('invalid_request');
        if(consent!=='crowd-public-v4')throw new Error('consent_required');
        if(!available(configuration)[platform])throw new Error('release_not_ready');
        const reservation={token_hash:await digest(invite),device_hash:await digest(install_secret),platform};
        const allocation=await rpc(backend,'reserve',reservation);
        let account=await installationUser(backend,{action:'auth_read',id:allocation.user_id,reservation});
        let result=await account.json();
        if(result.error?.message==='account_not_ready') {
          account=await installationUser(backend,{action:'auth_create',id:allocation.user_id,password:'Cr4!'+install_secret,reservation});result=await account.json();
        }
        if(result.error||!result.data?.user)throw new Error('backend_unavailable');
        await rpc(backend,'complete',{...reservation,consent});
        response=json({email:result.data.user.email,joined:true});
      }
    }
  } catch(error) {
    const safe=['operator_required','invalid_request','release_not_ready',...known];
    const message=safe.includes(error.message)?error.message:'backend_unavailable';
    response=json({error:message},message==='operator_required'?403:safe.includes(message)?400:503);
  }
  if(suppliedOrigin){response.headers.set('Access-Control-Allow-Origin',suppliedOrigin);response.headers.set('Vary','Origin');}
  response.headers.set('Access-Control-Allow-Methods','POST, GET, OPTIONS');response.headers.set('Access-Control-Allow-Headers','Content-Type, Authorization, apikey');
  return response;
}

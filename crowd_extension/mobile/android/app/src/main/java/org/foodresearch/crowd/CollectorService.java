package org.foodresearch.crowd;

import android.app.*;
import android.content.*;
import android.content.pm.ServiceInfo;
import android.os.*;
import android.security.keystore.*;
import android.webkit.*;
import android.net.Uri;
import android.util.Base64;
import org.json.*;
import javax.crypto.*;
import javax.crypto.spec.GCMParameterSpec;
import java.security.KeyStore;
import java.nio.charset.StandardCharsets;

public class CollectorService extends Service {
    private static boolean isPublicPage(Uri u) {
        return u != null && "https".equals(u.getScheme()) && u.getUserInfo() == null
            && (u.getPort() == -1 || u.getPort() == 443)
            && ("www.xiaohongshu.com".equals(u.getHost()) || "m.xiaohongshu.com".equals(u.getHost()));
    }
    public static CollectorService instance;
    public WebView control, browser;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Binder binder = new LocalBinder();
    private Runnable wake;
    private boolean running = false;
    private final Runnable expiry = () -> { control.evaluateJavascript("CrowdNative.suspend()", null); endBatch(); };
    public class LocalBinder extends Binder { public CollectorService getService() { return CollectorService.this; } }
    @Override public IBinder onBind(Intent intent) { return binder; }
    @Override public void onCreate() {
        super.onCreate(); instance = this;
        control = new WebView(this); browser = new WebView(this);
        control.getSettings().setJavaScriptEnabled(true);
        control.getSettings().setDomStorageEnabled(true);
        // Never allow a remote page to navigate into the credential-bearing context.
        control.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                return !"https://crowd.local/controller.html".equals(req.getUrl().toString());
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest req) {
                Uri u=req.getUrl(); if(!"crowd.local".equals(u.getHost())) return null;
                String name=u.getPath().substring(1);
                if(!name.matches("[a-z-]+\\.(html|js|css)")) return new WebResourceResponse("text/plain","UTF-8",new java.io.ByteArrayInputStream(new byte[0]));
                try { return new WebResourceResponse(name.endsWith(".js")?"application/javascript":name.endsWith(".css")?"text/css":"text/html","UTF-8",getAssets().open(name)); }
                catch(Exception e){return new WebResourceResponse("text/plain","UTF-8",new java.io.ByteArrayInputStream(new byte[0]));}
            }
        });
        control.addJavascriptInterface(new Host(), "CrowdHost");
        browser.getSettings().setJavaScriptEnabled(true); browser.getSettings().setDomStorageEnabled(true);
        browser.getSettings().setAllowFileAccess(false); browser.getSettings().setAllowContentAccess(false);
        CookieManager.getInstance().setAcceptCookie(true);
        browser.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                return !isPublicPage(req.getUrl());
            }
            @Override public void onPageFinished(WebView view, String url) { if (running) control.evaluateJavascript("CrowdNative.wake()", null); }
        });
        control.loadUrl("https://crowd.local/controller.html");
        browser.loadUrl("https://www.xiaohongshu.com");
    }
    @Override public int onStartCommand(Intent intent, int flags, int startId) { return START_NOT_STICKY; }
    public void receiveInvite(Uri uri) {
        if(!"foodcrowd".equals(uri.getScheme()) || !"join".equals(uri.getHost()))return;
        String fragment=uri.getFragment(); if(fragment==null || !fragment.matches("invite=[a-f0-9]{64}"))return;
        try {
            put("pending_invite",fragment.substring(7));
            control.evaluateJavascript("window.dispatchEvent(new Event('crowd_invite'))",null);
        } catch(Exception e){android.widget.Toast.makeText(this,"邀请暂未保存，请重新打开邀请链接",android.widget.Toast.LENGTH_LONG).show();}
    }
    private void beginBatch() {
        if (running) return;
        // Explicit UI start only; no boot receivers or silent foreground service launch.
        startForegroundService(new Intent(this, CollectorService.class));
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel("collect", "自愿公开笔记采集", NotificationManager.IMPORTANCE_LOW));
        PendingIntent open = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class), PendingIntent.FLAG_IMMUTABLE);
        PendingIntent stop = PendingIntent.getActivity(this, 1, new Intent(this, MainActivity.class).putExtra("stop", true), PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification note = new Notification.Builder(this,"collect").setSmallIcon(android.R.drawable.ic_menu_info_details).setContentTitle("众包采集中")
          .setContentText("自动搜索公开笔记；15 分钟后保存并暂停").setContentIntent(open).addAction(new Notification.Action.Builder(null,"停止",stop).build()).setOngoing(true).build();
        if (Build.VERSION.SDK_INT >= 29) startForeground(4,note,ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC); else startForeground(4,note);
        running=true; handler.postDelayed(expiry, 15*60*1000);
    }
    private void endBatch() { running=false; handler.removeCallbacks(expiry); if(wake!=null) handler.removeCallbacks(wake); stopForeground(STOP_FOREGROUND_REMOVE); stopSelf(); }
    @Override public void onTimeout(int startId, int fgsType) { control.evaluateJavascript("CrowdNative.suspend()",null); endBatch(); }
    @Override public void onDestroy() { handler.removeCallbacksAndMessages(null); control.destroy(); browser.destroy(); instance=null; super.onDestroy(); }
    private String asset(String name) throws Exception { try(var in=getAssets().open(name)) { var out=new java.io.ByteArrayOutputStream(); byte[] buffer=new byte[8192]; int n; while((n=in.read(buffer))!=-1) out.write(buffer,0,n); return out.toString("UTF-8"); } }
    private SecretKey key() throws Exception {
        KeyStore ks=KeyStore.getInstance("AndroidKeyStore"); ks.load(null);
        if(!ks.containsAlias("crowd-state")) {
            KeyGenerator kg=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");
            kg.init(new KeyGenParameterSpec.Builder("crowd-state",KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build()); kg.generateKey();
        }
        return (SecretKey)ks.getKey("crowd-state",null);
    }
    private void put(String keyName,Object value) throws Exception {
        // ponytail: encrypted preferences, at most 20 rejected records; SQLite if that ceiling grows.
        Cipher c=Cipher.getInstance("AES/GCM/NoPadding"); c.init(Cipher.ENCRYPT_MODE,key());
        String json=new JSONArray().put(value).toString(); json=json.substring(1,json.length()-1);
        String encoded=Base64.encodeToString(c.getIV(),Base64.NO_WRAP)+":"+Base64.encodeToString(c.doFinal(json.getBytes(StandardCharsets.UTF_8)),Base64.NO_WRAP);
        if(!getSharedPreferences("state",MODE_PRIVATE).edit().putString(keyName,encoded).commit()) throw new Exception("storage_failed");
    }
    private Object get(String keyName) throws Exception {
        String value=getSharedPreferences("state",MODE_PRIVATE).getString(keyName,null); if(value==null) return JSONObject.NULL;
        String[] parts=value.split(":",2); Cipher c=Cipher.getInstance("AES/GCM/NoPadding");
        c.init(Cipher.DECRYPT_MODE,key(),new GCMParameterSpec(128,Base64.decode(parts[0],Base64.NO_WRAP)));
        return new JSONTokener(new String(c.doFinal(Base64.decode(parts[1],Base64.NO_WRAP)),StandardCharsets.UTF_8)).nextValue();
    }
    private void reply(String id,Object data,String error) {
        try { JSONObject r=new JSONObject().put("ok",error==null); if(error==null) r.put("data",data==null?JSONObject.NULL:data); else r.put("error",error);
          control.evaluateJavascript("CrowdBridgeReply("+JSONObject.quote(id)+","+r+")",null);
        } catch(Exception e) { android.util.Log.e("Crowd","bridge reply failed"); }
    }
    public class Host {
        @JavascriptInterface public void postMessage(String message) {
            handler.post(() -> {
                String id="";
                try {
                    JSONObject m=new JSONObject(message); id=m.getString("id"); JSONObject p=m.getJSONObject("params");
                    switch(m.getString("method")) {
                      case "get": reply(id,get(p.getString("key")),null); return;
                      case "set": put(p.getString("key"),p.get("value")); break;
                      case "begin": beginBatch(); break;
                      case "background": reply(id,new JSONObject().put("collect_allowed",running),null); return;
                      case "end": endBatch(); break;
                      case "schedule": {
                        if(wake!=null) handler.removeCallbacks(wake);
                        wake=()->{ if(running) control.evaluateJavascript("CrowdNative.wake()",null); };
                        if(running) handler.postDelayed(wake,Math.max(1000,p.getLong("when")-System.currentTimeMillis())); break;
                      }
                      case "cancel": if(wake!=null) handler.removeCallbacks(wake); break;
                      case "open": {
                        Uri u=Uri.parse(p.getString("url"));
                        if(!isPublicPage(u)) throw new Exception("unsupported_origin");
                        browser.loadUrl(u.toString()); break;
                      }
                      case "probe": {
                        String action=p.getString("action"), callback=id;
                        if(!isPublicPage(Uri.parse(browser.getUrl()))) { reply(id,new JSONObject().put("ready",false),null); return; }
                        browser.evaluateJavascript(asset("core.js")+asset("content.js")+";JSON.stringify(CrowdPage.probe("+JSONObject.quote(action)+"))",value->{
                            try { Object json=new JSONTokener(value).nextValue(); reply(callback,new JSONObject((String)json),null); }
                            catch(Exception e){ reply(callback,new JSONObject(),"page_not_ready"); }
                        }); return;
                      }
                      case "close": browser.loadUrl("about:blank"); break;
                      case "showBrowser": browser.loadUrl("https://www.xiaohongshu.com"); if(MainActivity.instance!=null) MainActivity.instance.showBrowser(); break;
                      case "export": if(MainActivity.instance==null) throw new Exception("open_app_to_export"); MainActivity.instance.export(p.getString("text")); break;
                      default: throw new Exception("unknown_method");
                    }
                    reply(id,JSONObject.NULL,null);
                } catch(Exception e) { reply(id,null,e.getMessage()); }
            });
        }
    }
}

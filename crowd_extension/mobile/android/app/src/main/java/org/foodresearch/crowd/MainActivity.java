package org.foodresearch.crowd;
import android.app.*;
import android.os.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.view.*;
import android.webkit.WebView;
import android.widget.*;
import java.nio.charset.StandardCharsets;

public class MainActivity extends Activity {
    public static MainActivity instance;
    private CollectorService service;
    private LinearLayout layout;
    private String exportText;
    private boolean connected;
    private final ServiceConnection connection=new ServiceConnection() {
        @Override public void onServiceConnected(ComponentName name, IBinder binder) {
            connected=true; service=((CollectorService.LocalBinder)binder).getService();
            attach(service.control,2); attach(service.browser,1); handleStop(getIntent());
        }
        @Override public void onServiceDisconnected(ComponentName name) { connected=false; service=null; }
    };
    private void attach(WebView view,int weight) { if(view.getParent()!=null) ((ViewGroup)view.getParent()).removeView(view); layout.addView(view,new LinearLayout.LayoutParams(-1,0,weight)); }
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved); instance=this; layout=new LinearLayout(this); layout.setOrientation(LinearLayout.VERTICAL); setContentView(layout);
        if(Build.VERSION.SDK_INT>=33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS")!=PackageManager.PERMISSION_GRANTED) requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"},1);
        bindService(new Intent(this,CollectorService.class),connection,BIND_AUTO_CREATE);
    }
    @Override public void onNewIntent(Intent intent) { super.onNewIntent(intent); setIntent(intent); handleStop(intent); }
    private void handleStop(Intent intent) {
        if(service==null)return;
        if(intent.getData()!=null)service.receiveInvite(intent.getData());
        if(intent.getBooleanExtra("stop",false))service.control.evaluateJavascript("CrowdNative.command('stop',{})",null);
    }
    public void showBrowser() { if(service!=null) { service.browser.requestFocus(); Toast.makeText(this,"在下方网页登录或处理验证",Toast.LENGTH_LONG).show(); } }
    public void export(String text) { exportText=text; Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT).setType("application/json").putExtra(Intent.EXTRA_TITLE,"crowd-pending-evidence.json").addCategory(Intent.CATEGORY_OPENABLE); startActivityForResult(intent,10); }
    @Override public void onActivityResult(int request,int result,Intent data) {
        super.onActivityResult(request,result,data);
        if(request==10 && result==RESULT_OK && data!=null && exportText!=null) {
            try(var out=getContentResolver().openOutputStream(data.getData())) { out.write(exportText.getBytes(StandardCharsets.UTF_8)); }
            catch(Exception e){Toast.makeText(this,"导出失败，证据仍在本机",Toast.LENGTH_LONG).show();}
        }
        exportText=null;
    }
    @Override public void onDestroy() { if(connected){layout.removeAllViews();unbindService(connection);} instance=null; super.onDestroy(); }
}

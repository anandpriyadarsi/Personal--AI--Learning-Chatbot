package in.anvaya.privateapp;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.*;
import android.widget.*;
import android.view.ViewGroup;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import java.io.ByteArrayInputStream;
import java.util.List;
import com.chaquo.python.PyObject;

public class MainActivity extends Activity {
    private WebView web;
    private LocalOrigin allowed;
    private ValueCallback<Uri[]> fileCallback;
    private static final int PICK_FILES = 41;
    private static final int SAVE_FILE = 42;
    private static final int VIEW_PDF = 43;
    private boolean documentBusy;
    private String viewerBrowserUrl;
    private String downloadUrl;
    private String downloadCookie;
    private String origin;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        // Screen captures are intentionally allowed for the owner's study and feedback.
        // Keep WebView, origin, capability-cookie and app-private storage protections.
        LinearLayout splash = new LinearLayout(this);
        splash.setGravity(android.view.Gravity.CENTER);
        splash.setOrientation(LinearLayout.VERTICAL);
        splash.setBackgroundColor(Color.rgb(11,15,20));
        ImageView logo = new ImageView(this); logo.setImageResource(in.anvaya.privateapp.R.drawable.anvaya_icon);
        splash.addView(logo, new LinearLayout.LayoutParams(160,160));
        TextView label = new TextView(this);
        label.setText("ANVAYA\nPersonal Learning Intelligence");
        label.setTextColor(Color.WHITE); label.setTextSize(19); label.setGravity(17);
        splash.addView(label); setContentView(splash);
        new Thread(() -> {
            try {
                if (!Python.isStarted()) Python.start(new AndroidPlatform(getApplicationContext()));
                List<PyObject> runtime = Python.getInstance().getModule("personal_learning_assistant.android_runtime")
                    .callAttr("launch", getFilesDir().getCanonicalPath()).asList();
                String address = runtime.get(0).toString();
                String token = runtime.get(1).toString();
                runOnUiThread(() -> openWorkspace(address, token));
            } catch (Exception error) {
                runOnUiThread(() -> { label.setText("ANVAYA could not open. Your saved data has been kept.\nClose and reopen the app."); });
                // Never log Python exceptions with academic paths/content to logcat.
            }
        }, "anvaya-launch").start();
    }

    @SuppressWarnings("deprecation")
    private void openWorkspace(String address, String token) {
        if (isFinishing() || isDestroyed()) return;
        origin = address; allowed = new LocalOrigin(origin);
        web = new WebView(this);
        web.setBackgroundColor(Color.rgb(11,15,20));
        WebView.setWebContentsDebuggingEnabled(false);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        // SAF supplies only user-selected content URIs. File access stays disabled.
        settings.setAllowContentAccess(true);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setSupportMultipleWindows(false);
        // The backend marks only bundled CSS/JS/images cacheable. Dynamic student
        // pages, source files and backups remain Cache-Control: no-store.
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setMediaPlaybackRequiresUserGesture(true);
        CookieManager cookies = CookieManager.getInstance();
        cookies.setAcceptCookie(true);
        cookies.setAcceptThirdPartyCookies(web, false);
        cookies.removeAllCookies(removed -> cookies.setCookie(origin,
            "anvaya_native="+token+"; Path=/; HttpOnly; SameSite=Strict", ok -> {
                setContentView(web);
                web.loadUrl(origin+"/");
            }));
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                if (allowed.permits(req.getUrl().toString()) && req.isForMainFrame()
                    && "/mobile/restart".equals(req.getUrl().getPath()) && req.hasGesture()) {
                    new AlertDialog.Builder(MainActivity.this).setTitle("Close ANVAYA?")
                        .setMessage("Save or pause your work first. Reopen the app icon after closing to apply a staged restore.")
                        .setNegativeButton("Keep studying", null)
                        .setPositiveButton("Close app", (dialog,which) -> {
                            finishAffinity(); android.os.Process.killProcess(android.os.Process.myPid());
                        }).show();
                    return true;
                }
                String address=req.getUrl().toString();
                if(req.isForMainFrame() && NativeDocumentRequest.parse(origin,address)!=null) {
                    if(req.hasGesture()) openNativeDocument(address);
                    return true;
                }
                return !allowed.permits(address);
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest req) {
                if (allowed.permits(req.getUrl().toString())) return null;
                return new WebResourceResponse("text/plain", "UTF-8",403,"Blocked", java.util.Collections.emptyMap(),
                    new ByteArrayInputStream("External requests are disabled.".getBytes()));
            }
        });
        web.setDownloadListener((url, agent, disposition, mime, length) -> {
            if (!allowed.permits(url)) return;
            if(openNativeDocument(url))return;
            DownloadSpec spec=DownloadSpec.from(URLUtil.guessFileName(url,disposition,mime),mime);
            downloadUrl=url; downloadCookie=CookieManager.getInstance().getCookie(url);
            Intent save=new Intent(Intent.ACTION_CREATE_DOCUMENT);
            save.addCategory(Intent.CATEGORY_OPENABLE);
            save.setType(spec.mime);
            save.putExtra(Intent.EXTRA_TITLE,spec.name);
            startActivityForResult(save,SAVE_FILE);
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback,
                                                       FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                Intent pick = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                pick.addCategory(Intent.CATEGORY_OPENABLE);
                pick.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                // Honor the requested MIME for PDF and other explicit import forms.
                // Every returned URI is still validated before handing it to WebView.
                String[] types = params.getAcceptTypes();
                String mime = "*/*";
                if (types != null && types.length == 1 && types[0] != null
                    && types[0].contains("/") && !types[0].contains(",")) {
                    mime = types[0];
                }
                pick.setType(mime);
                pick.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, params.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE);
                try { startActivityForResult(pick, PICK_FILES); }
                catch (android.content.ActivityNotFoundException e) { fileCallback.onReceiveValue(null); fileCallback=null; }
                return true;
            }
        });
    }
    private boolean openNativeDocument(String address) {
        NativeDocumentRequest request=NativeDocumentRequest.parse(origin,address);
        if(request==null)return false;
        if(documentBusy)return true;
        documentBusy=true;
        final String cookie=CookieManager.getInstance().getCookie(origin);
        new Thread(()->{
            java.net.HttpURLConnection connection=null;
            try {
                java.io.File directory=new java.io.File(getCacheDir(),"shared-originals");directory.mkdirs();
                // Only old, explicit share/view copies are removed; originals live in filesDir.
                java.io.File[] old=directory.listFiles();
                if(old!=null)for(java.io.File folder:old)if(folder.isDirectory()&&System.currentTimeMillis()-folder.lastModified()>86400000L){
                    java.io.File[] files=folder.listFiles();if(files!=null)for(java.io.File file:files)file.delete();folder.delete();
                }
                connection=(java.net.HttpURLConnection)new java.net.URL(request.originalAddress).openConnection();
                connection.setInstanceFollowRedirects(false);connection.setConnectTimeout(10000);connection.setReadTimeout(30000);
                connection.setRequestProperty("Cookie",cookie);
                if(connection.getResponseCode()!=200)throw new java.io.IOException("Original unavailable");
                String mime=connection.getContentType();
                if(!"application/pdf".equals(mime)&&!"application/vnd.ms-powerpoint".equals(mime)&&
                   !"application/vnd.openxmlformats-officedocument.presentationml.presentation".equals(mime))throw new java.io.IOException("Unsupported original");
                DownloadSpec spec=DownloadSpec.from(URLUtil.guessFileName(address,connection.getHeaderField("Content-Disposition"),mime),mime);
                java.io.File folder=new java.io.File(directory,java.util.UUID.randomUUID().toString());folder.mkdir();
                java.io.File original=new java.io.File(folder,spec.name);
                try(java.io.InputStream input=connection.getInputStream();java.io.FileOutputStream output=new java.io.FileOutputStream(original)){
                    byte[] buffer=new byte[32768];int n;long total=0;
                    while((n=input.read(buffer))!=-1){total+=n;if(total>100L*1024*1024)throw new java.io.IOException("Original too large");output.write(buffer,0,n);}
                    output.getFD().sync();
                }catch(Exception error){original.delete();folder.delete();throw error;}
                Uri uri=androidx.core.content.FileProvider.getUriForFile(this,getPackageName()+".documents",original);
                runOnUiThread(()->{
                    documentBusy=false;if(isFinishing()||isDestroyed())return;
                    try {
                        if(request.share){
                            Intent share=new Intent(Intent.ACTION_SEND);share.setType(spec.mime);share.putExtra(Intent.EXTRA_STREAM,uri);
                            share.setClipData(android.content.ClipData.newRawUri("Original document",uri));
                            share.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);startActivity(Intent.createChooser(share,"Share original document"));
                        }else if("application/pdf".equals(spec.mime)){
                            viewerBrowserUrl=request.browserAddress;
                            Intent view=new Intent(this,PdfPageActivity.class);view.setData(uri);view.putExtra("page",request.position);
                            startActivityForResult(view,VIEW_PDF);
                        }else{
                            Intent view=new Intent(Intent.ACTION_VIEW);view.setDataAndType(uri,spec.mime);
                            view.setClipData(android.content.ClipData.newRawUri("Original document",uri));view.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                            Toast.makeText(this,"Open slide "+request.position+" in your viewer. Slide linking is not supported.",Toast.LENGTH_LONG).show();
                            startActivity(Intent.createChooser(view,"Open original slides"));
                        }
                    }catch(android.content.ActivityNotFoundException error){Toast.makeText(this,"No compatible viewer. Use Download original to save the file.",Toast.LENGTH_LONG).show();}
                });
            }catch(Exception error){runOnUiThread(()->{documentBusy=false;Toast.makeText(this,"Could not open original. Return to Library or download it.",Toast.LENGTH_LONG).show();});}
            finally{if(connection!=null)connection.disconnect();}
        },"anvaya-original-document").start();
        return true;
    }

    @Override protected void onActivityResult(int code, int result, Intent data) {
        super.onActivityResult(code,result,data);
        if(code==VIEW_PDF && result==RESULT_OK && data!=null && data.getBooleanExtra("find",false) && viewerBrowserUrl!=null) {
            web.loadUrl(viewerBrowserUrl+"&position="+Math.max(1,Math.min(2500,data.getIntExtra("page",1))));
        }
        if (code == SAVE_FILE && result == RESULT_OK && data != null && data.getData() != null) {
            final Uri destination=data.getData(); final String address=downloadUrl, cookie=downloadCookie;
            downloadUrl=null; downloadCookie=null;
            new Thread(() -> {
                try {
                    java.net.HttpURLConnection connection=(java.net.HttpURLConnection)new java.net.URL(address).openConnection();
                    connection.setInstanceFollowRedirects(false);
                    connection.setConnectTimeout(10000); connection.setReadTimeout(30000);
                    connection.setRequestProperty("Cookie",cookie);
                    if(connection.getResponseCode()!=200) throw new java.io.IOException("Download unavailable");
                    try (java.io.InputStream input=connection.getInputStream();
                         java.io.OutputStream output=getContentResolver().openOutputStream(destination,"wt")) {
                        byte[] buffer=new byte[32768]; int count; long total=0;
                        while((count=input.read(buffer))!=-1) {
                            total+=count; if(total>100L*1024*1024) throw new java.io.IOException("Download too large");
                            output.write(buffer,0,count);
                        }
                    } finally { connection.disconnect(); }
                    runOnUiThread(() -> Toast.makeText(this,"Download saved",Toast.LENGTH_LONG).show());
                } catch(Exception error) {
                    runOnUiThread(() -> Toast.makeText(this,"Download could not be saved. Your app data is kept.",Toast.LENGTH_LONG).show());
                }
            },"anvaya-export").start();
        }
        if (code == PICK_FILES && fileCallback != null) {
            Uri[] selected = WebChromeClient.FileChooserParams.parseResult(result,data);
            if (selected != null) {
                for (Uri chosen : selected) {
                    if (chosen == null || !"content".equals(chosen.getScheme())) {
                        selected = null; // Reject file:// or unexpected schemes.
                        break;
                    }
                }
            }
            fileCallback.onReceiveValue(selected); fileCallback = null;
        }
    }
    @Override public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }
    @Override protected void onDestroy() {
        if (fileCallback != null) fileCallback.onReceiveValue(null);
        if (web != null) { web.stopLoading(); web.destroy(); }
        super.onDestroy();
    }
}

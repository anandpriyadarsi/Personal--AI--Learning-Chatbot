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
    private String downloadUrl;
    private String downloadCookie;
    private String origin;
    private final java.util.concurrent.atomic.AtomicBoolean mediaBusy=new java.util.concurrent.atomic.AtomicBoolean();
    private static final int EXTERNAL_MEDIA=43;
    private long downloadLimit=100L*1024*1024;

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
        // SAF file chooser supplies a user-selected content:// URI. File-system and\n        // file:// access stay disabled; navigation remains loopback-origin restricted.\n        settings.setAllowContentAccess(true);
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
                MediaRequest media=MediaRequest.parse(allowed,req.getUrl().toString(),req.isForMainFrame(),req.hasGesture());
                if(media!=null) {openExternalMedia(media);return true;}
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
                return !allowed.permits(req.getUrl().toString());
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest req) {
                if (allowed.permits(req.getUrl().toString())) return null;
                return new WebResourceResponse("text/plain", "UTF-8",403,"Blocked", java.util.Collections.emptyMap(),
                    new ByteArrayInputStream("External requests are disabled.".getBytes()));
            }
        });
        web.setDownloadListener((url, agent, disposition, mime, length) -> {
            if (!allowed.permits(url)) return;
            DownloadSpec spec=DownloadSpec.from(URLUtil.guessFileName(url,disposition,mime),mime);
            downloadLimit=MediaRequest.isDownload(allowed,url) ? 512L*1024*1024 : 100L*1024*1024;
            downloadUrl=url; downloadCookie=CookieManager.getInstance().getCookie(url);
            Intent save=new Intent(Intent.ACTION_CREATE_DOCUMENT);
            save.addCategory(Intent.CATEGORY_OPENABLE);
            save.setType(spec.mime);
            save.putExtra(Intent.EXTRA_TITLE,spec.name);
            try {startActivityForResult(save,SAVE_FILE);}
            catch(android.content.ActivityNotFoundException | SecurityException error) {
                downloadUrl=null;downloadCookie=null;
                Toast.makeText(this,"No file-saving application is available on this phone.",Toast.LENGTH_LONG).show();
            }
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
    /** Native-only resolver: JS supplies no paths, URLs, cookies or MIME overrides. */
    void openExternalMedia(MediaRequest request) {
        if(!mediaBusy.compareAndSet(false,true)) return;
        Toast.makeText(this,"Opening attachment…",Toast.LENGTH_SHORT).show();
        new Thread(() -> {
            try {
                List<PyObject> item=Python.getInstance().getModule("personal_learning_assistant.services.notes_media_service")
                    .callAttr("resolve_android_media",getFilesDir().getCanonicalPath(),request.noteId,request.assetId).asList();
                java.io.File file=new java.io.File(item.get(0).toString());
                Uri uri=androidx.core.content.FileProvider.getUriForFile(this,getPackageName()+".note_media",file,item.get(2).toString());
                String mime=item.get(1).toString();
                runOnUiThread(() -> {
                    mediaBusy.set(false);
                    if(isFinishing() || isDestroyed()) return;
                    if(request.share) shareMedia(uri,mime);
                    else {
                        try {startActivityForResult(MediaIntents.view(uri,mime),EXTERNAL_MEDIA);}
                        catch(android.content.ActivityNotFoundException error) {noMediaPlayer(request,uri,mime);}
                        catch(SecurityException | IllegalArgumentException error) {mediaError();}
                    }
                });
            } catch(Exception error) {
                runOnUiThread(() -> {mediaBusy.set(false);mediaError();});
            }
        },"anvaya-media-open").start();
    }
    private void shareMedia(Uri uri,String mime) {
        try {startActivityForResult(Intent.createChooser(MediaIntents.share(uri,mime),"Share attachment"),EXTERNAL_MEDIA);}
        catch(android.content.ActivityNotFoundException | SecurityException | IllegalArgumentException error) {
            Toast.makeText(this,"No sharing app is available. Use Download in the attachment menu.",Toast.LENGTH_LONG).show();
        }
    }
    private void noMediaPlayer(MediaRequest request,Uri uri,String mime) {
        new AlertDialog.Builder(this).setTitle("No compatible player found")
            .setMessage("Install a player that supports this format, or share or save the file to open it later.")
            .setPositiveButton("Share file",(dialog,which)->shareMedia(uri,mime))
            .setNeutralButton("Save file",(dialog,which)->web.loadUrl(origin+"/notes/media/"+request.noteId+"/"+request.assetId+"/file"))
            .setNegativeButton("Cancel",null).show();
    }
    private void mediaError() {
        if(!isFinishing() && !isDestroyed()) Toast.makeText(this,"Attachment could not be opened. It may be missing or damaged. Try attaching the original file again.",Toast.LENGTH_LONG).show();
    }
    @Override protected void onActivityResult(int code, int result, Intent data) {
        super.onActivityResult(code,result,data);
        if (code == SAVE_FILE && result == RESULT_OK && data != null && data.getData() != null) {
            final Uri destination=data.getData(); final String address=downloadUrl, cookie=downloadCookie; final long limit=downloadLimit;
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
                            total+=count; if(total>limit) throw new java.io.IOException("Download too large");
                            output.write(buffer,0,count);
                        }
                    } finally { connection.disconnect(); }
                    runOnUiThread(() -> Toast.makeText(this,"Download saved",Toast.LENGTH_LONG).show());
                } catch(Exception error) {
                    runOnUiThread(() -> Toast.makeText(this,"Download could not be saved. Your app data is kept.",Toast.LENGTH_LONG).show());
                }
            },"anvaya-export").start();
        }
        if(code==SAVE_FILE) {downloadUrl=null;downloadCookie=null;}
        // Player/chooser cancellation and returning from the external Activity
        // leave the current WebView/document untouched.
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

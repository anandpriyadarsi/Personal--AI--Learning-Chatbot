package in.anvaya.privateapp;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import java.lang.ref.WeakReference;
import android.webkit.*;
import android.widget.*;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import java.io.ByteArrayInputStream;
import java.util.List;
import com.chaquo.python.PyObject;

public class MainActivity extends Activity {
    private WebView web;
    private LocalOrigin allowed;
    private ValueCallback<Uri[]> fileCallback;
    private int pickerGeneration;
    private final java.util.concurrent.ExecutorService pickerWorker = java.util.concurrent.Executors.newSingleThreadExecutor();
    private java.io.File uploadSelections;
    private long selectedUploadBytes;
    private static final int PICK_FILES = 41;
    private static final int SAVE_FILE = 42;
    private static final int VIEW_PDF = 43;
    private boolean documentBusy;
    private String viewerBrowserUrl;
    private String downloadUrl;
    private String downloadCookie;
    private String origin;
    private final java.util.concurrent.atomic.AtomicBoolean mediaBusy=new java.util.concurrent.atomic.AtomicBoolean();
    private static final int EXTERNAL_MEDIA=44;
    private long downloadLimit=100L*1024*1024;

    private FrameLayout workspaceRoot;
    private StartupSplashView splash;
    private androidx.core.view.WindowInsetsControllerCompat startupBars;
    private int workspaceBarBehavior;
    private final Handler startupHandler = new Handler(Looper.getMainLooper());
    private int startupAttempt;
    private boolean workspaceVisible, startupFailed, runtimePending;
    private final Runnable slowStartup = () -> {
        if (startupActive()) splash.feedback(runtimePending
            ? "Preparing your private workspace…\nYour saved data stays on this phone."
            : "Opening your workspace…", false, false);
    };
    private final Runnable delayedStartup = () -> {
        if (startupActive()) splash.feedback(runtimePending
            ? "Setup is taking longer than usual. You can keep waiting, or close and reopen ANVAYA. Your saved data is kept."
            : "The workspace is taking longer than usual to display. Try again, or close and reopen ANVAYA.",
            !runtimePending, true);
    };
    private boolean backPending;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        uploadSelections = new java.io.File(getFilesDir(), "upload-selections");
        // No old WebView survives a new Activity/process. Never touch academic data.
        clearUploadSelections();
        // Screen captures remain available for the owner's study and feedback.
        startupBars = androidx.core.view.WindowCompat.getInsetsController(getWindow(), getWindow().getDecorView());
        workspaceBarBehavior = startupBars.getSystemBarsBehavior();
        startupBars.setSystemBarsBehavior(androidx.core.view.WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
        startupBars.hide(androidx.core.view.WindowInsetsCompat.Type.systemBars());
        workspaceRoot = new FrameLayout(this);
        workspaceRoot.setBackgroundColor(StartupSplashView.BACKGROUND);
        splash = new StartupSplashView(this, this::startWorkspace, () -> {
            finishAffinity(); android.os.Process.killProcess(android.os.Process.myPid());
        });
        workspaceRoot.addView(splash, new FrameLayout.LayoutParams(-1, -1));
        setContentView(workspaceRoot);
        if (Build.VERSION.SDK_INT >= 31) {
            getSplashScreen().setOnExitAnimationListener(platformSplash -> {
                platformSplash.remove();
                if (startupActive()) splash.startBranding();
            });
        } else splash.post(() -> { if (startupActive()) splash.startBranding(); });
        startWorkspace();
    }

    private boolean startupActive() {
        return !workspaceVisible && !isFinishing() && !isDestroyed();
    }
    private void scheduleStartupFeedback() {
        startupHandler.removeCallbacksAndMessages(null);
        startupHandler.postDelayed(slowStartup, 8000);
        startupHandler.postDelayed(delayedStartup, 30000);
    }
    private void startWorkspace() {
        if (!startupActive() || runtimePending) return;
        startupFailed = false;
        runtimePending = true;
        splash.feedback("", false, false);
        if (web != null) {
            workspaceRoot.removeView(web);
            web.stopLoading(); web.destroy(); web = null;
        }
        scheduleStartupFeedback();
        // Only an application Context and weak Activity reference cross the
        // worker boundary. A destroyed Activity cannot receive a late launch.
        new Thread(new StartupTask(this, ++startupAttempt), "anvaya-launch").start();
    }
    private static final class StartupTask implements Runnable {
        private final WeakReference<MainActivity> owner;
        private final android.content.Context context;
        private final int attempt;
        StartupTask(MainActivity activity, int attempt) {
            owner = new WeakReference<>(activity);
            context = activity.getApplicationContext();
            this.attempt = attempt;
        }
        @Override public void run() {
            String address = null, token = null;
            try {
                synchronized (Python.class) {
                    if (!Python.isStarted()) Python.start(new AndroidPlatform(context));
                }
                List<PyObject> runtime = Python.getInstance().getModule("personal_learning_assistant.android_runtime")
                    .callAttr("launch", context.getFilesDir().getCanonicalPath(),
                        BuildConfig.SOURCE_SHA, BuildConfig.VERSION_NAME, BuildConfig.VERSION_CODE).asList();
                address = runtime.get(0).toString(); token = runtime.get(1).toString();
            } catch (Exception error) {
                // Never log Python exceptions with academic paths/content.
            }
            final String readyAddress = address, readyToken = token;
            new Handler(Looper.getMainLooper()).post(() -> {
                MainActivity activity = owner.get();
                if (activity == null || !activity.startupActive() || activity.startupAttempt != attempt) return;
                activity.runtimePending = false;
                if (readyAddress == null) activity.startupFailure("ANVAYA could not prepare your workspace. Your saved data is kept. Try again, or close and reopen the app.");
                else {
                    activity.scheduleStartupFeedback();
                    try { activity.openWorkspace(readyAddress, readyToken); }
                    catch (Exception error) { activity.startupFailure("ANVAYA could not display your workspace. Your saved data is kept. Try again, or close and reopen the app."); }
                }
            });
        }
    }
    private void startupFailure(String message) {
        if (!startupActive()) return;
        startupFailed = true;
        startupHandler.removeCallbacksAndMessages(null);
        splash.feedback(message, true, true);
    }
    private void revealWorkspace(WebView painted) {
        if (!startupActive() || startupFailed || painted != web) return;
        workspaceVisible = true;
        startupHandler.removeCallbacksAndMessages(null);
        splash.cancelBranding();
        workspaceRoot.removeView(splash);
        // Use the same visibility controller for both transitions. Mixing
        // legacy hide flags with modern show requests retained a hidden API31
        // navigation source after an immediately replaced Activity.
        startupBars.show(androidx.core.view.WindowInsetsCompat.Type.systemBars());
        startupBars.setSystemBarsBehavior(workspaceBarBehavior);
        painted.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_AUTO);
        painted.requestFocus();
    }

    @SuppressWarnings("deprecation")
    private void openWorkspace(String address, String token) {
        if (isFinishing() || isDestroyed()) return;
        origin = address; allowed = new LocalOrigin(origin);
        web = new WebView(this);
        web.setBackgroundColor(StartupSplashView.BACKGROUND);
        final WebView workspace = web;
        web.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS);
        workspaceRoot.addView(web, 0, new FrameLayout.LayoutParams(-1, -1));
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
        web.setWebViewClient(new WebViewClient() {
            @Override public void onPageCommitVisible(WebView view, String url) {
                if (!startupActive() || startupFailed || view != web || !allowed.permits(url)) return;
                // A finished HTTP request is not proof of a painted page. Keep
                // the opaque native splash through the compositor's first frame.
                view.postVisualStateCallback(startupAttempt, new WebView.VisualStateCallback() {
                    @Override public void onComplete(long requestId) {
                        view.postOnAnimation(() -> revealWorkspace(view));
                    }
                });
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (view == web && request.isForMainFrame()) startupFailure("Your workspace could not load. Your saved data is kept. Try again.");
            }
            @Override public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse response) {
                if (view == web && request.isForMainFrame()) startupFailure("Your workspace could not open. Your saved data is kept. Try again.");
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                if (ObsidianOpenRequest.permits(req.getUrl().toString(), req.isForMainFrame(), req.hasGesture())) {
                    try { startActivity(new Intent(Intent.ACTION_VIEW, req.getUrl())); }
                    catch (android.content.ActivityNotFoundException error) {
                        Toast.makeText(MainActivity.this, "Obsidian is not installed. Install it and open the exported vault to use this link.", Toast.LENGTH_LONG).show();
                    } catch (SecurityException error) {
                        Toast.makeText(MainActivity.this, "This phone could not open Obsidian. Open the exported vault in Obsidian manually.", Toast.LENGTH_LONG).show();
                    }
                    return true;
                }
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
                ++pickerGeneration;
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
        cookies.removeAllCookies(removed -> {
            if (!startupActive() || workspace != web) return;
            cookies.setCookie(origin, "anvaya_native="+token+"; Path=/; HttpOnly; SameSite=Strict", ok -> {
                if (!startupActive() || workspace != web) return;
                if (!ok) { startupFailure("Your workspace could not connect securely. Try again."); return; }
                workspace.loadUrl(origin+"/");
            });
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
                        catch(android.content.ActivityNotFoundException error) {noCompatibleApp(request,uri,mime);}
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
    private void noCompatibleApp(MediaRequest request,Uri uri,String mime) {
        new AlertDialog.Builder(this).setTitle("No compatible app found")
            .setMessage("Install an app that supports this format, or share or save the file to open it later.")
            .setPositiveButton("Share file",(dialog,which)->shareMedia(uri,mime))
            .setNeutralButton("Save file",(dialog,which)->web.loadUrl(origin+"/notes/media/"+request.noteId+"/"+request.assetId+"/file"))
            .setNegativeButton("Cancel",null).show();
    }
    private void mediaError() {
        if(!isFinishing() && !isDestroyed()) Toast.makeText(this,"Attachment could not be opened. It may be missing or damaged. Try attaching the original file again.",Toast.LENGTH_LONG).show();
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
            final ValueCallback<Uri[]> callback = fileCallback;
            fileCallback = null;
            if (selected == null || selected.length == 0 || selected.length > 20) {
                callback.onReceiveValue(null);
                return;
            }
            final Uri[] sources = selected;
            final int generation = pickerGeneration;
            Toast.makeText(this, "Preparing selected files…", Toast.LENGTH_SHORT).show();
            pickerWorker.execute(() -> {
                Uri[] stable = new Uri[sources.length];
                java.util.ArrayList<java.io.File> copied = new java.util.ArrayList<>();
                long batchBytes = 0;
                try {
                    for (int i = 0; i < sources.length; i++) {
                        String name = "Selected-file";
                        try (android.database.Cursor cursor = getContentResolver().query(sources[i],
                                new String[]{android.provider.OpenableColumns.DISPLAY_NAME}, null, null, null)) {
                            if (cursor != null && cursor.moveToFirst() && !cursor.isNull(0)) name = cursor.getString(0);
                        }
                        long remaining = 1024L * 1024 * 1024 - selectedUploadBytes - batchBytes;
                        java.io.File copy = UploadSnapshot.copy(getContentResolver().openInputStream(sources[i]),
                            uploadSelections, name, Math.min(512L * 1024 * 1024, remaining));
                        copied.add(copy); batchBytes += copy.length();
                        stable[i] = androidx.core.content.FileProvider.getUriForFile(this, getPackageName()+".uploads", copy);
                    }
                    selectedUploadBytes += batchBytes;
                    runOnUiThread(() -> {
                        if (isFinishing() || isDestroyed() || generation != pickerGeneration) callback.onReceiveValue(null);
                        else callback.onReceiveValue(stable);
                    });
                } catch (Exception error) {
                    for (java.io.File file : copied) { file.delete(); file.getParentFile().delete(); }
                    runOnUiThread(() -> {
                        callback.onReceiveValue(null);
                        if (!isFinishing() && !isDestroyed()) Toast.makeText(this,
                            "Could not prepare selected files. Choose a downloaded local copy and retry. Selection storage is limited to 1 GB per app session; reopening clears it. Your saved study data is kept.",
                            Toast.LENGTH_LONG).show();
                    });
                }
            });
        }
    }
    private void clearUploadSelections() {
        java.io.File[] directories = uploadSelections.listFiles();
        if (directories == null) return;
        for (java.io.File directory : directories) {
            java.io.File[] files = directory.listFiles();
            if (files != null) for (java.io.File file : files) file.delete();
            directory.delete();
        }
    }
    @Override public void onBackPressed() {
        final WebView target = web;
        final String page = target == null ? null : target.getUrl();
        if (backPending) return;
        if (target == null || page == null || allowed == null || !allowed.permits(page)) {
            super.onBackPressed();
            return;
        }
        // Native WebView history may lag the renderer's same-document history.
        // Let the trusted local reader close its active mode before a page Back.
        // This evaluates fixed app code; no JavaScript bridge is exposed.
        backPending = true;
        target.evaluateJavascript("(() => {"
            + "const modal=document.querySelector('dialog[open]');"
            + "if(modal){modal.close();return true;}"
            + "const focus=document.getElementById('ls-focus');"
            + "if(focus&&document.body.classList.contains('ls-focus')){focus.click();return true;}"
            + "return false;})()", consumed -> {
                backPending = false;
                if (target != web || isFinishing() || isDestroyed()) return;
                if ("true".equals(consumed)) return;
                if (!page.equals(target.getUrl())) return;
                if (target.canGoBack()) target.goBack();
                else MainActivity.super.onBackPressed();
            });
    }
    @Override protected void onDestroy() {
        ++pickerGeneration;
        pickerWorker.shutdownNow();
        ++startupAttempt;
        startupHandler.removeCallbacksAndMessages(null);
        if (splash != null) splash.cancelBranding();
        if (Build.VERSION.SDK_INT >= 31) getSplashScreen().clearOnExitAnimationListener();
        if (fileCallback != null) fileCallback.onReceiveValue(null);
        if (web != null) { workspaceRoot.removeView(web); web.stopLoading(); web.destroy(); web = null; }
        super.onDestroy();
    }
}

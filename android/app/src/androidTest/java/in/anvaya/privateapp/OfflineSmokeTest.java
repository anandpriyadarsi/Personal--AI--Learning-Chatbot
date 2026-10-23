package in.anvaya.privateapp;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Bitmap;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.WebView;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import org.json.JSONObject;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/** Actual Activity/WebView/embedded-Python checks using synthetic records only. */
@RunWith(AndroidJUnit4.class)
public class OfflineSmokeTest {
    private android.app.Instrumentation getInstrumentation() { return InstrumentationRegistry.getInstrumentation(); }
    private Activity activity;
    private WebView web;
    private WebView find(View view) {
        if(view instanceof WebView) return (WebView)view;
        if(view instanceof ViewGroup) {
            ViewGroup group=(ViewGroup)view;
            for(int i=0;i<group.getChildCount();i++) {WebView found=find(group.getChildAt(i));if(found!=null)return found;}
        }
        return null;
    }
    private void open() throws Exception {
        Intent intent=new Intent(getInstrumentation().getTargetContext(),MainActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        activity=getInstrumentation().startActivitySync(intent);
        long deadline=System.currentTimeMillis()+90000;
        while(System.currentTimeMillis()<deadline) {
            getInstrumentation().runOnMainSync(()->web=find(activity.getWindow().getDecorView()));
            if(web!=null && "true".equals(js("document.readyState==='complete' && !!document.querySelector('main')"))) {
                waitFor("!!document.getElementById('mobile-connection') && document.getElementById('mobile-connection').hidden");
                return;
            }
            Thread.sleep(100);
        }
        // Surface an embedded startup exception to synthetic instrumentation logs.
        com.chaquo.python.Python.getInstance().getModule("personal_learning_assistant.android_runtime")
            .callAttr("launch",getInstrumentation().getTargetContext().getFilesDir().getCanonicalPath());
        fail("Embedded runtime did not render main within 90s");
    }
    private String js(String script) throws Exception {
        CountDownLatch done=new CountDownLatch(1);String[] value={null};
        getInstrumentation().runOnMainSync(()->web.evaluateJavascript(script,result->{value[0]=result;done.countDown();}));
        assertTrue("JavaScript callback",done.await(10,TimeUnit.SECONDS));return value[0];
    }
    private void waitFor(String expression) throws Exception {
        long deadline=System.currentTimeMillis()+30000;
        while(System.currentTimeMillis()<deadline) {
            // Server-rendered status can appear before deferred handlers attach
            // after a mutation reload. Do not click a new form in that gap.
            if("true".equals(js("document.readyState==='complete' && ("+expression+")")))return;
            Thread.sleep(100);
        }
        fail("Missing live DOM state: "+expression+"; body="+js("document.body.innerText"));
    }
    private void go(String path) throws Exception {
        js("location.href="+org.json.JSONObject.quote(path));
        waitFor("location.pathname+location.search==="+org.json.JSONObject.quote(path)+" && document.readyState==='complete' && !!document.querySelector('main')");
    }
    private JSONObject sessions() throws Exception {
        try(InputStream in=getInstrumentation().getContext().getAssets().open("acceptance/sessions.json")) {
            java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream();
            byte[] bytes=new byte[4096];int n;while((n=in.read(bytes))!=-1)out.write(bytes,0,n);
            return new JSONObject(out.toString("UTF-8"));
        }
    }
    private String attempt(String kind) throws Exception {
        return "/assessments/extended/sessions/"+sessions().getString(kind);
    }
    private void checkDownload(String path,String mime,String name) throws Exception {
        // Let the real local attachment response reach DownloadListener, then
        // inspect its SAF request and cancel. No shared storage is written.
        java.util.concurrent.atomic.AtomicReference<Intent> request=new java.util.concurrent.atomic.AtomicReference<>();
        android.app.Instrumentation.ActivityMonitor monitor=new android.app.Instrumentation.ActivityMonitor() {
            @Override public android.app.Instrumentation.ActivityResult onStartActivity(Intent intent) {
                if(Intent.ACTION_CREATE_DOCUMENT.equals(intent.getAction())) {
                    request.set(new Intent(intent));
                    return new android.app.Instrumentation.ActivityResult(Activity.RESULT_CANCELED,null);
                }
                return null;
            }
        };
        getInstrumentation().addMonitor(monitor);
        try {
            js("location.href="+JSONObject.quote(path));
            long deadline=System.currentTimeMillis()+10000;
            while(request.get()==null && System.currentTimeMillis()<deadline)Thread.sleep(100);
            assertNotNull("Native document picker request",request.get());
            assertEquals(mime,request.get().getType());
            assertEquals(name,request.get().getStringExtra(Intent.EXTRA_TITLE));
        } finally {getInstrumentation().removeMonitor(monitor);}
    }
    private void confirmAction(String selector, boolean accept) throws Exception {
        // Exercise the real Android JS confirmation, never replace window.confirm.
        android.accessibilityservice.AccessibilityServiceInfo info=getInstrumentation().getUiAutomation().getServiceInfo();
        info.flags|=android.accessibilityservice.AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS;
        getInstrumentation().getUiAutomation().setServiceInfo(info);
        getInstrumentation().runOnMainSync(()->web.evaluateJavascript(
            "document.querySelector("+JSONObject.quote(selector)+").click()",null));
        long deadline=System.currentTimeMillis()+10000;
        while(System.currentTimeMillis()<deadline) {
            android.view.accessibility.AccessibilityNodeInfo root=getInstrumentation().getUiAutomation().getRootInActiveWindow();
            if(root!=null) {
                java.util.List<android.view.accessibility.AccessibilityNodeInfo> buttons=root.findAccessibilityNodeInfosByViewId(
                    accept ? "android:id/button1" : "android:id/button2");
                if(!buttons.isEmpty()) {
                    assertTrue(buttons.get(0).performAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK));return;
                }
            }
            Thread.sleep(100);
        }
        fail("Native confirmation dialog was not shown; ready/state="+js("JSON.stringify({ready:document.readyState,status:document.querySelector('#workspace')?.dataset.status})"));
    }
    private void screenshot(String name) throws Exception {
        getInstrumentation().runOnMainSync(()->activity.getWindow().clearFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE));
        CountDownLatch rendered=new CountDownLatch(1);
        getInstrumentation().runOnMainSync(()->web.postVisualStateCallback(System.nanoTime(),new WebView.VisualStateCallback(){
            @Override public void onComplete(long id) {
                web.invalidate();
                web.postOnAnimation(()->web.postOnAnimation(rendered::countDown));
            }
        }));
        assertTrue("WebView compositor frame",rendered.await(10,TimeUnit.SECONDS));
        getInstrumentation().waitForIdleSync();
        Bitmap image=getInstrumentation().getUiAutomation().takeScreenshot();
        assertNotNull("Actual emulator capture",image);
        File folder=new File(getInstrumentation().getTargetContext().getFilesDir(),"evidence");folder.mkdirs();
        try(FileOutputStream out=new FileOutputStream(new File(folder,name+".png"))) {
            image.compress(Bitmap.CompressFormat.PNG,100,out);
        }
        image.recycle();
    }
    @Test public void testCreateOfflineNote() throws Exception {
        // The fixture exists only in the instrumentation APK. Production restore
        // validation and migrations run before the ordinary launcher starts.
        File pending=new File(getInstrumentation().getTargetContext().getFilesDir(),"restore-pending.zip");
        try(InputStream in=getInstrumentation().getContext().getAssets().open("acceptance/workspace.zip");
            FileOutputStream out=new FileOutputStream(pending)) {
            byte[] bytes=new byte[32768];int n;while((n=in.read(bytes))!=-1)out.write(bytes,0,n);
        }
        open();screenshot("android-today");
        go("/notes/create/typed");
        waitFor("!!document.querySelector('textarea[name=body]')");
        js("document.querySelector('[name=title]').value='Synthetic Android restart note';document.querySelector('[name=body]').value='Saved offline through the real Android WebView and production Notes service.';document.querySelector('.anvaya-native-note-form').requestSubmit()");
        waitFor("location.pathname.startsWith('/notes/view/') && document.body.innerText.includes('Synthetic Android restart note')");
        screenshot("android-note-saved");
        go("/planning/tasks");
        waitFor("!!document.querySelector('form[action=\"/planning/tasks\"]')");
        js("document.querySelector('form[action=\"/planning/tasks\"] [name=title]').value='Synthetic Android SQLite task';document.querySelector('form[action=\"/planning/tasks\"] [name=estimated_minutes]').value='30';document.querySelector('form[action=\"/planning/tasks\"]').requestSubmit()");
        waitFor("!!document.querySelector('.planner-task-list') && document.querySelector('.planner-task-list').innerText.includes('Synthetic Android SQLite task')");
        screenshot("android-sqlite-task-saved");
        for(String path:new String[]{"/learning","/agent","/assessments","/library","/mobile/settings","/mobile/device"}) {
            go(path);screenshot("android-"+path.replace('/','-'));
            assertEquals("No document overflow at "+path,"true",js("document.documentElement.scrollWidth<=innerWidth+1"));
        }
        go("/learning/modules/uc100n-demo/1?view=learn");
        waitFor("!!document.querySelector('.ls-block-definition') && document.querySelector('#ls-reading-status').innerText.includes('saved')");
        screenshot("android-active-lesson");
        go("/learning/modules/uc100n-demo/1?view=practice&question=mean-score");
        js("document.querySelector('.ls-question input[value=\"0\"]').checked=true;document.querySelector('.ls-question button[type=submit]').click()");
        waitFor("document.querySelector('.ls-feedback').innerText.includes('Incorrect')");
        screenshot("android-learning-mistake");
        go("/learning/modules/uc100n-demo/1/conversion");
        waitFor("document.body.innerText.includes('PDF draft conversion is unavailable in this Android build')");
        assertEquals("Unsupported extractor action is not offered","true",js("!document.querySelector('form[action$=\"/conversion/preview\"]')"));
        screenshot("android-conversion-capability");
        go("/knowledge/item/"+sessions().getString("source_id"));
        waitFor("document.body.innerText.includes('Mean score')");
        screenshot("android-library-reader");
        checkDownload("/learning/modules/uc100n-demo/1/source.pdf","application/pdf","synthetic-uc100n.pdf");
        checkDownload("/learning/modules/uc100n-demo/1/review-brief","text/plain","learning-review-brief.txt");
        checkDownload("/mobile/device/export","application/zip","ANVAYA-private-backup.zip");
        go(attempt("online"));
        waitFor("document.querySelector('#workspace').dataset.status==='paused'");
        js("document.querySelector('form[action$=\"/resume\"] button').click()");
        waitFor("document.querySelector('#workspace').dataset.status==='active'");
        js("document.querySelector('input[value=\"B\"]').checked=true;document.querySelector('select[name=ordinal]').value='2';document.querySelector('button[value=navigate]').click()");
        waitFor("document.querySelector('.palette-position').innerText.trim()==='2 / 2' && !!document.querySelector('#question-2 input[value=\"B\"]')");
        js("document.querySelector('#question-2 input[value=\"B\"]').checked=true;document.querySelector('.palette-pause').click()");
        waitFor("document.querySelector('#workspace').dataset.status==='paused'");
        activity.getSharedPreferences("synthetic-evidence",0).edit().putString("pausedTimer",js("document.querySelector('#timer').textContent")).commit();
        screenshot("android-assessment-paused");
        go(attempt("paper"));
        js("document.querySelector('form[action$=\"/resume\"] button').click()");
        waitFor("document.querySelector('#workspace').dataset.status==='active'");
        confirmAction("form[action$='/finish_solving'] button",false);
        assertEquals("Cancel preserves active attempt","true",js("document.querySelector('#workspace').dataset.status==='active'"));
        confirmAction("form[action$='/finish_solving'] button",true);
        waitFor("document.querySelector('#state-banner').innerText.includes('Self-check workspace')");
        js("document.querySelector('form[action$=\"/reveal\"] button').click()");
        waitFor("document.querySelectorAll('select[name^=step_]').length===3");
        js("document.querySelectorAll('select[name^=step_]').forEach(s=>s.value='1.0');document.querySelector('form[action$=\"/self_save\"] button').click()");
        waitFor("document.querySelector('.mark-state').innerText.includes('3.0 marks')");
        screenshot("android-paper-step-review");
    }
    @Test public void testNoteAfterForceStop() throws Exception {
        open();go("/notes");
        waitFor("document.body.innerText.includes('Synthetic Android restart note')");
        screenshot("android-note-after-force-stop");
        getInstrumentation().runOnMainSync(()->activity.setRequestedOrientation(android.content.pm.ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE));
        waitFor("innerWidth>innerHeight && document.documentElement.scrollWidth<=innerWidth+1");
        screenshot("android-notes-landscape");
        getInstrumentation().runOnMainSync(()->activity.setRequestedOrientation(android.content.pm.ActivityInfo.SCREEN_ORIENTATION_PORTRAIT));
        waitFor("innerHeight>innerWidth");
        go("/planning/tasks");
        waitFor("!!document.querySelector('.planner-task-list') && document.querySelector('.planner-task-list').innerText.includes('Synthetic Android SQLite task')");
        screenshot("android-sqlite-task-after-force-stop");
        go(attempt("online"));
        waitFor("document.querySelector('#workspace').dataset.status==='paused'");
        assertEquals("Paused active time survives process death",activity.getSharedPreferences("synthetic-evidence",0).getString("pausedTimer","missing"),js("document.querySelector('#timer').textContent"));
        assertEquals("Last question preserved","true",js("document.querySelector('.palette-position').innerText.trim()==='2 / 2'"));
        screenshot("android-assessment-after-force-stop");
        js("document.querySelector('form[action$=\"/resume\"] button').click()");
        waitFor("document.querySelector('#workspace').dataset.status==='active'");
        waitFor("!!document.querySelector('#question-2 input[value=\"B\"]:checked')");
        screenshot("android-assessment-resumed");
        js("document.querySelector('.palette-pause').click()");
        waitFor("document.querySelector('#workspace').dataset.status==='paused'");
        go(attempt("paper"));
        waitFor("document.querySelector('.mark-state').innerText.includes('3.0 marks')");
        screenshot("android-paper-review-after-force-stop");
        go("/learning/modules/uc100n-demo/1?view=practice&question=mean-score");
        waitFor("document.querySelector('.ls-question-state').innerText.includes('1 recorded attempts')");
        // Verify the embedded interpreter is running in this installed package.
        assertTrue(com.chaquo.python.Python.isStarted());
    }
}

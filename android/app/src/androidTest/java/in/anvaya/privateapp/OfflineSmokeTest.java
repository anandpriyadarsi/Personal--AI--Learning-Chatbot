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
            if(web!=null && "true".equals(js("!!document.querySelector('main')"))) return;
            Thread.sleep(100);
        }
        // Surface an embedded startup exception to synthetic instrumentation logs.
        com.chaquo.python.Python.getInstance().getModule("personal_learning_assistant.android_runtime")
            .callAttr("launch",getInstrumentation().getTargetContext().getFilesDir().getAbsolutePath());
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
            if("true".equals(js(expression)))return;
            Thread.sleep(100);
        }
        fail("Missing live DOM state: "+expression+"; body="+js("document.body.innerText"));
    }
    private void go(String path) throws Exception {
        js("location.href="+org.json.JSONObject.quote(path));
        waitFor("location.pathname==="+org.json.JSONObject.quote(path)+" && !!document.querySelector('main')");
    }
    private void screenshot(String name) throws Exception {
        getInstrumentation().runOnMainSync(()->activity.getWindow().clearFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE));
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
        open();screenshot("android-today");
        go("/notes/create/typed");
        waitFor("!!document.querySelector('textarea[name=body]')");
        js("document.querySelector('[name=title]').value='Synthetic Android restart note';document.querySelector('[name=body]').value='Saved offline through the real Android WebView and production Notes service.';document.querySelector('.anvaya-native-note-form').requestSubmit()");
        waitFor("location.pathname.startsWith('/notes/view/') && document.body.innerText.includes('Synthetic Android restart note')");
        screenshot("android-note-saved");
        for(String path:new String[]{"/learning","/agent","/assessments","/library","/mobile/settings","/mobile/device"}) {
            go(path);screenshot("android-"+path.replace('/','-'));
            assertEquals("No document overflow at "+path,"true",js("document.documentElement.scrollWidth<=innerWidth+1"));
        }
    }
    @Test public void testNoteAfterForceStop() throws Exception {
        open();go("/notes");
        waitFor("document.body.innerText.includes('Synthetic Android restart note')");
        screenshot("android-note-after-force-stop");
        // Verify the embedded interpreter is running in this installed package.
        assertTrue(com.chaquo.python.Python.isStarted());
    }
}

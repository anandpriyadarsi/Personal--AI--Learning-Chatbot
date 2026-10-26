package in.anvaya.privateapp;

import android.app.*;
import android.content.*;
import android.net.Uri;
import android.view.*;
import android.webkit.WebView;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.util.concurrent.*;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

/** Real WebView multipart POST using a timestamp-changing external document. */
@RunWith(AndroidJUnit4.class)
public class UploadPickerTest {
    private Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
    private WebView find(View view) {
        if (view instanceof WebView) return (WebView)view;
        if (view instanceof ViewGroup) {
            ViewGroup group=(ViewGroup)view;
            for(int i=0;i<group.getChildCount();i++) { WebView found=find(group.getChildAt(i)); if(found!=null)return found; }
        }
        return null;
    }
    private String js(WebView web, String expression) throws Exception {
        CountDownLatch latch=new CountDownLatch(1); String[] value={null};
        instrumentation.runOnMainSync(()->web.evaluateJavascript(expression,result->{value[0]=result;latch.countDown();}));
        assertTrue("JavaScript response",latch.await(10,TimeUnit.SECONDS)); return value[0];
    }
    private void waitFor(WebView web,String expression) throws Exception {
        long deadline=System.currentTimeMillis()+60000;
        while(System.currentTimeMillis()<deadline) { if("true".equals(js(web,expression)))return;Thread.sleep(100); }
        fail("Upload workflow did not finish: "+js(web,"document.body.innerText.slice(0,300)"));
    }
    private void tap(WebView web,String selector) throws Exception {
        String bounds=js(web,"(()=>{const a=document.querySelector("+org.json.JSONObject.quote(selector)+");a.scrollIntoView({block:'center'});const r=a.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2,width:innerWidth}})()");
        org.json.JSONObject point=new org.json.JSONObject(bounds);
        int[] location=new int[2];instrumentation.runOnMainSync(()->web.getLocationOnScreen(location));
        float scale=web.getWidth()/(float)point.getDouble("width");
        float x=location[0]+(float)point.getDouble("x")*scale;
        float y=location[1]+(float)point.getDouble("y")*scale;
        CountDownLatch frame=new CountDownLatch(1);
        instrumentation.runOnMainSync(()->web.postVisualStateCallback(System.nanoTime(),new WebView.VisualStateCallback() {
            @Override public void onComplete(long id) {web.postOnAnimation(frame::countDown);}
        }));
        assertTrue("Picker compositor frame",frame.await(10,TimeUnit.SECONDS));
        long now=android.os.SystemClock.uptimeMillis();
        MotionEvent down=MotionEvent.obtain(now,now,MotionEvent.ACTION_DOWN,x,y,0);
        MotionEvent up=MotionEvent.obtain(now,now+80,MotionEvent.ACTION_UP,x,y,0);
        down.setSource(InputDevice.SOURCE_TOUCHSCREEN);up.setSource(InputDevice.SOURCE_TOUCHSCREEN);
        assertTrue(instrumentation.getUiAutomation().injectInputEvent(down,true));
        assertTrue(instrumentation.getUiAutomation().injectInputEvent(up,true));down.recycle();up.recycle();
    }
    @Test public void changingProviderDocumentUploadsWithoutFileChangedError() throws Exception {
        Context target=instrumentation.getTargetContext();
        Uri source=Uri.parse("content://in.anvaya.privateapp.test.changing_upload/document.pdf");
        instrumentation.getContext().grantUriPermission(target.getPackageName(),source,Intent.FLAG_GRANT_READ_URI_PERMISSION);
        Intent chosen=new Intent().setData(source).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        java.util.concurrent.atomic.AtomicInteger pickerCalls=new java.util.concurrent.atomic.AtomicInteger();
        Instrumentation.ActivityMonitor monitor=new Instrumentation.ActivityMonitor() {
            @Override public Instrumentation.ActivityResult onStartActivity(Intent intent) {
                if (!Intent.ACTION_OPEN_DOCUMENT.equals(intent.getAction())) return null;
                pickerCalls.incrementAndGet();
                return new Instrumentation.ActivityResult(Activity.RESULT_OK,chosen);
            }
        };
        instrumentation.addMonitor(monitor);
        Activity activity=null;
        try {
            Intent intent=new Intent(target,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            activity=instrumentation.startActivitySync(intent);
            WebView[] found={null}; final Activity current=activity;
            long deadline=System.currentTimeMillis()+90000;
            while(found[0]==null&&System.currentTimeMillis()<deadline) {
                instrumentation.runOnMainSync(()->found[0]=find(current.getWindow().getDecorView()));Thread.sleep(100);
            }
            assertNotNull(found[0]);WebView web=found[0];
            waitFor(web,"document.readyState==='complete' && !!document.querySelector('main')");
            js(web,"location.href='/library/files'");
            waitFor(web,"!!document.querySelector('input[type=file]')");
            js(web,"document.querySelector('[data-action=upload-dialog]').click()");
            tap(web,"#upload-form input[type=file]");
            waitFor(web,"document.querySelector('input[type=file]').files.length===1");
            assertTrue("System picker intent used",pickerCalls.get()>0);
            assertEquals("\"Changing lecture.pdf\"",js(web,"document.querySelector('input[type=file]').files[0].name"));
            js(web,"document.querySelector('input[type=file]').closest('form').requestSubmit()");
            waitFor(web,"Array.from(document.querySelectorAll('.file-row h2')).some(row=>row.innerText==='Changing lecture.pdf')");
            assertEquals("false",js(web,"document.body.innerText.includes('Web page not available')"));
        } finally {
            instrumentation.removeMonitor(monitor);
            if(activity!=null) { final Activity close=activity;instrumentation.runOnMainSync(close::finish); }
            instrumentation.getContext().revokeUriPermission(source,Intent.FLAG_GRANT_READ_URI_PERMISSION);
        }
    }
}

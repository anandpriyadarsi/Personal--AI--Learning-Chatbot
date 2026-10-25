package in.anvaya.privateapp;

import android.app.Activity;
import android.content.*;
import android.net.Uri;
import android.os.Build;
import androidx.core.content.FileProvider;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.*;
import java.util.concurrent.*;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class MediaHandoffTest {
    @Test public void actualExternalUidReadsContentUriWithReadOnlyGrantAndReturns() throws Exception {
        android.app.Instrumentation instrumentation=InstrumentationRegistry.getInstrumentation();
        Context context=instrumentation.getTargetContext();
        byte[] payload="ID3ANVAYA synthetic external recipient test".getBytes("UTF-8");
        File folder=new File(context.getFilesDir(),"data/anvaya_notes_assets/synthetic/media");folder.mkdirs();
        File source=new File(folder,"synthetic.mp3");
        try(FileOutputStream out=new FileOutputStream(source)) {out.write(payload);}
        Uri uri=FileProvider.getUriForFile(context,context.getPackageName()+".note_media",source,"Teacher.mp3");
        Intent intent=MediaIntents.view(uri,"audio/mpeg");
        assertEquals(Intent.ACTION_VIEW,intent.getAction());
        assertEquals("content",intent.getData().getScheme());
        assertEquals("audio/mpeg",intent.getType());
        assertTrue((intent.getFlags() & Intent.FLAG_GRANT_READ_URI_PERMISSION)!=0);
        assertEquals(0,intent.getFlags() & Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
        assertEquals(uri,intent.getClipData().getItemAt(0).getUri());
        assertFalse(intent.toUri(0).contains(context.getFilesDir().getPath()));
        CountDownLatch done=new CountDownLatch(1);
        Intent[] received={null};
        BroadcastReceiver receiver=new BroadcastReceiver() {
            @Override public void onReceive(Context c,Intent report) {received[0]=report;done.countDown();}
        };
        IntentFilter filter=new IntentFilter("in.anvaya.privateapp.TEST_MEDIA_RESULT");
        if(Build.VERSION.SDK_INT>=33) context.registerReceiver(receiver,filter,Context.RECEIVER_EXPORTED);
        else context.registerReceiver(receiver,filter);
        try {
            // Explicit test-only package stands in for an independently installed
            // player. Exercise the actual cross-UID grant, not a mocked resolver.
            intent.setComponent(new ComponentName(instrumentation.getContext().getPackageName(),"in.anvaya.privateapp.test.MediaReceiverActivity"));
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(intent);
            assertTrue("External recipient returned",done.await(20,TimeUnit.SECONDS));
            assertNotNull(received[0]);
            assertNull(received[0].getStringExtra("error"));
            assertArrayEquals(payload,received[0].getByteArrayExtra("payload"));
            assertEquals("audio/mpeg",received[0].getStringExtra("mime"));
            assertTrue(received[0].getBooleanExtra("writeDenied",false));
            assertNotEquals(android.os.Process.myUid(),received[0].getIntExtra("uid",-1));
        } finally {context.unregisterReceiver(receiver);source.delete();}
    }

    @Test public void providerCannotOpenPagesOrWriteAndShareCarriesGrant() throws Exception {
        Context context=InstrumentationRegistry.getInstrumentation().getTargetContext();
        File folder=new File(context.getFilesDir(),"data/anvaya_notes_assets/synthetic");folder.mkdirs();
        File page=new File(folder,"private.pdf");
        try(FileOutputStream out=new FileOutputStream(page)) {out.write("%PDF-private".getBytes());}
        Uri uri=FileProvider.getUriForFile(context,context.getPackageName()+".note_media",page);
        try {
            context.getContentResolver().openFileDescriptor(uri,"r");
            fail("Provider exposed a handwritten page");
        } catch(FileNotFoundException expected) {} finally {page.delete();}
        Intent share=MediaIntents.share(Uri.parse("content://in.anvaya.privateapp.note_media/media/synthetic/media/synthetic.mp3"),"audio/mpeg");
        assertEquals(Intent.ACTION_SEND,share.getAction());
        assertNotNull(share.getParcelableExtra(Intent.EXTRA_STREAM));
        assertTrue((share.getFlags() & Intent.FLAG_GRANT_READ_URI_PERMISSION)!=0);
    }
    @Test public void absentPlayerAndChooserCancellationPreserveNote() throws Exception {
        android.app.Instrumentation instrumentation=InstrumentationRegistry.getInstrumentation();
        Intent launch=new Intent(instrumentation.getTargetContext(),MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        MainActivity activity=(MainActivity)instrumentation.startActivitySync(launch);
        android.webkit.WebView[] web={null};
        long deadline=System.currentTimeMillis()+90000;
        while(web[0]==null && System.currentTimeMillis()<deadline) {
            instrumentation.runOnMainSync(()->web[0]=findWeb(activity.getWindow().getDecorView()));
            Thread.sleep(100);
        }
        assertNotNull("Workspace WebView",web[0]);
        waitForWorkspace(instrumentation,web[0]);
        // Resolve a real production-owned synthetic note/file, never a test-only
        // implementation path. Native errors/chooser cancellation keep it open.
        String fixture="__import__('personal_learning_assistant.services.anvaya_notes_service',fromlist=['AnvayaNotesService']).AnvayaNotesService().create_handwritten_note({'title':'Synthetic media return note'},[('page.pdf',b'%PDF-1.4 synthetic')])['id']";
        String note=com.chaquo.python.Python.getInstance().getModule("builtins").callAttr("eval",fixture,com.chaquo.python.Python.getInstance().getModule("builtins").callAttr("dict")).toString();
        String add="__import__('personal_learning_assistant.services.notes_media_service',fromlist=['NotesMediaStore']).NotesMediaStore(__import__('personal_learning_assistant.repositories.json.anvaya_notes_repository',fromlist=['AnvayaNotesRepository']).AnvayaNotesRepository()).add('"+note+"',[('audio.mp3',__import__('io').BytesIO(b'ID3'+b'0'*40))])[0]['id']";
        String asset=com.chaquo.python.Python.getInstance().getModule("builtins").callAttr("eval",add,com.chaquo.python.Python.getInstance().getModule("builtins").callAttr("dict")).toString();
        String[] url={null}; CountDownLatch loaded=new CountDownLatch(1);
        instrumentation.runOnMainSync(()->web[0].evaluateJavascript("location.origin",value->{url[0]=value.substring(1,value.length()-1);loaded.countDown();}));
        assertTrue(loaded.await(10,TimeUnit.SECONDS));
        instrumentation.runOnMainSync(()->web[0].loadUrl(url[0]+"/notes/view/"+note));
        waitForText(instrumentation,web[0],"Synthetic media return note");
        java.util.concurrent.atomic.AtomicInteger dispatches=new java.util.concurrent.atomic.AtomicInteger();
        android.app.Instrumentation.ActivityMonitor monitor=new android.app.Instrumentation.ActivityMonitor() {
            @Override public android.app.Instrumentation.ActivityResult onStartActivity(Intent intent) {
                if(Intent.ACTION_VIEW.equals(intent.getAction())) {
                    dispatches.incrementAndGet();
                    throw new ActivityNotFoundException("Synthetic no-compatible-player case");
                }
                return null;
            }
        };
        instrumentation.addMonitor(monitor);
        java.util.concurrent.atomic.AtomicReference<String> navigation=new java.util.concurrent.atomic.AtomicReference<>("no navigation");
        instrumentation.runOnMainSync(()->{
            android.webkit.WebViewClient original=web[0].getWebViewClient();
            web[0].setWebViewClient(new android.webkit.WebViewClient() {
                @Override public boolean shouldOverrideUrlLoading(android.webkit.WebView view,android.webkit.WebResourceRequest request) {
                    navigation.set(request.getUrl()+" gesture="+request.hasGesture()+" main="+request.isForMainFrame());
                    return original.shouldOverrideUrlLoading(view,request);
                }
                @Override public android.webkit.WebResourceResponse shouldInterceptRequest(android.webkit.WebView view,android.webkit.WebResourceRequest request) {
                    return original.shouldInterceptRequest(view,request);
                }
            });
            web[0].evaluateJavascript("document.addEventListener('click',e=>{window.__mediaTap=JSON.stringify({trusted:e.isTrusted,href:e.target.closest('a')?.href})},true)",null);
        });
        try {
            MediaRequest request=MediaRequest.parse(new LocalOrigin(url[0]),url[0]+"/notes/media/"+note+"/"+asset+"/open",true,true);
            tapMediaLink(instrumentation,web[0]);
            deadline=System.currentTimeMillis()+20000;
            while(dispatches.get()==0 && System.currentTimeMillis()<deadline) Thread.sleep(100);
            assertEquals("Native dispatch; observed "+navigation.get()+"; DOM "+domState(instrumentation,web[0]),1,dispatches.get());
            instrumentation.waitForIdleSync();
            android.view.accessibility.AccessibilityNodeInfo root=instrumentation.getUiAutomation().getRootInActiveWindow();
            assertNotNull(root);
            assertFalse(root.findAccessibilityNodeInfosByText("No compatible player found").isEmpty());
            // Android back dismisses this native fallback; the same WebView/note remains.
            instrumentation.sendKeyDownUpSync(android.view.KeyEvent.KEYCODE_BACK);
            waitForText(instrumentation,web[0],"Synthetic media return note");
        } finally {instrumentation.removeMonitor(monitor);}
        android.app.Instrumentation.ActivityMonitor cancel=new android.app.Instrumentation.ActivityMonitor() {
            @Override public android.app.Instrumentation.ActivityResult onStartActivity(Intent intent) {
                if(Intent.ACTION_VIEW.equals(intent.getAction())) {
                    return new android.app.Instrumentation.ActivityResult(Activity.RESULT_CANCELED,null);
                }
                return null;
            }
        };
        instrumentation.addMonitor(cancel);
        try {
            MediaRequest request=MediaRequest.parse(new LocalOrigin(url[0]),url[0]+"/notes/media/"+note+"/"+asset+"/open",true,true);
            instrumentation.runOnMainSync(()->activity.openExternalMedia(request));
            Thread.sleep(1000);
            waitForText(instrumentation,web[0],"Synthetic media return note");
        } finally {instrumentation.removeMonitor(cancel);}
    }
    private void tapMediaLink(android.app.Instrumentation instrumentation,android.webkit.WebView web) throws Exception {
        long deadline=System.currentTimeMillis()+10000;
        String[] bounds={null};
        while(System.currentTimeMillis()<deadline) {
            CountDownLatch done=new CountDownLatch(1);
            instrumentation.runOnMainSync(()->web.evaluateJavascript("(()=>{const a=document.querySelector('.notes-media-open');if(!a)return null;a.scrollIntoView({block:'center'});const r=a.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2,width:innerWidth}})()",value->{bounds[0]=value;done.countDown();}));
            assertTrue(done.await(10,TimeUnit.SECONDS));
            if(bounds[0]!=null && !"null".equals(bounds[0])) break;
            Thread.sleep(100);
        }
        assertNotNull(bounds[0]);
        org.json.JSONObject point=new org.json.JSONObject(bounds[0]);
        int[] location=new int[2];instrumentation.runOnMainSync(()->web.getLocationOnScreen(location));
        float scale=web.getWidth()/(float)point.getDouble("width");
        float x=location[0]+(float)point.getDouble("x")*scale;
        float y=location[1]+(float)point.getDouble("y")*scale;
        CountDownLatch frame=new CountDownLatch(1);
        instrumentation.runOnMainSync(()->web.postVisualStateCallback(System.nanoTime(),new android.webkit.WebView.VisualStateCallback() {
            @Override public void onComplete(long id) {web.postOnAnimation(frame::countDown);}
        }));
        assertTrue("Scrolled link compositor frame",frame.await(10,TimeUnit.SECONDS));
        long now=android.os.SystemClock.uptimeMillis();
        android.view.MotionEvent down=android.view.MotionEvent.obtain(now,now,android.view.MotionEvent.ACTION_DOWN,x,y,0);
        android.view.MotionEvent up=android.view.MotionEvent.obtain(now,now+80,android.view.MotionEvent.ACTION_UP,x,y,0);
        down.setSource(android.view.InputDevice.SOURCE_TOUCHSCREEN);
        up.setSource(android.view.InputDevice.SOURCE_TOUCHSCREEN);
        assertTrue("Touch DOWN injected",instrumentation.getUiAutomation().injectInputEvent(down,true));
        assertTrue("Touch UP injected",instrumentation.getUiAutomation().injectInputEvent(up,true));down.recycle();up.recycle();
    }
    @Test public void mediaRemainsAfterForceStop() throws Exception {
        android.app.Instrumentation instrumentation=InstrumentationRegistry.getInstrumentation();
        MainActivity activity=(MainActivity)instrumentation.startActivitySync(new Intent(instrumentation.getTargetContext(),MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        long deadline=System.currentTimeMillis()+90000;
        while(System.currentTimeMillis()<deadline) {
            android.webkit.WebView[] web={null};
            instrumentation.runOnMainSync(()->web[0]=findWeb(activity.getWindow().getDecorView()));
            if(web[0]!=null) break;
            Thread.sleep(100);
        }
        String check="(lambda s: all(s.resolve(n['id'],a['id'])['path'].is_file() for n in s.repository.list_notes() if n.get('title')=='Synthetic media return note' for a in n.get('media',[])) and any(n.get('title')=='Synthetic media return note' and n.get('media') for n in s.repository.list_notes()))(__import__('personal_learning_assistant.services.notes_media_service',fromlist=['NotesMediaStore']).NotesMediaStore(__import__('personal_learning_assistant.repositories.json.anvaya_notes_repository',fromlist=['AnvayaNotesRepository']).AnvayaNotesRepository()))";
        assertTrue(com.chaquo.python.Python.getInstance().getModule("builtins").callAttr("eval",check,com.chaquo.python.Python.getInstance().getModule("builtins").callAttr("dict")).toBoolean());
    }
    private String domState(android.app.Instrumentation instrumentation,android.webkit.WebView web) throws Exception {
        CountDownLatch done=new CountDownLatch(1);String[] state={null};
        instrumentation.runOnMainSync(()->web.evaluateJavascript("JSON.stringify({url:location.href,tap:window.__mediaTap,link:document.querySelector('.notes-media-open')?.href,text:document.body?.innerText.slice(-600)})",result->{state[0]=result;done.countDown();}));
        assertTrue(done.await(10,TimeUnit.SECONDS));return state[0];
    }
    private android.webkit.WebView findWeb(android.view.View view) {
        if(view instanceof android.webkit.WebView) return (android.webkit.WebView)view;
        if(view instanceof android.view.ViewGroup) {
            android.view.ViewGroup group=(android.view.ViewGroup)view;
            for(int i=0;i<group.getChildCount();i++) {android.webkit.WebView web=findWeb(group.getChildAt(i));if(web!=null)return web;}
        }
        return null;
    }
    private void waitForWorkspace(android.app.Instrumentation instrumentation,android.webkit.WebView web) throws Exception {
        // Native construction precedes the async capability-cookie callback and
        // first loadUrl. about:blank has origin "null" and must not be used as
        // the base for the reader URL. Wait for the real authenticated document.
        long deadline=System.currentTimeMillis()+30000;
        while(System.currentTimeMillis()<deadline) {
            CountDownLatch done=new CountDownLatch(1);String[] value={null};
            instrumentation.runOnMainSync(()->web.evaluateJavascript("location.origin.startsWith('http://127.0.0.1:') && document.readyState==='complete' && !!document.querySelector('main')",result->{value[0]=result;done.countDown();}));
            assertTrue(done.await(10,TimeUnit.SECONDS));
            if("true".equals(value[0])) return;
            Thread.sleep(100);
        }
        fail("Authenticated workspace did not finish its initial load");
    }
    private void waitForText(android.app.Instrumentation instrumentation,android.webkit.WebView web,String text) throws Exception {
        long deadline=System.currentTimeMillis()+30000;
        while(System.currentTimeMillis()<deadline) {
            CountDownLatch done=new CountDownLatch(1);String[] value={null};
            instrumentation.runOnMainSync(()->web.evaluateJavascript("document.readyState==='complete' && document.body.innerText.includes("+org.json.JSONObject.quote(text)+")",result->{value[0]=result;done.countDown();}));
            assertTrue(done.await(10,TimeUnit.SECONDS));
            if("true".equals(value[0])) return;
            Thread.sleep(100);
        }
        CountDownLatch diagnostic=new CountDownLatch(1);String[] state={null};
        instrumentation.runOnMainSync(()->web.evaluateJavascript("JSON.stringify({url:location.href,ready:document.readyState,hasMain:!!document.querySelector('main'),text:document.body?.innerText.slice(0,1000)})",result->{state[0]=result;diagnostic.countDown();}));
        diagnostic.await(10,TimeUnit.SECONDS);
        fail("Expected synthetic note state: "+state[0]);
    }

}

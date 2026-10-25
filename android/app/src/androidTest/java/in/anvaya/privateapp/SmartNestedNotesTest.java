package in.anvaya.privateapp;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.*;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Build;
import android.os.SystemClock;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.WebView;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import org.json.JSONObject;
import org.json.JSONTokener;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.File;
import java.io.FileOutputStream;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import static org.junit.Assert.*;

/** Installed WebView + embedded Python + cross-UID receiver; synthetic records only.
 * Each test is independently runnable. Fixtures remain for optional force-stop
 * inspection; Activity recreation below is not presented as process-death proof.
 */
@RunWith(AndroidJUnit4.class)
public class SmartNestedNotesTest {
    private final Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
    private MainActivity activity;
    private WebView web;
    private String origin;

    private <T> T find(View view, Class<T> type) {
        if (type.isInstance(view)) return type.cast(view);
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup)view;
            for (int i=0; i<group.getChildCount(); i++) {
                T child = find(group.getChildAt(i), type);
                if (child != null) return child;
            }
        }
        return null;
    }
    private void open() throws Exception {
        activity = (MainActivity)instrumentation.startActivitySync(new Intent(instrumentation.getTargetContext(), MainActivity.class)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        long deadline = SystemClock.uptimeMillis()+90000;
        while (SystemClock.uptimeMillis()<deadline) {
            boolean[] revealed = {false};
            instrumentation.runOnMainSync(() -> {
                View decor = activity.getWindow().getDecorView();
                web = find(decor, WebView.class);
                revealed[0] = web != null && find(decor, StartupSplashView.class) == null && web.hasWindowFocus();
            });
            if (revealed[0] && "true".equals(js("location.origin.startsWith('http://127.0.0.1:') && document.readyState==='complete' && !!document.querySelector('main')"))) {
                origin = string("location.origin"); return;
            }
            Thread.sleep(100);
        }
        fail("Authenticated workspace did not paint and gain focus within 90 seconds");
    }
    private void close() {
        if (activity != null) instrumentation.runOnMainSync(activity::finish);
        instrumentation.waitForIdleSync();
        activity = null; web = null;
    }
    private String js(String script) throws Exception {
        CountDownLatch done = new CountDownLatch(1);
        String[] result = {null};
        instrumentation.runOnMainSync(() -> web.evaluateJavascript(script, value -> {result[0]=value;done.countDown();}));
        assertTrue("WebView JavaScript callback", done.await(10, TimeUnit.SECONDS));
        return result[0];
    }
    private String string(String script) throws Exception { return (String)new JSONTokener(js(script)).nextValue(); }
    private PyObject py(String expression) {
        PyObject builtins = Python.getInstance().getModule("builtins");
        return builtins.callAttr("eval", expression, builtins.callAttr("dict"));
    }
    private String createTyped(String title) {
        return py("__import__('personal_learning_assistant.services.anvaya_notes_service',fromlist=['AnvayaNotesService']).AnvayaNotesService().create_typed_note({'title':"
            + JSONObject.quote(title) + ", 'body':'Synthetic original content remains intact.'})['id']").toString();
    }
    private void waitFor(String expression) throws Exception {
        long deadline = SystemClock.uptimeMillis()+30000;
        while (SystemClock.uptimeMillis()<deadline) {
            if ("true".equals(js("document.readyState==='complete' && ("+expression+")"))) return;
            Thread.sleep(100);
        }
        fail("Missing DOM state: "+expression+"; actual="+js("JSON.stringify({url:location.href,ready:document.readyState,status:document.querySelector('#section-status')?.textContent,media:document.querySelector('#notes-media-status')?.textContent,text:document.body?.innerText.slice(0,2500)})"));
    }
    private void go(String note) throws Exception {
        js("window.__smartNavigationPending=true");
        instrumentation.runOnMainSync(() -> web.loadUrl(origin+"/notes/view/"+note));
        waitFor("!window.__smartNavigationPending && location.pathname==="+JSONObject.quote("/notes/view/"+note)+" && !!document.querySelector('#mini-original-content') && !document.querySelector('#notes-media-status').textContent.includes('Loading')");
    }
    private String row(String title) {
        return "Array.from(document.querySelectorAll('#section-list > .mini-note')).find(d=>d.querySelector('summary').textContent==="+JSONObject.quote(title)+")";
    }
    private String rowById(String id) { return "document.getElementById("+JSONObject.quote(id)+")"; }
    private void expand(String id) throws Exception {
        js(rowById(id)+".open=true");
        waitFor(rowById(id)+".open && "+rowById(id)+".querySelector('.mini-note-content').dataset.loaded==='1'");
    }
    private String addSection(String title, String body) throws Exception {
        js("document.querySelector('#section-add').click()");
        waitFor("!document.querySelector('#section-editor').hidden");
        js("document.querySelector('#section-title').value="+JSONObject.quote(title)+";document.querySelector('#section-body').value="+JSONObject.quote(body)+";document.querySelector('#section-editor').requestSubmit()");
        waitFor("document.querySelector('#section-editor').hidden && document.querySelector('#nested-notes').getAttribute('aria-busy')==='false' && !!("+row(title)+")");
        return string("("+row(title)+").id");
    }
    private void sectionAction(String id, String label) throws Exception {
        expand(id);
        String script = "(()=>{const row="+rowById(id)+";const more=row.querySelector('.mini-note-more');if(more)more.open=true;Array.from(row.querySelectorAll('.mini-note-actions button')).find(b=>b.textContent==="+JSONObject.quote(label)+").click()})()";
        // confirm() holds evaluation until Android's real dialog is answered.
        if ("Delete".equals(label)) instrumentation.runOnMainSync(() -> web.evaluateJavascript(script,null));
        else js(script);
    }
    private void reload() throws Exception {
        js("window.__smartNavigationPending=true;location.reload()");
        waitFor("!window.__smartNavigationPending && !!document.querySelector('#nested-notes') && !!document.querySelector('#mini-original-content')");
    }
    private void acceptConfirmation() throws Exception {
        android.accessibilityservice.AccessibilityServiceInfo info = instrumentation.getUiAutomation().getServiceInfo();
        info.flags |= android.accessibilityservice.AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS;
        instrumentation.getUiAutomation().setServiceInfo(info);
        long deadline = SystemClock.uptimeMillis()+10000;
        while (SystemClock.uptimeMillis()<deadline) {
            android.view.accessibility.AccessibilityNodeInfo root = instrumentation.getUiAutomation().getRootInActiveWindow();
            if (root != null) {
                java.util.List<android.view.accessibility.AccessibilityNodeInfo> buttons = root.findAccessibilityNodeInfosByViewId("android:id/button1");
                if (!buttons.isEmpty()) {
                    assertTrue("Native delete confirmation accepted", buttons.get(0).performAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK)); return;
                }
            }
            Thread.sleep(100);
        }
        fail("Native mini-note deletion confirmation was not shown");
    }
    private void frame() throws Exception {
        CountDownLatch rendered = new CountDownLatch(1);
        instrumentation.runOnMainSync(() -> web.postVisualStateCallback(System.nanoTime(), new WebView.VisualStateCallback() {
            @Override public void onComplete(long id) {web.postOnAnimation(rendered::countDown);}
        }));
        assertTrue("Visible workspace compositor frame", rendered.await(10, TimeUnit.SECONDS));
        instrumentation.waitForIdleSync();
    }
    private void screenshot(String name) throws Exception {
        frame();
        Bitmap screenshot = instrumentation.getUiAutomation().takeScreenshot();
        assertNotNull("Actual installed UI screenshot", screenshot);
        File folder = new File(instrumentation.getTargetContext().getFilesDir(), "evidence");
        assertTrue(folder.isDirectory() || folder.mkdirs());
        try (FileOutputStream output = new FileOutputStream(new File(folder, name+".png"))) {
            assertTrue(screenshot.compress(Bitmap.CompressFormat.PNG,100,output));
        } finally {screenshot.recycle();}
    }
    private void tap(String selector) throws Exception {
        waitFor("!!document.querySelector("+JSONObject.quote(selector)+")");
        JSONObject point = new JSONObject(js("(()=>{const a=document.querySelector("+JSONObject.quote(selector)+");a.scrollIntoView({block:'center',behavior:'instant'});const r=a.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2,width:innerWidth}})()"));
        frame();
        int[] location = new int[2]; float[] scale = new float[1];
        instrumentation.runOnMainSync(() -> {web.getLocationOnScreen(location);scale[0]=web.getWidth()/(float)point.optDouble("width");});
        float x = location[0]+(float)point.getDouble("x")*scale[0];
        float y = location[1]+(float)point.getDouble("y")*scale[0];
        long now = SystemClock.uptimeMillis();
        MotionEvent down = MotionEvent.obtain(now,now,MotionEvent.ACTION_DOWN,x,y,0);
        MotionEvent up = MotionEvent.obtain(now,now+80,MotionEvent.ACTION_UP,x,y,0);
        down.setSource(android.view.InputDevice.SOURCE_TOUCHSCREEN);up.setSource(android.view.InputDevice.SOURCE_TOUCHSCREEN);
        try {
            assertTrue("Trusted attachment touch DOWN",instrumentation.getUiAutomation().injectInputEvent(down,true));
            assertTrue("Trusted attachment touch UP",instrumentation.getUiAutomation().injectInputEvent(up,true));
        } finally {down.recycle();up.recycle();}
    }

    @Test public void typedMiniNotesCrudAccordionAndActivityRestartPersistence() throws Exception {
        open();
        try {
            String note = createTyped("Synthetic nested notes · examination revision");
            go(note);
            assertEquals("Original content starts collapsed and unloaded","true",js("!document.querySelector('#mini-original-content').open && !document.querySelector('#mini-original-content .mini-note-content').dataset.loaded"));
            String first = addSection("Recall cues", "**Key relationship**\n\n- [ ] Explain the example without looking.");
            String second = addSection("Exam checklist", "- Define the terms\n- Compare the two examples");
            expand(first); expand(second);
            assertEquals("Single-open mode closes its sibling","false",js(rowById(first)+".open"));
            js("document.querySelector('#section-multiple').click()");
            expand(first);
            assertEquals("Multiple-open mode keeps both sections visible","true",js(rowById(first)+".open && "+rowById(second)+".open"));
            js("document.querySelector('#sections-collapse').click()");
            assertEquals("Collapse all closes every section","0",js("document.querySelectorAll('#section-list > .mini-note[open]').length"));
            js("document.querySelector('#sections-expand').click()");
            waitFor("document.querySelectorAll('#section-list > .mini-note[open] .mini-note-content[data-loaded]').length===3");
            assertEquals("Markdown checklist renders as a read-only checkbox","true",js(rowById(first)+".querySelector('input[type=checkbox]').disabled"));
            js("document.querySelector('#nested-notes').scrollIntoView({block:'start',behavior:'instant'})");
            screenshot("android-smart-mini-notes-expanded");
            sectionAction(first,"Edit");
            waitFor("!document.querySelector('#section-editor').hidden");
            js("document.querySelector('#section-title').value='Recall cues revised';document.querySelector('#section-body').value="+JSONObject.quote("**Revised retrieval cue**\n\n- [x] Explain the example without looking.")+";document.querySelector('#section-editor').requestSubmit()");
            waitFor("document.querySelector('#section-editor').hidden && !!("+row("Recall cues revised")+") && document.querySelector('#nested-notes').getAttribute('aria-busy')==='false'");
            sectionAction(second,"Delete");
            acceptConfirmation();
            waitFor("!"+rowById(second)+" && document.querySelectorAll('#section-list > .mini-note').length===2 && document.querySelector('#nested-notes').getAttribute('aria-busy')==='false'");
            reload();
            waitFor("document.querySelectorAll('#section-list > .mini-note').length===2 && !!("+row("Recall cues revised")+")");
            expand(first);
            waitFor(rowById(first)+".textContent.includes('Revised retrieval cue')");
            assertTrue("Original body survives section CRUD",py("__import__('personal_learning_assistant.services.anvaya_notes_service',fromlist=['AnvayaNotesService']).AnvayaNotesService().repository.get_note('"+note+"')['body']=='Synthetic original content remains intact.'").toBoolean());
            instrumentation.getTargetContext().getSharedPreferences("synthetic-evidence",0).edit()
                .putString("smartNestedTypedNote",note).putString("smartNestedSection",first).commit();
            close(); open(); go(note); expand(first);
            waitFor(rowById(first)+".textContent.includes('Revised retrieval cue')");
            assertEquals("Deleted section stays deleted after Activity restart","null",js(rowById(second)));
            js(rowById(first)+".scrollIntoView({block:'start',behavior:'instant'})");
            screenshot("android-smart-mini-notes-after-activity-restart");
        } finally {close();}
    }

    @Test public void typedDocumentUsesProductionGestureIntentAndExternalUidReadGrant() throws Exception {
        open();
        try {
            String note = createTyped("Synthetic typed note · attachment return");
            go(note);
            String section = addSection("Reference material", "Open the reference in a device application, then return to this note.");
            String payload = "ANVAYA synthetic typed attachment reference";
            String asset = py("__import__('personal_learning_assistant.services.notes_media_service',fromlist=['NotesMediaStore']).NotesMediaStore(__import__('personal_learning_assistant.repositories.json.anvaya_notes_repository',fromlist=['AnvayaNotesRepository']).AnvayaNotesRepository()).add('"+note+"',[('Synthetic reference.txt',__import__('io').BytesIO(b'"+payload+"'))],section_id='"+section.substring(5)+"')[0]['id']").toString();
            go(note);
            waitFor("document.querySelector('#notes-media-list .notes-media-open')?.textContent==='Synthetic reference.txt'");
            expand(section);
            assertEquals("Attachment remains scoped to the mini-note","true",js(rowById(section)+".querySelector('.mini-note-files').textContent.includes('Synthetic reference.txt')"));
            js("window.__typedAttachmentReturn='retained'");
            AtomicReference<Intent> launched = new AtomicReference<>(), received = new AtomicReference<>();
            CountDownLatch result = new CountDownLatch(1);
            Context context = instrumentation.getTargetContext();
            BroadcastReceiver receiver = new BroadcastReceiver() {
                @Override public void onReceive(Context c, Intent report) {received.set(report);result.countDown();}
            };
            IntentFilter filter = new IntentFilter("in.anvaya.privateapp.TEST_MEDIA_RESULT");
            if (Build.VERSION.SDK_INT>=33) context.registerReceiver(receiver,filter,Context.RECEIVER_EXPORTED);
            else context.registerReceiver(receiver,filter);
            Instrumentation.ActivityMonitor monitor = new Instrumentation.ActivityMonitor() {
                @Override public Instrumentation.ActivityResult onStartActivity(Intent intent) {
                    Uri uri = intent.getData();
                    if (Intent.ACTION_VIEW.equals(intent.getAction()) && uri != null
                        && "content".equals(uri.getScheme()) && (context.getPackageName()+".note_media").equals(uri.getAuthority())) {
                        launched.set(new Intent(intent));
                        // Redirect the production Intent to the separate-UID test
                        // receiver; keep its real URI, MIME and temporary grants.
                        intent.setComponent(new ComponentName(instrumentation.getContext().getPackageName(),"in.anvaya.privateapp.test.MediaReceiverActivity"));
                    }
                    return null;
                }
            };
            instrumentation.addMonitor(monitor);
            try {
                tap("#notes-media-list .notes-media-open");
                assertTrue("Actual external recipient returned",result.await(20,TimeUnit.SECONDS));
                Intent sent = launched.get(), report = received.get();
                assertNotNull("Production main-frame gesture dispatched ACTION_VIEW",sent);
                assertEquals("text/plain",sent.getType());
                assertEquals("content",sent.getData().getScheme());
                assertTrue((sent.getFlags() & Intent.FLAG_GRANT_READ_URI_PERMISSION)!=0);
                assertEquals(0,sent.getFlags() & Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
                assertNotNull(sent.getClipData());
                assertEquals(sent.getData(),sent.getClipData().getItemAt(0).getUri());
                assertFalse(sent.toUri(0).contains(context.getFilesDir().getPath()));
                assertNotNull(report);assertNull(report.getStringExtra("error"));
                assertArrayEquals(payload.getBytes("UTF-8"),report.getByteArrayExtra("payload"));
                assertEquals("text/plain",report.getStringExtra("mime"));
                assertTrue(report.getBooleanExtra("writeDenied",false));
                assertNotEquals(android.os.Process.myUid(),report.getIntExtra("uid",-1));
                // Same provider-backed typed URI must also be shareable.
                Intent share = MediaIntents.share(sent.getData(),sent.getType());
                assertEquals(Intent.ACTION_SEND,share.getAction());
                assertEquals(sent.getData(),share.getParcelableExtra(Intent.EXTRA_STREAM));
                assertEquals(sent.getData(),share.getClipData().getItemAt(0).getUri());
                assertEquals(0,share.getFlags() & Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
            } finally {instrumentation.removeMonitor(monitor);context.unregisterReceiver(receiver);}
            waitFor("location.pathname==="+JSONObject.quote("/notes/view/"+note)+" && window.__typedAttachmentReturn==='retained'");
            instrumentation.getTargetContext().getSharedPreferences("synthetic-evidence",0).edit()
                .putString("smartTypedMediaNote",note).putString("smartTypedMediaAsset",asset).putString("smartTypedMediaSection",section).commit();
            reload();
            waitFor("document.querySelector('#notes-media-list .notes-media-open')?.textContent==='Synthetic reference.txt'");
            close(); open(); go(note); expand(section);
            waitFor(rowById(section)+".querySelector('.mini-note-files').textContent.includes('Synthetic reference.txt')");
            js(rowById(section)+".scrollIntoView({block:'start',behavior:'instant'})");
            screenshot("android-smart-typed-attachment-after-activity-restart");
        } finally {close();}
    }
    @Test public void savedTypedNotesAndAttachmentsSurviveForceStop() throws Exception {
        open();
        try {
            android.content.SharedPreferences evidence=instrumentation.getTargetContext().getSharedPreferences("synthetic-evidence",0);
            String note=evidence.getString("smartNestedTypedNote",null), section=evidence.getString("smartNestedSection",null);
            String mediaNote=evidence.getString("smartTypedMediaNote",null), asset=evidence.getString("smartTypedMediaAsset",null), mediaSection=evidence.getString("smartTypedMediaSection",null);
            assertNotNull("Earlier installed CRUD journey stored a real note",note);
            assertNotNull(section);assertNotNull(mediaNote);assertNotNull(asset);assertNotNull(mediaSection);
            go(note);expand(section);
            waitFor(rowById(section)+".textContent.includes('Revised retrieval cue')");
            go(mediaNote);expand(mediaSection);
            waitFor(rowById(mediaSection)+".querySelector('.mini-note-files').textContent.includes('Synthetic reference.txt')");
            assertTrue("Original stored file survives process death",py("__import__('personal_learning_assistant.services.notes_media_service',fromlist=['NotesMediaStore']).NotesMediaStore(__import__('personal_learning_assistant.repositories.json.anvaya_notes_repository',fromlist=['AnvayaNotesRepository']).AnvayaNotesRepository()).resolve('"+mediaNote+"','"+asset+"')['path'].is_file()").toBoolean());
            js(rowById(mediaSection)+".scrollIntoView({block:'start',behavior:'instant'})");
            screenshot("android-smart-typed-after-force-stop");
        } finally {close();}
    }

}

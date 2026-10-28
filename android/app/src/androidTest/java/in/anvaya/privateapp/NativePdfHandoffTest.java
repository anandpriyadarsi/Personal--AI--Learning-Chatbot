package in.anvaya.privateapp;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.*;
import android.graphics.Bitmap;
import android.graphics.Paint;
import android.graphics.pdf.PdfDocument;
import android.net.Uri;
import android.os.Build;
import android.webkit.WebView;
import androidx.core.content.FileProvider;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import com.chaquo.python.Python;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.*;
import java.security.MessageDigest;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;
import static org.junit.Assert.*;

/** Real gesture -> production bridge -> installed, separate-UID PDF viewer. */
@RunWith(AndroidJUnit4.class)
public class NativePdfHandoffTest {
    private final Instrumentation inst=InstrumentationRegistry.getInstrumentation();
    private final Context context=inst.getTargetContext();
    private MainActivity activity;
    private WebView web;
    private String origin;
    private JSONObject fixture;
    private File fixtureFile(){return new File(context.getFilesDir(),"evidence/native-pdf-fixture.json");}
    private File routeFailureFile(){return new File(context.getFilesDir(),"evidence/android-native-pdf-route-failure.txt");}
    private String row(){return "[data-document-id=\""+fixture.optString("id")+"\"]";}
    private com.chaquo.python.PyObject eval(String expression){return Python.getInstance().getModule("builtins").callAttr("eval",expression,Python.getInstance().getModule("builtins").callAttr("dict"));}
    private void workspace(boolean create) throws Exception {
        activity=(MainActivity)inst.startActivitySync(new Intent(context,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        long deadline=System.currentTimeMillis()+90000;
        while(System.currentTimeMillis()<deadline){
            inst.runOnMainSync(()->web=findWeb(activity.getWindow().getDecorView()));
            if(web!=null&&"true".equals(js("location.origin.startsWith('http://127.0.0.1:')&&document.readyState==='complete'&&!!document.querySelector('main')")))break;
            Thread.sleep(100);
        }
        assertNotNull("Authenticated workspace",web);
        assertEquals("true",js("location.origin.startsWith('http://127.0.0.1:')"));
        origin=new org.json.JSONTokener(js("location.origin")).nextValue().toString();
        deadline=System.currentTimeMillis()+15000;boolean[] visible={false};
        while(System.currentTimeMillis()<deadline){inst.runOnMainSync(()->visible[0]=web.hasWindowFocus()&&web.getImportantForAccessibility()==android.view.View.IMPORTANT_FOR_ACCESSIBILITY_AUTO);if(visible[0])break;Thread.sleep(100);}
        assertTrue("Splash is dismissed",visible[0]);
        if(create&&!fixtureFile().isFile())createFixture();
        assertTrue("Imported fixture persists",fixtureFile().isFile());fixture=new JSONObject(read(fixtureFile()));
        assertManagedOriginal();
        assertEquals("Fixture and running web service use the same durable Library",new File(context.getFilesDir(),"data/native_library").getCanonicalPath(),eval("str(__import__('personal_learning_assistant.android_runtime',fromlist=['_runtime'])._runtime.app.config['NATIVE_LIBRARY_ROOT'])").toString());
        routeFailureFile().delete();
        eval("__import__('flask').got_request_exception.connect(lambda sender,exception: __import__('pathlib').Path("+JSONObject.quote(routeFailureFile().getCanonicalPath())+").write_text(''.join(__import__('traceback').format_exception(type(exception),exception,exception.__traceback__)),encoding='utf-8'),sender=__import__('personal_learning_assistant.android_runtime',fromlist=['_runtime'])._runtime.app,weak=False)");
        js("window.__nativePdfNavigationPending=true");
        inst.runOnMainSync(()->web.loadUrl(origin+"/library/files"));waitJs("!window.__nativePdfNavigationPending&&location.pathname==='/library/files'&&!!document.querySelector("+JSONObject.quote(row())+")");
    }
    private void createFixture() throws Exception {
        ByteArrayOutputStream output=new ByteArrayOutputStream();PdfDocument pdf=new PdfDocument();
        try {
            for(int n=1;n<=3;n++){PdfDocument.Page page=pdf.startPage(new PdfDocument.PageInfo.Builder(300,420,n).create());Paint paint=new Paint();paint.setTextSize(18);page.getCanvas().drawText("Synthetic PDF page "+n,30,70,paint);pdf.finishPage(page);}
            pdf.writeTo(output);
        } finally {pdf.close();}
        String encoded=android.util.Base64.encodeToString(output.toByteArray(),android.util.Base64.NO_WRAP);
        String expression="(lambda lib: (lambda d: [d['id'],d['sha256'],d['size']])(lib.update(lib.upload(__import__('io').BytesIO(__import__('base64').b64decode('"+encoded+"')),'Imported lecture.pdf',indexing=False)['id'],display_name='गणित π + λ ∈ ℝ',subject_id='ma103',tags=['native-viewer-test'])))(__import__('personal_learning_assistant.services.native_document_library',fromlist=['NativeDocumentLibrary']).NativeDocumentLibrary("+JSONObject.quote(context.getFilesDir().getCanonicalPath())+"+'/data/native_library',autostart=False))";
        java.util.List<com.chaquo.python.PyObject> item=eval(expression).asList();JSONObject data=new JSONObject();data.put("id",item.get(0).toString());data.put("sha256",item.get(1).toString());data.put("size",item.get(2).toLong());
        fixtureFile().getParentFile().mkdirs();try(FileOutputStream file=new FileOutputStream(fixtureFile())){file.write(data.toString().getBytes("UTF-8"));file.getFD().sync();}
    }
    @Test public void libraryTapOpensExternalPdfWithCurrentNameAndReadOnlyGrant() throws Exception {
        workspace(true);CountDownLatch done=new CountDownLatch(1);Intent[] report={null};
        BroadcastReceiver receiver=new BroadcastReceiver(){@Override public void onReceive(Context c,Intent value){report[0]=value;done.countDown();}};
        IntentFilter filter=new IntentFilter("in.anvaya.privateapp.TEST_PDF_RESULT");
        if(Build.VERSION.SDK_INT>=33)context.registerReceiver(receiver,filter,Context.RECEIVER_EXPORTED);else context.registerReceiver(receiver,filter);
        AtomicReference<Intent> observed=new AtomicReference<>();
        Instrumentation.ActivityMonitor route=new Instrumentation.ActivityMonitor(){@Override public Instrumentation.ActivityResult onStartActivity(Intent intent){
            if(Intent.ACTION_VIEW.equals(intent.getAction())&&"application/pdf".equals(intent.getType())){observed.set(new Intent(intent));intent.setPackage(inst.getContext().getPackageName());}return null;
        }};
        inst.addMonitor(route);
        try {
            tap(row()+" .file-main h2 a");assertTrue("Installed PDF receiver returned",done.await(25,TimeUnit.SECONDS));Intent sent=observed.get();assertNotNull(sent);
            assertNull("System owns the preferred viewer",sent.getPackage());assertNull(sent.getComponent());assertEquals(Intent.ACTION_VIEW,sent.getAction());assertEquals("application/pdf",sent.getType());assertEquals("content",sent.getData().getScheme());
            assertTrue((sent.getFlags()&Intent.FLAG_GRANT_READ_URI_PERMISSION)!=0);assertEquals(0,sent.getFlags()&Intent.FLAG_GRANT_WRITE_URI_PERMISSION);assertEquals(sent.getData(),sent.getClipData().getItemAt(0).getUri());assertFalse(sent.toUri(0).contains(context.getFilesDir().getPath()));
            assertNull(report[0].getStringExtra("error"));assertNotEquals(android.os.Process.myUid(),report[0].getIntExtra("uid",-1));assertEquals("application/pdf",report[0].getStringExtra("mime"));assertEquals("गणित π + λ ∈ ℝ.pdf",report[0].getStringExtra("filename"));assertEquals(fixture.getString("sha256"),report[0].getStringExtra("sha256"));assertEquals(fixture.getLong("size"),report[0].getLongExtra("size",-1));assertEquals(3,report[0].getIntExtra("pages",-1));assertEquals(300,report[0].getIntExtra("pageWidth",-1));assertEquals(420,report[0].getIntExtra("pageHeight",-1));assertTrue(report[0].getBooleanExtra("writeDenied",false));assertTrue(report[0].getBooleanExtra("deleteDenied",false));
            screenshot("android-native-pdf-external-viewer");inst.sendKeyDownUpSync(android.view.KeyEvent.KEYCODE_BACK);waitJs("location.pathname==='/library/files'&&!!document.querySelector('"+row()+"')");assertManagedOriginal();screenshot("android-native-pdf-library");
        } finally {inst.removeMonitor(route);context.unregisterReceiver(receiver);}
    }
    @Test public void openWithCancellationAndAbsentViewerPreserveLibrary() throws Exception {
        workspace(true);AtomicReference<Intent> chooser=new AtomicReference<>();
        Instrumentation.ActivityMonitor cancel=new Instrumentation.ActivityMonitor(){@Override public Instrumentation.ActivityResult onStartActivity(Intent intent){if(Intent.ACTION_CHOOSER.equals(intent.getAction())){chooser.set(new Intent(intent));return new Instrumentation.ActivityResult(Activity.RESULT_CANCELED,null);}return null;}};
        inst.addMonitor(cancel);
        try {
            tap(row()+" summary");tap(row()+" a[href*=\"native_action=open_with\"]");long deadline=System.currentTimeMillis()+15000;while(chooser.get()==null&&System.currentTimeMillis()<deadline)Thread.sleep(100);assertNotNull("Open with uses chooser",chooser.get());
            Intent inner=chooser.get().getParcelableExtra(Intent.EXTRA_INTENT);assertNotNull(inner);assertEquals(Intent.ACTION_VIEW,inner.getAction());assertEquals("application/pdf",inner.getType());assertEquals(0,inner.getFlags()&Intent.FLAG_GRANT_WRITE_URI_PERMISSION);waitJs("location.pathname==='/library/files'");
        } finally {inst.removeMonitor(cancel);}
        AtomicReference<Intent> saved=new AtomicReference<>();
        Instrumentation.ActivityMonitor save=new Instrumentation.ActivityMonitor(){@Override public Instrumentation.ActivityResult onStartActivity(Intent intent){
            if(Intent.ACTION_CREATE_DOCUMENT.equals(intent.getAction())){saved.set(new Intent(intent));return new Instrumentation.ActivityResult(Activity.RESULT_CANCELED,null);}return null;
        }};
        inst.addMonitor(save);
        try {
            js("document.querySelector('"+row()+" details').removeAttribute('open')");
            tap(row()+" summary");tap(row()+" a[href*=\"download=1\"]");
            long deadline=System.currentTimeMillis()+15000;while(saved.get()==null&&System.currentTimeMillis()<deadline)Thread.sleep(100);
            assertNotNull("Trusted Save / Export tap reaches system document picker",saved.get());
            assertEquals("application/pdf",saved.get().getType());
            assertEquals("गणित π + λ ∈ ℝ.pdf",saved.get().getStringExtra(Intent.EXTRA_TITLE));
            assertTrue(saved.get().hasCategory(Intent.CATEGORY_OPENABLE));
            waitJs("location.pathname==='/library/files'");assertManagedOriginal();
        } finally {inst.removeMonitor(save);}
        Instrumentation.ActivityMonitor absent=new Instrumentation.ActivityMonitor(){@Override public Instrumentation.ActivityResult onStartActivity(Intent intent){if(Intent.ACTION_VIEW.equals(intent.getAction())&&"application/pdf".equals(intent.getType()))throw new ActivityNotFoundException("Synthetic absent viewer");return null;}};
        inst.addMonitor(absent);
        try {
            js("document.querySelector('"+row()+" details').removeAttribute('open')");tap(row()+" .file-main h2 a");long deadline=System.currentTimeMillis()+15000;boolean found=false;
            while(System.currentTimeMillis()<deadline){android.view.accessibility.AccessibilityNodeInfo root=inst.getUiAutomation().getRootInActiveWindow();found=root!=null&&!root.findAccessibilityNodeInfosByText("No compatible viewer found").isEmpty();if(found)break;Thread.sleep(100);}
            assertTrue("Friendly no-viewer fallback",found);screenshot("android-native-pdf-no-viewer");inst.sendKeyDownUpSync(android.view.KeyEvent.KEYCODE_BACK);waitJs("location.pathname==='/library/files'");assertManagedOriginal();
        } finally {inst.removeMonitor(absent);}
    }
    @Test public void managedOriginalAndMetadataSurviveActivityRestart() throws Exception {
        workspace(true);String id=fixture.getString("id"),hash=fixture.getString("sha256");inst.runOnMainSync(activity::finish);inst.waitForIdleSync();workspace(false);assertEquals(id,fixture.getString("id"));assertEquals(hash,fixture.getString("sha256"));assertManagedOriginal();screenshot("android-native-pdf-after-activity-restart");
    }
    @Test public void managedOriginalSurvivesForceStop() throws Exception {workspace(false);assertManagedOriginal();screenshot("android-native-pdf-after-force-stop");}
    @Test public void documentProviderRejectsWritesAndUnrelatedFilesAndShareKeepsName() throws Exception {
        File directory=new File(context.getFilesDir(),"data/native_library/blobs");directory.mkdirs();File source=new File(directory,"synthetic-provider-policy");
        try {
            try(FileOutputStream output=new FileOutputStream(source)){output.write("%PDF-synthetic".getBytes("UTF-8"));}
            Uri uri=FileProvider.getUriForFile(context,context.getPackageName()+".documents",source,"Renamed.pdf");assertEquals("application/pdf",context.getContentResolver().getType(uri));
            for(String mode:new String[]{"w","wt","wa","rw","rwt"}){try {context.getContentResolver().openFileDescriptor(uri,mode);fail("Original allowed "+mode);}catch(FileNotFoundException expected){}}
            try{context.getContentResolver().delete(uri,null,null);fail("Original allowed deletion");}catch(SecurityException expected){}
            try{FileProvider.getUriForFile(context,context.getPackageName()+".documents",new File(context.getFilesDir(),"data/native_library/library.sqlite3"));fail("Provider exposed database");}catch(IllegalArgumentException expected){}
            Intent chooser=DocumentIntents.intent(uri,"application/pdf",DocumentIntents.Action.SHARE);assertEquals(Intent.ACTION_CHOOSER,chooser.getAction());Intent share=chooser.getParcelableExtra(Intent.EXTRA_INTENT);assertNotNull(share);assertEquals(Intent.ACTION_SEND,share.getAction());assertEquals(uri,share.getParcelableExtra(Intent.EXTRA_STREAM));assertEquals(uri,share.getClipData().getItemAt(0).getUri());assertEquals(0,share.getFlags()&Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
            assertEquals(DocumentIntents.Result.NO_COMPATIBLE_APP,DocumentIntents.launch(intent->{throw new ActivityNotFoundException();},uri,"application/pdf",DocumentIntents.Action.VIEW));assertEquals(DocumentIntents.Result.FAILED,DocumentIntents.launch(intent->{throw new SecurityException();},uri,"application/pdf",DocumentIntents.Action.VIEW));
        } finally {source.delete();}
    }
    private void assertManagedOriginal() throws Exception {
        java.util.List<com.chaquo.python.PyObject> item;
        try {
            item=Python.getInstance().getModule("personal_learning_assistant.services.native_document_library").callAttr("resolve_android_document",context.getFilesDir().getCanonicalPath(),fixture.getString("id")).asList();
        } catch(RuntimeException failure) {
            String diagnostic=originalResolverDiagnostic();
            // Instrumentation teardown closes the Activity. Log and persist the
            // underlying Python exception before that loses the installed state.
            for(String line:diagnostic.split("\\n"))System.err.println("NATIVE_PDF_RESOLVER "+line);
            File evidence=new File(context.getFilesDir(),"evidence/android-native-pdf-resolver-failure.txt");evidence.getParentFile().mkdirs();
            try(FileOutputStream output=new FileOutputStream(evidence)){output.write(diagnostic.getBytes("UTF-8"));}
            fail("Production original resolver failed: "+diagnostic);
            throw failure;
        }
        File file=new File(item.get(0).toString());assertTrue(file.isFile());assertEquals(new File(context.getFilesDir(),"data/native_library/blobs/"+fixture.getString("sha256")).getCanonicalPath(),file.getCanonicalPath());
        MessageDigest hash=MessageDigest.getInstance("SHA-256");try(InputStream input=new FileInputStream(file)){byte[] buffer=new byte[32768];int count;while((count=input.read(buffer))!=-1)hash.update(buffer,0,count);}StringBuilder actual=new StringBuilder();for(byte b:hash.digest())actual.append(String.format(java.util.Locale.ROOT,"%02x",b&255));assertEquals(fixture.getString("sha256"),actual.toString());assertEquals("गणित π + λ ∈ ℝ.pdf",item.get(2).toString());
        String check="(lambda d: d['display_name']=='गणित π + λ ∈ ℝ' and d['subject_id']=='ma103' and d['tags']==['native-viewer-test'] and d['status']=='disabled')(__import__('personal_learning_assistant.services.native_document_library',fromlist=['NativeDocumentLibrary']).NativeDocumentLibrary("+JSONObject.quote(context.getFilesDir().getCanonicalPath())+"+'/data/native_library',autostart=False).get('"+fixture.getString("id")+"'))";assertTrue("Rename/course/tags/index choice persist",eval(check).toBoolean());File copies=new File(context.getCacheDir(),"shared-originals");assertFalse("No view copy",copies.isDirectory()&&copies.list().length>0);
    }
    private String originalResolverDiagnostic() throws Exception {
        com.chaquo.python.PyObject builtins=Python.getInstance().getModule("builtins");
        com.chaquo.python.PyObject globals=builtins.callAttr("dict");
        builtins.callAttr("exec", """
            def diagnose_original(root_path, document_id):
                import json, os, sqlite3, traceback
                from pathlib import Path
                from urllib.parse import quote
                from personal_learning_assistant.services.native_document_library import resolve_android_document
                root = Path(root_path).absolute()
                database = root/'data/native_library/library.sqlite3'
                result = {'root': str(root), 'root_realpath': os.path.realpath(root), 'cwd': os.getcwd(),
                          'database': str(database), 'database_realpath': os.path.realpath(database),
                          'sqlite_version': sqlite3.sqlite_version, 'sqlite_module': sqlite3.__file__}
                def error_details(error):
                    return {'error': repr(error), 'cause': repr(error.__cause__), 'traceback': traceback.format_exc()}
                for label, path in [('root_stat', root), ('database_stat', database)]:
                    try:
                        stat = path.stat()
                        result[label] = {'exists': path.exists(), 'is_file': path.is_file(),
                                         'mode': oct(stat.st_mode), 'size': stat.st_size,
                                         'uid': stat.st_uid, 'gid': stat.st_gid}
                    except Exception as error:
                        result[label] = error_details(error)
                try:
                    result['production_resolver'] = resolve_android_document(root_path, document_id)
                except Exception as error:
                    result['production_resolver'] = error_details(error)
                with sqlite3.connect(':memory:') as connection:
                    result['sqlite_compile_options'] = [row[0] for row in connection.execute('PRAGMA compile_options')]
                variants = [('path_as_uri', database.as_uri()+'?mode=ro', True),
                            ('file_quoted_posix', 'file:'+quote(database.as_posix(), safe='/:')+'?mode=ro', True),
                            ('plain_existing_query_only', str(database), False)]
                result['connection_probes'] = {}
                for label, address, uri in variants:
                    probe = {'address': address, 'uri': uri}
                    result['connection_probes'][label] = probe
                    connection = None
                    try:
                        if not database.is_file():
                            raise FileNotFoundError('Existing Library database is absent; will not create it')
                        connection = sqlite3.connect(address, uri=uri)
                        connection.execute('PRAGMA query_only=ON')
                        probe['query_only'] = connection.execute('PRAGMA query_only').fetchone()[0]
                        probe['database_list'] = connection.execute('PRAGMA database_list').fetchall()
                        probe['count'] = connection.execute('SELECT count(*) FROM documents').fetchone()[0]
                        probe['fixture_row'] = connection.execute('SELECT id,sha256,size,status,display_name FROM documents WHERE id=?', (document_id,)).fetchone()
                    except Exception as error:
                        probe.update(error_details(error))
                    finally:
                        if connection is not None:
                            connection.close()
                return json.dumps(result, ensure_ascii=False, indent=2)
            """, globals);
        return globals.callAttr("__getitem__","diagnose_original").call(context.getFilesDir().getCanonicalPath(),fixture.getString("id")).toString();
    }
    private String js(String source) throws Exception {CountDownLatch done=new CountDownLatch(1);String[] result={null};inst.runOnMainSync(()->web.evaluateJavascript(source,value->{result[0]=value;done.countDown();}));assertTrue(done.await(10,TimeUnit.SECONDS));return result[0];}
    private void waitJs(String condition) throws Exception {
        long deadline=System.currentTimeMillis()+20000;
        while(System.currentTimeMillis()<deadline){if("true".equals(js("document.readyState==='complete'&&("+condition+")")))return;Thread.sleep(100);}
        String page=js("JSON.stringify({url:location.href,ready:document.readyState,title:document.title,pending:!!window.__nativePdfNavigationPending,ids:Array.from(document.querySelectorAll('[data-document-id]')).map(r=>r.dataset.documentId),body:document.body?.innerText.slice(0,5000)})");
        // This uses the real authenticated WebView connection. Capture the HTTP
        // status/body as well as DOM so route errors cannot look like missing rows.
        js("window.__nativePdfHttpProbe=null;fetch('/library/files',{cache:'no-store',credentials:'same-origin'}).then(async r=>{window.__nativePdfHttpProbe=JSON.stringify({status:r.status,url:r.url,body:(await r.text()).slice(0,6000)})}).catch(e=>{window.__nativePdfHttpProbe=String(e)})");
        long probeDeadline=System.currentTimeMillis()+10000;
        while(System.currentTimeMillis()<probeDeadline&&"true".equals(js("window.__nativePdfHttpProbe===null")))Thread.sleep(100);
        String details="condition="+condition+"; fixture="+fixture+"; page="+page+"; HTTP="+js("window.__nativePdfHttpProbe")+"; routeException="+(routeFailureFile().isFile()?read(routeFailureFile()):"none");
        File evidence=new File(context.getFilesDir(),"evidence/android-native-pdf-state-failure.txt");evidence.getParentFile().mkdirs();
        try(FileOutputStream output=new FileOutputStream(evidence)){output.write(details.getBytes("UTF-8"));}
        screenshot("android-native-pdf-state-failure");
        fail("Library state did not appear: "+details);
    }
    private void tap(String selector) throws Exception {
        waitJs("!!document.querySelector("+JSONObject.quote(selector)+")");JSONObject point=new JSONObject(js("(()=>{const a=document.querySelector("+JSONObject.quote(selector)+");a.scrollIntoView({block:'center'});const r=a.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2,width:innerWidth}})()"));
        CountDownLatch frame=new CountDownLatch(1);int[] location=new int[2];inst.runOnMainSync(()->{web.getLocationOnScreen(location);web.postVisualStateCallback(System.nanoTime(),new WebView.VisualStateCallback(){@Override public void onComplete(long id){web.postOnAnimation(frame::countDown);}});});assertTrue(frame.await(10,TimeUnit.SECONDS));float scale=web.getWidth()/(float)point.getDouble("width");float x=location[0]+(float)point.getDouble("x")*scale,y=location[1]+(float)point.getDouble("y")*scale;long now=android.os.SystemClock.uptimeMillis();android.view.MotionEvent down=android.view.MotionEvent.obtain(now,now,android.view.MotionEvent.ACTION_DOWN,x,y,0),up=android.view.MotionEvent.obtain(now,now+80,android.view.MotionEvent.ACTION_UP,x,y,0);down.setSource(android.view.InputDevice.SOURCE_TOUCHSCREEN);up.setSource(android.view.InputDevice.SOURCE_TOUCHSCREEN);assertTrue(inst.getUiAutomation().injectInputEvent(down,true));assertTrue(inst.getUiAutomation().injectInputEvent(up,true));down.recycle();up.recycle();
    }
    private void screenshot(String name) throws Exception {inst.waitForIdleSync();Bitmap image=inst.getUiAutomation().takeScreenshot();assertNotNull(image);File output=new File(context.getFilesDir(),"evidence/"+name+".png");output.getParentFile().mkdirs();try(FileOutputStream stream=new FileOutputStream(output)){assertTrue(image.compress(Bitmap.CompressFormat.PNG,100,stream));}image.recycle();}
    private String read(File file) throws Exception {try(InputStream input=new FileInputStream(file);ByteArrayOutputStream output=new ByteArrayOutputStream()){byte[] buffer=new byte[4096];int count;while((count=input.read(buffer))!=-1)output.write(buffer,0,count);return output.toString("UTF-8");}}
    private WebView findWeb(android.view.View view){if(view instanceof WebView)return (WebView)view;if(view instanceof android.view.ViewGroup){android.view.ViewGroup group=(android.view.ViewGroup)view;for(int n=0;n<group.getChildCount();n++){WebView found=findWeb(group.getChildAt(n));if(found!=null)return found;}}return null;}
}

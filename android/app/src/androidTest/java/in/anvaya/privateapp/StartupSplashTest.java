package in.anvaya.privateapp;

import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.BitmapDrawable;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Matrix;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.security.MessageDigest;
import android.view.View;
import android.view.ViewGroup;
import android.widget.*;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.Assert.*;

/** Actual Android Views: reduced motion, readable branding and recovery controls. */
@RunWith(AndroidJUnit4.class)
public class StartupSplashTest {
    private TextView text(View view, String value) {
        if (view instanceof TextView && value.contentEquals(((TextView)view).getText())) return (TextView)view;
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup)view;
            for (int i=0; i<group.getChildCount(); i++) {
                TextView found = text(group.getChildAt(i), value);
                if (found != null) return found;
            }
        }
        return null;
    }
    @Test public void disabledMotionShowsFullBrandImmediatelyAndRecoveryIsActionable() {
        android.app.Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        instrumentation.runOnMainSync(() -> {
            AtomicInteger retries = new AtomicInteger(), closes = new AtomicInteger();
            StartupSplashView splash = new StartupSplashView(instrumentation.getTargetContext(),
                retries::incrementAndGet, closes::incrementAndGet);
            splash.startBranding(false);
            assertEquals(0xFF000000, ((ColorDrawable)splash.getBackground()).getColor());
            ImageView artwork = find(splash, ImageView.class);
            assertNotNull(artwork);
            assertEquals("ANVAYA. Personal Learning Intelligence...", artwork.getContentDescription());
            assertEquals(ImageView.ScaleType.FIT_CENTER, artwork.getScaleType());
            assertEquals(1f, artwork.getAlpha(), 0f);
            assertNull(artwork.getAnimation());
            assertEquals(View.GONE, text(splash, "Try again").getVisibility());
            splash.feedback("Your saved data is kept. Try again.", true, true);
            assertNotNull(text(splash, "Your saved data is kept. Try again."));
            assertEquals(View.VISIBLE, text(splash, "Try again").getVisibility());
            text(splash, "Try again").performClick();
            text(splash, "Close app").performClick();
            assertEquals(1, retries.get()); assertEquals(1, closes.get());
            splash.feedback("Preparing your private workspace…", false, true);
            assertEquals(View.GONE, text(splash, "Try again").getVisibility());
            assertEquals(View.VISIBLE, text(splash, "Close app").getVisibility());
            splash.cancelBranding();
        });
    }
    private void save(Bitmap image, String name) {
        File directory = new File(InstrumentationRegistry.getInstrumentation().getTargetContext().getFilesDir(), "evidence");
        assertTrue(directory.isDirectory() || directory.mkdirs());
        try (FileOutputStream output = new FileOutputStream(new File(directory, name + ".png"))) {
            assertTrue(image.compress(Bitmap.CompressFormat.PNG, 100, output));
        } catch (java.io.IOException error) { throw new AssertionError(error); }
    }
    @Test public void completeApprovedArtworkFitsPortraitAndLandscapeWithoutAnimationOrCrop() throws Exception {
        android.app.Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream input = instrumentation.getTargetContext().getResources().openRawResource(R.drawable.anvaya_opening)) {
            byte[] buffer = new byte[8192]; int length;
            while ((length = input.read(buffer)) != -1) digest.update(buffer, 0, length);
        }
        StringBuilder hash = new StringBuilder();
        for (byte value : digest.digest()) hash.append(String.format("%02x", value & 255));
        assertEquals("Packaged resource must be the owner's exact original file",
            "319e31420b50e2e420de571d0906835ee4f9894dedbd26b88435d0ca57415fb6", hash.toString());
        instrumentation.runOnMainSync(() -> {
            StartupSplashView splash = new StartupSplashView(instrumentation.getTargetContext(), () -> {}, () -> {});
            ImageView image = find(splash, ImageView.class);
            Bitmap original = ((BitmapDrawable)image.getDrawable()).getBitmap();
            assertEquals(864, original.getWidth()); assertEquals(1536, original.getHeight());
            // Literal expected transforms: full portrait, letterboxed landscape,
            // and a tall phone. A crop, fill or density-scaled resource fails here.
            int[][] sizes = {{864,1536}, {1536,864}, {720,1600}};
            float[][] transforms = {{1,0,0}, {0.5625f,525,0}, {0.8333333f,0,160}};
            for (int i=0; i<sizes.length; i++) {
                int width=sizes[i][0], height=sizes[i][1];
                splash.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                    View.MeasureSpec.makeMeasureSpec(height, View.MeasureSpec.EXACTLY));
                splash.layout(0,0,width,height);
                splash.startBranding(true);
                float[] matrix = new float[9]; image.getImageMatrix().getValues(matrix);
                assertEquals(transforms[i][0], matrix[Matrix.MSCALE_X], 0.001f);
                assertEquals(transforms[i][0], matrix[Matrix.MSCALE_Y], 0.001f);
                assertEquals(transforms[i][1], matrix[Matrix.MTRANS_X], 0.6f);
                assertEquals(transforms[i][2], matrix[Matrix.MTRANS_Y], 0.6f);
                Bitmap frame = Bitmap.createBitmap(width,height,Bitmap.Config.ARGB_8888);
                splash.draw(new Canvas(frame));
                assertNull(image.getAnimation()); assertEquals(1f,image.getAlpha(),0f);
                if (i == 0) {
                    // Identity-sized Android raster must contain the full source,
                    // including the corner arcs and the last dots of the tagline.
                    for (int y=0; y<height; y+=17) for (int x=0; x<width; x+=17)
                        assertEquals(original.getPixel(x,y), frame.getPixel(x,y));
                    save(frame,"android-opening-portrait");
                } else if (i == 1) {
                    assertEquals(0xFF000000, frame.getPixel(20,height/2));
                    assertEquals(0xFF000000, frame.getPixel(width-20,height/2));
                    save(frame,"android-opening-landscape");
                }
                frame.recycle();
            }
            StringBuilder longMessage=new StringBuilder();
            for(int i=0;i<50;i++) longMessage.append("A long recoverable startup message. ");
            splash.feedback(longMessage.toString(),true,true);
            splash.measure(View.MeasureSpec.makeMeasureSpec(720,View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(320,View.MeasureSpec.EXACTLY));
            splash.layout(0,0,720,320);
            ScrollView feedback=find(splash,ScrollView.class);
            assertTrue("Recovery scrolls within half the display",feedback.getMeasuredHeight()<=160);
            assertEquals(View.VISIBLE,text(splash,"Close app").getVisibility());
            splash.feedback("",false,false);
            assertEquals(View.GONE,feedback.getVisibility());
        });
    }
    private <T> T find(View view, Class<T> type) {
        if (type.isInstance(view)) return type.cast(view);
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup)view;
            for (int i=0; i<group.getChildCount(); i++) {
                T found = find(group.getChildAt(i), type);
                if (found != null) return found;
            }
        }
        return null;
    }
    @Test public void finishedActivityCannotReceiveLateLaunchAndNewActivityRevealsPaintedWorkspace() throws Exception {
        android.app.Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        android.content.Intent launch = new android.content.Intent(instrumentation.getTargetContext(), MainActivity.class)
            .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK);
        MainActivity first = (MainActivity)instrumentation.startActivitySync(launch);
        instrumentation.runOnMainSync(first::finish);
        instrumentation.waitForIdleSync();
        assertTrue(first.isFinishing());
        java.util.concurrent.CountDownLatch openingBarsHidden = new java.util.concurrent.CountDownLatch(1);
        androidx.test.runner.lifecycle.ActivityLifecycleCallback capture = (activity, stage) -> {
            if (!(activity instanceof MainActivity) || stage != androidx.test.runner.lifecycle.Stage.RESUMED) return;
            StartupSplashView cover = find(activity.getWindow().getDecorView(), StartupSplashView.class);
            assertNotNull("First app-controlled surface", cover);
            cover.getViewTreeObserver().addOnPreDrawListener(new android.view.ViewTreeObserver.OnPreDrawListener() {
                @Override public boolean onPreDraw() {
                    android.view.WindowInsets insets=cover.getRootWindowInsets();
                    if (insets!=null && !insets.isVisible(android.view.WindowInsets.Type.statusBars())
                        && !insets.isVisible(android.view.WindowInsets.Type.navigationBars())) {
                        cover.getViewTreeObserver().removeOnPreDrawListener(this);
                        openingBarsHidden.countDown();
                    }
                    return true;
                }
            });
        };
        instrumentation.runOnMainSync(() -> androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry.getInstance().addLifecycleCallback(capture));
        MainActivity second = (MainActivity)instrumentation.startActivitySync(launch);
        try {
            long deadline = System.currentTimeMillis() + 90000;
            while (System.currentTimeMillis() < deadline) {
                boolean[] ready = {false};
                instrumentation.runOnMainSync(() -> {
                    View decor = second.getWindow().getDecorView();
                    android.webkit.WebView web = find(decor, android.webkit.WebView.class);
                    if (web == null) return;
                    StartupSplashView cover = find(decor, StartupSplashView.class);
                    if (cover == null) {
                        assertTrue("Revealed document uses the authenticated local origin", web.getUrl().startsWith("http://127.0.0.1:"));
                        assertEquals(View.IMPORTANT_FOR_ACCESSIBILITY_AUTO, web.getImportantForAccessibility());
                        android.view.WindowInsets insets=decor.getRootWindowInsets();
                        ready[0] = insets!=null && insets.isVisible(android.view.WindowInsets.Type.statusBars())
                            && insets.isVisible(android.view.WindowInsets.Type.navigationBars());
                    } else {
                        assertEquals("Hidden workspace cannot be navigated by accessibility before paint",
                            View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS, web.getImportantForAccessibility());
                        assertEquals(0xFF000000, ((ColorDrawable)cover.getBackground()).getColor());
                    }
                });
                if (ready[0]) {
                    assertTrue("Actual opening system bars hidden before workspace restores them",openingBarsHidden.await(5,java.util.concurrent.TimeUnit.SECONDS));
                    return;
                }
                Thread.sleep(100);
            }
            String[] observed={""};
            instrumentation.runOnMainSync(() -> {
                View decor=second.getWindow().getDecorView();
                android.view.WindowInsets insets=decor.getRootWindowInsets();
                int saved=-1;
                try {java.lang.reflect.Field field=MainActivity.class.getDeclaredField("workspaceSystemUi");field.setAccessible(true);saved=field.getInt(second);} catch(Exception ignored) {}
                observed[0]="cover="+(find(decor,StartupSplashView.class)!=null)+",web="+(find(decor,android.webkit.WebView.class)!=null)
                    +",flags="+decor.getSystemUiVisibility()+",saved="+saved+",windowFlags="+second.getWindow().getAttributes().flags
                    +",status="+(insets==null?"null":insets.isVisible(android.view.WindowInsets.Type.statusBars()))
                    +",navigation="+(insets==null?"null":insets.isVisible(android.view.WindowInsets.Type.navigationBars()))
                    +",hiddenObserved="+(openingBarsHidden.getCount()==0);
            });
            Bitmap failure=instrumentation.getUiAutomation().takeScreenshot();
            if(failure!=null){save(failure,"startup-failure");failure.recycle();}
            fail("Workspace did not replace the native splash after its first frame: "+observed[0]);
        } finally { instrumentation.runOnMainSync(() -> {
            androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry.getInstance().removeLifecycleCallback(capture);
            second.finish();
        }); }
    }

}

package in.anvaya.privateapp;

import android.graphics.drawable.ColorDrawable;
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
            assertEquals(0xFFF8FAFB, ((ColorDrawable)splash.getBackground()).getColor());
            TextView title = text(splash, "ANVAYA");
            TextView subtitle = text(splash, "Personal Learning Intelligence");
            assertNotNull(title); assertNotNull(subtitle);
            assertEquals(1f, title.getAlpha(), 0f);
            assertEquals(1f, subtitle.getAlpha(), 0f);
            assertEquals(0xFF142D43, title.getCurrentTextColor());
            assertEquals(View.INVISIBLE, text(splash, "Try again").getVisibility());
            splash.feedback("Your saved data is kept. Try again.", true, true);
            assertNotNull(text(splash, "Your saved data is kept. Try again."));
            assertEquals(View.VISIBLE, text(splash, "Try again").getVisibility());
            text(splash, "Try again").performClick();
            text(splash, "Close app").performClick();
            assertEquals(1, retries.get()); assertEquals(1, closes.get());
            splash.feedback("Preparing your private workspace…", false, true);
            assertEquals(View.INVISIBLE, text(splash, "Try again").getVisibility());
            assertEquals(View.VISIBLE, text(splash, "Close app").getVisibility());
            splash.cancelBranding();
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
                        ready[0] = true;
                    } else {
                        assertEquals("Hidden workspace cannot be navigated by accessibility before paint",
                            View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS, web.getImportantForAccessibility());
                        assertEquals(0xFFF8FAFB, ((ColorDrawable)cover.getBackground()).getColor());
                    }
                });
                if (ready[0]) return;
                Thread.sleep(100);
            }
            fail("Workspace did not replace the native splash after its first frame");
        } finally { instrumentation.runOnMainSync(second::finish); }
    }

}

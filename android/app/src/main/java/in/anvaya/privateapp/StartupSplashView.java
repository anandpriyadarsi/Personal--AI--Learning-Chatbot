package in.anvaya.privateapp;

import android.content.Context;
import android.graphics.Typeface;
import android.view.Gravity;
import android.view.View;
import android.widget.*;

/** Owner-selected static branding; workspace readiness never waits for decoration. */
final class StartupSplashView extends ScrollView {
    static final int BACKGROUND = 0xFF000000;
    private static final int NAVY = 0xFFF8FAFB;
    private final ImageView logo;
    private final TextView title, subtitle, status;
    private final Button retry, close;
    private boolean brandingStarted;

    StartupSplashView(Context context, Runnable retryAction, Runnable closeAction) {
        super(context);
        setBackgroundColor(BACKGROUND);
        setFillViewport(true);
        LinearLayout content = new LinearLayout(context);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setGravity(Gravity.CENTER);
        content.setPadding(dp(28), dp(28), dp(28), dp(28));
        addView(content, new ScrollView.LayoutParams(-1, -2));
        setClickable(true); // The covered WebView cannot receive accidental taps.
        logo = new ImageView(context);
        logo.setImageResource(R.drawable.anvaya_mark);
        logo.setScaleType(ImageView.ScaleType.FIT_CENTER);
        logo.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        content.addView(logo, new LinearLayout.LayoutParams(dp(140), dp(140)));
        title = text("ANVAYA", 31, NAVY);
        title.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        title.setLetterSpacing(0.16f);
        LinearLayout.LayoutParams titleParams = new LinearLayout.LayoutParams(-1, -2);
        titleParams.topMargin = dp(12);
        content.addView(title, titleParams);
        subtitle = text("Personal Learning Intelligence...", 14, NAVY);
        LinearLayout.LayoutParams subtitleParams = new LinearLayout.LayoutParams(-1, -2);
        subtitleParams.topMargin = dp(10);
        content.addView(subtitle, subtitleParams);
        status = text("", 14, 0xFFB5C5D2);
        status.setMinHeight(dp(76));
        status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        // Reserve room for brief startup feedback. Long text can scroll on small screens.
        LinearLayout.LayoutParams statusParams = new LinearLayout.LayoutParams(-1, -2);
        statusParams.topMargin = dp(36);
        content.addView(status, statusParams);
        LinearLayout actions = new LinearLayout(context);
        actions.setGravity(Gravity.CENTER);
        retry = new Button(context);
        retry.setText("Try again"); retry.setTextColor(0xFF142D43);
        retry.setOnClickListener(view -> retryAction.run());
        actions.addView(retry);
        close = new Button(context);
        close.setText("Close app"); close.setTextColor(0xFF142D43);
        close.setOnClickListener(view -> closeAction.run());
        actions.addView(close);
        retry.setVisibility(INVISIBLE); close.setVisibility(INVISIBLE);
        actions.setMinimumHeight(dp(56));
        content.addView(actions, new LinearLayout.LayoutParams(-1, -2));
    }

    private TextView text(String value, int size, int color) {
        TextView view = new TextView(getContext());
        view.setText(value); view.setTextSize(size); view.setTextColor(color);
        view.setGravity(Gravity.CENTER);
        return view;
    }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }

    void startBranding() {
        startBranding(false);
    }
    // Package-visible for the real View instrumentation test, with no global setting mutation.
    void startBranding(boolean motionEnabled) {
        if (brandingStarted) return;
        brandingStarted = true;
        // Static for both accessibility motion settings, as selected by the owner.
    }
    void feedback(String message, boolean canRetry, boolean canClose) {
        status.setText(message);
        retry.setVisibility(canRetry ? VISIBLE : INVISIBLE);
        close.setVisibility(canClose ? VISIBLE : INVISIBLE);
    }
    void cancelBranding() {
        // No pending branding animation or delay.
    }
    @Override protected void onDetachedFromWindow() {
        cancelBranding();
        super.onDetachedFromWindow();
    }
}

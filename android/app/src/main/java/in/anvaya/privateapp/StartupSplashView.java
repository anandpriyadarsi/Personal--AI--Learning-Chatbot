package in.anvaya.privateapp;

import android.content.Context;
import android.view.Gravity;
import android.view.View;
import android.widget.*;

/** Exact owner-supplied static artwork, with recoverable startup feedback. */
final class StartupSplashView extends FrameLayout {
    static final int BACKGROUND = 0xFF000000;
    private final TextView status;
    private final Button retry, close;
    private final ScrollView feedbackPanel;

    StartupSplashView(Context context, Runnable retryAction, Runnable closeAction) {
        super(context);
        setBackgroundColor(BACKGROUND);
        setClickable(true); // The covered WebView cannot receive accidental taps.
        ImageView artwork = new ImageView(context);
        artwork.setImageResource(R.drawable.anvaya_opening);
        artwork.setScaleType(ImageView.ScaleType.FIT_CENTER);
        artwork.setContentDescription("ANVAYA. Personal Learning Intelligence...");
        addView(artwork, new FrameLayout.LayoutParams(-1, -1));

        // Hidden on normal startup. Long failures remain readable and actionable
        // with large fonts, small screens and landscape; the artwork never moves.
        feedbackPanel = new ScrollView(context);
        feedbackPanel.setBackgroundColor(0xF0000000);
        LinearLayout content = new LinearLayout(context);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setGravity(Gravity.CENTER);
        content.setPadding(dp(20), dp(12), dp(20), dp(12));
        feedbackPanel.addView(content, new ScrollView.LayoutParams(-1, -2));
        status = new TextView(context);
        status.setTextSize(14); status.setTextColor(0xFFF8FAFB);
        status.setGravity(Gravity.CENTER);
        status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        content.addView(status, new LinearLayout.LayoutParams(-1, -2));
        // Stack buttons so translated text/large fonts cannot push Close offscreen.
        retry = new Button(context);
        retry.setText("Try again"); retry.setTextColor(0xFF142D43);
        retry.setOnClickListener(view -> retryAction.run());
        content.addView(retry, new LinearLayout.LayoutParams(-1, -2));
        close = new Button(context);
        close.setText("Close app"); close.setTextColor(0xFF142D43);
        close.setOnClickListener(view -> closeAction.run());
        content.addView(close, new LinearLayout.LayoutParams(-1, -2));
        retry.setVisibility(GONE); close.setVisibility(GONE);
        feedbackPanel.setVisibility(GONE);
        addView(feedbackPanel, new FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM));
    }

    // Limit recovery feedback to half the screen; ScrollView handles overflow.
    @Override protected void onMeasure(int widthSpec, int heightSpec) {
        super.onMeasure(widthSpec, heightSpec);
        int limit = getMeasuredHeight() / 2;
        if (feedbackPanel.getVisibility() != GONE && feedbackPanel.getMeasuredHeight() > limit) {
            feedbackPanel.measure(MeasureSpec.makeMeasureSpec(getMeasuredWidth(), MeasureSpec.EXACTLY),
                MeasureSpec.makeMeasureSpec(limit, MeasureSpec.EXACTLY));
        }
    }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    void startBranding() { startBranding(false); }
    void startBranding(boolean motionEnabled) { /* Static for every motion setting. */ }
    void feedback(String message, boolean canRetry, boolean canClose) {
        status.setText(message);
        retry.setVisibility(canRetry ? VISIBLE : GONE);
        close.setVisibility(canClose ? VISIBLE : GONE);
        feedbackPanel.setVisibility(message.isEmpty() && !canRetry && !canClose ? GONE : VISIBLE);
    }
    void cancelBranding() { /* No animation, timer or delayed reveal. */ }
}

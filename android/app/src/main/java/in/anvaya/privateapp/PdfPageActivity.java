package in.anvaya.privateapp;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.pdf.PdfRenderer;
import android.os.Bundle;
import android.os.ParcelFileDescriptor;
import android.view.ScaleGestureDetector;
import android.view.WindowManager;
import android.widget.*;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** One bounded PDF bitmap at a time. The private original is never modified. */
public class PdfPageActivity extends Activity {
    private PdfRenderer renderer;
    private ParcelFileDescriptor descriptor;
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private ImageView image;
    private TextView position;
    private int page, count;
    private volatile int revision;
    private float zoom=1f;
    private Bitmap displayed;
    private ScaleGestureDetector pinch;
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN);
        page=state==null?Math.max(0,getIntent().getIntExtra("page",1)-1):state.getInt("page",0);
        LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setBackgroundColor(Color.rgb(20,24,30));
        LinearLayout nav=new LinearLayout(this);nav.setGravity(17);
        Button back=button("‹",()->{if(page>0){page--;render();}});
        Button next=button("›",()->{if(page+1<count){page++;render();}});
        position=new TextView(this);position.setTextColor(Color.WHITE);position.setTextSize(14);position.setText("Opening original…");
        nav.addView(back);nav.addView(position,new LinearLayout.LayoutParams(0,56,1));nav.addView(next);
        Button close=button("Close",this::finish);nav.addView(close);root.addView(nav);
        LinearLayout controls=new LinearLayout(this);
        controls.addView(button("Zoom −",()->{zoom=Math.max(.5f,zoom-.25f);render();}));
        controls.addView(button("Zoom +",()->{zoom=Math.min(3f,zoom+.25f);render();}));
        controls.addView(button("Find in document",()->{
            Intent result=new Intent();result.putExtra("find",true);result.putExtra("page",page+1);
            setResult(RESULT_OK,result);finish();
        }));root.addView(controls);
        ScrollView vertical=new ScrollView(this){
            @Override public boolean dispatchTouchEvent(android.view.MotionEvent event){
                if(pinch!=null){pinch.onTouchEvent(event);if(pinch.isInProgress()){requestDisallowInterceptTouchEvent(true);return true;}}
                return super.dispatchTouchEvent(event);
            }
        };
        HorizontalScrollView horizontal=new HorizontalScrollView(this);
        image=new ImageView(this);image.setAdjustViewBounds(true);image.setScaleType(ImageView.ScaleType.FIT_XY);
        horizontal.addView(image);vertical.addView(horizontal);root.addView(vertical,new LinearLayout.LayoutParams(-1,0,1));
        pinch=new ScaleGestureDetector(this,new ScaleGestureDetector.SimpleOnScaleGestureListener(){
            @Override public boolean onScale(ScaleGestureDetector detector){zoom=Math.max(.5f,Math.min(3f,zoom*detector.getScaleFactor()));return true;}
            @Override public void onScaleEnd(ScaleGestureDetector detector){render();}
        });
        setContentView(root);
        worker.execute(()->{
            try {
                descriptor=getContentResolver().openFileDescriptor(getIntent().getData(),"r");
                renderer=new PdfRenderer(descriptor);count=renderer.getPageCount();page=Math.min(page,count-1);
                runOnUiThread(this::render);
            }catch(Exception error){runOnUiThread(()->position.setText("PDF unavailable or password protected. Use another viewer."));}
        });
    }
    private Button button(String text,Runnable action){Button b=new Button(this);b.setText(text);b.setMinWidth(0);b.setPadding(10,0,10,0);b.setOnClickListener(v->action.run());return b;}
    private void render(){
        if(renderer==null||isFinishing()||isDestroyed())return;
        final int selected=page, requested=++revision;
        final int width=Math.min(2400,Math.max(200,(int)(getResources().getDisplayMetrics().widthPixels*zoom)));
        position.setText("Page "+(page+1)+" / "+count);
        worker.execute(()->{
            if(requested!=revision)return;
            try(PdfRenderer.Page original=renderer.openPage(selected)){
                float scale=Math.min((float)width/original.getWidth(),4096f/original.getHeight());
                float pixels=original.getWidth()*scale*original.getHeight()*scale;
                if(pixels>4000000f)scale*=(float)Math.sqrt(4000000f/pixels);
                int w=Math.max(1,(int)(original.getWidth()*scale)),h=Math.max(1,(int)(original.getHeight()*scale));
                Bitmap bitmap=Bitmap.createBitmap(w,h,Bitmap.Config.ARGB_8888);bitmap.eraseColor(Color.WHITE);
                original.render(bitmap,null,null,PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY);
                if(requested!=revision){bitmap.recycle();return;}
                runOnUiThread(()->{
                    if(requested!=revision||isFinishing()||isDestroyed()){bitmap.recycle();return;}
                    image.setLayoutParams(new android.widget.FrameLayout.LayoutParams(w,h));
                    image.setImageBitmap(bitmap);image.setContentDescription("PDF page "+(selected+1)+" of "+count);
                    Bitmap previous=displayed;displayed=bitmap;if(previous!=null)previous.recycle();
                });
            }catch(Exception|OutOfMemoryError error){runOnUiThread(()->position.setText("Page unavailable. Try a lower zoom or another viewer."));}
        });
    }
    @Override protected void onSaveInstanceState(Bundle state){super.onSaveInstanceState(state);state.putInt("page",page);}
    @Override protected void onDestroy(){
        revision++;
        worker.execute(()->{try{if(renderer!=null)renderer.close();if(descriptor!=null)descriptor.close();}catch(Exception ignored){}});
        worker.shutdown();super.onDestroy();
    }
}

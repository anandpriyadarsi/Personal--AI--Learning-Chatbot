package in.anvaya.privateapp;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Paint;
import android.graphics.pdf.PdfDocument;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.File;
import java.io.FileOutputStream;
import static org.junit.Assert.*;

/** Installed PDF renderer contract. This must run on API31/newer before release. */
@RunWith(AndroidJUnit4.class)
public class NativePdfPageTest {
    private ImageView pageImage(View view){
        if(view instanceof ImageView)return (ImageView)view;
        if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++){ImageView found=pageImage(group.getChildAt(i));if(found!=null)return found;}}
        return null;
    }
    @Test public void rendersRequestedPageThroughPrivateContentUri() throws Exception {
        android.app.Instrumentation instrumentation=InstrumentationRegistry.getInstrumentation();
        android.content.Context context=instrumentation.getTargetContext();
        File directory=new File(context.getCacheDir(),"shared-originals/synthetic-render-test");directory.mkdirs();
        File original=new File(directory,"synthetic-three-pages.pdf");
        try(PdfDocument pdf=new PdfDocument()){
            for(int number=1;number<=3;number++){
                PdfDocument.Page page=pdf.startPage(new PdfDocument.PageInfo.Builder(300,450,number).create());
                Paint paint=new Paint();paint.setTextSize(18);page.getCanvas().drawText("Synthetic page "+number,30,60,paint);pdf.finishPage(page);
            }
            try(FileOutputStream output=new FileOutputStream(original)){pdf.writeTo(output);}
        }
        android.net.Uri uri=androidx.core.content.FileProvider.getUriForFile(context,context.getPackageName()+".documents",original);
        assertEquals("content",uri.getScheme());
        Intent intent=new Intent(context,PdfPageActivity.class);intent.setData(uri);intent.putExtra("page",2);intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        Activity activity=instrumentation.startActivitySync(intent);
        try {
            long deadline=System.currentTimeMillis()+15000;boolean[] matched={false};
            while(System.currentTimeMillis()<deadline){
                instrumentation.runOnMainSync(()->{ImageView image=pageImage(activity.getWindow().getDecorView());matched[0]=image!=null&&"PDF page 2 of 3".contentEquals(image.getContentDescription()==null?"":image.getContentDescription());});
                if(matched[0])break;Thread.sleep(100);
            }
            assertTrue("Actual original PDF page 2 must render",matched[0]);
            assertTrue("Original is retained",original.length()>0);
        }finally{instrumentation.runOnMainSync(activity::finish);}
    }
}

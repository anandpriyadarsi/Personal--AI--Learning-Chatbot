package in.anvaya.privateapp.test;

import android.app.Activity;
import android.content.Intent;
import android.database.Cursor;
import android.graphics.Bitmap;
import android.graphics.pdf.PdfRenderer;
import android.net.Uri;
import android.os.Bundle;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.io.InputStream;
import java.security.MessageDigest;

/** Installed separate-UID PDF viewer; present only in the instrumentation APK. */
public final class PdfReceiverActivity extends Activity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        Intent report=new Intent("in.anvaya.privateapp.TEST_PDF_RESULT").setPackage("in.anvaya.privateapp");
        report.putExtra("uid",android.os.Process.myUid());
        Uri uri=getIntent().getData();
        LinearLayout layout=new LinearLayout(this);layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(20,20,20,20);layout.setBackgroundColor(android.graphics.Color.WHITE);
        TextView heading=new TextView(this);heading.setText("Synthetic external PDF viewer");heading.setTextSize(22);heading.setTextColor(android.graphics.Color.BLACK);layout.addView(heading);
        setContentView(layout);
        try {
            report.putExtra("mime",getContentResolver().getType(uri));
            String name="";
            try(Cursor cursor=getContentResolver().query(uri,new String[]{OpenableColumns.DISPLAY_NAME},null,null,null)) {
                if(cursor!=null&&cursor.moveToFirst())name=cursor.getString(0);
            }
            report.putExtra("filename",name);
            TextView filename=new TextView(this);filename.setText(name);filename.setTextColor(android.graphics.Color.BLACK);layout.addView(filename);
            MessageDigest hash=MessageDigest.getInstance("SHA-256");long size=0;
            try(InputStream input=getContentResolver().openInputStream(uri)) {
                byte[] buffer=new byte[32768];int count;
                while((count=input.read(buffer))!=-1){hash.update(buffer,0,count);size+=count;}
            }
            StringBuilder digest=new StringBuilder();for(byte b:hash.digest())digest.append(String.format(java.util.Locale.ROOT,"%02x",b&255));
            report.putExtra("sha256",digest.toString());report.putExtra("size",size);
            try(ParcelFileDescriptor descriptor=getContentResolver().openFileDescriptor(uri,"r");PdfRenderer pdf=new PdfRenderer(descriptor);PdfRenderer.Page page=pdf.openPage(0)) {
                Bitmap image=Bitmap.createBitmap(page.getWidth()*2,page.getHeight()*2,Bitmap.Config.ARGB_8888);
                image.eraseColor(android.graphics.Color.WHITE);page.render(image,null,null,PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY);
                ImageView view=new ImageView(this);view.setImageBitmap(image);view.setAdjustViewBounds(true);view.setContentDescription("External PDF page 1");layout.addView(view);
                report.putExtra("pages",pdf.getPageCount());report.putExtra("pageWidth",page.getWidth());report.putExtra("pageHeight",page.getHeight());
            }
            try {getContentResolver().openFileDescriptor(uri,"rw").close();report.putExtra("writeDenied",false);}
            catch(Exception expected){report.putExtra("writeDenied",true);}
            try {getContentResolver().delete(uri,null,null);report.putExtra("deleteDenied",false);}
            catch(Exception expected){report.putExtra("deleteDenied",true);}
        } catch(Exception error) {report.putExtra("error",error.getClass().getSimpleName());}
        layout.postOnAnimation(()->layout.postOnAnimation(()->sendBroadcast(report)));
        // Remain visible for the installed screenshot and the user's Back action.
    }
}

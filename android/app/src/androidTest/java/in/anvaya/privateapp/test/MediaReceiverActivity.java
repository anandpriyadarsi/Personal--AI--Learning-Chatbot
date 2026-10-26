package in.anvaya.privateapp.test;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import java.io.InputStream;

/** Separate-UID synthetic receiver, never shipped in the installable app. */
public class MediaReceiverActivity extends Activity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        Intent report=new Intent("in.anvaya.privateapp.TEST_MEDIA_RESULT").setPackage("in.anvaya.privateapp");
        report.putExtra("uid",android.os.Process.myUid());
        try(InputStream in=getContentResolver().openInputStream(getIntent().getData())) {
            java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream();
            byte[] bytes=new byte[4096];int count;
            while((count=in.read(bytes))!=-1) out.write(bytes,0,count);
            report.putExtra("payload",out.toByteArray());
            report.putExtra("mime",getContentResolver().getType(getIntent().getData()));
            try {
                getContentResolver().openFileDescriptor(getIntent().getData(),"rw").close();
                report.putExtra("writeDenied",false);
            } catch(Exception expected) { report.putExtra("writeDenied",true); }
        } catch(Exception error) {report.putExtra("error",error.getClass().getSimpleName());}
        sendBroadcast(report);
        setResult(RESULT_OK); finish();
    }
}

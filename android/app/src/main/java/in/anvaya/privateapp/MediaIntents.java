package in.anvaya.privateapp;

import android.content.ClipData;
import android.content.Intent;
import android.net.Uri;

/** Real files with temporary read access; Android owns selection and playback. */
public final class MediaIntents {
    private static Intent grant(Intent intent,Uri uri,String mime) {
        if(!"content".equals(uri.getScheme()) || mime==null || !(mime.startsWith("audio/") || mime.startsWith("video/"))) {
            throw new IllegalArgumentException("Invalid media handoff");
        }
        intent.setClipData(ClipData.newRawUri("ANVAYA attachment",uri));
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        return intent;
    }
    public static Intent view(Uri uri,String mime) {
        return grant(new Intent(Intent.ACTION_VIEW).setDataAndType(uri,mime),uri,mime);
    }
    public static Intent share(Uri uri,String mime) {
        return grant(new Intent(Intent.ACTION_SEND).setType(mime).putExtra(Intent.EXTRA_STREAM,uri),uri,mime);
    }
}

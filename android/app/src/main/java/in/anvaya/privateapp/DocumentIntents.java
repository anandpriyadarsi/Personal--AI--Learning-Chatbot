package in.anvaya.privateapp;

import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Intent;
import android.net.Uri;

/** Android owns viewer defaults; only Open with and Share force a chooser. */
public final class DocumentIntents {
    public enum Action { VIEW, OPEN_WITH, SHARE }
    public enum Result { OPENED, NO_COMPATIBLE_APP, FAILED }
    public interface Launcher { void start(Intent intent); }
    private DocumentIntents() {}
    public static boolean supportsMime(String mime) {
        return DocumentFormats.supportsMime(mime);
    }
    public static Intent view(Uri uri,String mime) {
        return grant(new Intent(Intent.ACTION_VIEW).setDataAndType(uri,mime),uri,mime);
    }
    private static Intent grant(Intent intent,Uri uri,String mime) {
        if(uri==null||!"content".equals(uri.getScheme())||!supportsMime(mime))throw new IllegalArgumentException("Invalid document handoff");
        intent.setClipData(ClipData.newRawUri("ANVAYA document",uri));
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        return intent;
    }
    public static Intent intent(Uri uri,String mime,Action action) {
        if(action==Action.VIEW)return view(uri,mime);
        Intent content=action==Action.SHARE
            ?grant(new Intent(Intent.ACTION_SEND).setType(mime).putExtra(Intent.EXTRA_STREAM,uri),uri,mime)
            :view(uri,mime);
        return grant(Intent.createChooser(content,action==Action.SHARE?"Share document":"Open with"),uri,mime);
    }
    public static Result launch(Launcher launcher,Uri uri,String mime,Action action) {
        try {launcher.start(intent(uri,mime,action));return Result.OPENED;}
        catch(ActivityNotFoundException error){return Result.NO_COMPATIBLE_APP;}
        catch(SecurityException|IllegalArgumentException error){return Result.FAILED;}
    }
}

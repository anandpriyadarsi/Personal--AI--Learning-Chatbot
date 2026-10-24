package in.anvaya.privateapp;

import android.database.Cursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import androidx.core.content.FileProvider;
import java.io.*;
import java.util.*;

/** Only note-media files, read-only even if a client asks for write access. */
public class MediaFileProvider extends FileProvider {
    private String checkedMime(Uri uri) throws FileNotFoundException {
        List<String> parts=uri.getPathSegments();
        if(parts.size()!=4 || !"note_media".equals(parts.get(0)) || !parts.get(1).matches("[A-Za-z0-9_-]+")
            || !"media".equals(parts.get(2)) || !parts.get(3).matches("[A-Za-z0-9_-]+\\.(mp3|wav|m4a|aac|mp4|mkv|mov|webm)")) {
            throw new FileNotFoundException("Attachment unavailable");
        }
        try {
            File base=getContext().getFilesDir().getCanonicalFile();
            File file=new File(base,"data/anvaya_notes_assets/"+parts.get(1)+"/media/"+parts.get(3));
            if(!file.getCanonicalFile().equals(file.getAbsoluteFile()) || !file.isFile()) throw new FileNotFoundException("Attachment unavailable");
        } catch(IOException error) {throw new FileNotFoundException("Attachment unavailable");}
        String suffix=parts.get(3).substring(parts.get(3).lastIndexOf('.')+1);
        switch(suffix) {
            case "mp3":return "audio/mpeg";case "wav":return "audio/wav";
            case "m4a":return "audio/mp4";case "aac":return "audio/aac";
            case "mp4":return "video/mp4";case "mkv":return "video/x-matroska";
            case "mov":return "video/quicktime";default:return "video/webm";
        }
    }
    @Override public ParcelFileDescriptor openFile(Uri uri,String mode) throws FileNotFoundException {
        if(!"r".equals(mode)) throw new FileNotFoundException("Attachment is read-only");
        checkedMime(uri);return super.openFile(uri,"r");
    }
    @Override public String getType(Uri uri) {
        try {return checkedMime(uri);} catch(FileNotFoundException error) {return "application/octet-stream";}
    }
    @Override public Cursor query(Uri uri,String[] projection,String selection,String[] args,String order) {
        try {checkedMime(uri);} catch(FileNotFoundException error) {throw new SecurityException("Attachment unavailable");}
        return super.query(uri,projection,selection,args,order);
    }
    @Override public int delete(Uri uri,String selection,String[] args) {
        throw new SecurityException("Attachments are read-only");
    }
}

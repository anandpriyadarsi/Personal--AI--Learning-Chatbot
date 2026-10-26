package in.anvaya.privateapp;

import android.net.Uri;
import android.os.ParcelFileDescriptor;
import androidx.core.content.FileProvider;
import java.io.FileNotFoundException;

/** App-private picker snapshots are read-only and never exported globally. */
public class UploadFileProvider extends FileProvider {
    @Override public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        if (!"r".equals(mode)) throw new FileNotFoundException("Upload selection is read-only");
        return super.openFile(uri, mode);
    }
    @Override public int delete(Uri uri, String selection, String[] args) {
        throw new SecurityException("Upload selection is read-only");
    }
}

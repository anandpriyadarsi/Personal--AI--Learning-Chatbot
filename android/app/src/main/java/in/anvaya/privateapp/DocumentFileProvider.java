package in.anvaya.privateapp;

import android.net.Uri;
import android.os.ParcelFileDescriptor;
import androidx.core.content.FileProvider;
import java.io.FileNotFoundException;
import java.util.Locale;

/** View/share grants expose immutable managed originals for reading only. */
public final class DocumentFileProvider extends FileProvider {
    @Override public ParcelFileDescriptor openFile(Uri uri,String mode) throws FileNotFoundException {
        if(!"r".equals(mode))throw new FileNotFoundException("Original document is read-only");
        return super.openFile(uri,mode);
    }
    @Override public int delete(Uri uri,String selection,String[] args) {
        throw new SecurityException("Original document is read-only");
    }
    @Override public String getType(Uri uri) {
        // Managed blobs have content hashes as filenames. The display name is
        // supplied by the verified resolver when creating each read grant.
        String name=uri.getQueryParameter("displayName");
        return DocumentFormats.mimeForName(name);
    }
}

package in.anvaya.privateapp.test;

import android.content.*;
import android.database.*;
import android.graphics.pdf.PdfDocument;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import java.io.*;

/** Test APK only: a picker document whose reported timestamp changes each query. */
public class ChangingUploadProvider extends ContentProvider {
    private File source;
    private long modified = System.currentTimeMillis();
    @Override public boolean onCreate() {
        source = new File(getContext().getCacheDir(), "changing-lecture.pdf");
        PdfDocument document = new PdfDocument();
        try {
            PdfDocument.Page page = document.startPage(new PdfDocument.PageInfo.Builder(400, 400, 1).create());
            page.getCanvas().drawText("Synthetic upload regression", 20, 50, new android.graphics.Paint());
            document.finishPage(page);
            try (FileOutputStream output = new FileOutputStream(source)) { document.writeTo(output); }
            return true;
        } catch (IOException error) { return false; }
        finally { document.close(); }
    }
    @Override public String getType(Uri uri) { return "application/pdf"; }
    @Override public Cursor query(Uri uri, String[] projection, String selection, String[] args, String sort) {
        String[] columns = projection == null ? new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE, "last_modified"} : projection;
        MatrixCursor result = new MatrixCursor(columns);
        Object[] row = new Object[columns.length];
        for (int i=0; i<columns.length; i++) {
            if (OpenableColumns.DISPLAY_NAME.equals(columns[i])) row[i] = "Changing lecture.pdf";
            else if (OpenableColumns.SIZE.equals(columns[i])) row[i] = source.length();
            else if ("last_modified".equals(columns[i])) row[i] = ++modified;
        }
        result.addRow(row); return result;
    }
    @Override public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        if (!"r".equals(mode)) throw new FileNotFoundException("read only");
        return ParcelFileDescriptor.open(source, ParcelFileDescriptor.MODE_READ_ONLY);
    }
    @Override public Uri insert(Uri uri, ContentValues values) { throw new UnsupportedOperationException(); }
    @Override public int update(Uri uri, ContentValues values, String where, String[] args) { throw new UnsupportedOperationException(); }
    @Override public int delete(Uri uri, String where, String[] args) { throw new UnsupportedOperationException(); }
}

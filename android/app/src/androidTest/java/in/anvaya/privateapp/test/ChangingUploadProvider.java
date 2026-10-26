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
    private File source, presentation;
    private long modified = System.currentTimeMillis();
    @Override public boolean onCreate() {
        source = new File(getContext().getCacheDir(), "changing-lecture.pdf");
        PdfDocument document = new PdfDocument();
        try {
            PdfDocument.Page page = document.startPage(new PdfDocument.PageInfo.Builder(400, 400, 1).create());
            page.getCanvas().drawText("Synthetic upload regression", 20, 50, new android.graphics.Paint());
            document.finishPage(page);
            try (FileOutputStream output = new FileOutputStream(source)) { document.writeTo(output); }
            presentation = new File(getContext().getCacheDir(), "changing-lecture.pptx");
            try (java.util.zip.ZipOutputStream zip = new java.util.zip.ZipOutputStream(new FileOutputStream(presentation))) {
                String[][] entries = {
                    {"[Content_Types].xml", "<Types/>"},
                    {"ppt/presentation.xml", "<p:presentation xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"><p:sldIdLst><p:sldId id=\"256\" r:id=\"r1\"/></p:sldIdLst></p:presentation>"},
                    {"ppt/_rels/presentation.xml.rels", "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"r1\" Target=\"slides/slide1.xml\"/></Relationships>"},
                    {"ppt/slides/slide1.xml", "<p:sld xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\" xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\"><a:p><a:r><a:t>AnvayaPptxVerificationToken</a:t></a:r></a:p></p:sld>"}
                };
                for (String[] entry: entries) {
                    zip.putNextEntry(new java.util.zip.ZipEntry(entry[0]));
                    zip.write(entry[1].getBytes(java.nio.charset.StandardCharsets.UTF_8)); zip.closeEntry();
                }
            }
            return true;
        } catch (IOException error) { return false; }
        finally { document.close(); }
    }
    private boolean isPresentation(Uri uri) { return uri.getLastPathSegment().endsWith(".pptx"); }
    @Override public String getType(Uri uri) { return isPresentation(uri) ? "application/vnd.openxmlformats-officedocument.presentationml.presentation" : "application/pdf"; }
    @Override public Cursor query(Uri uri, String[] projection, String selection, String[] args, String sort) {
        String[] columns = projection == null ? new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE, "last_modified"} : projection;
        MatrixCursor result = new MatrixCursor(columns);
        Object[] row = new Object[columns.length];
        for (int i=0; i<columns.length; i++) {
            if (OpenableColumns.DISPLAY_NAME.equals(columns[i])) row[i] = isPresentation(uri) ? "Changing lecture.pptx" : "Changing lecture.pdf";
            else if (OpenableColumns.SIZE.equals(columns[i])) row[i] = (isPresentation(uri) ? presentation : source).length();
            else if ("last_modified".equals(columns[i])) row[i] = ++modified;
        }
        result.addRow(row); return result;
    }
    @Override public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        if (!"r".equals(mode)) throw new FileNotFoundException("read only");
        return ParcelFileDescriptor.open(isPresentation(uri) ? presentation : source, ParcelFileDescriptor.MODE_READ_ONLY);
    }
    @Override public Uri insert(Uri uri, ContentValues values) { throw new UnsupportedOperationException(); }
    @Override public int update(Uri uri, ContentValues values, String where, String[] args) { throw new UnsupportedOperationException(); }
    @Override public int delete(Uri uri, String where, String[] args) { throw new UnsupportedOperationException(); }
}

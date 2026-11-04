package in.anvaya.privateapp;
import org.junit.Test;
import static org.junit.Assert.*;
public class DocumentFormatsTest {
    @Test public void filenamesKeepCorrectPassiveMimeAfterRename() {
        assertEquals("application/msword",DocumentFormats.mimeForName("Chemistry.DOC"));
        assertEquals("text/plain",DocumentFormats.mimeForName("डेटा.py"));
        assertEquals("application/vnd.openxmlformats-officedocument.wordprocessingml.document",DocumentFormats.mimeForName("Notes.docx"));
        assertEquals("image/jpeg",DocumentFormats.mimeForName("Photo.jpeg"));
        assertTrue(DocumentFormats.supportsMime("text/csv"));
        assertFalse(DocumentFormats.supportsMime("application/vnd.android.package-archive"));
        assertFalse(DocumentFormats.supportsMime("text/html"));
        assertEquals("application/octet-stream",DocumentFormats.mimeForName("file.apk"));
    }
}

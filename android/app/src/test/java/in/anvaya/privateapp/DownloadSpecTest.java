package in.anvaya.privateapp;
import org.junit.Test;
import static org.junit.Assert.*;

public class DownloadSpecTest {
    @Test public void preservesLocalDocumentTypesAndNames() {
        DownloadSpec pdf=DownloadSpec.from("linear-algebra.pdf","application/pdf");
        assertEquals("linear-algebra.pdf",pdf.name);
        assertEquals("application/pdf",pdf.mime);
        DownloadSpec brief=DownloadSpec.from("learning-review-brief.txt","text/plain; charset=utf-8");
        assertEquals("learning-review-brief.txt",brief.name);
        assertEquals("text/plain",brief.mime);
        assertEquals("ANVAYA-private-backup.zip",DownloadSpec.from("ANVAYA-private-backup.zip","application/zip").name);
    }
    @Test public void boundsUntrustedNamesAndMimeWithoutLosingFileExtension() {
        DownloadSpec unsafe=DownloadSpec.from("../private\\notes\n.pdf","invalid\r\nmime");
        assertFalse(unsafe.name.contains("/"));assertFalse(unsafe.name.contains("\\"));
        assertFalse(unsafe.name.contains("\n"));assertFalse(unsafe.name.startsWith("."));
        assertEquals("application/octet-stream",unsafe.mime);
        DownloadSpec longName=DownloadSpec.from("a".repeat(200)+".pdf","application/pdf");
        assertTrue(longName.name.length()<=120);assertTrue(longName.name.endsWith(".pdf"));
        assertEquals("ANVAYA-download",DownloadSpec.from(null,null).name);
    }
}

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
    @Test public void dispositionPrefersUtf8AndPreservesLiteralPlus() {
        String header="attachment; filename=math.pdf; filename*=UTF-8''%CF%80%20+%20%CE%BB%20%E2%88%88%20%E2%84%9D.pdf";
        DownloadSpec file=DownloadSpec.fromDisposition("math.pdf",header,"application/pdf");
        assertEquals("π + λ ∈ ℝ.pdf",file.name);assertEquals("application/pdf",file.mime);
        assertEquals("browser.pdf",DownloadSpec.fromDisposition("browser.pdf","attachment; filename=browser.pdf","application/pdf").name);
    }
    @Test public void malformedExtendedNamesFallBackAndUnsafeNamesStayBounded() {
        for(String value:new String[]{"UTF-8''%ZZ.pdf","UTF-8''%C3%28.pdf","ISO-8859-1''%E9.pdf","UTF-8''%４１.pdf","UTF-8''"})
            assertEquals("fallback.pdf",DownloadSpec.fromDisposition("fallback.pdf","attachment; filename*="+value,"application/pdf").name);
        String unsafe=DownloadSpec.fromDisposition("fallback.pdf","attachment; filename*=UTF-8''..%2Fnotes%5Cprivate%0D%0A.pdf","application/pdf").name;
        assertFalse(unsafe.contains("/"));assertFalse(unsafe.contains("\\"));assertFalse(unsafe.contains("\n"));assertFalse(unsafe.contains("\r"));assertFalse(unsafe.startsWith("."));
        assertEquals("fallback.pdf",DownloadSpec.fromDisposition("fallback.pdf","attachment; filename*=UTF-8''"+"a".repeat(9000),"application/pdf").name);
        DownloadSpec emoji=DownloadSpec.fromDisposition("fallback.pdf","attachment; filename*=UTF-8''a"+"%F0%9F%92%A1".repeat(100)+".pdf","application/pdf");
        assertTrue(emoji.name.length()<=120);assertTrue(Character.isLowSurrogate(emoji.name.charAt(emoji.name.length()-5)));
    }
}

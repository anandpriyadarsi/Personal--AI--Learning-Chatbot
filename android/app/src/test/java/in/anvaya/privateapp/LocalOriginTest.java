package in.anvaya.privateapp;
import org.junit.Test;
import static org.junit.Assert.*;
public class LocalOriginTest {
    @Test public void permitsOnlyExactLocalOrigin() {
        LocalOrigin origin = new LocalOrigin("http://127.0.0.1:12345");
        assertTrue(origin.permits("http://127.0.0.1:12345/notes?q=hello"));
        for (String url : new String[]{"https://127.0.0.1:12345/", "http://127.0.0.1:12346/",
            "http://localhost:12345/", "file:///etc/passwd", "content://private/1", "javascript:alert(1)",
            "http://127.0.0.1.evil:12345/", "http://evil@127.0.0.1:12345/", "https://example.com/"}) {
            assertFalse(url, origin.permits(url));
        }
    }
}

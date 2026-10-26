package in.anvaya.privateapp;
import org.junit.Test;
import static org.junit.Assert.*;

public class NativeDocumentRequestTest {
    private final String origin="http://127.0.0.1:12345";
    private final String base=origin+"/library/files/"+"a".repeat(32);
    @Test public void opensMatchAtRequestedPageWithoutPassingCapabilityToIntent(){
        NativeDocumentRequest request=NativeDocumentRequest.parse(origin,base+"/open?position=18&q=Eigenvalues");
        assertNotNull(request);assertEquals(18,request.position);assertFalse(request.share);
        assertEquals(base+"/original?download=1",request.originalAddress);
        assertEquals(base+"/open?browser=1",request.browserAddress);
        assertTrue(NativeDocumentRequest.parse(origin,base+"/original?native_action=share").share);
    }
    @Test public void rejectsOtherOriginsPathsDuplicatesAndUnsupportedNavigation(){
        for(String url:new String[]{base+"/original",base+"/open?browser=1",base+"/open?position=0",base+"/open?position=2501",base+"/open?position=1&position=2",base.replace(":12345",":12346")+"/open",base.replace("127.0.0.1","evil.test")+"/open",origin+"/mobile/backup?native_action=share"})assertNull(url,NativeDocumentRequest.parse(origin,url));
    }
}

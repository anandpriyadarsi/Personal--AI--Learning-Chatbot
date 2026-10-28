package in.anvaya.privateapp;
import org.junit.Test;
import static org.junit.Assert.*;

public class NativeDocumentRequestTest {
    private final String origin="http://127.0.0.1:12345";
    private final String identity="a".repeat(32);
    private final String base=origin+"/library/files/"+identity;
    @Test public void defaultViewAndChooserAreDifferentExplicitActions(){
        NativeDocumentRequest view=NativeDocumentRequest.parse(origin,base+"/original?native_action=view");
        assertNotNull(view);assertEquals(identity,view.documentId);assertFalse(view.openWith);assertFalse(view.reader);
        assertTrue(NativeDocumentRequest.parse(origin,base+"/original?native_action=open_with").openWith);
        assertTrue(NativeDocumentRequest.parse(origin,base+"/original?native_action=share").share);
    }
    @Test public void matchedReaderIsExplicitAndDoesNotForwardQueryOrCapability(){
        NativeDocumentRequest request=NativeDocumentRequest.parse(origin,base+"/open?native_action=reader&position=18&q=Eigenvalues");
        assertNotNull(request);assertTrue(request.reader);assertEquals(18,request.position);
        assertEquals(base+"/original?download=1",request.originalAddress);
        assertEquals(base+"/open?browser=1",request.browserAddress);
    }
    @Test public void rejectsOtherOriginsPathsDuplicatesAndUnsupportedNavigation(){
        for(String url:new String[]{base+"/original",base+"/open",base+"/open?browser=1",base+"/original?native_action=reader",base+"/original?native_action=unknown",base+"/original?native_action=view&download=0",base+"/open?native_action=reader&position=0",base+"/open?native_action=reader&position=2501",base+"/open?native_action=reader&position=1&position=2",base.replace(":12345",":12346")+"/original?native_action=view",base.replace("127.0.0.1","evil.test")+"/original?native_action=view",origin+"/mobile/backup?native_action=view"})assertNull(url,NativeDocumentRequest.parse(origin,url));
    }
}

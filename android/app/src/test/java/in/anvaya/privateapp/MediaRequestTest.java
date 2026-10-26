package in.anvaya.privateapp;
import org.junit.Test;
import static org.junit.Assert.*;
public class MediaRequestTest {
    @Test public void onlyExactGesturedMainFrameLinksAreAccepted() {
        LocalOrigin origin=new LocalOrigin("http://127.0.0.1:3210");
        String good="http://127.0.0.1:3210/notes/media/note_1/file-2/open";
        MediaRequest request=MediaRequest.parse(origin,good,true,true);
        assertNotNull(request);assertEquals("note_1",request.noteId);assertEquals("file-2",request.assetId);assertFalse(request.share);
        assertNull(MediaRequest.parse(origin,good,false,true));assertNull(MediaRequest.parse(origin,good,true,false));
        assertTrue(MediaRequest.parse(origin,good.replace("/open","/share"),true,true).share);
        for(String bad:new String[]{good+"?q=1",good+"#x",good.replace(":3210",":3211"),good.replace("note_1",".."),good.replace("file-2","%2fsecret"),good.replace("127.0.0.1","evil.example"),good.replace("127.0.0.1","a@127.0.0.1")}) assertNull(bad,MediaRequest.parse(origin,bad,true,true));
        assertTrue(MediaRequest.isDownload(origin,good.replace("/open","/file")));
        assertFalse(MediaRequest.isDownload(origin,good));
    }
}

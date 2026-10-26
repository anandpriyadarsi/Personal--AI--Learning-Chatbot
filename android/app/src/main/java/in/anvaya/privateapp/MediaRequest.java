package in.anvaya.privateapp;

import java.net.URI;
import java.util.regex.*;

/** A navigation bridge, not a JavaScript interface. Never accepts a file path. */
public final class MediaRequest {
    private static final Pattern PATH=Pattern.compile("^/notes/media/([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)/(open|share)$");
    public final String noteId,assetId;
    public final boolean share;
    private MediaRequest(String note,String asset,boolean share) {noteId=note;assetId=asset;this.share=share;}
    public static MediaRequest parse(LocalOrigin origin,String url,boolean mainFrame,boolean gesture) {
        if(!mainFrame || !gesture || !origin.permits(url)) return null;
        try {
            URI uri=URI.create(url);
            if(uri.getRawQuery()!=null || uri.getRawFragment()!=null) return null;
            Matcher match=PATH.matcher(uri.getRawPath());
            return match.matches() ? new MediaRequest(match.group(1),match.group(2),"share".equals(match.group(3))) : null;
        } catch(IllegalArgumentException error) {return null;}
    }
    public static boolean isDownload(LocalOrigin origin,String url) {
        return url!=null && parse(origin,url.replaceFirst("/file$","/open"),true,true)!=null && url.endsWith("/file");
    }
}

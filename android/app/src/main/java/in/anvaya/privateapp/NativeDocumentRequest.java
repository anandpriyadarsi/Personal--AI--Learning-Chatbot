package in.anvaya.privateapp;

import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

/** Only explicit original-document links may become Android intents. */
public final class NativeDocumentRequest {
    public final boolean share;
    public final int position;
    public final String originalAddress;
    public final String browserAddress;
    private NativeDocumentRequest(boolean share, int position, String original, String browser) { this.share=share; this.position=position; this.originalAddress=original; this.browserAddress=browser; }
    public static NativeDocumentRequest parse(String origin, String address) {
        try {
            if (!new LocalOrigin(origin).permits(address)) return null;
            URI uri=URI.create(address);
            if (!uri.getRawPath().matches("/library/files/[0-9a-f]{32}/(original|open)") || uri.getFragment()!=null) return null;
            boolean reader=uri.getRawPath().endsWith("/open");
            Map<String,String> query=new HashMap<>();
            for(String pair:(uri.getRawQuery()==null?new String[0]:uri.getRawQuery().split("&"))) {
                String[] kv=pair.split("=",2);
                if(kv.length!=2)return null;
                String key=URLDecoder.decode(kv[0],StandardCharsets.UTF_8.name());
                String value=URLDecoder.decode(kv[1],StandardCharsets.UTF_8.name());
                if(query.put(key,value)!=null)return null;
                if(!key.equals("download")&&!key.equals("native_action")&&!key.equals("position")&&!(reader&&(key.equals("q")||key.equals("action"))))return null;
            }
            String action=query.getOrDefault("native_action",reader?query.getOrDefault("action","open"):"");
            if(!"open".equals(action)&&!"share".equals(action))return null;
            int position=Integer.parseInt(query.getOrDefault("position","1"));
            if(position<1||position>2500)return null;
            String prefix=origin+uri.getRawPath().replaceFirst("/(original|open)$","");
            return new NativeDocumentRequest("share".equals(action),position,prefix+"/original?download=1",prefix+"/open?browser=1");
        }catch(Exception error){return null;}
    }
}

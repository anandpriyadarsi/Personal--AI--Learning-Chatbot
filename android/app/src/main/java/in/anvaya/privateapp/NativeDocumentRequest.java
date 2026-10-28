package in.anvaya.privateapp;

import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

/** Only an explicit same-origin document action can cross the native boundary. */
public final class NativeDocumentRequest {
    public final boolean share, openWith, reader;
    public final int position;
    public final String documentId, originalAddress, browserAddress;
    private NativeDocumentRequest(String action, String identity, int position, String prefix) {
        share="share".equals(action);openWith="open_with".equals(action);reader="reader".equals(action);
        documentId=identity;this.position=position;
        originalAddress=prefix+"/original?download=1";browserAddress=prefix+"/open?browser=1";
    }
    public static NativeDocumentRequest parse(String origin, String address) {
        try {
            if (!new LocalOrigin(origin).permits(address)) return null;
            URI uri=URI.create(address);
            if (!uri.getRawPath().matches("/library/files/[0-9a-f]{32}/(original|open)") || uri.getFragment()!=null) return null;
            boolean readerPath=uri.getRawPath().endsWith("/open");
            Map<String,String> query=new HashMap<>();
            for(String pair:(uri.getRawQuery()==null?new String[0]:uri.getRawQuery().split("&",-1))) {
                String[] kv=pair.split("=",2);
                if(kv.length!=2)return null;
                String key=URLDecoder.decode(kv[0],StandardCharsets.UTF_8.name());
                String value=URLDecoder.decode(kv[1],StandardCharsets.UTF_8.name());
                if(query.put(key,value)!=null)return null;
                if(!key.equals("download")&&!key.equals("native_action")&&!key.equals("position")&&!(readerPath&&key.equals("q")))return null;
            }
            String action=query.getOrDefault("native_action","");
            if("open".equals(action))action="view"; // previously shared original links
            if(readerPath ? !"reader".equals(action) : !("view".equals(action)||"open_with".equals(action)||"share".equals(action)))return null;
            if(query.containsKey("download")&&!"1".equals(query.get("download")))return null;
            if(query.getOrDefault("q","").length()>500)return null;
            int position=Integer.parseInt(query.getOrDefault("position","1"));
            if(position<1||position>2500)return null;
            String identity=uri.getRawPath().split("/")[3];
            return new NativeDocumentRequest(action,identity,position,origin+"/library/files/"+identity);
        }catch(Exception error){return null;}
    }
}

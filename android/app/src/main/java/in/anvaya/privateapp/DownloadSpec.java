package in.anvaya.privateapp;

/** Bounded metadata for local attachments selected through Android's picker. */
public final class DownloadSpec {
    public final String name;
    public final String mime;
    private DownloadSpec(String name,String mime) { this.name=name;this.mime=mime; }
    /** Android 12 URLUtil ignores filename*=, so prefer a valid RFC 5987 name. */
    public static DownloadSpec fromDisposition(String guessedName,String disposition,String mimeType) {
        String extended=extendedFilename(disposition);
        return from(extended==null?guessedName:extended,mimeType);
    }
    private static String extendedFilename(String disposition) {
        if(disposition==null||disposition.length()>8192||disposition.indexOf('\r')>=0||disposition.indexOf('\n')>=0)return null;
        // Split only outside quoted parameters. A semicolon in filename="..."
        // must not impersonate a filename* parameter.
        java.util.List<String> parts=new java.util.ArrayList<>();
        boolean quoted=false,escaped=false;int start=0;
        for(int i=0;i<disposition.length();i++){
            char c=disposition.charAt(i);
            if(escaped){escaped=false;continue;}
            if(quoted&&c=='\\'){escaped=true;continue;}
            if(c=='"')quoted=!quoted;
            else if(c==';'&&!quoted){parts.add(disposition.substring(start,i));start=i+1;}
        }
        if(quoted||escaped)return null;
        parts.add(disposition.substring(start));String value=null;
        for(int i=1;i<parts.size();i++){
            String parameter=parts.get(i);int equals=parameter.indexOf('=');
            if(equals<0||!"filename*".equalsIgnoreCase(parameter.substring(0,equals).trim()))continue;
            if(value!=null)return null; // ambiguous duplicate parameters
            value=parameter.substring(equals+1).trim();
        }
        if(value==null||value.length()>4096)return null;
        int first=value.indexOf('\''),second=first<0?-1:value.indexOf('\'',first+1);
        if(first<0||second<0||!"UTF-8".equalsIgnoreCase(value.substring(0,first))||!value.substring(first+1,second).matches("[A-Za-z0-9-]*"))return null;
        java.io.ByteArrayOutputStream bytes=new java.io.ByteArrayOutputStream();
        for(int i=second+1;i<value.length();i++){
            char c=value.charAt(i);
            if(c=='%'){
                if(i+2>=value.length())return null;
                if(value.charAt(i+1)>127||value.charAt(i+2)>127)return null;
                int high=Character.digit(value.charAt(i+1),16),low=Character.digit(value.charAt(i+2),16);
                if(high<0||low<0)return null;
                bytes.write((high<<4)|low);i+=2;
            } else {
                // RFC 5987 attr-char; '+' is literal, never form-decoded.
                if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||"!#$&+-.^_`|~".indexOf(c)>=0))return null;
                bytes.write(c);
            }
            if(bytes.size()>1024)return null;
        }
        if(bytes.size()==0)return null;
        try {
            return java.nio.charset.StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
                .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT)
                .decode(java.nio.ByteBuffer.wrap(bytes.toByteArray())).toString();
        } catch(java.nio.charset.CharacterCodingException error){return null;}
    }
    public static DownloadSpec from(String guessedName,String mimeType) {
        String name=guessedName==null ? "" : guessedName.replaceAll("[\\\\/\\p{Cntrl}]","_").trim().replaceFirst("^\\.+","");
        if(name.isEmpty())name="ANVAYA-download";
        if(name.length()>120) {
            int dot=name.lastIndexOf('.');
            String extension=dot>=0 && name.length()-dot<=12 ? name.substring(dot) : "";
            int end=120-extension.length();
            if(end>0&&Character.isHighSurrogate(name.charAt(end-1)))end--;
            name=name.substring(0,end)+extension;
        }
        String mime=mimeType==null ? "" : mimeType.split(";",2)[0].trim().toLowerCase(java.util.Locale.ROOT);
        if(!mime.matches("[a-z0-9.+-]+/[a-z0-9.+-]+"))mime="application/octet-stream";
        return new DownloadSpec(name,mime);
    }
}

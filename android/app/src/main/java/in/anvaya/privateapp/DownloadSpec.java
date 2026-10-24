package in.anvaya.privateapp;

/** Bounded metadata for local attachments selected through Android's picker. */
public final class DownloadSpec {
    public final String name;
    public final String mime;
    private DownloadSpec(String name,String mime) { this.name=name;this.mime=mime; }
    public static DownloadSpec from(String guessedName,String mimeType) {
        String name=guessedName==null ? "" : guessedName.replaceAll("[\\\\/\\p{Cntrl}]","_").trim().replaceFirst("^\\.+","");
        if(name.isEmpty())name="ANVAYA-download";
        if(name.length()>120) {
            int dot=name.lastIndexOf('.');
            String extension=dot>=0 && name.length()-dot<=12 ? name.substring(dot) : "";
            name=name.substring(0,120-extension.length())+extension;
        }
        String mime=mimeType==null ? "" : mimeType.split(";",2)[0].trim().toLowerCase(java.util.Locale.ROOT);
        if(!mime.matches("[a-z0-9.+-]+/[a-z0-9.+-]+"))mime="application/octet-stream";
        return new DownloadSpec(name,mime);
    }
}

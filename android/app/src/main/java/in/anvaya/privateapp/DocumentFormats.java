package in.anvaya.privateapp;

/** Mirrors native_document_formats.MIMES; contract-tested at the Python boundary. */
public final class DocumentFormats {
    private DocumentFormats() {}
    public static String mimeForName(String name) {
        String lower=name==null?"":name.toLowerCase(java.util.Locale.ROOT);
        int dot=lower.lastIndexOf('.');String extension=dot<0?"":lower.substring(dot+1);
        switch(extension) {
            case "pdf": return "application/pdf";
            case "ppt": return "application/vnd.ms-powerpoint";
            case "pptx": return "application/vnd.openxmlformats-officedocument.presentationml.presentation";
            case "doc": return "application/msword";
            case "docx": return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
            case "png": return "image/png";
            case "jpg": case "jpeg": return "image/jpeg";
            case "webp": return "image/webp";
            case "txt": case "py": return "text/plain";
            case "md": return "text/markdown";
            case "csv": return "text/csv";
            default: return "application/octet-stream";
        }
    }
    public static boolean supportsMime(String mime) {
        for(String extension:new String[]{"pdf","ppt","pptx","doc","docx","png","jpg","webp","txt","md","csv"})
            if(mimeForName("file."+extension).equals(mime))return true;
        return false;
    }
}

package in.anvaya.privateapp;

/** Exact storage filenames accepted by the read-only note attachment provider. */
final class NoteAttachmentType {
    private NoteAttachmentType() {}
    static boolean supportsMime(String mime) {
        if (mime == null) return false;
        for (String suffix : new String[]{"mp3","wav","m4a","aac","mp4","mkv","mov","webm",
                "png","jpg","pdf","txt","md","csv","docx","pptx","xlsx"}) {
            if (mime.equals(mimeForFilename("asset." + suffix))) return true;
        }
        return false;
    }
    static String mimeForFilename(String filename) {
        if (filename == null || !filename.matches("[A-Za-z0-9_-]+\\.[a-z0-9]+")) return null;
        switch (filename.substring(filename.lastIndexOf('.') + 1)) {
            case "mp3": return "audio/mpeg";
            case "wav": return "audio/wav";
            case "m4a": return "audio/mp4";
            case "aac": return "audio/aac";
            case "mp4": return "video/mp4";
            case "mkv": return "video/x-matroska";
            case "mov": return "video/quicktime";
            case "webm": return "video/webm";
            case "png": return "image/png";
            case "jpg": case "jpeg": return "image/jpeg";
            case "pdf": return "application/pdf";
            case "txt": return "text/plain";
            case "md": return "text/markdown";
            case "csv": return "text/csv";
            case "docx": return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
            case "pptx": return "application/vnd.openxmlformats-officedocument.presentationml.presentation";
            case "xlsx": return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
            default: return null;
        }
    }
}

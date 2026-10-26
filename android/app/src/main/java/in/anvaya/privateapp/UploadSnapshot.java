package in.anvaya.privateapp;

import java.io.*;
import java.util.UUID;

/** Immutable, bounded copy of a selected provider stream before WebView sees it. */
public final class UploadSnapshot {
    private UploadSnapshot() {}

    public static File copy(InputStream source, File root, String name, long limit) throws IOException {
        File directory = null, destination = null;
        try (InputStream input = source) {
            if (input == null || limit < 1) throw new IOException("Selected file unavailable");
            directory = new File(root, UUID.randomUUID().toString());
            if (!directory.mkdirs()) throw new IOException("Upload storage unavailable");
            destination = new File(directory, DownloadSpec.from(name, null).name);
            try (FileOutputStream output = new FileOutputStream(destination)) {
                byte[] buffer = new byte[32768]; long size = 0; int count;
                while ((count = input.read(buffer)) != -1) {
                    size += count;
                    if (size > limit) throw new IOException("Selected files exceed the upload limit");
                    output.write(buffer, 0, count);
                }
                output.getFD().sync();
            }
        } catch (IOException | RuntimeException error) {
            if (destination != null) destination.delete();
            if (directory != null) directory.delete();
            throw error;
        }
        return destination;
    }
}

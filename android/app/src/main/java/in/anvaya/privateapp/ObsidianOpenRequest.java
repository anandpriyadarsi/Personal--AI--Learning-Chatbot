package in.anvaya.privateapp;

import java.net.URI;
import java.net.URLDecoder;
import java.util.HashSet;
import java.util.Set;

/** Only explicit reader gestures may ask Obsidian to open a named vault note. */
final class ObsidianOpenRequest {
    private ObsidianOpenRequest() {}
    static boolean permits(String address, boolean mainFrame, boolean gesture) {
        if (!mainFrame || !gesture || address == null) return false;
        try {
            URI uri = new URI(address);
            if (!"obsidian".equals(uri.getScheme()) || !"open".equals(uri.getRawAuthority())
                || !uri.getPath().isEmpty() || uri.getRawFragment() != null || uri.getRawQuery() == null) return false;
            Set<String> keys = new HashSet<>();
            for (String part : uri.getRawQuery().split("&", -1)) {
                int equals = part.indexOf('=');
                if (equals < 0) return false;
                String key = URLDecoder.decode(part.substring(0, equals), "UTF-8");
                String value = URLDecoder.decode(part.substring(equals + 1), "UTF-8");
                if (!("vault".equals(key) || "file".equals(key)) || !keys.add(key)
                    || value.trim().isEmpty() || value.matches("(?s).*\\p{Cntrl}.*")) return false;
            }
            return keys.size() == 2;
        } catch (Exception invalid) { return false; }
    }
}

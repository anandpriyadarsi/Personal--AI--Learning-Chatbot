package in.anvaya.privateapp;

import java.net.URI;

/** Exact scheme/host/port boundary shared by navigation and subrequests. */
public final class LocalOrigin {
    private final URI origin;
    public LocalOrigin(String value) { origin = URI.create(value); }
    public boolean permits(String value) {
        try {
            URI candidate = URI.create(value);
            return "http".equals(candidate.getScheme())
                && "127.0.0.1".equals(candidate.getHost())
                && origin.getPort() == candidate.getPort()
                && candidate.getRawUserInfo() == null;
        } catch (IllegalArgumentException error) { return false; }
    }
}

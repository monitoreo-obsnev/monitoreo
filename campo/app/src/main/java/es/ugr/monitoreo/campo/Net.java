package es.ugr.monitoreo.campo;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.PrivateKey;
import java.security.Signature;
import java.security.spec.PKCS8EncodedKeySpec;
import java.util.Base64;

/**
 * HTTP and the OAuth flow of a Google service account (JWT bearer, RFC 7523), with the standard library of Java only,
 * so that it is also tested on the desktop (see tools/TestAuth.java).
 */
public final class Net {

    public static final String SCOPES =
            "https://www.googleapis.com/auth/earthengine https://www.googleapis.com/auth/cloud-platform";
    public static final String TOKEN_URI = "https://oauth2.googleapis.com/token";

    private Net() {
    }

    /** {status, body} of a request (BODY null: GET). */
    public static Object[] request(String method, String url, String body, String contentType) throws IOException {
        return request(method, url, body, contentType, null, 60000);
    }

    /** The same with extra HEADERS (name, value, name, value…) and a read timeout of READ ms. */
    public static Object[] request(String method, String url, String body, String contentType, String[] headers, int read)
            throws IOException {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(20000);
        c.setReadTimeout(read);
        c.setRequestMethod(method);
        c.setRequestProperty("User-Agent", "monitoreo-campo");
        c.setRequestProperty("Accept", "application/json");
        if (headers != null) for (int i = 0; i + 1 < headers.length; i += 2) c.setRequestProperty(headers[i], headers[i + 1]);
        if (body != null) {
            c.setDoOutput(true);
            c.setRequestProperty("Content-Type", contentType);
            try (OutputStream out = c.getOutputStream()) {
                out.write(body.getBytes(StandardCharsets.UTF_8));
            }
        }
        int status = c.getResponseCode();
        InputStream in = status >= 400 ? c.getErrorStream() : c.getInputStream();
        String text = in == null ? "" : read(in);
        c.disconnect();
        return new Object[]{status, text};
    }

    public static String read(InputStream in) throws IOException {
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        byte[] b = new byte[16384];
        int n;
        while ((n = in.read(b)) > 0) buf.write(b, 0, n);
        in.close();
        return buf.toString("UTF-8");
    }

    private static String b64url(byte[] b) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(b);
    }

    private static String jsonString(String s) {
        StringBuilder out = new StringBuilder("\"");
        for (char ch : s.toCharArray()) {
            if (ch == '"' || ch == '\\') out.append('\\').append(ch);
            else if (ch < 0x20) out.append(String.format("\\u%04x", (int) ch));
            else out.append(ch);
        }
        return out.append('"').toString();
    }

    public static PrivateKey privateKey(String pem) throws Exception {
        String b64 = pem.replace("-----BEGIN PRIVATE KEY-----", "").replace("-----END PRIVATE KEY-----", "")
                .replaceAll("\\s", "");
        return KeyFactory.getInstance("RSA").generatePrivate(new PKCS8EncodedKeySpec(Base64.getDecoder().decode(b64)));
    }

    /** The signed JWT that asks TOKEN_URI for a token of EMAIL with SCOPES for one hour. */
    public static String assertion(String email, String pem, String tokenUri) throws Exception {
        long now = System.currentTimeMillis() / 1000L;
        String header = b64url("{\"alg\":\"RS256\",\"typ\":\"JWT\"}".getBytes(StandardCharsets.UTF_8));
        String claims = "{\"iss\":" + jsonString(email) + ",\"scope\":" + jsonString(SCOPES) + ",\"aud\":" +
                jsonString(tokenUri) + ",\"iat\":" + (now - 30) + ",\"exp\":" + (now + 3570) + "}";
        String unsigned = header + "." + b64url(claims.getBytes(StandardCharsets.UTF_8));
        Signature sig = Signature.getInstance("SHA256withRSA");
        sig.initSign(privateKey(pem));
        sig.update(unsigned.getBytes(StandardCharsets.UTF_8));
        return unsigned + "." + b64url(sig.sign());
    }

    /** The answer of TOKEN_URI ({"access_token", "expires_in", "token_type"}) for the service account EMAIL. */
    public static String serviceAccountToken(String email, String pem, String tokenUri) throws Exception {
        if (tokenUri == null || tokenUri.isEmpty()) tokenUri = TOKEN_URI;
        String body = "grant_type=" + URLEncoder.encode("urn:ietf:params:oauth:grant-type:jwt-bearer", "UTF-8") +
                "&assertion=" + URLEncoder.encode(assertion(email, pem, tokenUri), "UTF-8");
        Object[] r = request("POST", tokenUri, body, "application/x-www-form-urlencoded");
        if ((Integer) r[0] != 200) throw new IOException("token " + r[0] + ": " + r[1]);
        return (String) r[1];
    }
}

package es.ugr.monitoreo.campo;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.OpenableColumns;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import org.json.JSONObject;

import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * MonitorEO Campo: the interface is a web page (assets/www) served from https://appassets.androidplatform.net, so it
 * is a secure context with an https origin that Earth Engine accepts. What a page cannot do well is done here and
 * offered to it as window.Android.call(callbackId, method, argument), answered with window.AndroidCallback(id, json):
 * the token of the service account (its key never reaches the page), any HTTP request without CORS (the broker of the
 * shared account of MonitorEO), the location of the GPS and the files of the phone.
 */
public class MainActivity extends Activity {

    static final String HOST = "appassets.androidplatform.net";
    static final int REQ_SA = 1, REQ_OPEN = 2, REQ_SAVE = 3, REQ_PERMISSION = 4;
    static final int MAX_FILE = 8 * 1024 * 1024;
    static final long GPS_TIMEOUT = 30000;  // ms: the best fix until then
    static final float GPS_GOOD = 8;  // m: a fix this precise ends the search at once

    WebView web;
    SharedPreferences prefs;
    final ExecutorService pool = Executors.newFixedThreadPool(3);
    final Handler main = new Handler(Looper.getMainLooper());
    final Map<Integer, String> pending = new HashMap<>();
    String pendingSave;
    String locateCb;

    final Object tokenLock = new Object();
    String token;
    long tokenExpiry;  // ms

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences("campo", MODE_PRIVATE);
        if ((getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0) WebView.setWebContentsDebuggingEnabled(true);
        web = new WebView(this);
        setContentView(web);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        web.setWebChromeClient(new WebChromeClient());
        web.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                Uri u = request.getUrl();
                if (!HOST.equals(u.getHost())) return null;
                return asset(u.getPath());
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri u = request.getUrl();
                if (HOST.equals(u.getHost())) return false;
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, u));
                } catch (Exception ignored) {
                }
                return true;
            }
        });
        web.addJavascriptInterface(new Bridge(), "Android");
        web.loadUrl("https://" + HOST + "/index.html");
    }

    WebResourceResponse asset(String path) {
        if (path == null || path.equals("/") || path.isEmpty()) path = "/index.html";
        String mime = "application/octet-stream";
        String p = path.toLowerCase();
        if (p.endsWith(".html")) mime = "text/html";
        else if (p.endsWith(".js")) mime = "application/javascript";
        else if (p.endsWith(".css")) mime = "text/css";
        else if (p.endsWith(".png")) mime = "image/png";
        else if (p.endsWith(".svg")) mime = "image/svg+xml";
        else if (p.endsWith(".json")) mime = "application/json";
        try {
            InputStream in = getAssets().open("www" + path);
            return new WebResourceResponse(mime, "UTF-8", in);
        } catch (Exception e) {
            WebResourceResponse r = new WebResourceResponse("text/plain", "UTF-8",
                    new ByteArrayInputStream("not found".getBytes(StandardCharsets.UTF_8)));
            r.setStatusCodeAndReasonPhrase(404, "Not Found");
            return r;
        }
    }

    @Override
    public void onBackPressed() {
        web.evaluateJavascript("window.onBack ? window.onBack() : false", v -> {
            if (!"true".equals(v)) finish();
        });
    }

    @Override
    protected void onDestroy() {
        stopLocation();
        pool.shutdownNow();
        web.destroy();
        super.onDestroy();
    }

    // Answers to the page ---------------------------------------------------------------------------------------------

    void answer(String cb, String json) {
        if (cb == null) return;
        String js = "window.AndroidCallback && window.AndroidCallback(" + JSONObject.quote(cb) + "," +
                JSONObject.quote(json) + ")";
        main.post(() -> web.evaluateJavascript(js, null));
    }

    static String error(String message) {
        try {
            return new JSONObject().put("error", message == null ? "error" : message).toString();
        } catch (Exception e) {
            return "{\"error\":\"error\"}";
        }
    }

    class Bridge {
        @JavascriptInterface
        public void call(String cb, String method, String arg) {
            switch (method) {
                case "pickServiceAccount":
                    main.post(() -> open(cb, REQ_SA));
                    return;
                case "openFile":
                    main.post(() -> open(cb, REQ_OPEN));
                    return;
                case "saveFile":
                    main.post(() -> save(cb, arg));
                    return;
                case "locate":
                    main.post(() -> locate(cb));
                    return;
                case "openUrl":
                    main.post(() -> {
                        try {
                            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(arg)));
                        } catch (Exception ignored) {
                        }
                    });
                    answer(cb, "{}");
                    return;
                default:
                    pool.execute(() -> {
                        String out;
                        try {
                            out = dispatch(method, arg);
                        } catch (Exception e) {
                            out = error(e.getMessage());
                        }
                        answer(cb, out);
                    });
            }
        }
    }

    String dispatch(String method, String arg) throws Exception {
        switch (method) {
            case "serviceAccountInfo":
                return serviceAccountInfo();
            case "serviceAccountToken":
                return serviceAccountToken("1".equals(arg));
            case "clearServiceAccount":
                prefs.edit().remove("sa").apply();
                synchronized (tokenLock) {
                    token = null;
                }
                return "{}";
            case "http": {
                JSONObject a = new JSONObject(arg);
                Object[] r = Net.request(a.optString("method", "GET"), a.getString("url"),
                        a.has("body") ? a.getString("body") : null, a.optString("contentType", "application/json"));
                return new JSONObject().put("status", r[0]).put("body", r[1]).toString();
            }
            case "aiKeys":
                return aiKeys();
            case "aiSetKey": {
                JSONObject a = new JSONObject(arg);
                String p = aiProvider(a.getString("provider")), k = a.getString("key").trim();
                if (k.length() < 8) return error("la clave es demasiado corta");
                prefs.edit().putString("ai_key_" + p, k).apply();
                return aiKeys();
            }
            case "aiClearKey":
                prefs.edit().remove("ai_key_" + aiProvider(arg)).apply();
                return aiKeys();
            case "aiRequest":
                return aiRequest(new JSONObject(arg));
            case "appInfo": {
                android.content.pm.PackageInfo i = getPackageManager().getPackageInfo(getPackageName(), 0);
                return new JSONObject().put("version", i.versionName).put("code", i.getLongVersionCode()).toString();
            }
            default:
                return error("unknown method " + method);
        }
    }

    // The keys of the AI providers ----------------------------------------------------------------------------------
    // Like the key of the service account, an API key stays in the private storage of the app: the page sends the body
    // of a request and the provider, and the key is added here, to a fixed URL of that provider.

    static final String[] AI_PROVIDERS = {"claude", "gemini", "glm"};

    static String aiProvider(String p) {
        for (String q : AI_PROVIDERS) if (q.equals(p)) return q;
        throw new IllegalArgumentException("proveedor desconocido: " + p);
    }

    String aiKeys() throws Exception {
        JSONObject out = new JSONObject();
        for (String p : AI_PROVIDERS) {
            String k = prefs.getString("ai_key_" + p, null);
            out.put(p, k == null ? "" : "…" + k.substring(Math.max(0, k.length() - 4)));
        }
        return out.toString();
    }

    /**
     * A request of the assistant (ai.js) to its language model: "monitoreo", the route /chat of the broker of MonitorEO
     * (its key of Claude, Gemini or GLM is in the broker and never leaves it; the URL comes from the page, but only
     * that route of an https host), or the API of Claude, Gemini (compatible with OpenAI) or GLM with the key of the
     * user, added here to the fixed URL of that provider.
     */
    String aiRequest(JSONObject a) throws Exception {
        String p = a.getString("provider");
        String url;
        String[] headers;
        if ("monitoreo".equals(p)) {
            url = a.getString("url");
            if (!url.matches("https://[A-Za-z0-9.\\-]+(:[0-9]+)?/chat\\?user=mo-[0-9a-f]{16}")) {
                return error("dirección del broker no válida");
            }
            headers = null;
        } else {
            p = aiProvider(p);
            String key = prefs.getString("ai_key_" + p, null);
            if (key == null) return error("no hay clave de API para " + p + ": ponla en Ajustes");
            switch (p) {
                case "claude": {
                    String beta = a.optString("beta", "");
                    if (!beta.matches("[a-z0-9\\-,]{0,200}")) return error("beta no válida");
                    url = "https://api.anthropic.com/v1/messages";
                    headers = beta.isEmpty() ? new String[]{"x-api-key", key, "anthropic-version", "2023-06-01"} :
                            new String[]{"x-api-key", key, "anthropic-version", "2023-06-01", "anthropic-beta", beta};
                    break;
                }
                case "gemini":
                    url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions";
                    headers = new String[]{"Authorization", "Bearer " + key};
                    break;
                default:
                    url = "https://api.z.ai/api/paas/v4/chat/completions";
                    headers = new String[]{"Authorization", "Bearer " + key, "Accept-Language", "en-US,en"};
            }
        }
        Object[] r = Net.request("POST", url, a.getString("body"), "application/json", headers, 300000);
        return new JSONObject().put("status", r[0]).put("body", r[1]).toString();
    }

    // The service account ---------------------------------------------------------------------------------------------

    String serviceAccountInfo() throws Exception {
        String text = prefs.getString("sa", null);
        if (text == null) return "{}";
        JSONObject j = new JSONObject(text);
        return new JSONObject().put("client_email", j.optString("client_email"))
                .put("project_id", j.optString("project_id")).toString();
    }

    String serviceAccountToken(boolean force) throws Exception {
        String text = prefs.getString("sa", null);
        if (text == null) return error("no hay cuenta de servicio: elige su JSON en Ajustes");
        JSONObject j = new JSONObject(text);
        synchronized (tokenLock) {
            long now = System.currentTimeMillis();
            if (force || token == null || tokenExpiry - now < 5 * 60 * 1000) {
                JSONObject t = new JSONObject(Net.serviceAccountToken(j.getString("client_email"),
                        j.getString("private_key"), j.optString("token_uri", Net.TOKEN_URI)));
                token = t.getString("access_token");
                tokenExpiry = now + t.optLong("expires_in", 3600) * 1000L;
            }
            return new JSONObject().put("access_token", token)
                    .put("expires_in", (tokenExpiry - now) / 1000L)
                    .put("project", j.optString("project_id")).toString();
        }
    }

    String saveServiceAccount(String text) throws Exception {
        JSONObject j = new JSONObject(text);
        if (!"service_account".equals(j.optString("type")) || !j.has("private_key") || !j.has("client_email")) {
            return error("ese archivo no es el JSON de una clave de cuenta de servicio de Google Cloud");
        }
        Net.privateKey(j.getString("private_key"));  // a key that Java can read
        prefs.edit().putString("sa", text).apply();
        synchronized (tokenLock) {
            token = null;
        }
        return serviceAccountInfo();
    }

    // Files -----------------------------------------------------------------------------------------------------------

    void open(String cb, int code) {
        Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        i.addCategory(Intent.CATEGORY_OPENABLE);
        i.setType("*/*");
        pending.put(code, cb);
        startActivityForResult(i, code);
    }

    void save(String cb, String arg) {
        try {
            JSONObject a = new JSONObject(arg);
            Intent i = new Intent(Intent.ACTION_CREATE_DOCUMENT);
            i.addCategory(Intent.CATEGORY_OPENABLE);
            i.setType(a.optString("mime", "text/plain"));
            i.putExtra(Intent.EXTRA_TITLE, a.getString("name"));
            pendingSave = a.getString("text");
            pending.put(REQ_SAVE, cb);
            startActivityForResult(i, REQ_SAVE);
        } catch (Exception e) {
            answer(cb, error(e.getMessage()));
        }
    }

    String displayName(Uri uri) {
        try (Cursor c = getContentResolver().query(uri, null, null, null, null)) {
            if (c != null && c.moveToFirst()) {
                int k = c.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (k >= 0) return c.getString(k);
            }
        } catch (Exception ignored) {
        }
        return uri.getLastPathSegment();
    }

    @Override
    protected void onActivityResult(int code, int result, Intent data) {
        super.onActivityResult(code, result, data);
        String cb = pending.remove(code);
        if (cb == null) return;
        if (result != RESULT_OK || data == null || data.getData() == null) {
            answer(cb, "{\"cancelled\":true}");
            return;
        }
        Uri uri = data.getData();
        if (code == REQ_SAVE) {
            String text = pendingSave;
            pendingSave = null;
            pool.execute(() -> {
                try (OutputStream out = getContentResolver().openOutputStream(uri, "wt")) {
                    out.write(text.getBytes(StandardCharsets.UTF_8));
                    answer(cb, new JSONObject().put("ok", true).put("name", displayName(uri)).toString());
                } catch (Exception e) {
                    answer(cb, error(e.getMessage()));
                }
            });
            return;
        }
        pool.execute(() -> {
            try (InputStream in = getContentResolver().openInputStream(uri)) {
                String text = Net.read(in);
                if (text.length() > MAX_FILE) throw new Exception("archivo demasiado grande");
                if (code == REQ_SA) answer(cb, saveServiceAccount(text));
                else answer(cb, new JSONObject().put("name", displayName(uri)).put("text", text).toString());
            } catch (Exception e) {
                answer(cb, error(e.getMessage()));
            }
        });
    }

    // Location --------------------------------------------------------------------------------------------------------

    LocationManager locations;
    LocationListener listener;
    Location best;
    final Runnable timeout = () -> finishLocation(null);

    void locate(String cb) {
        if (locateCb != null) answer(locateCb, "{\"cancelled\":true}");
        locateCb = cb;
        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.ACCESS_FINE_LOCATION,
                    Manifest.permission.ACCESS_COARSE_LOCATION}, REQ_PERMISSION);
            return;
        }
        startLocation();
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] permissions, int[] results) {
        if (code != REQ_PERMISSION) return;
        boolean any = false;
        for (int r : results) any |= r == PackageManager.PERMISSION_GRANTED;
        if (any) startLocation();
        else finishLocation("sin permiso de ubicación");
    }

    @SuppressWarnings("MissingPermission")
    void startLocation() {
        stopLocation();
        locations = (LocationManager) getSystemService(LOCATION_SERVICE);
        best = null;
        boolean gps = locations.isProviderEnabled(LocationManager.GPS_PROVIDER);
        boolean net = locations.isProviderEnabled(LocationManager.NETWORK_PROVIDER);
        if (!gps && !net) {
            finishLocation("la ubicación del teléfono está desactivada");
            return;
        }
        listener = new LocationListener() {
            @Override
            public void onLocationChanged(Location l) {
                if (best == null || l.getAccuracy() <= best.getAccuracy()) best = l;
                if (l.getAccuracy() <= GPS_GOOD) finishLocation(null);
            }

            @Override
            public void onStatusChanged(String provider, int status, Bundle extras) {
            }

            @Override
            public void onProviderEnabled(String provider) {
            }

            @Override
            public void onProviderDisabled(String provider) {
            }
        };
        try {
            if (gps) locations.requestLocationUpdates(LocationManager.GPS_PROVIDER, 1000, 0, listener, Looper.getMainLooper());
            if (net) locations.requestLocationUpdates(LocationManager.NETWORK_PROVIDER, 1000, 0, listener, Looper.getMainLooper());
        } catch (SecurityException e) {
            finishLocation("sin permiso de ubicación");
            return;
        }
        main.postDelayed(timeout, GPS_TIMEOUT);
    }

    @SuppressWarnings("MissingPermission")
    void finishLocation(String failure) {
        String cb = locateCb;
        locateCb = null;
        Location l = best;
        boolean stale = false;
        if (failure == null && l == null && locations != null) {  // nothing new: the last fix known, marked as old
            try {
                Location g = locations.getLastKnownLocation(LocationManager.GPS_PROVIDER);
                Location n = locations.getLastKnownLocation(LocationManager.NETWORK_PROVIDER);
                l = g != null && (n == null || g.getTime() >= n.getTime()) ? g : n;
                stale = l != null;
            } catch (SecurityException ignored) {
            }
        }
        stopLocation();
        if (cb == null) return;
        if (failure != null || l == null) {
            answer(cb, error(failure != null ? failure : "no hay señal de GPS: prueba al aire libre"));
            return;
        }
        try {
            answer(cb, new JSONObject().put("lat", l.getLatitude()).put("lon", l.getLongitude())
                    .put("accuracy", l.getAccuracy()).put("altitude", l.hasAltitude() ? l.getAltitude() : JSONObject.NULL)
                    .put("provider", l.getProvider()).put("time", l.getTime()).put("stale", stale).toString());
        } catch (Exception e) {
            answer(cb, error(e.getMessage()));
        }
    }

    void stopLocation() {
        main.removeCallbacks(timeout);
        if (locations != null && listener != null) locations.removeUpdates(listener);
        listener = null;
    }
}

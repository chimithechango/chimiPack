package app.chimipack;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;

/**
 * Generic launcher used by every APK chimiPack produces.
 * The web files live in assets/www and are served from a virtual https origin,
 * so fetch(), ES modules, localStorage and IndexedDB all behave like a real site.
 */
public class MainActivity extends Activity {
    static final String HOST = "appassets.androidplatform.net";
    static final int IMMERSIVE = 0x1706;

    WebView web;
    String entry = "index.html";
    boolean fullscreen;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        requestWindowFeature(1); // Window.FEATURE_NO_TITLE

        String cfg = readAsset("chimipack.cfg");
        entry = cfgValue(cfg, "entry", "index.html");
        fullscreen = "1".equals(cfgValue(cfg, "fullscreen", "0"));

        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setAllowFileAccess(true);
        web.setWebViewClient(new AssetClient(this));
        web.setWebChromeClient(new WebChromeClient());
        setContentView(web);
        applyFullscreen();
        web.loadUrl("https://" + HOST + "/" + entry);
    }

    void applyFullscreen() {
        if (fullscreen && web != null) web.setSystemUiVisibility(IMMERSIVE);
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) applyFullscreen();
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    String readAsset(String name) {
        try {
            InputStream in = getAssets().open(name);
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[4096];
            int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
            in.close();
            return new String(out.toByteArray(), "UTF-8");
        } catch (Exception e) {
            return "";
        }
    }

    static String cfgValue(String cfg, String key, String def) {
        for (String line : cfg.split("\n")) {
            int eq = line.indexOf('=');
            if (eq > 0 && line.substring(0, eq).trim().equals(key)) return line.substring(eq + 1).trim();
        }
        return def;
    }

    static String mime(String path) {
        String p = path.toLowerCase();
        int dot = p.lastIndexOf('.');
        String ext = dot >= 0 ? p.substring(dot + 1) : "";
        String[][] map = {
            {"html", "text/html"}, {"htm", "text/html"}, {"js", "text/javascript"}, {"mjs", "text/javascript"},
            {"css", "text/css"}, {"json", "application/json"}, {"map", "application/json"}, {"txt", "text/plain"},
            {"xml", "application/xml"}, {"svg", "image/svg+xml"}, {"png", "image/png"}, {"jpg", "image/jpeg"},
            {"jpeg", "image/jpeg"}, {"gif", "image/gif"}, {"webp", "image/webp"}, {"ico", "image/x-icon"},
            {"bmp", "image/bmp"}, {"wasm", "application/wasm"}, {"mp3", "audio/mpeg"}, {"ogg", "audio/ogg"},
            {"wav", "audio/wav"}, {"m4a", "audio/mp4"}, {"mp4", "video/mp4"}, {"webm", "video/webm"},
            {"woff", "font/woff"}, {"woff2", "font/woff2"}, {"ttf", "font/ttf"}, {"otf", "font/otf"}
        };
        for (String[] m : map) if (m[0].equals(ext)) return m[1];
        return "application/octet-stream";
    }
}

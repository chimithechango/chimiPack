package app.chimipack;

import android.content.Intent;
import android.net.Uri;
import android.webkit.*;
import java.io.ByteArrayInputStream;
import java.io.InputStream;

public class AssetClient extends WebViewClient {
    final MainActivity act;
    AssetClient(MainActivity a) { act = a; }
        @Override
        public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest req) {
            Uri u = req.getUrl();
            if (u == null || !MainActivity.HOST.equals(u.getHost())) return null;
            String path = u.getPath();
            if (path == null || path.equals("/") || path.length() == 0) path = "/" + act.entry;
            if (path.endsWith("/")) path = path + "index.html";
            path = path.substring(1);
            try {
                InputStream in = act.getAssets().open("www/" + path);
                return new WebResourceResponse(MainActivity.mime(path), null, in);
            } catch (Exception e) {
                return new WebResourceResponse("text/plain", "utf-8", 404, "Not Found", null,
                        new ByteArrayInputStream(new byte[0]));
            }
        }

        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
            Uri u = req.getUrl();
            if (u != null && MainActivity.HOST.equals(u.getHost())) return false;
            try {
                act.startActivity(new Intent(Intent.ACTION_VIEW, u));
            } catch (Exception ignored) {
            }
            return true;
        }
    }


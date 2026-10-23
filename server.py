# LemoNx downloader backend, ready for Render.
# Start command on Render: gunicorn server:app --workers 1 --threads 4 --timeout 120
import os, re, socket, ipaddress
from urllib.parse import urlparse
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
import yt_dlp, requests

# Only your Netlify site may call this API from a browser.
# To allow more sites, set ALLOWED_ORIGINS on Render (comma separated).
ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "https://lmntools27.netlify.app").split(",")]

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
CORS(app, origins=ORIGINS)
limiter = Limiter(get_remote_address, app=app, default_limits=["60 per hour"], storage_uri="memory://")
OPT = {"quiet": True, "noplaylist": True, "format": "best[ext=mp4]/best"}

def safe(u):
    # Only public http(s) links; blocks localhost and private network addresses.
    p = urlparse(u or "")
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("bad link")
    for a in socket.getaddrinfo(p.hostname, None):
        ip = ipaddress.ip_address(a[4][0].split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError("blocked link")

def info(u):
    safe(u)
    with yt_dlp.YoutubeDL(OPT) as y:
        return y.extract_info(u, download=False)

@app.get("/")
def home():
    return "LemoNx backend is running"

@app.get("/api/info")
@limiter.limit("20 per hour")
def api_info():
    try:
        d = info(request.args.get("url"))
        return jsonify(title=d.get("title"), thumbnail=d.get("thumbnail"))
    except Exception as e:
        return jsonify(error=str(e)[:160]), 400

@app.get("/api/dl")
@limiter.limit("10 per hour")
def api_dl():
    try:
        d = info(request.args.get("url"))
        safe(d["url"])
        r = requests.get(d["url"], headers=d.get("http_headers", {}), stream=True, timeout=30)
    except Exception as e:
        return jsonify(error=str(e)[:160]), 400
    name = re.sub(r"[^\w.-]+", "_", d.get("title") or "video")[:60] + "." + d.get("ext", "mp4")
    return Response(stream_with_context(r.iter_content(65536)),
                    content_type=r.headers.get("Content-Type", "video/mp4"),
                    headers={"Content-Disposition": 'attachment; filename="' + name + '"'})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)))

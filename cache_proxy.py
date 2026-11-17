from flask import Flask, Response, request
from urllib.parse import urljoin
import httpx
import time
import threading
import random

app = Flask(__name__)
SERVER = "http://localhost:8080"
playlist_cache = {}
session = httpx.Client()

user_agents = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15'
]

def extract_target_duration(content):
    for line in content.splitlines():
        if line.startswith("#EXT-X-TARGETDURATION"):
            return int(line.split(":")[1])
    
    return 6  # fallback

def extract_media_sequence(content):
    for line in content.splitlines():
        if line.startswith("#EXT-X-MEDIA-SEQUENCE"):
            return int(line.split(":")[1])
    
    return 0  # fallback

def fetch_playlist(url):
    try:
        r = session.get(url, follow_redirects=True, headers={"User-Agent": random.choice(user_agents), "Accept": "*/*", "Connection": "keep-alive"}, timeout=5)

        r.raise_for_status()
        base = str(r.url).rsplit("/", 1)[0] + "/"
        lines = r.text.splitlines()

        rewritten = [
            urljoin(base, l) if l and not l.startswith("#") else l
            for l in lines
        ]

        return "\n".join(rewritten)
    except Exception as e:
        print(f"{type(e).__name__} at line {e.__traceback__.tb_lineno} of {__file__} {e}")
    
    if url in playlist_cache:
        return playlist_cache[url].get_content()

    return ""

class PlaylistCache:
    def __init__(self, url, now):
        self.url = url
        self.last_accessed = now
        self.content = None
        self.ttl = None
        self.lock = threading.Lock()
        self.updating = False
        self.media_sequence = None
        self.drift = 0

        self.update_content()

        self.expiry = now + self.ttl

    def fetch(self):
        content = self.get_content()

        if not content or time.time() > self.get_expiry():
            self.update_content()

        return content

    def fetch_new_content(self):
        return fetch_playlist(self.url)

    def update_content(self):
        if self.updating: return
        self.updating = True

        new_content = self.fetch_new_content()
        new_sequence = extract_media_sequence(new_content)

        with self.lock:
            self.ttl = max(1, extract_target_duration(new_content) // 2)
            self.expiry = time.time() + self.ttl

            if self.media_sequence:
                self.drift = new_sequence - self.media_sequence

            if self.drift > 0 or not self.media_sequence:
                self.content = new_content
                self.media_sequence = new_sequence
                self.drift = 0

        self.updating = False

    def get_content(self):
        with self.lock:
            self.last_accessed = time.time()

            return self.content

    def get_last_accessed(self):
        with self.lock:
            return self.last_accessed

    def get_expiry(self):
        with self.lock:
            return self.expiry

def fetch_playlist_cached(url):
    now = time.time()

    playlist: PlaylistCache = playlist_cache.get(url, None)
    
    if playlist:
        content = playlist.fetch()

        # if now < playlist.get_expiry():
        return content

    playlist = PlaylistCache(url, now)
    playlist_cache[url] = playlist

    return playlist.get_content()

@app.route("/play/<server>/<ch>")
def playlist(server, ch):
    return Response(fetch_playlist_cached(f"{SERVER}/play/{server}/{ch}"), content_type="application/vnd.apple.mpegurl")

@app.route("/subplaylist")
def subplaylist():
    return Response(fetch_playlist_cached(request.args.get("url")), content_type="application/vnd.apple.mpegurl")

def refresh_thread():
    while True:
        removeable = []
        now = time.time()

        for url, playlist in playlist_cache.items():
            if now >= playlist.get_last_accessed() + 60:
                removeable.append(url)

            if now < playlist.get_expiry():
                continue

            if playlist not in removeable:
                threading.Thread(target=playlist.update_content, daemon=True).start()

        for url in removeable:
            del playlist_cache[url]

        time.sleep(1)

if __name__ == "__main__":
    threading.Thread(target=refresh_thread, daemon=True).start()

    app.run("0.0.0.0", 5000)
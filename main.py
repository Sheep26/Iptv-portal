from flask import Flask, redirect, request, Response, stream_with_context, send_file
from flask_cors import CORS
import httpx
import time
import json
import threading
import random
import os
import hashlib
import string
import sys
import atexit

servers = []
config = {}
config_dir = ""
user_agents = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36'
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36'
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15'
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15'
]

last_server_update = 0

def rand_str(len = 32):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=len))

app = Flask(__name__)
CORS(app)
app.secret_key = rand_str(32)
login_sessions = []

class Server:
    def __init__(self, id):
        self.channels = config["channels"]
        self.id = id
        self.session = httpx.Client()
        self.user_agent = random.choice(user_agents)
    
    def get_epg(self):
        return None
    
    def get_epg_channel(self, channel):
        return None
    
    def get_channels(self):
        return self.channels

    def health_check(self):
        return True

    def add_channel(self, name, logo, url):
        config["channels"].append({
            "id": int(len(config["channels"])),
            "name": name,
            "logo": logo,
            "url": url,
        })
        
        dump_config()
    
    def remove_channel(self, name=None, id=None):
        for channel in self.get_channels():
            if name != None:
                if channel["name"] == name:
                    config["channels"].remove(channel)
                    break
            if id != None:
                if channel["id"] == id:
                    config["channels"].remove(channel)
                    break
        
        dump_config()
    
    def handle_play(self, channel_id, session_id):
        for channel in self.get_channels():
            if channel["id"] == int(channel_id):
                return redirect(channel["url"], code=301)

        return Response(status=500)

class XtreamServer(Server):
    def __init__(self, url, id, username, password, stream_prefix="", stream_suffix=""):
        self.url = url
        self.username = username
        self.password = password
        self.channels = []
        self.id = id
        self.session = httpx.Client()
        self.user_agent = random.choice(user_agents)
        self.stream_prefix = stream_prefix
        self.stream_suffix = stream_suffix
        
        self.setup()
    
    def setup(self):
        print(f"Starting setup for {self.url}")
        
        try:
            self.update_channels()
        except Exception as e:
            print(e)
            print(f"Setup for {self.url} failed.")

    def health_check(self):
        req = self.session.get(f'http://mains.services/player_api.php?username={self.username}&password={self.password}', follow_redirects=False)

        if req.status_code != 200:
            return False

        json = req.json()
        if json['user_info']['status'] != 'Active':
            return False

        return super().health_check()
    
    def get_m3u(self):
        m3u_request = self.session.get(f"{self.url}/get.php?username={self.username}&password={self.password}&type=m3u")
        
        return m3u_request.content
    
    def get_epg(self):
        epg_request = self.session.get(f"{self.url}/xmltv.php?username={self.username}&password={self.password}")

        return epg_request.text
    
    def get_epg_channel(self, channel):
        epg_request = self.session.get(f"{self.url}/player_api.php?username={self.username}&password={self.password}&action=get_simple_data_table&stream_id={channel}")

        return epg_request.text
    
    def update_channels(self):
        self.channels.clear()
        channels_request = self.session.get(f"{self.url}/player_api.php?username={self.username}&password={self.password}&action=get_live_streams", headers={"User-Agent": self.user_agent})
        
        for channel in json.loads(channels_request.text):
            self.channels.append({
                "id": channel["stream_id"],
                "name": channel["name"],
                "logo": channel["stream_icon"],
                "epg_channel_id": channel["epg_channel_id"],
                "url": f"{self.url}/{self.stream_prefix}{self.username}/{self.password}/{channel['stream_id']}{self.stream_suffix}"
            })
        
        print(f"{self.url} has {len(self.channels)} channels.")
    
    def handle_play(self, channel, session_id):
        stream_url = f"{self.url}/{self.stream_prefix}{self.username}/{self.password}/{channel}{self.stream_suffix}"
        
        return redirect(stream_url, code=301)

def setup_servers():
    if not servers:
        servers.append(Server(0))

    for entry in config["xtream_servers"]:
        servers.append(XtreamServer(entry["url"], len(servers), entry["username"], entry["passwd"], entry.get("stream_prefix", ""), entry.get("stream_suffix", "")))

    last_server_update = time.time()

@app.route("/hls/<server>/<channel>/<file>")
def return_hls_stream_part(server, channel, file):
    return send_file(os.path.join(config["stream_path"], str(server), channel, file))

@app.route("/api/login")
def login():
    username = request.headers.get("username", None)
    passwd = request.headers.get("passwd", None)
    
    for user in config["users"]:
        if user["username"] != username: return Response(status=403)
        if user["passwd"] != hashlib.sha256(bytes(passwd.encode())).hexdigest(): return Response(status=403)
    
        session_id = rand_str(32)
        
        login_sessions.append({
            "session_id": session_id,
            "user": user,
        })
        
        return session_id
    
    return Response(status=403)

@app.route("/api/logout")
def logout():
    session_id = request.headers.get("session", None)
    
    for login_session in login_sessions:
        if login_session["session_id"] == session_id:
            login_sessions.remove(login_session)
            return Response(status=200)
    
    return Response(status=403)

@app.route("/api/get_user")
def get_user():
    session_id = request.headers.get("session", None)
    
    for login_session in login_sessions:
        if login_session["session_id"] == session_id:
            return login_session["user"]
    
    return Response(status=403)

@app.route("/server/<server>/get_channels")
def get_channels(server):
    return servers[int(server)].get_channels()

@app.route("/server/<server>/get_xtream_m3u")
def get_xtream_m3u(server):
    return servers[int(server)].get_m3u() if type(servers[int(server)]) == XtreamServer else Response(status=400)

@app.route("/server/get_m3u")
def get_m3u_all():
    search = request.args.get("search", None)
    original_links = request.args.get("original_links", 0)
    exclude = json.loads(request.args.get("exclude", "[]"))
    
    file_content = "#EXTM3U"
    for server in servers:
        for channel in server.get_channels():
            if search != None:
                if not search.lower() in channel["name"].lower():
                    continue
            
            found = False
        
            for exclude_url in exclude:
                if exclude_url.lower() in channel["name"].lower():
                    found = True
                    break
            if found: continue
            
            tvg_id = channel.get('epg_channel_id', f"{channel['name'].replace(' ', '').replace('(', '').replace(')', '')}.{server.id}.{channel['id']}")
            if tvg_id==None:
                tvg_id = f"{channel['name'].replace(' ', '').replace('(', '').replace(')', '')}.{server.id}.{channel['id']}"
            
            file_content += f"\n#EXTINF:-1 tvg-id=\"{tvg_id}\" tvg-logo=\"{channel['logo']}\" group-title=\"{channel['name']}\",{channel['name']}"
            server_url = f"{'https' if config['https'] else 'http'}://{request.url.split('/')[2]}" if not config["proxy"] or int(request.args.get('noproxy', 0)) == 1 else config["proxy_url"]
            stream_url = f"{server_url}/play/{server.id}/{channel['id']}"
            if original_links: file_content += f"\n{channel['url'] if type(server) == Server or type(server) == XtreamServer else stream_url}"
            else: file_content += f"\n{stream_url}"
    response = Response(file_content, mimetype='text/plain')
    response.headers["Content-Disposition"] = "attachment; filename=index.m3u"
    
    return response

@app.route("/server/get_channels")
def get_channels_all():
    channels = []
    for server in servers:
        for channel in server.get_channels():
            channels.append(channel)
    
    return channels

@app.route("/server/<server_id>/add_channel")
def add_channel(server_id):
    server = servers[int(server_id)]
    if type(server) == Server:
        session_id = request.headers.get("session", None)
        name = request.args.get("name", None)
        logo = request.args.get("logo", None)
        url = request.args.get("url", None)
        
        for login_session in login_sessions:
            if login_session["session_id"] == session_id and login_session["user"]["admin"]:
                server.add_channel(name, logo, url)
                
                return Response(status=200)
    else: return Response(status=500)
    
    return Response(status=403)

@app.route("/server/<server_id>/remove_channel")
def remove_channel(server_id):
    server = servers[int(server_id)]
    if type(server) == Server:
        session_id = request.headers.get("session", None)
        name = request.args.get("name", None)
        id = request.args.get("id", None)
        
        for login_session in login_sessions:
            if login_session["session_id"] == session_id and login_session["user"]["admin"]:
                server.remove_channel(name, id)
        
                return Response(status=200)
    else: return Response(status=500)
    
    return Response(status=403)

@app.route("/server/<server>/get_epg")
def get_epg(server):
    return servers[int(server)].get_epg()

@app.route('/server/<server>/health_check')
def health_check(server):
    try:
        return Response(200 if servers[server].health_check() else 418)
    except:
        return Response(418)

@app.route("/server/<server>/get_m3u")
def get_m3u(server):
    search = request.args.get("search", None)
    original_links = request.args.get("original_links", 0)
    exclude = json.loads(request.args.get("exclude", "[]"))
    
    file_content = "#EXTM3U"
    for channel in servers[int(server)].get_channels():
        if search != None:
            if not search.lower() in channel["name"].lower():
                continue
        
        found = False
        
        for exclude_url in exclude:
            if exclude_url.lower() in channel["name"].lower():
                found = True
                break
        if found: continue
        
        tvg_id = channel.get('epg_channel_id', f"{channel['name'].replace(' ', '').replace('(', '').replace(')', '')}.{servers[int(server)].id}.{channel['id']}")
        if tvg_id == None:
            tvg_id = f"{channel['name'].replace(' ', '').replace('(', '').replace(')', '')}.{servers[int(server)].id}.{channel['id']}"
        
        file_content += f"\n#EXTINF:-1 tvg-id=\"{tvg_id}\" tvg-logo=\"{channel['logo']}\" group-title=\"{channel['name']}\",{channel['name']}"
        server_url = f"{'https' if config['https'] else 'http'}://{request.url.split('/')[2]}" if not config["proxy"] or int(request.args.get('noproxy', 0)) == 1 else config["proxy_url"]
        stream_url = f"{server_url}/play/{servers[int(server)].id}/{channel['id']}"
        if original_links: file_content += f"\n{channel['url'] if type(servers[int(server)]) == Server or type(servers[int(server)]) == XtreamServer else stream_url}"
        else: file_content += f"\n{stream_url}"
    
    response = Response(file_content, mimetype='text/plain')
    response.headers["Content-Disposition"] = "attachment; filename=index.m3u"
    
    return response

@app.route("/play/<server>/<channel>")
def play(server, channel):
    print(f"Recieved request {channel} on server {server} with ip {request.headers.get('CF-Connecting-IP', request.headers.get('X-Real-IP', request.remote_addr))}")
    return servers[int(server)].handle_play(channel, request.headers.get("CF-Connecting-IP", request.headers.get("X-Real-IP", request.remote_addr)))

def start_web_server():
    app.run("0.0.0.0", 8080)

def read_config():
    with open(f"{config_dir}/config.json", "r") as f:
        return json.load(f)

def dump_config():
    print(f"Saving config to {config_dir}/config.json")
    with open(f"{config_dir}/config.json", "w") as f:
        return json.dump(config, f)

def main():
    global servers
    global config
    global config_dir
    global last_server_update
    
    atexit.register(exit_handler)
    
    debug = "--debug" in sys.argv
    config_dir = ("/etc/iptv" if os.system != "nt" else os.path.join(os.environ['appdata'], "iptv")) if not debug else "./"
    print(f"Config dir: {config_dir}")
    print(f"Config file {config_dir}/config.json")
    
    if not os.path.exists(config_dir):
        os.mkdir(config_dir)
    
    if not os.path.exists(f"{config_dir}/config.json"):
        print("Config missing, creating.")
        config = {"https": True, "proxy": False, "proxy_url": None, "xtream_servers": [], "channels": [], "users": []}
        
        dump_config()
    
    # Setup.
    servers = []
    config = read_config()
    
    setup_servers()
    
    # Check if there are any users, if none create one.
    if len(config["users"]) == 0:
        print("No users configured.")
        print("Creating user admin.")
        passwd = rand_str(32)
        print(f"Admin passwd: {passwd}")
        config["users"].append({"username": "admin", "passwd": hashlib.sha256(bytes(passwd.encode())).hexdigest(), "admin": True})

        dump_config()
    
    webserver_thread = threading.Thread(target=start_web_server, daemon=True)
    webserver_thread.start()
    
    last_server_update = time.time()
    
    while True:
        time.sleep(60*30) # Update every 30mins.
        
        if time.time() - last_server_update > 60*60*24: # Every day.
            for server in servers:
                try:
                    if type(server) == XtreamServer:
                        server.update_channels()
                except Exception as e:
                    print(e)

        last_server_update = time.time()
        
def exit_handler():
    print("Exitting.")

if __name__ == "__main__":
    main()
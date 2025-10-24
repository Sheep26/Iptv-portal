from flask import Flask, redirect, request, Response, stream_with_context, send_file
from flask_cors import CORS
import requests
import httpx
import datetime
import time
import json
import threading
import random
import subprocess
import os
import hashlib
import string
import sys
import atexit
import shutil
import gc

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

class Server:
    def __init__(self, id):
        self.channels = config["channels"]
        self.id = id
        self.user_agent = random.choice(user_agents)
    
    def add_channel(self, name, logo, url):
        config["channels"].append({
            "id": int(len(config["channels"])),
            "name": name,
            "logo": logo,
            "url": url,
        })
        
        dump_config()
    
    def remove_channel(self, name=None, id=None):
        for channel in self.channels:
            if name != None:
                if channel["name"] == name:
                    config["channels"].remove(channel)
                    break
            if id != None:
                if channel["id"] == id:
                    config["channels"].remove(channel)
                    break
        
        dump_config()
    
    def handle_play(self, channel_id, session_id, proxy):
        user_session = None
        
        for stream_session in stream_sessions:
            if stream_session["session_id"] == session_id:
                user_session = stream_session
                break
        
        if user_session == None:
            req_session = None
            if proxy != 0:
                req_session = httpx.Client()
            
            user_session = {
                "session_id": session_id,
                "mac": None,
                "session": req_session,
                "timestamp": time.time()
            }
            
            stream_sessions.append(user_session)
        
        for channel in self.channels:
            if channel["id"] == int(channel_id):
                user_session["timestamp"] = time.time()
                
                def generate():
                    with user_session['session'].stream("GET", channel["url"], follow_redirects=True, headers={"User-Agent": self.user_agent}, timeout=10) as r:
                        for chunk in r.iter_bytes(chunk_size=8192):
                            yield chunk
        
                match proxy:
                    case 1:
                        return Response(stream_with_context(generate()), mimetype='video/mp2t', direct_passthrough=True)
                    case _:
                        return redirect(channel["url"], code=301)
        
        return Response(status=500)

class XtreamServer:
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
    
    def get_m3u(self):
        m3u_request = self.session.get(f"{self.url}/get.php?username={self.username}&password={self.password}&type=m3u")
        
        return m3u_request.content
    
    def update_channels(self):
        self.channels.clear()
        channels_request = self.session.get(f"{self.url}/player_api.php?username={self.username}&password={self.password}&action=get_live_streams", headers={"User-Agent": self.user_agent})
        
        for channel in json.loads(channels_request.text):
            self.channels.append({
                "id": channel["stream_id"],
                "name": channel["name"],
                "logo": channel["stream_icon"],
                "url": f"{self.url}/{self.stream_prefix}{self.username}/{self.password}/{channel['stream_id']}{self.stream_suffix}"
            })
        
        print(f"{self.url} has {len(self.channels)} channels.")
    
    def handle_play(self, channel, session_id, proxy):
        user_session = None
        
        for stream_session in stream_sessions:
            if stream_session["session_id"] == session_id:
                user_session = stream_session
                break
        
        if user_session == None:
            req_session = None
            if proxy != 0:
                req_session = httpx.Client()
            
            user_session = {
                "session_id": session_id,
                "mac": None,
                "session": req_session,
                "timestamp": time.time()
            }
            
            stream_sessions.append(user_session)
        
        user_session["timestamp"] = time.time()
        stream_url = f"{self.url}/{self.stream_prefix}{self.username}/{self.password}/{channel}{self.stream_suffix}"
        
        def generate():
            with user_session['session'].stream("GET", stream_url, follow_redirects=True, headers={"User-Agent": self.user_agent}, timeout=10) as r:
                for chunk in r.iter_bytes(chunk_size=8192):
                    yield chunk
        
        match proxy:
            case 1:
                return Response(stream_with_context(generate()), mimetype='video/mp2t', direct_passthrough=True)
            case _:
                return redirect(stream_url, code=301)
        
class IPTVServer:
    def __init__(self, url, id, mac_free_needed=True, mcbash_file=None, run_mcbash=True, extension="ts"):
        self.url = url
        self.mcbash_file = mcbash_file if mcbash_file != None else f"{os.getenv('HOME')}/.mcbash/valid_macs_{url.split('/')[2].replace(":", "")}"
        self.mac_addrs = None
        self.channels = None
        self.id = id
        self.session = httpx.Client()
        self.user_agent = random.choice(user_agents)
        self.run_mcbash = run_mcbash
        self.mac_free_needed = mac_free_needed
        self.extension = extension
        
        self.setup()
    
    def setup(self):
        print(f"Setup {self.url}")
        
        try:
            # Get mac addrs
            self.update_macs()
            
            if len(self.mac_addrs) == 0:
                print(f"Setup for {self.url} failed")
                return
            
            # Get channels.
            self.update_channels()
            
            print(f"Setup for {self.url} complete")
        except httpx.TimeoutException as e:
            print(e)
            print(f"Setup for {self.url} failed.")
    
    def update_macs(self):
        self.mac_addrs = self.get_macs_from_mcbash(self.mcbash_file)
        
        if len(self.mac_addrs) == 0:
            open(self.mcbash_file, "w").close()
            
            print(f"There a no mac addrs available on {self.url}.")
            return
        
        print(f"There are {len(self.mac_addrs)} mac addrs available on {self.url}.")
    
    def update_channels(self):
        handshake = None
        
        while handshake == None:
            mac = random.choice(self.mac_addrs)["addr"]
            handshake = self.get_handshake(mac)
        
        print(f"Token: {handshake}")
        
        headers = {
            "Authorization": f"Bearer {handshake}",
            "User-Agent": self.user_agent
        }
        
        cookies = {
            "mac": mac,
            "stb_lang": "en",
            "timezone": "Europe/Amsterdam"
        }
        
        channel_request = self.session.get(f"{self.url}/server/load.php?type=itv&action=get_all_channels", headers=headers, cookies=cookies)
        if channel_request.status_code == 200:
            self.channels = json.loads(channel_request.text)["js"]["data"]
            print(f"{self.url} has {len(self.channels)} channels.")

    def get_handshake(self, mac):
        request = self.session.get(f"{self.url}/portal.php?action=handshake&type=stb&token=&mac={mac.replace(':', '%3A')}", headers={"User-Agent": self.user_agent})
        return json.loads(request.text)["js"]["token"] if request.status_code == 200 else None

    def mac_free(self, mac, channel):
        if not self.mac_free_needed:
            return True
        
        try:
            with requests.get(f"{self.url}/play/live.php?mac={mac}&stream={channel}&extension={self.extension}", headers={"User-Agent": self.user_agent}, stream=True) as response:
                print("Response " + str(response.status_code))
                if response.status_code == 405: return None
                return response.status_code == 200
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            return False
    
    def handle_play(self, channel, session_id, proxy):
        print(f"Request for channnel {channel} on server {self.url}")

        user_session = None
        
        for stream_session in stream_sessions:
            if stream_session["session_id"] != session_id:
                continue
            
            if stream_session['mac'] == None:
                stream_sessions.remove(stream_session)
                break
                
            user_session = stream_session
            print(f"Session {session_id} is already using mac {user_session['mac']['addr']}")
            break
        
        if user_session == None or not self.mac_free(user_session['mac']['addr'], channel):
            if user_session != None:
                stream_sessions.remove(user_session)
            
            print(f"Starting session {session_id}")
            
            req_session = None
            if proxy != 0:
                req_session = httpx.Client()
            
            while True:
                mac = random.choice(self.mac_addrs)
                print(f"Trying mac {mac}")
                
                mac_free = self.mac_free(mac["addr"], channel)
                
                if mac_free == None: return Response(status=500)
                
                if mac_free:
                    print(f"Found mac: {mac}.")
                    break
            
            user_session = {
                "session_id": session_id,
                "mac": mac,
                "session": req_session,
                "timestamp": time.time()
            }
            
            stream_sessions.append(user_session)
        
        user_session["timestamp"] = time.time()
        
        time.sleep(1)
        stream_url = f"{self.url}/play/live.php?mac={user_session['mac']['addr']}&stream={channel}&extension={self.extension}"
        # Proxy the stream
        
        def generate():
            with user_session['session'].stream("GET", stream_url, follow_redirects=True, headers={"User-Agent": self.user_agent}, timeout=10) as r:
                for chunk in r.iter_bytes(chunk_size=8192):
                    yield chunk
        
        match proxy:
            case 1:
                if user_session['session'] == None:
                    user_session['session'] = httpx.Client()
                
                return Response(stream_with_context(generate()), mimetype='video/mp2t', direct_passthrough=True)
            case _:
                return redirect(stream_url, code=301)
    
    def get_macs_from_mcbash(self, path) -> list[dict]:
        if not os.path.exists(path):
            return []
        
        mac_addrs = []
        with open(path, "r") as f:
            for line in f.readlines():
                if line.startswith("00:1A:79"):
                    newline = line.replace("[", "").replace("]", "").removesuffix("\n").split(" ", 1)
                    mac = newline[0]
                    dt = datetime.datetime.strptime(newline[1], "%B %d, %Y, %I:%M %p")
                    timestamp = dt.timestamp()
                    if timestamp > time.time():
                        mac_addrs.append({
                            "addr": mac,
                            "timestamp": timestamp
                        })
        
        return mac_addrs

def setup_servers():
    if not servers:
        servers.append(Server(0))
    
    for entry in config["iptv_servers"]:
        found = False
        for server in servers:
            if type(server) == IPTVServer:
                if server.url == entry["url"]:
                    found = True
                    break
        
        if not found:
            servers.append(IPTVServer(entry["url"], len(servers), entry.get("mac_free_needed", True), entry.get("mcbash_file", None), entry.get("run_mcbash", True), entry.get("extension", True)))
    
    for entry in config["xtream_servers"]:
        servers.append(XtreamServer(entry["url"], len(servers), entry["username"], entry["passwd"], entry.get("stream_prefix", ""), entry.get("stream_suffix", "")))
    
    # Stop all existing processes.
    for proc in mcbash_processes:
        proc.terminate()
        mcbash_processes.remove(proc)

    for server in servers:
        if type(server) == IPTVServer:
            if server.run_mcbash:
                mcbash_processes.append(subprocess.Popen(f"mcbash -u {server.url} -w 3 -b 10 -d 5 -s 0 -t 0 --prefix 00:1A:79", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    
    last_server_update = time.time()

def web_server():
    global stream_sessions
    global login_sessions
    app = Flask(__name__)
    CORS(app)
    app.secret_key = rand_str(32)
    
    login_sessions = []
    stream_sessions = []
    
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
        return servers[int(server)].channels
    
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
            for channel in server.channels:
                if search != None:
                    if not search.lower() in channel["name"].lower():
                        continue
                
                found = False
            
                for exclude_url in exclude:
                    if exclude_url.lower() in channel["name"].lower():
                        found = True
                        break
                if found: continue
            
                file_content += f"\n#EXTINF:-1 tvg-id=\"{channel['name'].replace(' ', '').replace('(', '').replace(')', '')}.{server.id}.{channel['id']}\" tvg-logo=\"{channel['logo']}\" group-title=\"{channel['name']}\",{channel['name']}"
                server_url = f"{'https' if config['https'] else 'http'}://{request.url.split('/')[2]}" if not config["proxy"] else config["proxy_url"]
                stream_url = f"{server_url}/play/{server.id}/{channel['id']}?proxy={int(request.args.get('proxy', 0))}"
                if original_links: file_content += f"\n{channel['url'] if type(server) == Server or type(server) == XtreamServer else stream_url}"
                else: file_content += f"\n{stream_url}"
        response = Response(file_content, mimetype='text/plain')
        response.headers["Content-Disposition"] = "attachment; filename=index.m3u"
        
        return response

    @app.route("/server/get_channels")
    def get_channels_all():
        channels = []
        for server in servers:
            for channel in server.channels:
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
    
    @app.route("/server/remove_iptv_server")
    def remove_iptv_server():
        url = request.args.get("url", None)
        session_id = request.headers.get("session", None)
        
        for login_session in login_sessions:
            if login_session["session_id"] == session_id and login_session["user"]["admin"]:
                # Remove the server from config["iptv_servers"]
                config["iptv_servers"] = [server for server in config["iptv_servers"] if server["url"] != url]

                # Remove the server from servers list if it's an IPTVServer and matches the url
                servers[:] = [x for x in servers if not (isinstance(x, IPTVServer) and x.url == url)]
                setup_servers()
                dump_config()

                return Response(status=200)
        
        return Response(status=403)
    
    @app.route("/server/add_iptv_server")
    def add_iptv_server():
        url = request.args["url"]
        session_id = request.headers.get("session", None)
        
        for login_session in login_sessions:
            if login_session["session_id"] == session_id and login_session["user"]["admin"]:
                server = {
                    "url": url,
                    "mcbash_file": f"{os.getenv('HOME')}/.mcbash/valid_macs_{url.split('/')[2]}",
                    "run_mcbash": True,
                }
                
                config["iptv_servers"].append(server)
                
                os.system(f"touch {server['mcbash_file']}")
                
                setup_servers()
                dump_config()
                
                return Response(status=200)

        return Response(status=403)
    
    @app.route("/server/<server>/get_m3u")
    def get_m3u(server):
        search = request.args.get("search", None)
        original_links = request.args.get("original_links", 0)
        exclude = json.loads(request.args.get("exclude", "[]"))
        
        file_content = "#EXTM3U"
        for channel in servers[int(server)].channels:
            if search != None:
                if not search.lower() in channel["name"].lower():
                    continue
            
            found = False
            
            for exclude_url in exclude:
                if exclude_url.lower() in channel["name"].lower():
                    found = True
                    break
            if found: continue
            
            file_content += f"\n#EXTINF:-1 tvg-id=\"{channel['name'].replace(' ', '').replace('(', '').replace(')', '')}.{servers[int(server)].id}.{channel['id']}\" tvg-logo=\"{channel['logo']}\" group-title=\"{channel['name']}\",{channel['name']}"
            server_url = f"{'https' if config['https'] else 'http'}://{request.url.split('/')[2]}" if not config["proxy"] else config["proxy_url"]
            stream_url = f"{server_url}/play/{servers[int(server)].id}/{channel['id']}?proxy={int(request.args.get('proxy', 0))}"
            if original_links: file_content += f"\n{channel['url'] if type(servers[int(server)]) == Server or type(servers[int(server)]) == XtreamServer else stream_url}"
            else: file_content += f"\n{stream_url}"
            #file_content += f"\n{'https' if config['https'] else 'http'}://{request.url.split('/')[2].replace(':', '')}/play/{servers[int(server)].id}/{channel['id']}?proxy={int(request.args.get('proxy', 0))}"
        
        response = Response(file_content, mimetype='text/plain')
        response.headers["Content-Disposition"] = "attachment; filename=index.m3u"
        
        return response
    
    @app.route("/play/<server>/<channel>")
    def play(server, channel):
        print(f"Recieved request {channel} on server {server} with ip {request.headers.get('CF-Connecting-IP', request.headers.get('X-Real-IP', request.remote_addr))}")
        return servers[int(server)].handle_play(channel, request.headers.get("CF-Connecting-IP", request.headers.get("X-Real-IP", request.remote_addr)), int(request.args.get("proxy", 0)))
    
    app.run("0.0.0.0", 8080)

def rand_str(len = 32):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=len))

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
    global mcbash_processes
    
    atexit.register(exit_handler)
    
    debug = "--debug" in sys.argv
    config_dir = ("/etc/iptv" if os.system != "nt" else os.path.join(os.environ['appdata'], "iptv")) if not debug else "./"
    print(f"Config dir: {config_dir}")
    print(f"Config file {config_dir}/config.json")
    
    if not os.path.exists(config_dir):
        os.mkdir(config_dir)
    
    if not os.path.exists(f"{config_dir}/config.json"):
        print("Config missing, creating.")
        config = {"https": True, "proxy": False, "proxy_url": None, "iptv_servers": [], "xtream_servers": [], "channels": [], "users": []}
        
        dump_config()
    
    # Setup.
    servers = []
    mcbash_processes = []
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
    
    webserver_thread = threading.Thread(target=web_server, daemon=True)
    webserver_thread.start()
    
    last_server_update = time.time()
    
    while True:
        time.sleep(60*30) # Update every 30mins.
        
        if time.time() - last_server_update > 60*60*24: # Every day.
            for server in servers:
                try:
                    if type(server) == IPTVServer:
                        server.update_macs()
                        server.update_channels()
                    elif type(server) == XtreamServer:
                        server.update_channels()
                except Exception as e:
                    print(e)

        for stream_session in stream_sessions:
            if time.time() - stream_session["timestamp"] > 60*30: # Delete sessions that haven't been used the past 30 mins.
                stream_sessions.remove(stream_session)
                del stream_session
        
        dump_config()
        
        gc.collect()
        
        last_server_update = time.time()
        
def exit_handler():
    print("Exitting.")

if __name__ == "__main__":
    main()
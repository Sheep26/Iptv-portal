from flask import Flask, redirect, request, Response, session, stream_with_context, send_file
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

class FfmpegStream:
    def __init__(self, server, channel, link, path, ffmpeg_str_arr, framerate = 0, flags="delete_segments+independent_segments", allow_cache=0, hls_time=0, hls_list_size=0):
        self.channel = channel
        self.link = link
        self.path = path
        self.framerate = framerate
        self.flags = flags
        self.allow_cache = allow_cache
        self.hls_time = hls_time
        self.hls_list_size = hls_list_size
        self.proc = 0
        self.ffmpeg_str_arr = ffmpeg_str_arr
        self.server = server
        self.last_used = time.time()
    
    def start_stream(self):
        hls_time_str = f"-hls_time {self.hls_time}" if self.hls_time != 0 else ""
        hls_list_size_str = f"-hls_list_size {self.hls_list_size}" if self.hls_list_size != 0 else ""
        framerate_str = f"-r {self.framerate}" if self.framerate != 0 else ""
        print(f"Starting stream {self.link}.")
        
        self.proc = subprocess.Popen(f'{config["ffmpeg_path"]} -re \
            -i "{self.link}" \
            -c copy \
            -f hls \
            {hls_time_str} \
            {hls_list_size_str} \
            -hls_flags {self.flags} \
            -hls_allow_cache {self.allow_cache} \
            {framerate_str} \
            -hls_base_url "/hls/{self.server}/{self.channel}/"\
            {os.path.join(self.path, "index.m3u8")}', shell=True) #, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    
    def stop_stream(self):
        self.proc.kill()
        time.sleep(2)
        self.ffmpeg_str_arr.remove(self)
        print(f"Stream {self.link} stopped.")
        print(f"Deleting {self.path}")
        shutil.rmtree(self.path, ignore_errors=True)

class Server:
    def __init__(self, id):
        self.channels = config["channels"]
        self.id = id
        self.ffmpeg_streams = []
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
        if proxy==2:
            found = False
            path = os.path.join(config["stream_path"], str(self.id), channel_id)
            
            for ffmpeg_stream in self.ffmpeg_streams:
                if ffmpeg_stream.channel == channel_id:
                    found = True
                    stream_obj = ffmpeg_stream
            
            if found:
                stream_obj.last_used = time.time()

                return send_file(os.path.join(path, "index.m3u8"))
        
        user_session = None
        
        for stream_session in stream_sessions:
            if stream_session["session_id"] == session_id:
                user_session = stream_session
                break
        
        if user_session == None:
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
                    case 2:
                        return
                        found = False
                        path = os.path.join(config["stream_path"], str(self.id), channel_id)
                        
                        for ffmpeg_stream in self.ffmpeg_streams:
                            if ffmpeg_stream.channel == channel_id:
                                found = True
                                stream_obj = ffmpeg_stream
                        
                        if not found:
                            print(f"Creating ffmpeg instance for {channel_id}")
                            
                            if not os.path.exists(os.path.join(config["stream_path"], str(self.id))):
                                try:
                                    os.mkdir(os.path.join(config["stream_path"], str(self.id)))
                                except:
                                    pass
                            
                            try:
                                os.mkdir(path)
                            except:
                                pass
                            
                            stream_obj = FfmpegStream(self.id, channel_id, channel["url"], path, ffmpeg_str_arr=self.ffmpeg_streams, hls_time=10, hls_list_size=30)
                            stream_obj.start_stream()
                            
                            self.ffmpeg_streams.append(stream_obj)
                        
                        stream_obj.last_used = time.time()
                
                        while not os.path.exists(os.path.join(path, "index.m3u8")):
                            print(f"File {os.path.join(path, 'index.m3u8')} doesn't exist sleeping 0.1s")
                            time.sleep(0.1)

                        return send_file(os.path.join(path, "index.m3u8"))
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
        self.ffmpeg_streams = []
        
        self.setup()
    
    def setup(self):
        print(f"Starting setup for {self.url}")
        
        self.update_channels()
    
    def get_m3u(self):
        m3u_request = self.session.get(f"{self.url}/get.php?username={self.username}&password={self.password}&type=m3u&output=ts")
        
        return m3u_request.content
    
    def update_channels(self):
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
        if proxy==2:
            found = False
            path = os.path.join(config["stream_path"], str(self.id), channel)
            
            for ffmpeg_stream in self.ffmpeg_streams:
                if ffmpeg_stream.channel == channel:
                    found = True
                    stream_obj = ffmpeg_stream
            
            if found:
                stream_obj.last_used = time.time()

                return send_file(os.path.join(path, "index.m3u8"))
        
        user_session = None
        
        for stream_session in stream_sessions:
            if stream_session["session_id"] == session_id:
                user_session = stream_session
                break
        
        if user_session == None:
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
            case 2:
                return
                found = False
                path = os.path.join(config["stream_path"], str(self.id), channel)
                
                for ffmpeg_stream in self.ffmpeg_streams:
                    if ffmpeg_stream.channel == channel:
                        found = True
                        stream_obj = ffmpeg_stream
                
                if not found:
                    print(f"Creating ffmpeg instance for {channel}")
                    
                    if not os.path.exists(os.path.join(config["stream_path"], str(self.id))):
                        try:
                            os.mkdir(os.path.join(config["stream_path"], str(self.id)))
                        except:
                            pass
                    
                    try:
                        os.mkdir(path)
                    except:
                        pass
                    
                    stream_obj = FfmpegStream(self.id, channel, stream_url, path, ffmpeg_str_arr=self.ffmpeg_streams, hls_time=10, hls_list_size=30)
                    stream_obj.start_stream()
                    
                    self.ffmpeg_streams.append(stream_obj)
                
                stream_obj.last_used = time.time()
                
                while not os.path.exists(os.path.join(path, "index.m3u8")):
                    print(f"File {os.path.join(path, 'index.m3u8')} doesn't exist sleeping 0.1s")
                    time.sleep(0.1)

                return send_file(os.path.join(path, "index.m3u8"))
            case 1:
                return Response(stream_with_context(generate()), mimetype='video/mp2t', direct_passthrough=True)
            case _:
                return redirect(stream_url, code=301)
        
class IPTVServer:
    def __init__(self, url, id, mcbash_file=None, run_mcbash=True):
        self.url = url
        self.mcbash_file = mcbash_file if mcbash_file != None else f"{os.getenv('HOME')}/.mcbash/valid_macs_{url.split('/')[2]}"
        self.mac_addrs = None
        self.channels = None
        self.id = id
        self.session = httpx.Client()
        self.user_agent = random.choice(user_agents)
        self.run_mcbash = run_mcbash
        self.ffmpeg_streams = []
        
        self.setup()
    
    def setup(self):
        print(f"Setup {self.url}")
        # Get mac addrs
        self.update_macs()
        
        if len(self.mac_addrs) == 0:
            print(f"Setup for {self.url} failed")
            return
        
        # Get channels.
        self.update_channels()
        
        print(f"Setup for {self.url} complete")
    
    def update_macs(self):
        self.mac_addrs = self.get_macs_from_mcbash(self.mcbash_file)
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
        try:
            with requests.get(f"{self.url}/play/live.php?mac={mac}&stream={channel}&extension=ts", headers={"User-Agent": self.user_agent}, stream=True) as response:
                print(response.status_code)
                return response.status_code == 200
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            return False
    
    def handle_play(self, channel, session_id, proxy):
        print(f"Request for channnel {channel} on server {self.url}")
        
        if proxy==2:
            found = False
            path = os.path.join(config["stream_path"], str(self.id), channel)
            
            for ffmpeg_stream in self.ffmpeg_streams:
                if ffmpeg_stream.channel == channel:
                    found = True
                    stream_obj = ffmpeg_stream
            
            if found:
                stream_obj.last_used = time.time()

                return send_file(os.path.join(path, "index.m3u8"))
        
        user_session = None
        
        for stream_session in stream_sessions:
            if stream_session["session_id"] == session_id:
                user_session = stream_session
                print(f"Session {session_id} is already using mac {user_session['mac']['addr']}")
                break
        
        if user_session == None or not self.mac_free(user_session['mac']['addr'], channel):
            if user_session != None:
                stream_sessions.remove(user_session)
            
            print(f"Starting session {session_id}")
            
            req_session = httpx.Client()
            
            while True:
                mac = random.choice(self.mac_addrs)
                print(f"Trying mac {mac}")
                
                mac_free = self.mac_free(mac["addr"], channel)
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
        stream_url = f"{self.url}/play/live.php?mac={user_session['mac']['addr']}&stream={channel}&extension=ts"
        # Proxy the stream
        
        def generate():
            with user_session['session'].stream("GET", stream_url, follow_redirects=True, headers={"User-Agent": self.user_agent}, timeout=10) as r:
                for chunk in r.iter_bytes(chunk_size=8192):
                    yield chunk
        
        match proxy:
            case 2:
                return
                found = False
                path = os.path.join(config["stream_path"], str(self.id), channel)
                
                for ffmpeg_stream in self.ffmpeg_streams:
                    if ffmpeg_stream.channel == channel:
                        found = True
                        stream_obj = ffmpeg_stream
                
                if not found:
                    print(f"Creating ffmpeg instance for {channel}")
                    
                    if not os.path.exists(os.path.join(config["stream_path"], str(self.id))):
                        try:
                            os.mkdir(os.path.join(config["stream_path"], str(self.id)))
                        except:
                            pass
                    
                    try:
                        os.mkdir(path)
                    except:
                        pass
                    
                    stream_obj = FfmpegStream(self.id, channel, stream_url, path, ffmpeg_str_arr=self.ffmpeg_streams, hls_time=10, hls_list_size=30)
                    stream_obj.start_stream()
                    
                    self.ffmpeg_streams.append(stream_obj)
                
                stream_obj.last_used = time.time()
                
                while not os.path.exists(os.path.join(path, "index.m3u8")):
                    print(f"File {os.path.join(path, 'index.m3u8')} doesn't exist sleeping 0.1s")
                    time.sleep(0.1)

                return send_file(os.path.join(path, "index.m3u8"))
            case 1:
                return Response(stream_with_context(generate()), mimetype='video/mp2t', direct_passthrough=True)
            case _:
                return redirect(stream_url, code=301)
    
    def get_macs_from_mcbash(self, path) -> list[dict]:
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
            servers.append(IPTVServer(entry["url"], len(servers), entry.get("mcbash_file", None), entry.get("run_mcbash", True)))
    
    for entry in config["xtream_servers"]:
        servers.append(XtreamServer(entry["url"], len(servers), entry["username"], entry["passwd"], entry.get("stream_prefix", ""), entry.get("stream_suffix", "")))
    
    # Stop all existing processes.
    for proc in mcbash_processes:
        proc.terminate()
        mcbash_processes.remove(proc)

    for server in servers:
        if type(server) == IPTVServer:
            if not os.path.exists(server.mcbash_file):
                os.system(f"touch {server.mcbash_file}")
            if server.run_mcbash:
                mcbash_processes.append(subprocess.Popen(f"mcbash -u {server.url} -w 2 -b 10 -d 2 -s 0 -t 0 --prefix 00:1A:79", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))

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
            
                file_content += f"\n#EXTINF:-1 tvg-logo=\"{channel['logo']}\" group-title=\"{channel['name']}\",{channel['name']}"
                stream_url = f"{'https' if config['https'] else 'http'}://{request.url.split('/')[2].replace(':', '')}/play/{server.id}/{channel['id']}?proxy={int(request.args.get('proxy', 0))}"
                if original_links: file_content += f"\n{channel['url'] if type(server) == Server or type(server) == XtreamServer else stream_url}"
                else: file_content += f"\n{stream_url}"
        
        return Response(file_content, mimetype='text/plain')

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
            
            file_content += f"\n#EXTINF:-1 tvg-logo=\"{channel['logo']}\" group-title=\"{channel['name']}\",{channel['name']}"
            stream_url = f"{'https' if config['https'] else 'http'}://{request.url.split('/')[2].replace(':', '')}/play/{servers[int(server)].id}/{channel['id']}?proxy={int(request.args.get('proxy', 0))}"
            if original_links: file_content += f"\n{channel['url'] if type(servers[int(server)]) == Server or type(servers[int(server)]) == XtreamServer else stream_url}"
            else: file_content += f"\n{stream_url}"
            #file_content += f"\n{'https' if config['https'] else 'http'}://{request.url.split('/')[2].replace(':', '')}/play/{servers[int(server)].id}/{channel['id']}?proxy={int(request.args.get('proxy', 0))}"
        
        return Response(file_content, mimetype='text/plain')
    
    @app.route("/play/<server>/<channel>")
    def play(server, channel):
        if session.get("session_id", None) == None:
            session["session_id"] = rand_str(32)
        return servers[int(server)].handle_play(channel, session["session_id"], int(request.args.get("proxy", 0)))
    
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
        config = {"https": True, "stream_path": "/streams", "ffmpeg_path": None, "iptv_servers": [], "channels": [], "users": []}
        
        dump_config()
    
    # Setup.
    servers = []
    mcbash_processes = []
    config = read_config()
    
    if not os.path.exists(config["stream_path"]):
        os.mkdir(config["stream_path"])
    
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
    
    while True:
        time.sleep(60*60*8) # Update every 8 hours.
        
        for server in servers:
            for ffmpeg_stream in server.ffmpeg_streams:
                if ffmpeg_stream.last_used > 60*60*8: # Check every 8 hours.
                    ffmpeg_stream.stop_stream()
            
            if type(server) == IPTVServer:
                server.update_macs()
                server.update_channels()
            elif type(server) == XtreamServer:
                server.update_channels()

        for stream_session in stream_sessions:
            if time.time() - stream_session["timestamp"] > 60*60*24: # Delete sessions that haven't been used in a day.
                stream_sessions.remove(stream_session)
        
        dump_config()
        
def exit_handler():
    print("Exitting.")
    if servers != None:
        for server in servers:
            for ffmpeg_stream in server.ffmpeg_streams:
                ffmpeg_stream.stop_stream()

if __name__ == "__main__": #/root/.mcbash/valid_macs_ledir.thund.re
    main()
from flask import Flask, redirect, request, Response, session
import requests
import datetime
import time
import json
import _thread
import random
import subprocess
import os
import hashlib
import string
import sys

servers = []
config = {}
config_dir = ""

class Server:
    def __init__(self, id):
        self.channels = config["channels"]
        self.id = id
    
    def add_channel(self, name, logo, url):
        config["channels"].append({
            "id": len(config["channels"]),
            "name": name,
            "logo": logo,
            "url": url,
        })
    
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
    
    def handle_play(self, channel_id, session_id, proxy, filename=None):
        for channel in self.channels:
            if channel["id"] == channel_id:
                def generate():
                    with requests.get(channel["url"], stream=True) as r:
                        for chunk in r.iter_content(chunk_size=4096):
                            if chunk:
                                yield chunk
                
                if proxy==1:
                    response = Response(generate(), mimetype='video/mp2t')
                    
                    return response
                else:
                    return redirect(channel["url"])
        
        return None

class MinistraServer:
    def __init__(self, url, id, mcbash_file=None):
        self.url = url
        self.mcbash_file = mcbash_file if mcbash_file != None else (f"/root/.mcbash/valid_macs_{url.split('/')[2]}" if os.getlogin() == "root" else f"/home/{os.getlogin()}/.mcbash/valid_macs_{url.split('/')[2]}")
        self.mac_addrs = None
        self.channels = None
        self.id = id
        self.session = requests.Session()
        
        self.setup()
    
    def setup(self):
        print(f"Setup {self.url}")
        # Get mac addrs
        self.mac_addrs = self.get_macs_from_mcbash(self.mcbash_file)
        print(f"There are {len(self.mac_addrs)} mac addrs available on {self.url}.")
        
        # Get channels.
        handshake = None
        
        while handshake == None:
            mac = random.choice(self.mac_addrs)["addr"]
            handshake = self.get_handshake(mac)
        
        print(f"Token: {handshake}")
        
        headers = {
            "Authorization": f"Bearer {handshake}",
            "Cookie": f"mac={mac}; stb_lang=en; timezone=Europe/Amsterdam; "
        }
        
        channel_request = self.session.get(f"{self.url}/server/load.php?type=itv&action=get_all_channels", headers=headers)
        if channel_request.status_code == 200:
            self.channels = json.loads(channel_request.text)["js"]["data"]
            print(f"Recieved channel list for {self.url}")
            print(f"{self.url} has {len(self.channels)} channels.")
        
        print(f"Setup for {self.url} complete")
    
    def update_macs(self):
        self.mac_addrs = self.get_macs_from_mcbash(self.mcbash_file)
        print(f"There are {len(self.mac_addrs)} mac addrs available on {self.url}.")
    
    def update_channels(self):
        mac = random.choice(self.mac_addrs)["addr"]
        handshake = self.get_handshake(mac)
        
        print(f"Token: {handshake}")
        
        headers = {
            "Authorization": f"Bearer {handshake}",
            "Cookie": f"mac={mac}; stb_lang=en; timezone=Europe/Amsterdam; "
        }
        
        channel_request = self.session.get(f"{self.url}/server/load.php?type=itv&action=get_all_channels", headers=headers)
        if channel_request.status_code == 200:
            self.channels = json.loads(channel_request.text)["js"]["data"]
            print(f"{self.url} has {len(self.channels)} channels.")

    def get_handshake(self, mac):
        request = self.session.get(f"{self.url}/portal.php?action=handshake&type=stb&token=&mac={mac.replace(':', '%3A')}")
        return json.loads(request.text)["js"]["token"] if request.status_code == 200 else None

    def mac_free(self, mac, session=requests.Session()):
        try:
            with session.get(f"{self.url}/play/live.php?mac={mac}&stream={self.channels[0]['id']}&extension=ts", stream=True) as response:
                return response.status_code == 200
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            return False
    
    def handle_play(self, channel, session_id, proxy):
        print(f"Request for channnel {channel} on server {self.url}")
        user_session = None
        
        for stream_session in stream_sessions:
            if stream_session["session_id"] == session_id:
                user_session = stream_session
                print(f"Session {session_id} is already using mac {user_session['mac']['addr']}")
                break
        
        if user_session == None or not self.mac_free(user_session['mac']['addr'], user_session['session']):
            if user_session != None:
                stream_sessions.remove(user_session)
            
            print(f"Starting session {session_id}")
            
            req_session = requests.Session()
            
            while True:
                mac = random.choice(self.mac_addrs)
                print(f"Trying mac {mac}")
                
                mac_free = self.mac_free(mac["addr"], req_session)
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
            with user_session['session'].get(stream_url, stream=True) as r:
                if r.status_code != 200:
                    print(f"Status code {r.status_code}")
                for chunk in r.iter_content(chunk_size=4096):
                    if chunk:
                        yield chunk
        
        if proxy==1:
            response = Response(generate(), mimetype='video/mp2t')
            
            return response
        else:
            return redirect(stream_url)
    
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
    x = []
    x.append(Server(len(x)))
    
    for entry in config["ministra_urls"]:
        x.append(MinistraServer(entry["url"], len(x), entry.get("mcbash_file", None)))
    
    return x

def mcbash(url):
    while-True:
        print("Starting mcbash.")
        proc = subprocess.Popen(f"mcbash -u {url} -w 2 -b 10 -d 2 -s 0 -t 0 --prefix 00:1A:79", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        proc.wait()
        print("Mcbash finished.")
        time.sleep(60)

def web_server(arg):
    global stream_sessions
    global login_sessions
    app = Flask(__name__)
    app.secret_key = rand_str(32)
    template_dir = os.path.abspath(f"{config_dir}/templates")
    
    login_sessions = []
    stream_sessions = []
    
    @app.route("/api/login")
    def login():
        username = request.args["username"]
        passwd = request.args["passwd"]
        
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
        session_id = request.headers.get("session_id", None)
        
        for login_session in login_sessions:
            if login_session["session_id"] == session_id:
                login_sessions.remove(login_session)
                return Response(status=200)
        
        return Response(status=403)
    
    @app.route("/api/get_user")
    def get_user():
        session_id = request.headers.get("session_id", None)
        
        for login_session in login_sessions:
            if login_session["session_id"] == session_id:
                return login_session["user"]
        
        return Response(status=403)
    
    @app.route("/server/<server>/get_channels")
    def get_channels(server):
        return servers[int(server)].channels
    
    @app.route("/server/get_m3u")
    def get_m3u_all():
        search = request.args.get("search", None)
        file_content = "#EXTM3U"
        for server in servers:
            for channel in server.channels:
                if search != None:
                    if not search.lower() in channel["name"].lower():
                        continue
                file_content += f"\n#EXTINF:-1 tvg-logo=\"{channel['logo']}\" group-title=\"{channel['name']}\",{channel['name']}"
                file_content += f"\n{'https' if config['https'] else 'http'}://{request.url.split('/')[2].replace(':', '')}/play/{server.id}/{channel['id']}"
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
        session_id = request.headers.get("session_id", None)
        name = request.args.get("name", None)
        logo = request.args.get("logo", None)
        url = request.args.get("url", None)
        
        for login_session in login_sessions:
            if login_session["session_id"] == session_id and login_session["user"]["admin"]:
                server.add_channel(name, logo, url)
                
                return Response(status=200)
        
        return Response(status=403)
    
    @app.route("/server/<server_id>/remove_channel")
    def remove_channel(server_id):
        server = servers[int(server_id)]
        session_id = request.headers.get("session_id", None)
        name = request.args.get("name", None)
        id = request.args.get("id", None)
        
        for login_session in login_sessions:
            if login_session["session_id"] == session_id and login_session["user"]["admin"]:
                server.remove_channel(name, id)
        
                return Response(status=200)
        
        return Response(status=403)
    
    @app.route("/server/remove_ministra_url")
    def remove_ministra():
        url = request.args.get("url", None)
        session_id = request.headers.get("session_id", None)
        
        for login_session in login_sessions:
            if login_session["session_id"] == session_id and login_session["user"]["admin"]:
                for m_url in config["ministra_urls"]:
                    if m_url["url"] == url:
                        config["ministra_urls"].remove(m_url)
                        break
                
                return Response(status=200)
        
        return Response(status=403)
    
    @app.route("/server/add_ministra_url")
    def add_ministra():
        url = request.args["url"]
        session_id = request.headers.get("session_id", None)
        
        for login_session in login_sessions:
            if login_session["session_id"] == session_id and login_session["user"]["admin"]:
                config["ministra_urls"].append({
                    "url": url,
                    "mcbash_file": f"{os.getenv("HOME")}/.mcbash/valid_macs_{url.split('/')[2]}",
                    "run_mcbash": True,
                })
                
                return Response(status=200)

        return Response(status=403)
    
    @app.route("/server/<server>/get_m3u")
    def get_m3u(server):
        search = request.args.get("search", None)
        file_content = "#EXTM3U"
        for channel in servers[int(server)].channels:
            if search != None:
                if not search.lower() in channel["name"].lower():
                    continue
            file_content += f"\n#EXTINF:-1 tvg-logo=\"{channel['logo']}\" group-title=\"{channel['name']}\",{channel['name']}"
            file_content += f"\n{request.url.split(':')[0]}://{request.url.split('/')[2].replace(':', '')}/play/{server}/{channel['id']}"
        
        return Response(file_content, mimetype='text/plain')
    
    @app.route("/play/<server>/<channel>")
    def play(server, channel):
        if session.get("session_id", None) == None:
            session["session_id"] = rand_str(32)
        return servers[int(server)].handle_play(channel, session["session_id"], request.args.get("proxy", 1))
    
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
    
    debug = "--debug" in sys.argv
    config_dir = ("/etc/iptv" if os.system != "nt" else f"{os.environ['appdata']}/iptv") if not debug else "./"
    print(f"Config dir: {config_dir}")
    print(f"Config file {config_dir}/config.json")
    
    if not os.path.exists(config_dir):
        os.mkdir(config_dir)
    if not os.path.exists(f"{config_dir}/config.json"):
        print("Config missing, creating.")
        config = {"https": True, "ministra_urls": [], "channels": [], "users": []}
        
        dump_config()
    
    # Setup.
    config = read_config()
    servers = setup_servers()
    
    for mcbash_file in config["ministra_urls"]:
        if not os.path.exists(mcbash_file["mcbash_file"]):
            os.system(f"touch {mcbash_file['mcbash_file']}" if os.name != "nt" else "")
    
    # Check if there are any users, if none create one.
    if len(config["users"]) == 0:
        print("No users configured.")
        print("Creating user admin.")
        passwd = rand_str(32)
        print(f"Admin passwd: {passwd}")
        config["users"].append({"username": "admin", "passwd": hashlib.sha256(bytes(passwd.encode())).hexdigest(), "last_watched": None, "admin": True})

        dump_config()
    
    _thread.start_new_thread(web_server, (0 ,))
    
    for entry in config["ministra_urls"]:
        if entry["run_mcbash"]:
            _thread.start_new_thread(mcbash, (entry["url"] ,))
    
    while True:
        time.sleep(60*60*24) # Update every day.
        
        for server in servers:
            if type(server) == MinistraServer:
                server.update_macs()
                server.update_channels()

        for stream_session in stream_sessions:
            if time.time() - stream_session["timestamp"] > 60*60*24*7: # Delete sessions that haven't been used in a week.
                stream_sessions.remove(stream_session)
        
        dump_config()

if __name__ == "__main__": #/root/.mcbash/valid_macs_ledir.thund.re
    main()
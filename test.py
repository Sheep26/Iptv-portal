import requests

session = requests.get("http://localhost:8080/api/login", headers={"username": "admin","passwd": "Aqv2MM6koMiQcdl3AjucjXH6w1AoqpvC"})
print(session.text)

r = requests.get("http://localhost:8080/server/add_iptv_server?url=http://tbtv.me:2095", headers={"session": session.text})
print(r.status_code)
print(r.text)
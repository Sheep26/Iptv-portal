mkdir /etc/iptv

apt install python3-flask
apt install python3-requests
mv main.py /etc/iptv/iptv
mv config.json /etc/iptv/config.json
mv iptv.service /etc/systemd/system/iptv.service

systemctl enable iptv
systemctl start iptv
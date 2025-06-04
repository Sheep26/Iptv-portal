systemctl stop iptv
rm /etc/iptv/iptv
mv main.py /etc/iptv/iptv
systemctl start iptv
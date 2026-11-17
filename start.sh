#!/bin/bash
set -e

python3 main.py &
python3 cache_proxy.py &

wait -n
exit $?
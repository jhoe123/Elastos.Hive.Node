#!/usr/bin/env bash

# function that install and configure the dependencies
function config() {
    echo 'Y' | sudo apt install python3 python3-venv pip libffi-dev mongodb
    # check if not file exists install ipfs
    if [ ! -f /root/snap/ipfs/common/config ]; then
        snap install ipfs
    fi
    
    # python setup
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    echo ''
    echo 'Note: You might want to configure hive .env file. Also you may need to allow PORT 5000, IPFS node and proxy ports.'
}

# function that starts running the application
function run() {
    ipfs daemon &
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    LD_LIBRARY_PATH="$PWD/hive/util/did/" 
    python manage.py runserver --host 0.0.0.0
}


# case select base from $1
case "$1" in
    config )
        config
        ;;
    run )
        run
        ;;
    * )
        echo "Usage: $0 {config|start}"
        exit 1
        ;;
esac
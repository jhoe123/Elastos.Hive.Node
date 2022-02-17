#!/usr/bin/env bash

# function that install and configure the dependencies
function config() {
    echo 'Y' | sudo apt install python3 python3-venv pip libffi-dev mongodb
    #sudo snap install ipfs

    # python setup
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
}

# function that starts running the application
function run() {
    ipfs daemon &
    LD_LIBRARY_PATH="$PWD/hive/util/did/" python manage.py runserver
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
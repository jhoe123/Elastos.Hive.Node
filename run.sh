#!/usr/bin/env bash

function start_db () {
    docker container list --all | grep hive-mongo > /dev/null \
              && docker container stop hive-mongo > /dev/null \
              && docker container rm -f hive-mongo > /dev/null
    echo -n "Hive-mongo Container: "
    docker run -d --name hive-mongo                     \
        --network hive                                  \
        -v ${PWD}/.mongodb-data:/data/db                \
        -p 27020:27017                                  \
        mongo:4.4.0
}

function setup_venv () {
  echo "setup_venv"
    case `uname` in
    Linux )
        #virtualenv -p `which python3.6` .venv
        python3 -m venv .venv
        source .venv/bin/activate
        pip install --upgrade pip
        pip install -r requirements.txt
        ;;
    Darwin )
        #virtualenv -p `which python3.7` .venv
        python3 -m venv .venv
        source .venv/bin/activate
        pip install --upgrade pip
        pip install --global-option=build_ext --global-option="-I/usr/local/include" --global-option="-L/usr/local/lib" -r requirements.txt
        ;;
    *)
    exit 1
    ;;
    esac
}

function start_docker () {
    echo "Running using docker..."
    docker version > /dev/null 2>&1
    if [ ! $? -eq 0 ];then
        echo "You don't have docker installed. Please run the below commands to install docker"
        echo "
$ curl -fsSL https://get.docker.com -o get-docker.sh
$ sudo sh get-docker.sh
$ sudo usermod -aG docker $(whoami)
        "
        exit
    fi

    if [ ! -f ".env" ];then
        cp .env.example .env
    fi

    DID_MNEMONIC=$(grep 'DID_MNEMONIC' .env | sed 's/DID_MNEMONIC="//;s/"//')
    echo -n "Your DID MNEMONIC: "
    echo -e "\033[;36m ${DID_MNEMONIC} \033[0m"
    echo -n "Confirm ? (y/n) "
    read RESULT
    RESULT=$(echo ${RESULT})
    if [ ! "${RESULT}" == "y" ];then
        echo -n "Please input your DID MNEMONIC: "
        read DID_MNEMONIC
        DID_MNEMONIC=$(echo ${DID_MNEMONIC})
        [ "${DID_MNEMONIC}" = "" ] && echo "You don't input DID MNEMONIC" && exit 1
        sed -i "/DID_MNEMONIC/s/^.*$/DID_MNEMONIC=\"${DID_MNEMONIC}\"/" .env
    fi


    echo -n "Please input your DID MNEMONIC PASSPHRASE: "
    read DID_PASSPHRASE
    DID_PASSPHRASE=$(echo ${DID_PASSPHRASE})
    sed -i "/DID_PASSPHRASE/s/^.*$/DID_PASSPHRASE=${DID_PASSPHRASE}/" .env
    echo -n "Please input your DID MNEMONIC SECRET: "
    read DID_STOREPASS
    DID_STOREPASS=$(echo ${DID_STOREPASS})
    [ "${DID_STOREPASS}" != "" ] && sed -i "/DID_STOREPASS/s/^.*$/DID_STOREPASS=${DID_STOREPASS}/" .env
    
    sed -i "/DID_RESOLVER/s/^.*$/DID_RESOLVER=http:\/\/api.elastos.io:20606/" .env
    sed -i "/ELA_RESOLVER/s/^.*$/ELA_RESOLVER=http:\/\/api.elastos.io:20336/" .env
    sed -i "/MONGO_HOST/s/^.*$/MONGO_HOST=hive-mongo/" .env
    sed -i "/MONGO_PORT/s/^.*$/MONGO_PORT=27017/" .env

    docker network ls | grep hive > /dev/null || docker network create hive
    start_db
    docker container list --all | grep hive-node > /dev/null \
              && docker container stop hive-node > /dev/null \
              && docker container rm -f hive-node > /dev/null
    docker build -t elastos/hive-node . > /dev/null
    echo -n "Hive-node Container: "
    docker run -d --name hive-node  \
      --network hive                \
      -v ${PWD}/.data:/src/data     \
      -v ${PWD}/.env:/src/.env      \
      -p 5000:5000                  \
      elastos/hive-node
    echo -n "Checking."
    timeout=0
    while true; do
        curl -s -X POST -H "Content-Type: application/json" -d '{"key":"value"}' http://localhost:5000/api/v1/echo > /dev/null
        if [ $? -eq 0 ];then
	        echo -e "\033[;32m Success \033[0m"
            echo -n "You can now access your hive node service at "
	        echo -e "\033[;36mhttp://0.0.0.0:5000\033[0m"
            exit 0
        else
            if [ ${timeout} -gt 10 ];then
	            echo -e "\033[;31m Failed \033[0m"
                exit 1
            else
                sleep 1
                echo -n "."
                let timeout++
            fi
        fi
    done
    
}

function start_direct () {
    docker network create hive

    start_db

    echo "Running directly on the machine..."
    ps -ef | grep gunicorn | awk '{print $2}' | xargs kill -9

    setup_venv

    LD_LIBRARY_PATH="$PWD/hive/util/did/" python manage.py runserver
}

function test () {
    docker network create hive

    start_db

    setup_venv

    # Run tests
    pytest --disable-pytest-warnings -xs tests/hive_auth_test.py
    pytest --disable-pytest-warnings -xs tests/hive_mongo_test.py
    pytest --disable-pytest-warnings -xs tests/hive_file_test.py
    pytest --disable-pytest-warnings -xs tests/hive_scripting_test.py
    pytest --disable-pytest-warnings -xs tests/hive_payment_test.py
    pytest --disable-pytest-warnings -xs tests/hive_backup_test.py
}

function stop() {
    hive_node=$(docker container list --all | grep hive-node | awk '{print $1}')
    if [ -n "${hive_node}" ];then
    	docker container stop ${hive_node}
    	docker container rm ${hive_node}
    fi
    hive_mongo=$(docker container list --all | grep hive-mongo | awk '{print $1}')
    if [ -n "${hive_mongo}" ];then
    	docker container stop ${hive_mongo}
    	docker container rm ${hive_mongo}
    fi
}

case "$1" in
    direct)
        start_direct
        ;;
    docker)
        start_docker
        ;;
    test)
        test
        ;;
    stop)
        stop
        ;;
    *)
    echo "Usage: run.sh {docker|direct|test}"
    exit 1
esac

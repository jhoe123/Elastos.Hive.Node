from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename

from hive.main.hive_file import HiveFile
from hive.main.hive_mongo import HiveMongo
from hive.main.hive_auth import HiveAuth
from hive.main.hive_sync import HiveSync

hive_mongo = HiveMongo()
hive_file = HiveFile()
hive_auth = HiveAuth()
hive_sync = HiveSync()
main = Blueprint('main', __name__)


def init_app(app):
    hive_auth.init_app(app)
    hive_mongo.init_app(app)
    hive_file.init_app(app)
    hive_sync.init_app(app)
    app.register_blueprint(main)


@main.route('/api/v1/echo', methods=['POST'])
def echo():
    # get_json(force=False, silent=False, cache=True)
    # 获取json失败会直接返回
    content = request.get_json()
    return jsonify(content)


# did register
@main.route('/api/v1/did/auth', methods=['POST'])
def did_auth_challenge():
    return hive_auth.did_auth_challenge()


@main.route('/api/v1/did/<did_base58>/callback', methods=['POST'])
def did_auth_callback(did_base58):
    return hive_auth.did_auth_callback(did_base58)


# db create and get
@main.route('/api/v1/db/create_collection', methods=['POST'])
def create_collection_view():
    return hive_mongo.create_collection()


# file create and get
@main.route('/api/v1/file/uploader', methods=['POST'])
def upload_file():
    return hive_file.upload_file()


@main.route('/api/v1/file/downloader', methods=['GET'])
def download_file():
    return hive_file.download_file()


@main.route('/api/v1/file/info', methods=['GET'])
def file_info():
    return hive_file.get_file_info()


@main.route('/api/v1/file/delete', methods=['POST'])
def delete_file():
    return hive_file.delete_file()


@main.route('/api/v1/file/list', methods=['GET'])
def list_files():
    return hive_file.list_files()


@main.route('/api/v1/syn/setup/google_drive', methods=['POST'])
def setup_syn_google_drive():
    return hive_sync.setup_google_drive_rclone()

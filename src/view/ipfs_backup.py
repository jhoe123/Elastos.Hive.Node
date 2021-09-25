# -*- coding: utf-8 -*-

"""
The view of ipfs-backup module for file saving and viewing.
"""
from flask import Blueprint, request

from src.modules.ipfs.ipfs_backup import IpfsBackupClient
from src.modules.ipfs.ipfs_backup_server import IpfsBackupServer
from src.utils.consts import URL_IPFS_BACKUP_SERVER_BACKUP, URL_IPFS_BACKUP_SERVER_BACKUP_STATE, \
    URL_IPFS_BACKUP_SERVER_RESTORE
from src.utils.http_request import params

blueprint = Blueprint('ipfs-backup', __name__)
backup_client: IpfsBackupClient = None
backup_server: IpfsBackupServer = None


def init_app(app, hive_setting):
    """ This will be called by application initializer. """
    global backup_client, backup_server
    backup_client = IpfsBackupClient(app=app, hive_setting=hive_setting)
    backup_server = IpfsBackupServer(app=app, hive_setting=hive_setting)
    app.register_blueprint(blueprint)


@blueprint.route('/api/v2/ipfs-vault/content', methods=['GET'])
def get_state():
    return backup_client.get_state()


@blueprint.route('/api/v2/ipfs-vault/content', methods=['POST'])
def backup_restore():
    to = request.args.get('to')
    fr = request.args.get('from')
    is_force = request.args.get('is_force', 'False') == 'True'
    if to == 'hive_node':
        return backup_client.backup(params.get('credential'), is_force)
    elif fr == 'hive_node':
        return backup_client.restore(params.get('credential'), is_force)


# ipfs-promotion on the backup server side


@blueprint.route('/api/v2/ipfs-backup/promotion', methods=['POST'])
def promotion():
    return backup_server.promotion()


# ipfs-backup internal APIs on the backup server side


@blueprint.route(URL_IPFS_BACKUP_SERVER_BACKUP, methods=['POST'])
def internal_backup():
    return backup_server.internal_backup(params.get('cid'), params.get('sha256'), params.get('size'),
                                         params.get('is_force', False))


@blueprint.route(URL_IPFS_BACKUP_SERVER_BACKUP_STATE, methods=['GET'])
def internal_backup_state():
    return backup_server.internal_backup_state()


@blueprint.route(URL_IPFS_BACKUP_SERVER_RESTORE, methods=['GET'])
def internal_restore():
    return backup_server.internal_restore()


# subscription


@blueprint.route('/api/v2/ipfs-subscription/backup', methods=['PUT'])
def backup_subscribe():
    return backup_server.subscribe()


@blueprint.route('/api/v2/ipfs-subscription/backup', methods=['DELETE'])
def backup_unsubscribe():
    return backup_server.unsubscribe()


@blueprint.route('/api/v2/ipfs-subscription/backup', methods=['GET'])
def backup_get_info():
    return backup_server.get_info()
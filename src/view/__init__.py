# -*- coding: utf-8 -*-
from src.settings import hive_setting
from src.utils.db_client import cli
from src.view import scripting, subscription, files, database, auth, backup, payment, about, \
    ipfs_files, ipfs_scripting, ipfs_backup


def retry_ipfs_backup():
    """ retry maybe because interrupt by reboot
    1. handle all backup request in the vault node.
    2. handle all backup request in the backup node.
    """
    user_dids = cli.get_all_user_dids()
    for user_did in user_dids:
        ipfs_backup.backup_client.retry_backup_request(user_did)
        ipfs_backup.backup_server.retry_backup_request(user_did)


def init_app(app, mode):
    about.init_app(app, hive_setting)
    auth.init_app(app, hive_setting)
    subscription.init_app(app, hive_setting)
    backup.init_app(app, hive_setting)
    scripting.init_app(app, hive_setting)
    files.init_app(app, hive_setting)
    database.init_app(app, hive_setting)
    payment.init_app(app, hive_setting)
    ipfs_files.init_app(app, hive_setting)
    ipfs_scripting.init_app(app, hive_setting)
    ipfs_backup.init_app(app, hive_setting)
    retry_ipfs_backup()

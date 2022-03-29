# -*- coding: utf-8 -*-
import logging
import threading

from src import hive_setting
from src.utils.db_client import cli
from src.utils.scheduler import scheduler_init
from src.view import about, auth, subscription, database, files, scripting, payment, backup, provider


def retry_ipfs_backup():
    """ retry maybe because interrupt by reboot
    1. handle all backup request in the vault node.
    2. handle all backup request in the backup node.
    """
    user_dids = cli.get_all_user_dids()
    logging.info(f'[retry_ipfs_backup] get {len(user_dids)} users')
    for user_did in user_dids:
        backup.backup_client.retry_backup_request(user_did)
        backup.backup_server.retry_backup_request(user_did)


class RetryIpfsBackupThread(threading.Thread):
    def __init__(self):
        super().__init__()

    def run(self):
        try:
            logging.info(f'[RetryIpfsBackupThread] enter')
            retry_ipfs_backup()
            logging.info(f'[RetryIpfsBackupThread] leave')
        except Exception as e:
            logging.error(f'[RetryIpfsBackupThread] error {str(e)}')


def init_app(app):
    logging.getLogger('v2_init').info('enter init_app')
    about.init_app(app)
    auth.init_app(app)
    subscription.init_app(app)
    database.init_app(app)
    files.init_app(app)
    scripting.init_app(app)
    backup.init_app(app)
    provider.init_app(app)
    if hive_setting.PAYMENT_ENABLED:
        payment.init_app(app)

    RetryIpfsBackupThread().start()
    scheduler_init(app)
    logging.getLogger('v2_init').info('leave init_app')

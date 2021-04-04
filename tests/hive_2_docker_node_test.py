import json
import logging
import shutil
import sys
import time
from io import BytesIO

import requests
import unittest

from hive.main.hive_backup import HiveBackup, VAULT_BACKUP_INFO_STATE, VAULT_BACKUP_MSG_SUCCESS, VAULT_BACKUP_INFO_MSG
from hive.util.error_code import NOT_FOUND
from hive.util.payment.vault_backup_service_manage import get_vault_backup_path
from hive.util.payment.vault_service_manage import delete_user_vault, delete_user_vault_data, get_vault_path
from tests.hive_auth_test import DIDApp, DApp
from hive.util.did.eladid import ffi, lib

from tests.test_common import upsert_collection, create_upload_file, prepare_vault_data, copy_to_backup_data

from hive import create_app

unittest.TestSuite

import hive
from hive import HIVE_MODE_TEST
from tests import test_common

logger = logging.getLogger()
logger.level = logging.DEBUG


class Hive2NodeTest(unittest.TestCase):
    def __init__(self, methodName='runTest'):
        super(Hive2NodeTest, self).__init__(methodName)

    @classmethod
    def setUpClass(cls):
        cls.stream_handler = logging.StreamHandler(sys.stdout)
        logger.addHandler(cls.stream_handler)
        logging.getLogger("HiveBackupTestCase").debug("Setting up HiveBackupTestCase\n")

    @classmethod
    def tearDownClass(cls):
        logging.getLogger("HiveBackupTestCase").debug("\n\nShutting down HiveBackupTestCase")
        logger.removeHandler(cls.stream_handler)

    def setUp(self):
        logging.getLogger("HiveBackupTestCase").info("\n")
        self.app = create_app(mode=HIVE_MODE_TEST)
        self.app.config['TESTING'] = True
        self.test_client = self.app.test_client()
        self.app_id = "appid"
        self.did = "did:elastos:ij8krAVRJitZKJmcCufoLHQjq7Mef3ZjTN"
        self.user_did = DIDApp("didapp", "clever bless future fuel obvious black subject cake art pyramid member clump")
        self.user_app_did = DApp("testapp", self.app_id,
                                 "amount material swim purse swallow gate pride series cannon patient dentist person")
        self.host1 = "http://127.0.0.1:5002"
        self.host2 = "http://127.0.0.1:5003"
        # self.docker_host1 = "http://host.docker.internal:5002"
        # self.docker_host2 = "http://host.docker.internal:5003"
        self.docker_host1 = "http://127.0.0.1:5002"
        self.docker_host2 = "http://127.0.0.1:5003"
        self.token1, self.hive_did1 = self.get_did_token(self.host1)
        self.token2, self.hive_did2 = self.get_did_token(self.host2)

    def json_header(self):
        headers = {"Content-Type": "application/json"}
        return headers

    def auth_header(self, token):
        headers = {"Content-Type": "application/json", "Authorization": "token " + token}
        return headers

    def upload_header(self, token):
        headers = {"Authorization": "token " + token}
        return headers

    def tearDown(self):
        logging.getLogger("HiveBackupTestCase").info("\n")

    def assert200(self, status):
        self.assertEqual(status, 200)

    def parse_response(self, r):
        try:
            v = json.loads(r.get_data())
        except json.JSONDecodeError:
            v = None
        return v, r.status_code

    def did_auth(self, host, user_did, app_did):
        # sign_in
        doc = lib.DIDStore_LoadDID(app_did.store, app_did.did)
        doc_str = ffi.string(lib.DIDDocument_ToJson(doc, True)).decode()
        logging.getLogger("test_auth_common").debug(f"\ndoc_str: {doc_str}")
        doc = json.loads(doc_str)

        param = {"document": doc}
        r = requests.post(host + '/api/v1/did/sign_in',
                          json=param,
                          headers=self.json_header())
        self.assert200(r.status_code)
        rt = r.json()

        jwt = rt["challenge"]
        # print(jwt)
        jws = lib.DefaultJWSParser_Parse(jwt.encode())
        # if not jws:
        #     print(ffi.string(lib.DIDError_GetMessage()).decode())
        aud = ffi.string(lib.JWT_GetAudience(jws)).decode()
        self.assertEqual(aud, app_did.get_did_string())
        nonce = ffi.string(lib.JWT_GetClaim(jws, "nonce".encode())).decode()
        hive_did = ffi.string(lib.JWT_GetIssuer(jws)).decode()
        lib.JWT_Destroy(jws)

        # auth
        vc = user_did.issue_auth(app_did)
        vp_json = app_did.create_presentation(vc, nonce, hive_did)
        auth_token = app_did.create_vp_token(vp_json, "DIDAuthResponse", hive_did, 60)
        # print(auth_token)
        logging.getLogger("test_auth_common").debug(f"\nauth_token: {auth_token}")
        param = {
            "jwt": auth_token,
        }
        r = requests.post(host + '/api/v1/did/auth',
                          json=param,
                          headers=self.json_header())
        self.assert200(r.status_code)
        rt = r.json()

        token = rt["access_token"]
        jws = lib.DefaultJWSParser_Parse(token.encode())
        aud = ffi.string(lib.JWT_GetAudience(jws)).decode()
        self.assertEqual(aud, app_did.get_did_string())
        issuer = ffi.string(lib.JWT_GetIssuer(jws)).decode()
        lib.JWT_Destroy(jws)
        # print(token)
        logging.getLogger("test_auth_common").debug(f"\ntoken: {token}")
        app_did.set_access_token(token)

        # auth_check
        # token = test_common.get_auth_token()
        r = requests.post(host + '/api/v1/did/check_token',
                          json=param,
                          headers=self.auth_header(token))
        self.assert200(r.status_code)
        return token, hive_did

    def get_did_token(self, host):
        token, hive_did = self.did_auth(host, self.user_did, self.user_app_did)
        return token, hive_did

    def init_vault_service(self, host, token):
        param = {}
        r = requests.post(host + '/api/v1/service/vault/create',
                          json=param,
                          headers={"Content-Type": "application/json", "Authorization": "token " + token})
        self.assert200(r.status_code)

    def init_backup_service(self, host, token):
        param = {}
        r = requests.post(host + '/api/v1/service/vault_backup/create',
                          json=param,
                          headers={"Content-Type": "application/json", "Authorization": "token " + token})
        self.assert200(r.status_code)

    def create_upload_file(self, host, token, file_name, data):
        temp = BytesIO()
        temp.write(data.encode(encoding="utf-8"))
        temp.seek(0)
        temp.name = 'temp.txt'
        upload_file_url = "/api/v1/files/upload/" + file_name
        r = requests.post(host + upload_file_url,
                          data=temp,
                          headers=self.upload_header(token))
        self.assert200(r.status_code)
        rt = r.json()
        self.assertEqual(rt["_status"], "OK")

    def upsert_collection(self, host, token, col_name, doc):
        r = requests.post(host + '/api/v1/db/create_collection',
                          json={
                              "collection": col_name
                          },
                          headers=self.auth_header(token))
        self.assert200(r.status_code)

        r = requests.post(host + '/api/v1/db/insert_one',
                          json={
                              "collection": col_name,
                              "document": doc,
                          },
                          headers=self.auth_header(token))
        self.assert200(r.status_code)

    def add_vault_data(self, host, token):
        doc = dict()
        for i in range(1, 10):
            doc["work" + str(i)] = "work_content" + str(i)
            self.upsert_collection(host, token, "works", doc)
        self.create_upload_file(host, token, "test0.txt", "this is a test 0 file")
        self.create_upload_file(host, token, "f1/test1.txt", "this is a test 1 file")
        self.create_upload_file(host, token, "f1/test1_2.txt", "this is a test 1_2 file")
        self.create_upload_file(host, token, "f2/f1/test2.txt", "this is a test 2 file")
        self.create_upload_file(host, token, "f2/f1/test2_2.txt", "this is a test 2_2 file")

    def check_vault_data(self, host, token):
        r = requests.post(host + '/api/v1/db/find_many',
                          json={
                              "collection": "works"
                          },
                          headers=self.auth_header(token))
        self.assert200(r.status_code)
        print(r.json())

        r1 = requests.get(host + '/api/v1/files/list/folder',
                          headers=self.auth_header(token))
        self.assert200(r1.status_code)
        print(r1.json())

    def clean_vault_data(self, host, token):
        r = requests.post(host + '/api/v1/db/delete_collection',
                          json={
                              "collection": "works"
                          },
                          headers=self.auth_header(token))
        self.assert200(r.status_code)
        r = requests.post(host + '/api/v1/db/find_many',
                          json={
                              "collection": "works"
                          },
                          headers=self.auth_header(token))
        self.assertEqual(NOT_FOUND, r.status_code)

        r = requests.post(host + '/api/v1/files/delete',
                          json={
                              "path": "/"
                          },
                          headers=self.auth_header(token))
        self.assert200(r.status_code)
        r = requests.post(host + '/api/v1/files/list/folder', headers=self.auth_header(token))
        self.assertEqual(NOT_FOUND, r.status_code)

    def save_to_backup(self, host, token, vc_json):
        r = requests.post(host + '/api/v1/backup/save_to_node',
                          json={
                              "backup_credential": vc_json,
                          },
                          headers=self.auth_header(token))
        self.assert200(r.status_code)

        for i in range(0, 3):
            r1 = requests.get(host + '/api/v1/backup/state',
                              headers=self.auth_header(token))
            self.assert200(r1.status_code)
            rt = r1.json()
            if rt["hive_backup_state"] != "stop":
                time.sleep(2)
            else:
                self.assertEqual(rt["result"], "success")
                return

        self.assertTrue(False)

    def restore_from_backup(self, host, token, vc_json):
        r = requests.post(host + '/api/v1/backup/restore_from_node',
                          json={
                              "backup_credential": vc_json,
                          },
                          headers=self.auth_header(token))
        self.assert200(r.status_code)

    def active_backup_vault(self, host, token):
        r = requests.post(host + '/api/v1/backup/activate_to_vault',
                          json={
                          },
                          headers=self.auth_header(token))
        self.assert200(r.status_code)

    def test_1_save_restore_hive_node(self):
        self.init_vault_service(self.host1, self.token1)
        self.add_vault_data(self.host1, self.token1)
        self.check_vault_data(self.host1, self.token1)

        self.init_backup_service(self.host2, self.token2)

        vc = self.user_did.issue_backup_auth(self.hive_did1, self.docker_host2, self.hive_did2)
        vc_json = ffi.string(lib.Credential_ToString(vc, True)).decode()

        self.save_to_backup(self.host1, self.token1, vc_json)

        self.clean_vault_data(self.host1, self.token1)
        self.restore_from_backup(self.host1, self.token1, vc_json)
        self.check_vault_data(self.host1, self.token1)

        # active test
        self.init_vault_service(self.host2, self.token2)
        self.active_backup_vault(self.host2, self.token2)
        self.check_vault_data(self.host2, self.token2)

# -*- coding: utf-8 -*-

"""
Testing file for the ipfs-backup module.
"""
import unittest

from tests import init_test, test_log
from tests.utils.http_client import HttpClient


class IpfsBackupTestCase(unittest.TestCase):
    def __init__(self, method_name='runTest'):
        super().__init__(method_name)
        init_test()
        self.cli = HttpClient(f'/api/v2')
        self.backup_cli = HttpClient(f'/api/v2', is_backup_node=True)

    @classmethod
    def setUpClass(cls):
        # subscribe the vault
        HttpClient(f'/api/v2').put('/subscription/vault')

    def test01_subscribe(self):
        response = self.backup_cli.put('/subscription/backup')
        self.assertIn(response.status_code, [200, 455])

    def test02_get_info(self):
        response = self.backup_cli.get('/subscription/backup')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(isinstance(response.json(), dict))
        test_log(f'backup info: {response.json()}')

    def test03_backup_invalid_parameter(self):
        r = self.cli.post('/vault/content?to=hive_node')
        self.assertEqual(r.status_code, 400)

    @unittest.skip
    def test03_backup_force(self):
        r = self.cli.post('/vault/content?to=hive_node&is_force=true',
                          body={'credential': self.cli.get_backup_credential()})
        self.assertEqual(r.status_code, 201)

    def test04_state(self):
        r = self.cli.get('/vault/content')
        self.assertEqual(r.status_code, 200)

    def test05_restore_invalid_parameter(self):
        r = self.cli.post('/vault/content?from=hive_node')
        self.assertEqual(r.status_code, 400)

    @unittest.skip
    def test05_restore_force(self):
        r = self.cli.post('/vault/content?from=hive_node&is_force=true',
                          body={'credential': self.cli.get_backup_credential()})
        self.assertEqual(r.status_code, 201)

    @unittest.skip
    def test06_promotion(self):
        # PREPARE: backup and remove the vault for local test.
        self.backup_cli.delete('/subscription/vault')
        # do promotion.
        r = self.backup_cli.post('/backup/promotion')
        self.assertEqual(r.status_code, 201)
        # check the vault state.
        response = self.backup_cli.get('/subscription/vault')
        self.assertEqual(response.status_code, 200)

    def test07_unsubscribe(self):
        response = self.backup_cli.delete('/subscription/backup')
        self.assertEqual(response.status_code, 204)
        self.backup_cli.delete('/subscription/vault')


if __name__ == '__main__':
    unittest.main()

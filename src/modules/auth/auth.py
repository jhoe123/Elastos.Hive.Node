# -*- coding: utf-8 -*-

"""
Entrance of the subscription module.
"""
import json
import logging
import os
from datetime import datetime

from src import hive_setting
from src.modules.auth.user import UserManager
from src.modules.database.mongodb_client import MongodbClient
from src.utils.http_request import RequestData
from src.utils_v1.constants import APP_INSTANCE_DID, DID_INFO_NONCE_EXPIRED, DID_INFO_REGISTER_COL, DID_INFO_NONCE
from src.utils.did.did_wrapper import Credential, DIDDocument, DID, JWT, Presentation
from src.utils.did.entity import Entity
from src.utils_v1.did_info import create_nonce, get_auth_info_by_nonce, update_token_of_did_info
from src.utils.http_client import HttpClient
from src.utils.http_exception import InvalidParameterException, BadRequestException

from src.utils.consts import URL_SIGN_IN, URL_BACKUP_AUTH, URL_V2
from src.utils.singleton import Singleton


class Auth(Entity, metaclass=Singleton):
    def __init__(self):
        Entity.__init__(self, "hive.auth", passphrase=hive_setting.PASSPHRASE, storepass=hive_setting.PASSWORD,
                        from_file=True, file_content=hive_setting.SERVICE_DID)
        self.http = HttpClient()
        self.mcli = MongodbClient()
        self.user_manager = UserManager()
        logging.info(f'Service DID V2: {self.get_did_string()}')

    def sign_in(self, doc: dict):
        app_instance_did = self.__get_app_instance_did(doc)
        return {
            "challenge": self.__create_challenge(app_instance_did, *self.__save_nonce_to_db(str(app_instance_did)))
        }

    def __get_app_instance_did(self, app_instance_doc: dict) -> DID:
        """ save did to cache and return DID object """
        doc_str = json.dumps(app_instance_doc)
        doc = DIDDocument.from_json(doc_str)
        if not doc.is_valid():
            raise BadRequestException(msg='The did document is invalid in getting app instance did.')
        did = doc.get_subject()

        # INFO: save application instance did document to /localdids folder
        spec_str = did.get_method_specific_id()
        try:
            with open(hive_setting.DID_DATA_LOCAL_DIDS + os.sep + spec_str, "w") as f:
                f.write(doc_str)
                f.flush()
        except Exception as e:
            raise BadRequestException(msg='Failed to cache application instance DID document.')

        return did

    def __save_nonce_to_db(self, app_instance_did: str):
        """ return nonce and 3 minutes expire time """
        nonce, expire_time = create_nonce(), int(datetime.now().timestamp()) + hive_setting.AUTH_CHALLENGE_EXPIRED
        try:
            filter_ = {APP_INSTANCE_DID: app_instance_did}
            update = {
                '$set': {  # for update and insert
                    DID_INFO_NONCE: nonce,
                    DID_INFO_NONCE_EXPIRED: expire_time
                }
            }
            col = self.mcli.get_management_collection(DID_INFO_REGISTER_COL)
            col.update_one(filter_, update, contains_extra=False, upsert=True)
        except Exception as e:
            logging.getLogger("HiveAuth").error(f"Exception in __save_nonce_to_db: {e}")
            raise BadRequestException(msg=f'Failed to generate nonce: {e}')
        return nonce, expire_time

    def __create_challenge(self, app_instance_did: DID, nonce: str, expire_time):
        """ Create challenge for sign in response with 3 minutes expire time. """
        return super().create_jwt_token('DIDAuthChallenge', str(app_instance_did), expire_time, 'nonce', nonce, claim_json=False)

    def auth(self, challenge_response):
        info = self.__get_info_from_challenge_response(challenge_response, ['appDid', ])

        props = {k: v for k, v in info.items() if k in ['userDid', 'appDid', 'nonce']}
        access_token = super().create_jwt_token('AccessToken', info["id"], info["expTime"], 'props', json.dumps(props), claim_json=False)

        try:
            update_token_of_did_info(info["userDid"], info["appDid"], info["id"], info["nonce"], access_token, info["expTime"])
        except Exception as e:
            # update to temporary auth collection, so failed can skip
            logging.info(f'Update access token to auth collection failed: {e}')

        # @deprecated auth_register is just a temporary collection, need keep relation here
        self.user_manager.add_app_if_not_exists(info["userDid"], info["appDid"])

        return {
            "token": access_token,
        }

    def __get_info_from_challenge_response(self, challenge_response, props: list):
        jwt: JWT = JWT.parse(challenge_response)

        # presentation check

        vp_str = jwt.get_claim_as_json('presentation')
        presentation: Presentation = Presentation.from_json(vp_str)
        if not presentation.is_valid():
            raise BadRequestException(msg=f'The presentation is invalid')

        if presentation.get_credential_count() < 1:
            raise BadRequestException(msg=f'No presentation credential exists')

        realm = presentation.get_realm()
        if realm != super().get_did_string():
            raise BadRequestException(msg=f'Invalid presentation realm or not match.')

        # presentation check nonce

        auth_info = get_auth_info_by_nonce(presentation.get_nonce())
        if not auth_info:
            raise BadRequestException(msg='Can not get presentation nonce information from database.')

        if auth_info[DID_INFO_NONCE_EXPIRED] < int(datetime.now().timestamp()):
            raise BadRequestException(msg='The nonce expired.')

        # credential check

        # vp = json.loads(vp_str)
        vp = RequestData(**json.loads(vp_str))
        vcs = vp.get('verifiableCredential', list)
        if not vcs or not vcs[0] or not isinstance(vcs[0], dict):
            raise BadRequestException(msg="'verifiableCredential' is invalid")

        credential = Credential.from_json(json.dumps(vcs[0]))
        if not credential.is_valid():
            raise BadRequestException(msg="First 'verifiableCredential' item is invalid'")
        exp_time = credential.get_expiration_date()
        issuer: DID = credential.get_issuer()

        # get the info from credential

        info = RequestData(**vcs[0]).get('credentialSubject', dict)
        if info.get('id', str) != auth_info[APP_INSTANCE_DID]:  # application instance did for user, service did for vault node
            raise BadRequestException(msg='Credentials "id" MUST be application instance DID')

        for key in props:
            info.validate(key, str)

        info["userDid"] = str(issuer)
        # min(7 days, credential expire time)
        info["expTime"] = min(int(datetime.now().timestamp()) + hive_setting.ACCESS_TOKEN_EXPIRED, exp_time)
        info["nonce"] = auth_info[DID_INFO_NONCE]

        return info

    def backup_auth(self, challenge_response):
        """ for the vault service node """
        info = self.__get_info_from_challenge_response(challenge_response, ['sourceDID', 'targetHost', 'targetDID'])

        props = {k: v for k, v in info.items() if k in ['sourceDID', 'targetHost', 'targetDID', 'userDid', 'nonce']}
        access_token = super().create_jwt_token('BackupToken', info["id"], info["expTime"], 'props', json.dumps(props), claim_json=False)

        return {
            'token': access_token
        }

    def get_backup_credential_info(self, credential):
        """ for vault /backup client to get the information from the backup credential """
        credential_info, err = self.__get_credential_info(credential, ["targetHost", "targetDID"])
        if credential_info is None:
            raise InvalidParameterException(msg=f'Failed to get credential info: {err}')
        return credential_info

    def backup_client_sign_in(self, host_url, credential: str, subject: str):
        """ for vault /backup & /restore, call /signin to the backup server

        :return challenge_response, backup_service_instance_did
        """
        vc = Credential.from_json(credential)
        doc: dict = json.loads(self.get_doc().to_json())
        body = self.http.post(host_url + URL_V2 + URL_SIGN_IN, None, {"id": doc})
        if 'challenge' not in body or not body["challenge"]:
            raise InvalidParameterException(msg='backup_sign_in: failed to sign in to backup node.')

        jwt: JWT = JWT.parse(body["challenge"])
        audience = jwt.get_audience()
        if audience != self.get_did_string():
            raise InvalidParameterException(msg=f'backup_sign_in: failed to get the audience of the challenge.')

        nonce, issuer = jwt.get_claim('nonce'), jwt.get_issuer()
        vp_json = self.create_presentation_str(vc, nonce, issuer)
        expire = int(datetime.now().timestamp()) + hive_setting.AUTH_CHALLENGE_EXPIRED
        challenge_response = self.create_vp_token(vp_json, subject, issuer, expire)
        if challenge_response is None:
            raise InvalidParameterException(msg=f'backup_sign_in: failed to create the challenge response.')
        return challenge_response, issuer

    def backup_client_auth(self, host_url, challenge_response, backup_service_instance_did):
        """ for vault /backup & /restore, call /backup_auth to the backup server

        :return backup access token
        """
        body = self.http.post(host_url + URL_V2 + URL_BACKUP_AUTH, None, {"challenge_response": challenge_response})
        if 'token' not in body or not body["token"]:
            raise InvalidParameterException(msg='backup_auth: failed to backup auth to backup node.')

        jwt = JWT.parse(body["token"])
        audience = jwt.get_audience()
        if audience != self.get_did_string():
            raise InvalidParameterException(msg=f'backup_auth: failed to get the audience of the challenge.')

        issuer = jwt.get_issuer()
        if issuer != backup_service_instance_did:
            raise InvalidParameterException(msg=f'backup_auth: failed to get the issuer of the challenge.')

        return body["token"]

    def create_proof_for_order(self, user_did, props: dict, exp: int):
        """ Only for payment proof creation """
        return super().create_jwt_token('Hive Payment', user_did, exp, 'order', json.dumps(props))

    def get_proof_info(self, proof, user_did):
        """ Only for payment to parse not-empty proof and return info """
        if not proof:
            raise BadRequestException(msg=f"Invalid proof {proof} from contract.")

        jwt = JWT.parse(proof)

        if jwt.get_issuer() != self.get_did_string() \
                or jwt.get_audience() != user_did \
                or jwt.get_subject() != 'Hive Payment':
            raise BadRequestException(msg=f"Invalid proof {proof} from contract: invalid issuer or audience or subject")

        return json.loads(jwt.get_claim_as_json('order'))

    def create_receipt_proof_for_order(self, user_did, props: dict):
        """ Only for payment receipt proof creation """
        return super().create_jwt_token('Hive Receipt', user_did, None, 'receipt', json.dumps(props))

    def get_ownership_presentation(self, credential: str):
        vc = Credential.from_json(credential)
        vp_json = self.create_presentation_str(vc, create_nonce(), super().get_did_string())
        return json.loads(vp_json)

    def __get_credential_info(self, vc_str, props: list):
        """
        :return: (dict, str)
        """
        vc: Credential = Credential.from_json(vc_str)
        if not vc.is_valid():
            return None, 'credential is invalid.'

        vc_json = json.loads(vc_str)
        if "credentialSubject" not in vc_json:
            return None, "The credentialSubject isn't exist."
        credential_subject = vc_json["credentialSubject"]

        if "id" not in credential_subject:
            return None, "The credentialSubject's id isn't exist."

        if 'sourceDID' not in props:
            props.append('sourceDID')

        for prop in props:
            if prop not in credential_subject:
                return None, "The credentialSubject's '" + prop + "' isn't exist."

        if credential_subject['sourceDID'] != super().get_did_string():
            return None, f'The sourceDID({credential_subject["sourceDID"]}) is not the hive node did.'

        if "issuer" not in vc_json:
            return None, "The credential issuer isn't exist."
        credential_subject["userDid"] = vc_json["issuer"]

        expire, exp = vc.get_expiration_date(), int(datetime.now().timestamp()) + hive_setting.ACCESS_TOKEN_EXPIRED
        if expire > exp:
            expire = exp

        credential_subject["expTime"] = expire
        return credential_subject, None


# INFO: create singleton object.
_auth = Auth()

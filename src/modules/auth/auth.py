# -*- coding: utf-8 -*-

"""
Entrance of the subscription module.
"""
import json
import logging
import os
from datetime import datetime

from hive.util.did.eladid import ffi, lib

from hive.util.constants import APP_INSTANCE_DID, DID_INFO_NONCE_EXPIRED
from hive.util.did.entity import Entity
from hive.util.did_info import create_nonce, get_did_info_by_app_instance_did, add_did_nonce_to_db, \
    update_did_info_by_app_instance_did, get_did_info_by_nonce, update_token_of_did_info
from hive.main import view

from src.utils.http_response import hive_restful_response, BadRequestException, InvalidParameterException
from src.view import URL_DID_SIGN_IN, URL_DID_BACKUP_AUTH


class Auth(Entity):
    def __init__(self, app, hive_setting):
        self.app = app
        self.hive_setting = hive_setting
        self.storepass = hive_setting.DID_STOREPASS
        Entity.__init__(self, "hive.auth", mnemonic=hive_setting.DID_MNEMONIC, passphrase=hive_setting.DID_PASSPHRASE)

    @hive_restful_response
    def sign_in(self, doc):
        if not doc:
            raise BadRequestException(msg='Invalid parameter')

        app_instance_did = self.__get_app_instance_did(doc)
        return {
            "challenge": self.__create_challenge(app_instance_did, *self.__save_nonce_to_db(app_instance_did))
        }

    def __get_app_instance_did(self, app_instance_doc):
        doc_str = json.dumps(app_instance_doc)
        app_instance_doc = lib.DIDDocument_FromJson(doc_str.encode())
        if not app_instance_doc or not lib.DIDDocument_IsValid(app_instance_doc):
            raise BadRequestException(msg='The did document is invalid in getting app instance did.')

        did = lib.DIDDocument_GetSubject(app_instance_doc)
        if not did:
            raise BadRequestException(msg='Can not get did from document in getting app instance did.')

        spec_did_str = ffi.string(lib.DID_GetMethodSpecificId(did)).decode()
        try:
            with open(self.hive_setting.DID_DATA_LOCAL_DIDS + os.sep + spec_did_str, "w") as f:
                f.write(doc_str)
        except Exception as e:
            logging.getLogger("HiveAuth").error(f"Exception in sign_in:{str(e)} in getting app instance did")

        return "did:" + ffi.string(lib.DID_GetMethod(did)).decode() + ":" + spec_did_str

    def __save_nonce_to_db(self, app_instance_did):
        nonce, expire_time = create_nonce(), int(datetime.now().timestamp()) + self.hive_setting.AUTH_CHALLENGE_EXPIRED
        try:
            if not get_did_info_by_app_instance_did(app_instance_did):
                add_did_nonce_to_db(app_instance_did, nonce, expire_time)
            else:
                update_did_info_by_app_instance_did(app_instance_did, nonce, expire_time)
        except Exception as e:
            logging.getLogger("HiveAuth").error(f"Exception in __save_nonce_to_db: {e}")
            raise e
        return nonce, expire_time

    def __create_challenge(self, did, nonce, expire_time):
        """
        Create challenge for sign in response.
        """
        builder = lib.DIDDocument_GetJwtBuilder(self.doc)  # service instance doc
        if not builder:
            raise BadRequestException(msg='Can not get challenge builder.')
        lib.JWTBuilder_SetHeader(builder, "type".encode(), "JWT".encode())
        lib.JWTBuilder_SetHeader(builder, "version".encode(), "1.0".encode())
        lib.JWTBuilder_SetSubject(builder, "DIDAuthChallenge".encode())
        lib.JWTBuilder_SetAudience(builder, did.encode())
        lib.JWTBuilder_SetClaim(builder, "nonce".encode(), nonce.encode())
        lib.JWTBuilder_SetExpiration(builder, expire_time)
        lib.JWTBuilder_Sign(builder, ffi.NULL, self.storepass)
        token = lib.JWTBuilder_Compact(builder)
        lib.JWTBuilder_Destroy(builder)
        if not token:
            raise BadRequestException(msg="Failed to create challenge token.")
        return ffi.string(token).decode()

    @hive_restful_response
    def auth(self, challenge_response):
        if not challenge_response:
            raise BadRequestException(msg='Invalid parameter')

        credential_info = self.__get_auth_info_from_challenge_response(challenge_response, ['appDid', ])
        access_token = self.__create_access_token(credential_info, "AccessToken")

        try:
            update_token_of_did_info(credential_info["userDid"],
                                     credential_info["appDid"],
                                     credential_info["id"],
                                     credential_info["nonce"],
                                     access_token,
                                     credential_info["expTime"])
        except Exception as e:
            logging.error(f"Exception in __save_auth_info_to_db:: {e}")
            raise e

        return {
            "token": access_token,
        }

    def __get_auth_info_from_challenge_response(self, challenge_response, props=None):
        presentation_json, nonce, nonce_info = self.__get_values_from_challenge_response(challenge_response)
        if nonce_info[DID_INFO_NONCE_EXPIRED] < int(datetime.now().timestamp()):
            raise BadRequestException(msg='The nonce expired.')
        credential_info = self.__get_presentation_credential_info(presentation_json, props)
        if credential_info["id"] != nonce_info[APP_INSTANCE_DID]:
            raise BadRequestException(msg='The app instance did of the credential does not match.')
        credential_info["nonce"] = nonce
        return credential_info

    def __get_values_from_challenge_response(self, challenge_response):
        challenge_response_cstr = lib.DefaultJWSParser_Parse(challenge_response.encode())
        if not challenge_response_cstr:
            raise BadRequestException(msg='Invalid challenge response.')

        presentation_cstr = lib.JWT_GetClaimAsJson(challenge_response_cstr, "presentation".encode())
        lib.JWT_Destroy(challenge_response_cstr)
        if not presentation_cstr:
            raise BadRequestException(msg='Can not get presentation cstr.')
        presentation = lib.Presentation_FromJson(presentation_cstr)
        if not presentation or not lib.Presentation_IsValid(presentation):
            raise BadRequestException(msg='The presentation is invalid.')
        if lib.Presentation_GetCredentialCount(presentation) < 1:
            raise BadRequestException(msg='No presentation credential exists.')

        self.__validate_presentation_realm(presentation)
        nonce, nonce_info = self.__get_presentation_nonce(presentation)
        return json.loads(ffi.string(presentation_cstr).decode()), nonce, nonce_info

    def __get_presentation_nonce(self, presentation):
        nonce = lib.Presentation_GetNonce(presentation)
        if not nonce:
            raise BadRequestException(msg='Failed to get presentation nonce.')
        nonce_str = ffi.string(nonce).decode()
        if not nonce_str:
            raise BadRequestException(msg='Invalid presentation nonce.')
        nonce_info = get_did_info_by_nonce(nonce_str)
        if not nonce_info:
            raise BadRequestException(msg='Can not get presentation nonce information from database.')
        return nonce_str, nonce_info

    def __validate_presentation_realm(self, presentation):
        realm = lib.Presentation_GetRealm(presentation)
        if not realm:
            raise BadRequestException(msg='Can not get presentation realm.')
        realm = ffi.string(realm).decode()
        if not realm or realm != self.get_did_string():
            raise BadRequestException(msg='Invalid presentation realm or not match.')

    def __get_presentation_credential_info(self, presentation_json, props=None):
        if "verifiableCredential" not in presentation_json:
            raise BadRequestException(msg='Verifiable credentials do not exist.')

        vcs_json = presentation_json["verifiableCredential"]
        if not isinstance(vcs_json, list):
            raise BadRequestException(msg="Verifiable credentials are not the list.")

        vc_json = vcs_json[0]
        if not vc_json:
            raise BadRequestException(msg='The credential is invalid.')
        if "credentialSubject" not in vc_json or type(vc_json["credentialSubject"]) != dict\
                or "issuer" not in vc_json:
            raise BadRequestException('The credential subject is invalid or the issuer does not exist.')
        credential_info = vc_json["credentialSubject"]

        required_props = ['id', ]
        if props:
            required_props.extend(props)
        not_exist_props = list(filter(lambda p: p not in credential_info, required_props))
        if not_exist_props:
            raise BadRequestException(f"The credentialSubject's prop ({not_exist_props}) does not exists.")

        credential_info["expTime"] = self.__get_presentation_credential_expire_time(vcs_json)
        credential_info["userDid"] = vc_json["issuer"]
        return credential_info

    def __get_presentation_credential_expire_time(self, vcs_json):
        vc_str = json.dumps(vcs_json[0])
        if not vc_str:
            raise BadRequestException(msg='The presentation credential does not exist.')
        vc = lib.Credential_FromJson(vc_str.encode(), ffi.NULL)
        if not vc or not lib.Credential_IsValid(vc):
            raise BadRequestException(msg='The presentation credential is invalid.')
        exp_time = lib.Credential_GetExpirationDate(vc)
        if exp_time <= 0:
            raise BadRequestException("The credential's expiration date does not exist.")
        return min(int(datetime.now().timestamp()) + self.hive_setting.ACCESS_TOKEN_EXPIRED, exp_time)

    def __create_access_token(self, credential_info, subject):
        doc = lib.DIDStore_LoadDID(self.store, self.did)
        if not doc:
            raise BadRequestException('Can not load service instance document in creating access token.')

        builder = lib.DIDDocument_GetJwtBuilder(doc)
        if not builder:
            raise BadRequestException(msg='Can not get builder from doc in creating access token.')

        lib.JWTBuilder_SetHeader(builder, "typ".encode(), "JWT".encode())
        lib.JWTBuilder_SetHeader(builder, "version".encode(), "1.0".encode())
        lib.JWTBuilder_SetSubject(builder, subject.encode())
        lib.JWTBuilder_SetAudience(builder, credential_info["id"].encode())
        lib.JWTBuilder_SetExpiration(builder, credential_info["expTime"])

        props = {k: credential_info[k] for k in credential_info if k not in ['id', 'expTime']}
        if not lib.JWTBuilder_SetClaim(builder, "props".encode(), json.dumps(props).encode()):
            lib.JWTBuilder_Destroy(builder)
            raise BadRequestException(msg='Can not set claim in creating access token.')

        lib.JWTBuilder_Sign(builder, ffi.NULL, self.storepass)
        token = lib.JWTBuilder_Compact(builder)
        lib.JWTBuilder_Destroy(builder)
        if not token:
            raise BadRequestException(msg='Can not build token in creating access token.')

        return ffi.string(token).decode()

    @hive_restful_response
    def backup_auth(self, challenge_response):
        credential_info = self.__get_auth_info_from_challenge_response(challenge_response, ["targetHost", "targetDID"])
        access_token = self.__create_access_token(credential_info, "BackupToken")
        return {'token': access_token}

    def get_error_message(self, prompt=None):
        """ helper method to get error message from did.so """
        err_message = ffi.string(lib.DIDError_GetMessage()).decode()
        return err_message if not prompt else f'[{prompt}] {err_message}'

    def get_backup_credential_info(self, credential):
        """ for vault /backup """
        if not credential:
            raise InvalidParameterException()
        credential_info, err = view.h_auth.get_credential_info(credential, ["targetHost", "targetDID"])
        if credential_info is None:
            raise InvalidParameterException(msg=err)
        return credential_info

    def backup_client_sign_in(self, host_url, credential, subject):
        """
        for vault /backup & /restore
        :return challenge_response, backup_service_instance_did
        """
        vc = lib.Credential_FromJson(credential.encode(), ffi.NULL)
        if not vc:
            raise InvalidParameterException(msg='backup_sign_in: invalid credential.')

        doc_str = ffi.string(lib.DIDDocument_ToJson(lib.DIDStore_LoadDID(self.store, self.did), True)).decode()
        doc = json.loads(doc_str)
        rt, status_code, err = self.post(host_url + URL_DID_SIGN_IN, {"id": doc})
        if err or 'challenge' not in rt or not rt["challenge"]:
            raise InvalidParameterException(msg='backup_sign_in: failed to sign in to backup node.')

        jws = lib.DefaultJWSParser_Parse(rt["challenge"].encode())
        if not jws:
            raise InvalidParameterException(
                msg=f'backup_sign_in: failed to parse challenge with error {self.get_error_message()}.')

        aud = ffi.string(lib.JWT_GetAudience(jws)).decode()
        if aud != self.get_did_string():
            lib.JWT_Destroy(jws)
            raise InvalidParameterException(msg=f'backup_sign_in: failed to get the audience of the challenge.')

        nonce = ffi.string(lib.JWT_GetClaim(jws, "nonce".encode())).decode()
        if nonce is None:
            lib.JWT_Destroy(jws)
            raise InvalidParameterException(
                msg=f'backup_sign_in: failed to get the nonce of the challenge.')

        issuer = ffi.string(lib.JWT_GetIssuer(jws)).decode()
        lib.JWT_Destroy(jws)
        if issuer is None:
            raise InvalidParameterException(
                msg=f'backup_sign_in: failed to get the issuer of the challenge.')

        vp_json = self.create_presentation(vc, nonce, issuer)
        if vp_json is None:
            raise InvalidParameterException(
                msg=f'backup_sign_in: failed to create presentation.')
        challenge_response = self.create_vp_token(vp_json, subject, issuer, self.hive_setting.AUTH_CHALLENGE_EXPIRED)
        if challenge_response is None:
            raise InvalidParameterException(
                msg=f'backup_sign_in: failed to create the challenge response.')
        return challenge_response, issuer

    def backup_client_auth(self, host_url, challenge_response, backup_service_instance_did):
        """
        for vault /backup & /restore
        :return backup access token
        """
        rt, _, err = self.post(host_url + URL_DID_BACKUP_AUTH, {"challenge_response": challenge_response})
        if err or 'token' not in rt or not rt["backup_token"]:
            raise InvalidParameterException(msg='backup_auth: failed to backup auth to backup node.')

        jws = lib.DefaultJWSParser_Parse(rt["token"].encode())
        if not jws:
            raise InvalidParameterException(
                msg=f'backup_auth: failed to parse token with error {self.get_error_message()}.')

        audience = ffi.string(lib.JWT_GetAudience(jws)).decode()
        if audience != self.get_did_string():
            lib.JWT_Destroy(jws)
            raise InvalidParameterException(msg=f'backup_auth: failed to get the audience of the challenge.')

        issuer = ffi.string(lib.JWT_GetIssuer(jws)).decode()
        lib.JWT_Destroy(jws)
        if issuer != backup_service_instance_did:
            raise InvalidParameterException(msg=f'backup_auth: failed to get the issuer of the challenge.')

        return rt["backup_token"]

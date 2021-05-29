# -*- coding: utf-8 -*-

"""
The view of authentication module.
"""
from flask import Blueprint, request
from src.modules.auth.auth import Auth

from src.utils.http_response import BadRequestException

blueprint = Blueprint('auth', __name__)
auth: Auth = None


def init_app(app, hive_setting):
    """ This will be called by application initializer. """
    global auth
    auth = Auth(app, hive_setting)
    app.register_blueprint(blueprint)


@blueprint.route('/api/v2/did/signin', methods=['POST'])
def sign_in():
    json_data = request.get_json(force=True, silent=True)
    doc = json_data.get('id')
    if not doc:
        raise BadRequestException(msg='Invalid parameter')
    return auth.sign_in(doc)


@blueprint.route('/api/v2/did/auth', methods=['POST'])
def auth():
    json_data = request.get_json(force=True, silent=True)
    challenge = json_data.get('challenge_response')
    if not challenge:
        raise BadRequestException(msg='Invalid parameter')
    return auth.auth(challenge)
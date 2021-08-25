# -*- coding: utf-8 -*-

"""
About module to show some information of the node.
"""
from flask import Blueprint

from src.modules.about.about import About

blueprint = Blueprint('about', __name__)
about: About = None


def init_app(app, hive_setting):
    """ This will be called by application initializer. """
    global about
    about = About(app, hive_setting)
    app.register_blueprint(blueprint)


@blueprint.route('/api/v2/about/version', methods=['GET'])
def get_version():
    """ Get the version of hive node. No authentication is required.

    .. :quickref: 08 About; Get the Version

    **Request**:

    .. sourcecode:: http

        None

    **Response OK**:

    .. sourcecode:: http

        HTTP/1.1 200 OK

    .. code-block:: json

        {
            "major": 1,
            "minor": 0,
            "patch": 0
        }

    """
    return about.get_version()


@blueprint.route('/api/v2/about/commit_id', methods=['GET'])
def get_commit_id():
    """ Get the commit ID of hive node. No authentication is required.

    .. :quickref: 08 About; Get the Commit ID

    **Request**:

    .. sourcecode:: http

        None

    **Response OK**:

    .. sourcecode:: http

        HTTP/1.1 200 OK

    .. code-block:: json

        {
            "commit_id": "<commit_id>"
        }

    """
    return about.get_commit_id()
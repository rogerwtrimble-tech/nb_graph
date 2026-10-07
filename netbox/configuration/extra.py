####
## This file contains extra configuration options that can't be configured
## directly through environment variables.
####

## Specify one or more name and email address tuples representing NetBox administrators. These people will be notified of
## application errors (assuming correct email settings are provided).
# ADMINS = [
#     # ['John Doe', 'jdoe@example.com'],
# ]


## URL schemes that are allowed within links in NetBox
# ALLOWED_URL_SCHEMES = (
#     'file', 'ftp', 'ftps', 'http', 'https', 'irc', 'mailto', 'sftp', 'ssh', 'tel', 'telnet', 'tftp', 'vnc', 'xmpp',
# )

## Enable installed plugins. Add the name of each plugin to the list.
# from netbox.configuration.configuration import PLUGINS
# PLUGINS.append('my_plugin')

## Plugins configuration settings. These settings are used by various plugins that the user may have installed.
## Each key in the dictionary is the name of an installed plugin and its value is a dictionary of settings.
# from netbox.configuration.configuration import PLUGINS_CONFIG
# PLUGINS_CONFIG['my_plugin'] = {
#   'foo': 'bar',
#   'buzz': 'bazz'
# }


## Remote authentication support
# REMOTE_AUTH_DEFAULT_PERMISSIONS = {}


## By default uploaded media is stored on the local filesystem. Using Django-storages is also supported. Provide the
## class path of the storage driver and any configuration options in STORAGES. For example:
# STORAGES = {
#     'default': {
#         'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
#         'OPTIONS': {
#             'access_key': 'Key ID',
#             'secret_key': 'Secret',
#             'bucket_name': 'netbox',
#             'region_name': 'us-west-1',
#         }
#     },
#     'staticfiles': {
#         'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
#     }
# }


## This file can contain arbitrary Python code, e.g.:
# from datetime import datetime
# now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
# BANNER_TOP = f'<marquee width="200px">This instance started on {now}.</marquee>'


####
## nb_graph: single sign-on to NetBox's own UI through the same OIDC provider the nb_graph UI uses.
## Off unless NETBOX_SSO=oidc (see docs/auth.md). Local username/password login keeps working for admins.
####
from os import environ as _env

if _env.get('NETBOX_SSO', 'none').lower() == 'oidc':
    REMOTE_AUTH_BACKEND = ['social_core.backends.open_id_connect.OpenIdConnectAuth']
    # SOCIAL_AUTH_OIDC_OIDC_ENDPOINT / _KEY / _SECRET come from the environment (configuration.py).
    # The endpoint is the issuer as NetBox reaches it (e.g. http://keycloak:8080/realms/nbgraph); the expected
    # "iss" is the issuer as browsers see it, which can differ inside a compose network or cluster.
    SOCIAL_AUTH_OIDC_SCOPE = ['openid', 'profile', 'email']
    if _env.get('NETBOX_SSO_ISSUER'):
        SOCIAL_AUTH_OIDC_ID_TOKEN_ISSUER = _env['NETBOX_SSO_ISSUER']
    SOCIAL_AUTH_BACKEND_ATTRS = {'oidc': (_env.get('NETBOX_SSO_LABEL', 'Single sign-on'), 'login')}
    SOCIAL_AUTH_PIPELINE = (
        'social_core.pipeline.social_auth.social_details',
        'social_core.pipeline.social_auth.social_uid',
        'nbgraph_sso.pipeline.require_group',           # not in an nb_graph group -> refused, no account created
        'social_core.pipeline.social_auth.social_user',
        'nbgraph_sso.pipeline.link_existing_user',      # reuse the account graph-api created; never a superuser
        'social_core.pipeline.user.get_username',
        'social_core.pipeline.user.create_user',
        'social_core.pipeline.social_auth.associate_user',
        'nbgraph_sso.pipeline.sync_groups',             # IdP groups -> NetBox groups (NBGRAPH_OIDC_GROUPS)
        'social_core.pipeline.social_auth.load_extra_data',
        'social_core.pipeline.user.user_details',
    )

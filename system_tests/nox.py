# Copyright 2016 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Noxfile for automating system tests.

This file handles setting up environments needed by the system tests. This
separates the tests from their environment configuration.

See the `nox docs`_ for details on how this file works:

.. _nox docs: http://nox.readthedocs.io/en/latest/
"""

import os
import subprocess

from nox.command import which
import py.path


HERE = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(HERE, 'data')
SERVICE_ACCOUNT_FILE = os.path.join(DATA_DIR, 'service_account.json')
AUTHORIZED_USER_FILE = os.path.join(DATA_DIR, 'authorized_user.json')
EXPLICIT_CREDENTIALS_ENV = 'GOOGLE_APPLICATION_CREDENTIALS'
EXPLICIT_PROJECT_ENV = 'GOOGLE_CLOUD_PROJECT'
EXPECT_PROJECT_ENV = 'EXPECT_PROJECT_ID'

SKIP_GAE_TEST_ENV = 'SKIP_APP_ENGINE_SYSTEM_TEST'
GAE_APP_URL_TMPL = 'https://{}-dot-{}.appspot.com'
GAE_TEST_APP_SERVICE = 'google-auth-system-tests'

# The download location for the Cloud SDK
CLOUD_SDK_DIST_FILENAME = 'google-cloud-sdk.tar.gz'
CLOUD_SDK_DOWNLOAD_URL = (
    'https://dl.google.com/dl/cloudsdk/release/{}'.format(
        CLOUD_SDK_DIST_FILENAME))

# This environment variable is recognized by the Cloud SDK and overrides
# the location of the SDK's configuration files (which is usually at
# ${HOME}/.config).
CLOUD_SDK_CONFIG_ENV = 'CLOUDSDK_CONFIG'

# If set, this is where the environment setup will install the Cloud SDK.
# If unset, it will download the SDK to a temporary directory.
CLOUD_SDK_ROOT = os.environ.get('CLOUD_SDK_ROOT')

if CLOUD_SDK_ROOT is not None:
    CLOUD_SDK_ROOT = py.path.local(CLOUD_SDK_ROOT)
    CLOUD_SDK_ROOT.ensure(dir=True)  # Makes sure the directory exists.
else:
    CLOUD_SDK_ROOT = py.path.local.mkdtemp()

# The full path the cloud sdk install directory
CLOUD_SDK_INSTALL_DIR = CLOUD_SDK_ROOT.join('google-cloud-sdk')

# The full path to the gcloud cli executable.
GCLOUD = str(CLOUD_SDK_INSTALL_DIR.join('bin', 'gcloud'))

# gcloud requires Python 2 and doesn't work on 3, so we need to tell it
# where to find 2 when we're running in a 3 environment.
CLOUD_SDK_PYTHON_ENV = 'CLOUDSDK_PYTHON'
CLOUD_SDK_PYTHON = which('python2', None)

# Cloud SDK helpers


def install_cloud_sdk(session):
    """Downloads and installs the Google Cloud SDK."""
    # Configure environment variables needed by the SDK.
    # This sets the config root to the tests' config root. This prevents
    # our tests from clobbering a developer's configuration when running
    # these tests locally.
    session.env[CLOUD_SDK_CONFIG_ENV] = str(CLOUD_SDK_ROOT)
    # This tells gcloud which Python interpreter to use (always use 2.7)
    session.env[CLOUD_SDK_PYTHON_ENV] = CLOUD_SDK_PYTHON

    # If gcloud cli executable already exists, we don't need to do anything
    # else.
    # Note that because of this we do not attempt to update the sdk -
    # if the CLOUD_SDK_ROOT is cached, it will need to be periodically cleared.
    if py.path.local(GCLOUD).exists():
        return

    tar_path = CLOUD_SDK_ROOT.join(CLOUD_SDK_DIST_FILENAME)

    # Download the release.
    session.run(
        'wget', CLOUD_SDK_DOWNLOAD_URL, '-O', str(tar_path), silent=True)

    # Extract the release.
    session.run(
        'tar', 'xzf', str(tar_path), '-C', str(CLOUD_SDK_ROOT))
    session.run(tar_path.remove)

    # Run the install script.
    session.run(
        str(CLOUD_SDK_INSTALL_DIR.join('install.sh')),
        '--usage-reporting', 'false',
        '--path-update', 'false',
        '--command-completion', 'false',
        silent=True)


def copy_credentials(credentials_path):
    """Copies credentials into the SDK root as the application default
    credentials."""
    dest = CLOUD_SDK_ROOT.join('application_default_credentials.json')
    if dest.exists():
        dest.remove()
    py.path.local(credentials_path).copy(dest)


def configure_cloud_sdk(
        session, application_default_credentials, project=False):
    """Installs and configures the Cloud SDK with the given application default
    credentials.

    If project is True, then a project will be set in the active config.
    If it is false, this will ensure no project is set.
    """
    install_cloud_sdk(session)

    if project:
        session.run(GCLOUD, 'config', 'set', 'project', 'example-project')
    else:
        session.run(GCLOUD, 'config', 'unset', 'project')

    # Copy the credentials file to the config root. This is needed because
    # unfortunately gcloud doesn't provide a clean way to tell it to use
    # a particular set of credentials. However, this does verify that gcloud
    # also considers the credentials valid by calling application-default
    # print-access-token
    session.run(copy_credentials, application_default_credentials)

    # Calling this forces the Cloud SDK to read the credentials we just wrote
    # and obtain a new access token with those credentials. This validates
    # that our credentials matches the format expected by gcloud.
    # Silent is set to True to prevent leaking secrets in test logs.
    session.run(
        GCLOUD, 'auth', 'application-default', 'print-access-token',
        silent=True)


# Test sesssions


def session_service_account(session):
    session.virtualenv = False
    session.run('pytest', 'test_service_account.py')


def session_oauth2_credentials(session):
    session.virtualenv = False
    session.run('pytest', 'test_oauth2_credentials.py')


def session_default_explicit_service_account(session):
    session.virtualenv = False
    session.env[EXPLICIT_CREDENTIALS_ENV] = SERVICE_ACCOUNT_FILE
    session.env[EXPECT_PROJECT_ENV] = '1'
    session.run('pytest', 'test_default.py')


def session_default_explicit_authorized_user(session):
    session.virtualenv = False
    session.env[EXPLICIT_CREDENTIALS_ENV] = AUTHORIZED_USER_FILE
    session.run('pytest', 'test_default.py')


def session_default_explicit_authorized_user_explicit_project(session):
    session.virtualenv = False
    session.env[EXPLICIT_CREDENTIALS_ENV] = AUTHORIZED_USER_FILE
    session.env[EXPLICIT_PROJECT_ENV] = 'example-project'
    session.env[EXPECT_PROJECT_ENV] = '1'
    session.run('pytest', 'test_default.py')


def session_default_cloud_sdk_service_account(session):
    session.virtualenv = False
    configure_cloud_sdk(session, SERVICE_ACCOUNT_FILE)
    session.env[EXPECT_PROJECT_ENV] = '1'
    session.run('pytest', 'test_default.py')


def session_default_cloud_sdk_authorized_user(session):
    session.virtualenv = False
    configure_cloud_sdk(session, AUTHORIZED_USER_FILE)
    session.run('pytest', 'test_default.py')


def session_default_cloud_sdk_authorized_user_configured_project(session):
    session.virtualenv = False
    configure_cloud_sdk(session, AUTHORIZED_USER_FILE, project=True)
    session.env[EXPECT_PROJECT_ENV] = '1'
    session.run('pytest', 'test_default.py')


def session_compute_engine(session):
    session.virtualenv = False
    session.run('pytest', 'test_compute_engine.py')


def session_app_engine(session):
    session.virtualenv = False

    if SKIP_GAE_TEST_ENV in os.environ:
        session.log('Skipping App Engine tests.')
        return

    # Unlike the default tests above, the App Engine system test require a
    # 'real' gcloud sdk installation that is configured to deploy to an
    # app engine project.
    # Grab the project ID from the cloud sdk.
    project_id = subprocess.check_output([
        'gcloud', 'config', 'list', 'project', '--format',
        'value(core.project)']).decode('utf-8').strip()

    if not project_id:
        session.error(
            'The Cloud SDK must be installed and configured to deploy to App '
            'Engine.')

    application_url = GAE_APP_URL_TMPL.format(
        GAE_TEST_APP_SERVICE, project_id)

    # Vendor in the test application's dependencies
    session.chdir(os.path.join(HERE, 'app_engine_test_app'))
    session.run(
        'pip', 'install', '--target', 'lib', '-r', 'requirements.txt',
        silent=True)

    # Deploy the application.
    session.run('gcloud', 'app', 'deploy', '-q', 'app.yaml')

    # Run the tests
    session.env['TEST_APP_URL'] = application_url
    session.chdir(HERE)
    session.run('pytest', 'test_app_engine.py')


def session_grpc(session):
    session.virtualenv = False
    session.env[EXPLICIT_CREDENTIALS_ENV] = SERVICE_ACCOUNT_FILE
    session.run('pytest', 'test_grpc.py')

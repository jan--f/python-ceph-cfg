# Import Python Libs
from __future__ import absolute_import
import logging
import os
import shutil
import tempfile
import os.path

# Local imports
from . import utils
from . import constants
from . import util_which


log = logging.getLogger(__name__)


class Error(Exception):
    """
    Error
    """

    def __str__(self):
        doc = self.__doc__.strip()
        return ': '.join([doc] + [str(a) for a in self.args])

def _get_path_keyring_admin(cluster_name):
    return '/etc/ceph/%s.client.admin.keyring' % (cluster_name)

def _get_path_keyring_mon(cluster_name, host_name):
    return os.path.join(constants._path_ceph_lib_mon, '%s-%s/keyring' % (cluster_name, host_name))

def _get_path_keyring_mon_bootstrap(cluster_name, host_name):
    return os.path.join(constants._path_ceph_lib, 'bootstrap-mon/%s-%s.keyring' % (cluster_name, host_name))


def _get_path_keyring_osd(cluster_name):
    return os.path.join(constants._path_ceph_lib, 'bootstrap-osd/%s.keyring' % (cluster_name))

def _get_path_keyring_mds(cluster_name):
    return os.path.join(constants._path_ceph_lib, 'bootstrap-mds/%s.keyring' % (cluster_name))


def _get_path_keyring_rgw(cluster_name):
    return os.path.join(constants._path_ceph_lib, 'bootstrap-rgw/%s.keyring' % (cluster_name))


def _keying_read(key_path):
    output = ""
    with open(key_path, 'r') as infile:
        output = infile.read()
    return output

def _keying_write(key_path,content):
    dirname = os.path.dirname(key_path)
    if not os.path.isdir(dirname):
        os.makedirs(dirname)
    with open(key_path, 'w') as infile:
        for line in content.split('\n'):
            stripped = line.strip()
            if len(stripped) == 0:
                continue
            if stripped[0] == '[':
                infile.write('%s\n' % (stripped))
                continue
            infile.write('\t%s\n' % (stripped))
    return


def Property(func):
    return property(**func())




class keyring_implementation_base(object):
    def __init__(self, mdl):
        self.model = mdl


    def invoke_ceph_authtool(self, keyring_name, keyring_path, caps, secret=None, extra_args=[]):
        """create arguments for invoking the ceph authtool, this simplifies most of
        the ways that ceph authtool could be invoked.

        Args:
            keyring_name: The name of keyring to be created
            keyring_path: path where keyring is to be created
            caps: A dictionary containing various k-v pairs of components and their respective auth
                  permission eg:
                  {'mon':'allow *'}
            secret: The base64 secret to create keyring from, if this is set we will use this secret
                    instead to create the keyring, otherwise authtool itself will generate one
            extra_args: any other extra arguments to be passed to ceph authtool"""

        args=[
            util_which.which_ceph_authtool.path,
            "-n", keyring_name,
            "--create-keyring", keyring_path
            ]

        if secret:
            args += ["--add-key", secret.strip()]
        else:
            args.append("--gen-key")

        args += extra_args

        for component,permission in caps.items():
            args += ["--cap", component, permission]
        return args


    def present(self):
        """
        Is keyring present
        """
        keyring_path = self.get_path_keyring()
        if os.path.isfile(keyring_path):
            return True
        return False


    def create(self, secret = None):
        """
        Create keyring
        """
        keyring_path = self.get_path_keyring()
        if os.path.isfile(keyring_path):
            return _keying_read(keyring_path)
        try:
            tmpd = tempfile.mkdtemp()
            key_path = os.path.join(tmpd,"keyring")
            arguments = self.get_arguments_create(key_path, secret)
            cmd_out = utils.execute_local_command(arguments)
            if cmd_out["retcode"] != 0:
                raise Error("Failed executing '%s' Error rc=%s, stdout=%s stderr=%s" % (
                    " ".join(arguments),
                    cmd_out["retcode"],
                    cmd_out["stdout"],
                    cmd_out["stderr"])
                    )
            output = _keying_read(key_path)
        finally:
            shutil.rmtree(tmpd)
        return output


    def write_content(self, key_content):
        """
        Persist keyring
        """
        keyring_path = self.get_path_keyring()
        if os.path.isfile(keyring_path):
            return True
        _keying_write(keyring_path, key_content)
        return True


    def write_secret(self, secret):
        """
        Persist keyring
        """
        keyring_path = self.get_path_keyring()
        if os.path.isfile(keyring_path):
            return True
        if secret is None:
            raise Error("Keyring secret is invalid")
        keyring_dir = os.path.dirname(keyring_path)
        if not os.path.isdir(keyring_dir):
            os.makedirs(keyring_dir)
        arguments = self.get_arguments_create(keyring_path, secret)
        cmd_out = utils.execute_local_command(arguments)
        if cmd_out["retcode"] != 0:
            raise Error("Failed executing '%s' Error rc=%s, stdout=%s stderr=%s" % (
                " ".join(arguments),
                cmd_out["retcode"],
                cmd_out["stdout"],
                cmd_out["stderr"])
                )
        return True


    def remove(self):
        """
        Delete keyring
        """
        keyring_path = self.get_path_keyring()
        if os.path.isfile(keyring_path):
            log.info("Removing:%s" % (keyring_path))
            try:
                os.remove(keyring_path)
            except OSError:
                raise Error("Keyring could not be deleted")
        return True


class keyring_implementation_admin(keyring_implementation_base):
    def __init__(self, mdl):
        keyring_implementation_base.__init__(self, mdl)
        self.keyring_name = "client.admin"
        self.caps = {"mon":"allow *", "osd":"allow *", "mds":"allow *"}

    def get_path_keyring(self):
        return _get_path_keyring_admin(self.model.cluster_name)

    def get_arguments_create(self, path, secret=None):
        extra_args=[]
        if self.model.ceph_version.major == 0:
            if self.model.ceph_version.minor < 95:
                extra_args+=["--set-uid=0"]
        return self.invoke_ceph_authtool(self.keyring_name, path, self.caps, secret=secret, extra_args=extra_args)

class keyring_implementation_mon(keyring_implementation_base):
    def __init__(self, mdl):
        keyring_implementation_base.__init__(self, mdl)
        self.keyring_name = "mon."
        self.caps = {"mon": "allow *"}

    def get_path_keyring(self):
        if self.model.cluster_name is None:
            raise  Error("Cluster name not found")
        if self.model.hostname is None:
            raise  Error("hostname not found")
        return _get_path_keyring_mon_bootstrap(self.model.cluster_name,
                self.model.hostname)

    def get_arguments_create(self, path, secret=None):
        return self.invoke_ceph_authtool(self.keyring_name, path, self.caps, secret=secret)


class keyring_implementation_osd(keyring_implementation_base):
    def __init__(self, mdl):
        keyring_implementation_base.__init__(self, mdl)
        self.keyring_name = "client.bootstrap-osd"
        self.caps = {"mon": "allow profile bootstrap-osd"}

    def get_path_keyring(self):
        if self.model.cluster_name is None:
            raise  Error("Cluster name not found")
        return _get_path_keyring_osd(self.model.cluster_name)

    def get_arguments_create(self, path, secret=None):
        return self.invoke_ceph_authtool(self.keyring_name, path, self.caps, secret=secret)

class keyring_implementation_rgw(keyring_implementation_base):
    def __init__(self, mdl):
        keyring_implementation_base.__init__(self, mdl)
        self.keyring_name = "client.bootstrap-rgw"
        self.caps = {"mon": "allow profile bootstrap-rgw"}

    def get_path_keyring(self):
        if self.model.cluster_name is None:
            raise  Error("Cluster name not found")
        return _get_path_keyring_rgw(self.model.cluster_name)


    def get_arguments_create(self, path, secret=None):
        return self.invoke_ceph_authtool(self.keyring_name, path, self.caps, secret=secret)


class keyring_implementation_mds(keyring_implementation_base):
    def __init__(self, mdl):
        keyring_implementation_base.__init__(self, mdl)
        self.keyring_name = "client.bootstrap-mds"
        self.caps = {"mon": "allow profile bootstrap-mds"}

    def get_path_keyring(self):
        if self.model.cluster_name is None:
            raise  Error("Cluster name not found")
        return _get_path_keyring_mds(self.model.cluster_name)

    def get_arguments_create(self, path, secret=None):
        return self.invoke_ceph_authtool(self.keyring_name, path, self.caps, secret=secret)


class keyring_facard(object):
    def __init__(self, mdl):
        self.model = mdl
        self._availableKeys = set(["admin", "mds", "mon", "osd", "rgw"])
        self._clear_implementation()


    def _clear_implementation(self):
        self._keyType = None
        self._keyImp = None


    @Property
    def key_type():
        doc = "key_type"

        def fget(self):
            return self._keyType


        def fset(self, name):
            if name is None:
                self._clear_implementation()
            if not name in self._availableKeys:
                self._clear_implementation()
                raise ValueError("Invalid key_type with value:%s" % (name))
            implementation = None
            if name == "admin":
                implementation = keyring_implementation_admin(self.model)
            if name == "mds":
                implementation = keyring_implementation_mds(self.model)
            if name == "mon":
                implementation = keyring_implementation_mon(self.model)
            if name == "osd":
                implementation = keyring_implementation_osd(self.model)
            if name == "rgw":
                implementation = keyring_implementation_rgw(self.model)
            if implementation is None:
                self._clear_implementation()
                raise ValueError("Programming error for key_type with value:%s" % (name))
            try:
                implementation.get_path_keyring()
            except (Error) as err:
                self._clear_implementation()
                raise err
            self._keyImp = implementation
            self._keyType = name
            return self._keyType


        def fdel(self):
            self._clear_implementation()


        return locals()


    def present(self):
        """
        Create keyring
        """
        if self._keyImp is None:
            raise Error("Programming error: key type unset")
        return self._keyImp.present()


    def create(self, secret = None):
        """
        Create keyring
        """
        if self._keyImp is None:
            raise Error("Programming error: key type unset")
        return self._keyImp.create(secret)


    def write_content(self, key_content):
        """
        Persist keyring
        """
        if self._keyImp is None:
            raise Error("Programming error: key type unset")
        return self._keyImp.write_content(key_content)


    def write_secret(self, secret):
        """
        Persist keyring
        """
        if self._keyImp is None:
            raise Error("Programming error: key type unset")
        return self._keyImp.write_secret(secret)


    def remove(self):
        """
        Remove keyring
        """
        if self._keyImp is None:
            raise Error("Programming error: key type unset")
        return self._keyImp.remove()


    def keyring_path_get(self):
        """
        Get keyring path
        """
        if self._keyImp is None:
            raise Error("Programming error: key type unset")
        return self._keyImp.get_path_keyring()


    def keyring_identity_get(self):
        """
        Get keyring path
        """
        if self._keyImp is None:
            raise Error("Programming error: key type unset")
        return self._keyImp.keyring_name

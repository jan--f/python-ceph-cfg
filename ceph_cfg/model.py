# Import Python Libs
from __future__ import absolute_import

# local modules
from . util_configparser import ConfigParserCeph as ConfigParser


class version(object):
    def __init__(self, **kwargs):
        self.major = kwargs.get("major")
        self.minor = kwargs.get("minor")
        self.revision = kwargs.get("revision")
        self.uuid = kwargs.get("uuid")


    def __repr__(self):
        if self.major is None:
            return "<version(None)>"
        if self.minor is None:
            return "<version(%s)>" % (self.major)
        if self.revision is None:
            return "<version(%s,%s)>" % (self.major, self.minor)
        if self.uuid is None:
            return "<version(%s,%s,%s)>" % (self.major, self.minor, self.revision)
        return "<version(%s,%s,%s,%s)>" % (self.major, self.minor, self.revision, self.uuid)


class connection(object):
    def __init__(self, **kwargs):
        self.keyring_type = kwargs.get("keyring_type")
        self.keyring_path = kwargs.get("keyring_path")
        self.keyring_identity = kwargs.get("keyring_identity")


class model(object):
    """
    Basic model class to store detrived data
    """
    def __init__(self, **kwargs):
        # map device to symlinks
        self.symlinks = {}
        # Discovered partions with lsblk
        self.lsblk = {}
        # Discovered partions with parted
        self.parted = {}
        # map partition to pairent
        self.part_pairent = {}
        self.partitions_osd = {}
        self.partitions_journal = {}
        self.ceph_conf = ConfigParser()
        # list of (hostname,addr) touples
        self.mon_members = []
        self.hostname = None
        self.kargs_apply(**kwargs)
        self.ceph_version = version()
        self.lsblk_version = version()
        # Result of local query of mon status
        self.mon_status = None
        # Remote connection details
        self.connection = connection()


    def kargs_apply(self, **kwargs):
        self.cluster_name = kwargs.get("cluster_name")
        self.cluster_uuid = kwargs.get("cluster_uuid")

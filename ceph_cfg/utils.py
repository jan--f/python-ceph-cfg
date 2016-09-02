# Import Python Libs
from __future__ import absolute_import
import logging
import os
import base64
import binascii

# local modules
from . util_configparser import ConfigParserCeph as ConfigParser

__has_salt = True

try:
    import salt.client
    import salt.config # noqa
except :
    __has_salt = False

log = logging.getLogger(__name__)


class Error(Exception):
    """
    Error
    """

    def __str__(self):
        doc = self.__doc__.strip()
        return ': '.join([doc] + [str(a) for a in self.args])


def _quote_arguments_with_space(argument):
    if " " in argument:
        return "'" + argument + "'"
    return argument


def execute_local_command(command_attrib_list):
    log.info("executing " + " ".join(map(_quote_arguments_with_space, command_attrib_list)))
    if '__salt__' in locals():
        return __salt__['cmd.run_all'](command_attrib_list, python_shell=False) # noqa

    # if we cant exute subprocess with salt, use python
    import subprocess
    output= {}
    proc=subprocess.Popen(command_attrib_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
    output['stdout'], output['stderr'] = proc.communicate()

    output['retcode'] = proc.returncode
    return output





def _get_cluster_uuid_from_name(cluster_name):
    configfile = "/etc/ceph/%s.conf" % (cluster_name)
    if not os.path.isfile(configfile):
        raise Error("Cluster confg file does not exist:'%s'" % configfile)
    config = ConfigParser()
    config.read(configfile)
    try:
        fsid = config.get("global","fsid")
    except ConfigParser.NoOptionError:
        raise Error("Cluster confg file does not sewt fsid:'%s'" % configfile)
    return fsid

def _get_cluster_name_from_uuid(cluster_uuid):
    output = None
    dir_content = os.listdir("/etc/ceph/")
    for file_name in dir_content:
        if file_name[-5:] != ".conf":
            continue
        fullpath = os.path.join("/etc/ceph/", file_name)
        config = ConfigParser()
        config.read(fullpath)
        try:
            fsid = config.get("global","fsid")
            if fsid is not None:
                output = file_name[:-5]
        except:
            continue
    return output

def is_valid_base64(s):
    try:
        base64.decodestring(s)
    except binascii.Error:
        raise Error("invalid base64 string supplied %s" % s)

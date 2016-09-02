# Import Python Libs
from __future__ import absolute_import
import logging
import os
import os.path

# local modules
from . import constants
from . import utils
from . import mdl_updater
from . import keyring
from . import util_which

log = logging.getLogger(__name__)

class Error(Exception):
    """
    Error
    """

    def __str__(self):
        doc = self.__doc__.strip()
        return ': '.join([doc] + [str(a) for a in self.args])


def service_shutdown_ceph():
    arguments = [
            util_which.which_systemctl.path,
            "stop",
            "ceph*",
            ]
    output = utils.execute_local_command(arguments)
    if output["retcode"] != 0:
        raise Error("Failed executing '%s' Error rc=%s, stdout=%s stderr=%s" % (
            " ".join(arguments),
            output["retcode"],
            output["stdout"],
            output["stderr"]
            ))




class purger(object):
    def __init__(self, mdl):
        self.model = mdl


    def auth_remove(self):
        keyobj = keyring.keyring_facard(self.model)
        for keytype in ["mds", "rgw", "osd", "mon", "admin"]:
            try:
                keyobj.key_type = keytype
            except (ValueError) as err:
                log.warning(err)
                continue
            if keyobj.present() is False:
                log.info("Already removed '%s' keyring" % (keytype))
                continue
            log.info("Removing '%s' keyring" % (keytype))
            keyobj.remove()


    def unmount_osd(self):
        for part in self.model.partitions_osd:
            disk = self.model.part_pairent.get(part)
            if disk is None:
                continue
            disk_details = self.model.lsblk.get(disk)
            if disk_details is None:
                continue
            all_parts = disk_details.get('PARTITION')
            if all_parts is None:
                continue
            part_details = all_parts.get(part)
            if part_details is None:
                continue
            mountpoint =  part_details.get("MOUNTPOINT")
            if mountpoint is None:
                continue
            arguments = [
                "umount",
                mountpoint
                ]
            output = utils.execute_local_command(arguments)
            if output["retcode"] != 0:
                raise Error("Failed executing '%s' Error rc=%s, stdout=%s stderr=%s" % (
                    " ".join(arguments),
                    output["retcode"],
                    output["stdout"],
                    output["stderr"]
                    ))


    def param_list_file(self,base_path):
        output = []
        for root, dirs, files in os.walk(base_path, topdown=True):
            for name in files:
                touple = (root,name)
                output.append(touple)
        return output

    def param_list_dir(self,base_path):
        output = []
        for root, dirs, files in os.walk(base_path, topdown=True):
            for name in dirs:
                touple = (root,name)
                output.append(touple)
        return output

    def param_list_empty(self,base_path):
        output = os.listdir(base_path)
        if len(output) > 0:
            return False
        return True


    def remove_config(self):
        if self.model.cluster_name == None:
            return
        cluster_conf = "/etc/ceph/%s.conf" % (self.model.cluster_name)
        if not os.path.isfile(cluster_conf):
            log.debug("no file found:%s" % (str(cluster_conf)))
            return
        log.debug("removing file:%s" % (str(cluster_conf)))
        os.remove(cluster_conf)

    def remove_file(self, file_data):
        path = file_data[0]
        name = file_data[1]
        fullpath = os.path.join(path, name)
        log.debug("removing file:%s" % (str(fullpath)))
        os.remove(fullpath)

    def remove_dir(self, dir_data):
        path = dir_data[0]
        name = dir_data[1]
        fullpath = os.path.join(path, name)
        empty = self.param_list_empty(fullpath)
        if empty == False:
            log.debug("dir not empty:%s" % (str(fullpath)))
            return
        if not os.path.isdir(fullpath):
            log.debug("path:%s" % (str(path)))
            log.debug("name:%s" % (str(name)))
            log.debug("not a dir:%s" % (str(fullpath)))
            return
        log.info("removing dir:%s" % (str(fullpath)))
        os.rmdir(fullpath)


    def list_files(self):
        for file_data in self.param_list_file(constants._path_ceph_lib_mds):
            log.debug("mds_f:%s" % (str(file_data)))
            self.remove_file(file_data)

        for file_data in self.param_list_file(constants._path_ceph_lib_rgw):
            log.debug("rgw_f:%s" % (str(file_data)))
            self.remove_file(file_data)

        for file_data in self.param_list_file(constants._path_ceph_lib_osd):
            self.remove_file(file_data)

        for file_data in self.param_list_file(constants._path_ceph_lib_mon):
            self.remove_file(file_data)

        for dir_data in self.param_list_dir(constants._path_ceph_lib_mds):
            self.remove_dir(dir_data)

        for dir_data in self.param_list_dir(constants._path_ceph_lib_rgw):
            self.remove_dir(dir_data)

        for dir_data in self.param_list_dir(constants._path_ceph_lib_osd):
            self.remove_dir(dir_data)

        for dir_data in self.param_list_dir(constants._path_ceph_lib_mon):
            self.remove_dir(dir_data)


def purge(mdl, **kwargs):
    """
    purge ceph configuration on the node
    """
    service_shutdown_ceph()
    pur_ctrl = purger(mdl)
    updater = mdl_updater.model_updater(mdl)
    updater.hostname_refresh()
    try:
        updater.defaults_refresh()
    except (utils.Error) as err:
        log.error("exception self.updater.defaults_refresh()")
        log.error(err)
    if mdl.cluster_name == None:
        log.error("Cluster name not found")
    else:
        try:
            log.debug("Cluster name %s" % (mdl.cluster_name))
            updater.load_confg(mdl.cluster_name)
            updater.mon_members_refresh()
        except (mdl_updater.Error) as err:
            log.error(err)
    pur_ctrl.auth_remove()
    updater.symlinks_refresh()
    updater.partitions_all_refresh()
    try:
        updater.discover_partitions_refresh()
    except (utils.Error) as err:
        log.error("exception self.updater.defaults_refresh()")
        log.error(err)
    pur_ctrl.unmount_osd()
    pur_ctrl.list_files()
    pur_ctrl.remove_config()

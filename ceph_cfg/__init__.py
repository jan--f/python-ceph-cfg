import logging
import stat
import os.path
import os
import util_which
import subprocess

# local modules
import utils
import model
import mdl_updater
import presenter
import mdl_query
import osd
import mon
import rgw
import mds
import purger
import mdl_updater_remote
import keyring_use

log = logging.getLogger(__name__)


class Error(Exception):
    """
    Error
    """

    def __str__(self):
        doc = self.__doc__.strip()
        return ': '.join([doc] + [str(a) for a in self.args])


def partition_list():
    '''
    List partitions by disk

    CLI Example:

        salt '*' sesceph.partitions_all
    '''
    m = model.model()
    u = mdl_updater.model_updater(m)
    u.symlinks_refresh()
    u.partitions_all_refresh()
    p = presenter.mdl_presentor(m)
    return p.partitions_all()

def partition_list_osd():
    '''
    List all OSD data partitions by partition

    CLI Example:

        salt '*' sesceph.partitions_osd
    '''
    m = model.model()
    u = mdl_updater.model_updater(m)
    u.symlinks_refresh()
    u.partitions_all_refresh()
    u.discover_partitions_refresh()
    p = presenter.mdl_presentor(m)
    return p.discover_osd_partitions()


def partition_list_journal():
    '''
    List all OSD journal partitions by partition

    CLI Example:

        salt '*' sesceph.partitions_journal
    '''
    m = model.model()
    u = mdl_updater.model_updater(m)
    u.symlinks_refresh()
    u.partitions_all_refresh()
    u.discover_partitions_refresh()
    p = presenter.mdl_presentor(m)
    return p.discover_journal_partitions()

def osd_discover():
    """
    List all OSD by cluster

    CLI Example:

        salt '*' sesceph.osd_discover

    """
    m = model.model()
    u = mdl_updater.model_updater(m)

    u.symlinks_refresh()
    u.partitions_all_refresh()
    u.discover_partitions_refresh()
    p = presenter.mdl_presentor(m)
    return p.discover_osd()


def partition_is(dev):
    """
    Check whether a given device path is a partition or a full disk.

    CLI Example:

    .. code-block:: bash
    salt '*' sesceph.partition_is /dev/sdc1

    """
    mdl = model.model()
    osdc = osd.osd_ctrl(mdl)
    return osdc.is_partition(dev)


def _update_partition(action, dev, description):
    # try to make sure the kernel refreshes the table.  note
    # that if this gets ebusy, we are probably racing with
    # udev because it already updated it.. ignore failure here.

    # On RHEL and CentOS distros, calling partprobe forces a reboot of the
    # server. Since we are not resizing partitons so we rely on calling
    # partx

    utils.execute_local_command(
        [
             util_which.which_partprobe.path,
             dev,
        ],
    )



def zap(dev = None, **kwargs):
    """
    Destroy the partition table and content of a given disk.
    """
    if dev is not None:
        log.warning("Depricated use of function, use kwargs")
    dev = kwargs.get("dev", dev)
    if dev == None:
        raise Error('Cannot find', dev)
    if not os.path.exists(dev):
        raise Error('Cannot find', dev)
    dmode = os.stat(dev).st_mode
    mdl = model.model(**kwargs)
    osdc = osd.osd_ctrl(mdl)
    if not stat.S_ISBLK(dmode) or osdc.is_partition(dev):
        raise Error('not full block device; cannot zap', dev)
    try:
        log.debug('Zapping partition table on %s', dev)

        # try to wipe out any GPT partition table backups.  sgdisk
        # isn't too thorough.
        lba_size = 4096
        size = 33 * lba_size
        with file(dev, 'wb') as dev_file:
            dev_file.seek(-size, os.SEEK_END)
            dev_file.write(size*'\0')

        utils.execute_local_command(
            [
                util_which.which_sgdisk.path,
                '--zap-all',
                '--',
                dev,
            ],
        )
        utils.execute_local_command(
            [
                util_which.which_sgdisk.path,
                '--clear',
                '--mbrtogpt',
                '--',
                dev,
            ],
        )


        _update_partition('-d', dev, 'zapped')
    except subprocess.CalledProcessError as e:
        raise Error(e)
    return True


def osd_prepare(**kwargs):
    """
    prepare an OSD

    CLI Example:

        salt '*' sesceph.osd_prepare 'osd_dev'='/dev/vdc' \\
                'journal_dev'='device' \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid' \\
                'osd_fs_type'='xfs' \\
                'osd_uuid'='2a143b73-6d85-4389-a9e9-b8a78d9e1e07' \\
                'journal_uuid'='4562a5db-ff6f-4268-811d-12fd4a09ae98'
    Notes:

    cluster_uuid
        Set the deivce to store the osd data on.

    journal_dev
        Set the journal device. defaults to osd_dev.

    cluster_name
        Set the cluster name. Defaults to "ceph".

    cluster_uuid
        Set the cluster date will be added too. Defaults to the value found in local config.

    osd_fs_type
        set the file system to store OSD data with. Defaults to "xfs".

    osd_uuid
        set the OSD data UUID. If set will return if OSD with data UUID already exists.

    journal_uuid
        set the OSD journal UUID. If set will return if OSD with journal UUID already exists.
    """
    return osd.osd_prepare(**kwargs)


def osd_activate(**kwargs):
    """
    Activate an OSD

    CLI Example:

        salt '*' sesceph.osd_activate 'osd_dev'='/dev/vdc'
    """
    return osd.osd_activate(**kwargs)


def keyring_create(**kwargs):
    """
    Create keyring for cluster

    CLI Example:

        salt '*' sesceph.keyring_create \\
                'keyring_type'='admin' \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    keyring_type
        Required paramter
        Can be set to:
            admin, mon, osd, rgw, mds

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    return keyring_use.keyring_create_type(**kwargs)


def keyring_save(**kwargs):
    """
    Create save keyring locally

    CLI Example:

        salt '*' sesceph.keyring_save \\
                'keyring_type'='admin' \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid' \\
                ''
    Notes:

    keyring_type
        Required paramter
        Can be set to:
            admin, mon, osd, rgw, mds

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    return keyring_use.keyring_save_type(**kwargs)


def keyring_purge(**kwargs):
    """
    Delete keyring for cluster

    CLI Example:

        salt '*' sesceph.keyring_purge \\
                'keyring_type'='admin' \\
                '[mds.]\n\tkey = AQA/vZ9WyDwsKRAAxQ6wjGJH6WV8fDJeyzxHrg==\n\tcaps mds = \"allow *\"\n' \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    keyring_type
        Required paramter
        Can be set to:
            admin, mon, osd, rgw, mds

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".

    If no ceph config file is found, this command will fail.
    """
    return keyring_use.keyring_purge_type(**kwargs)


def keyring_present(**kwargs):
    """
    Is keyring on disk

    CLI Example:

        salt '*' sesceph.keyring_mon_present \\
                'keyring_type'='admin' \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    keyring_type
    Required paramter
    Can be set to:
        admin, mon, osd, rgw, mds

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    return keyring_use.keyring_present_type(**kwargs)


def keyring_auth_add(**kwargs):
    """
    Add keyring to authorised list

    CLI Example:

        salt '*' sesceph.keyring_mon_present \\
                'keyring_type'='admin' \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    keyring_type
        Required paramter
        Can be set to:
            admin, mon, osd, rgw, mds

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    return keyring_use.keyring_auth_add_type(**kwargs)


def keyring_auth_del(**kwargs):
    """
    Remove keyring from authorised list

    CLI Example:

        salt '*' sesceph.keyring_osd_auth_del \\
                'keyring_type'='admin' \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    keyring_type
        Required paramter
        Can be set to:
            admin, mon, osd, rgw, mds

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    return keyring_use.keyring_auth_add_type(**kwargs)


def keyring_admin_create(**kwargs):
    """
    Create admin keyring for cluster

    CLI Example:

        salt '*' sesceph.keyring_admin_create \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    params = dict(kwargs)
    params["keyring_type"] = "admin"
    return keyring_create(**params)


def keyring_admin_save(key_content=None, **kwargs):
    """
    Write admin keyring for cluster

    CLI Example:

        salt '*' sesceph.keyring_admin_save \\
                '[mon.]\n\tkey = AQA/vZ9WyDwsKRAAxQ6wjGJH6WV8fDJeyzxHrg==\n\tcaps mon = \"allow *\"\n' \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    params = dict(kwargs)
    params["keyring_type"] = "admin"
    if key_content is None:
        return keyring_save(**params)
    log.warning("keyring_admin_save using legacy argument call")
    params["key_content"] = str(key_content)
    return keyring_save(**params)


def keyring_admin_purge(**kwargs):
    """
    Delete Mon keyring for cluster

    CLI Example:

        salt '*' sesceph.keyring_admin_purge \\
                '[mds.]\n\tkey = AQA/vZ9WyDwsKRAAxQ6wjGJH6WV8fDJeyzxHrg==\n\tcaps mds = \"allow *\"\n' \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".

    If no ceph config file is found, this command will fail.
    """
    params = dict(kwargs)
    params["keyring_type"] = "admin"
    return keyring_purge(**params)


def keyring_mon_create(**kwargs):
    """
    Create mon keyring for cluster

    CLI Example:

        salt '*' sesceph.keyring_mon_create \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    params = dict(kwargs)
    params["keyring_type"] = "mon"
    return keyring_create(**params)


def keyring_mon_save(key_content=None, **kwargs):
    """
    Write admin keyring for cluster

    CLI Example:

        salt '*' sesceph.keyring_mon_save \\
                '[mon.]\n\tkey = AQA/vZ9WyDwsKRAAxQ6wjGJH6WV8fDJeyzxHrg==\n\tcaps mon = \"allow *\"\n' \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    params = dict(kwargs)
    params["keyring_type"] = "mon"
    if key_content is None:
        return keyring_save(**params)
    log.warning("keyring_admin_save using legacy argument call")
    params["key_content"] = str(key_content)
    return keyring_save(**params)


def keyring_mon_purge(**kwargs):
    """
    Delete Mon keyring for cluster

    CLI Example:

        salt '*' sesceph.keyring_mon_purge \\
                '[mds.]\n\tkey = AQA/vZ9WyDwsKRAAxQ6wjGJH6WV8fDJeyzxHrg==\n\tcaps mds = \"allow *\"\n' \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".

    If no ceph config file is found, this command will fail.
    """
    params = dict(kwargs)
    params["keyring_type"] = "mon"
    return keyring_purge(**params)


def keyring_osd_create(**kwargs):
    """
    Create osd keyring for cluster

    CLI Example:

        salt '*' sesceph.keyring_osd_create \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    params = dict(kwargs)
    params["keyring_type"] = "osd"
    return keyring_create(**params)


def keyring_osd_save(key_content=None, **kwargs):
    """
    Write admin keyring for cluster

    CLI Example:

        salt '*' sesceph.keyring_osd_save \\
                '[osd.]\n\tkey = AQA/vZ9WyDwsKRAAxQ6wjGJH6WV8fDJeyzxHrg==\n\tcaps osd = \"allow *\"\n' \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    params = dict(kwargs)
    params["keyring_type"] = "osd"
    if key_content is None:
        return keyring_save(**params)
    log.warning("keyring_admin_save using legacy argument call")
    params["key_content"] = str(key_content)
    return keyring_save(**params)


def keyring_osd_auth_add(**kwargs):
    """
    Write admin keyring for cluster

    CLI Example:

        salt '*' sesceph.keyring_osd_auth_add \\
                '[osd.]\n\tkey = AQA/vZ9WyDwsKRAAxQ6wjGJH6WV8fDJeyzxHrg==\n\tcaps osd = \"allow *\"\n' \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    params = dict(kwargs)
    params["keyring_type"] = "osd"
    return keyring_auth_add(**params)


def keyring_osd_auth_del(**kwargs):
    """
    Write rgw keyring for cluster

    CLI Example:

        salt '*' sesceph.keyring_osd_auth_del \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    params = dict(kwargs)
    params["keyring_type"] = "osd"
    return keyring_auth_del(**params)


def keyring_osd_purge(**kwargs):
    """
    Write admin keyring for cluster

    CLI Example:

        salt '*' sesceph.keyring_osd_purge \\
                '[osd.]\n\tkey = AQA/vZ9WyDwsKRAAxQ6wjGJH6WV8fDJeyzxHrg==\n\tcaps osd = \"allow *\"\n' \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    params = dict(kwargs)
    params["keyring_type"] = "osd"
    return keyring_purge(**params)


def keyring_mds_create(**kwargs):
    """
    Create mds keyring for cluster

    CLI Example:

        salt '*' sesceph.keyring_mds_create \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    params = dict(kwargs)
    params["keyring_type"] = "mds"
    return keyring_create(**params)


def keyring_mds_save(key_content=None, **kwargs):
    """
    Write mds keyring for cluster

    CLI Example:

        salt '*' sesceph.keyring_mds_save \\
                '[mds.]\n\tkey = AQA/vZ9WyDwsKRAAxQ6wjGJH6WV8fDJeyzxHrg==\n\tcaps mds = \"allow *\"\n' \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".

    If the value is set, it will not be changed untill the keyring is deleted.
    """
    params = dict(kwargs)
    params["keyring_type"] = "mds"
    if key_content is None:
        return keyring_save(**params)
    log.warning("keyring_admin_save using legacy argument call")
    params["key_content"] = str(key_content)
    return keyring_save(**params)


def keyring_mds_auth_add(**kwargs):
    """
    Write mds keyring for cluster

    CLI Example:

        salt '*' sesceph.keyring_mds_auth_add \\
                '[mds.]\n\tkey = AQA/vZ9WyDwsKRAAxQ6wjGJH6WV8fDJeyzxHrg==\n\tcaps mds = \"allow *\"\n' \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    params = dict(kwargs)
    params["keyring_type"] = "mds"
    return keyring_auth_add(**params)


def keyring_mds_auth_del(**kwargs):
    """
    Write rgw keyring for cluster

    CLI Example:

        salt '*' sesceph.keyring_mds_auth_del \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    params = dict(kwargs)
    params["keyring_type"] = "mds"
    return keyring_auth_del(**params)


def keyring_mds_purge(**kwargs):
    """
    Delete MDS keyring for cluster

    CLI Example:

        salt '*' sesceph.keyring_mds_purge \\
                '[mds.]\n\tkey = AQA/vZ9WyDwsKRAAxQ6wjGJH6WV8fDJeyzxHrg==\n\tcaps mds = \"allow *\"\n' \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".

    If no ceph config file is found, this command will fail.
    """
    params = dict(kwargs)
    params["keyring_type"] = "mds"
    return keyring_purge(**params)


def keyring_rgw_create(**kwargs):
    """
    Create rgw keyring for cluster

    CLI Example:

        salt '*' sesceph.keyring_rgw_create \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    params = dict(kwargs)
    params["keyring_type"] = "rgw"
    return keyring_create(**params)


def keyring_rgw_save(key_content=None, **kwargs):
    """
    Write rgw keyring for cluster

    CLI Example:

        salt '*' sesceph.keyring_rgw_save \\
                '[rgw.]\n\tkey = AQA/vZ9WyDwsKRAAxQ6wjGJH6WV8fDJeyzxHrg==\n\tcaps rgw = \"allow *\"\n' \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".

    If the value is set, it will not be changed untill the keyring is deleted.
    """
    params = dict(kwargs)
    params["keyring_type"] = "rgw"
    if key_content is None:
        return keyring_save(**params)
    log.warning("keyring_admin_save using legacy argument call")
    params["key_content"] = str(key_content)
    return keyring_save(**params)


def keyring_rgw_auth_add(**kwargs):
    """
    Write rgw keyring for cluster

    CLI Example:

        salt '*' sesceph.keyring_rgw_auth_add \\
                '[rgw.]\n\tkey = AQA/vZ9WyDwsKRAAxQ6wjGJH6WV8fDJeyzxHrg==\n\tcaps rgw = \"allow *\"\n' \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    params = dict(kwargs)
    params["keyring_type"] = "rgw"
    return keyring_auth_add(**params)


def keyring_rgw_auth_del(**kwargs):
    """
    Write rgw keyring for cluster

    CLI Example:

        salt '*' sesceph.keyring_rgw_auth_del \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    params = dict(kwargs)
    params["keyring_type"] = "rgw"
    return keyring_auth_del(**params)


def keyring_rgw_purge(**kwargs):
    """
    Delete rgw keyring for cluster

    CLI Example:

        salt '*' sesceph.keyring_rgw_purge \\
                '[rgw.]\n\tkey = AQA/vZ9WyDwsKRAAxQ6wjGJH6WV8fDJeyzxHrg==\n\tcaps rgw = \"allow *\"\n' \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".

    If no ceph config file is found, this command will fail.
    """
    params = dict(kwargs)
    params["keyring_type"] = "rgw"
    return keyring_purge(**params)


def mon_is(**kwargs):
    """
    Is this a mon node

    CLI Example:

        salt '*' sesceph.mon_is \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_name
        Set the cluster name. Defaults to "ceph".

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.
    """
    ctrl_mon = mon.mon_facard(**kwargs)
    return ctrl_mon.is_mon()


def mon_status(**kwargs):
    """
    Get status from mon deamon

    CLI Example:

        salt '*' sesceph.mon_status \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    ctrl_mon = mon.mon_facard(**kwargs)
    return ctrl_mon.status()

def mon_quorum(**kwargs):
    """
    Is mon deamon in quorum

    CLI Example:

        salt '*' sesceph.mon_quorum \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    ctrl_mon = mon.mon_facard(**kwargs)
    return ctrl_mon.quorum()



def mon_active(**kwargs):
    """
    Is mon deamon running

    CLI Example:

        salt '*' sesceph.mon_active \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    ctrl_mon = mon.mon_facard(**kwargs)
    return ctrl_mon.active()


def mon_create(**kwargs):
    """
    Create a mon node

    CLI Example:

        salt '*' sesceph.mon_create \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    ctrl_mon = mon.mon_facard(**kwargs)
    return ctrl_mon.create()


def rgw_pools_create(**kwargs):
    """
    Create pools for rgw
    """
    ctrl_rgw = rgw.rgw_ctrl(**kwargs)
    ctrl_rgw.update()
    return ctrl_rgw.rgw_pools_create()

def rgw_pools_missing(**kwargs):
    """
    Show pools missing for rgw
    """
    ctrl_rgw = rgw.rgw_ctrl(**kwargs)
    ctrl_rgw.update()
    return ctrl_rgw.rgw_pools_missing()


def rgw_create(**kwargs):
    """
    Create a rgw
    """
    ctrl_rgw = rgw.rgw_ctrl(**kwargs)
    ctrl_rgw.update()
    return ctrl_rgw.create()


def rgw_destroy(**kwargs):
    """
    Remove a rgw
    """
    ctrl_rgw = rgw.rgw_ctrl(**kwargs)
    ctrl_rgw.update()
    return ctrl_rgw.destroy()



def mds_create(**kwargs):
    """
    Create a mds
    """
    ctrl_mds = mds.mds_ctrl(**kwargs)
    ctrl_mds.update()
    return ctrl_mds.create()


def mds_destroy(**kwargs):
    """
    Remove a mds
    """
    ctrl_mds = mds.mds_ctrl(**kwargs)
    ctrl_mds.update()
    return ctrl_mds.destroy()


def keyring_auth_list(**kwargs):
    """
    List all cephx authorization keys

    CLI Example:

        salt '*' sesceph.auth_list \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_name
        Set the cluster name. Defaults to "ceph".

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.
    """
    m = model.model(**kwargs)
    u = mdl_updater.model_updater(m)
    u.hostname_refresh()
    try:
        u.defaults_refresh()
    except:
        return {}
    u.load_confg(m.cluster_name)
    u.mon_members_refresh()
    mur = mdl_updater_remote.model_updater_remote(m)
    can_connect = mur.connect()
    if not can_connect:
        raise Error("Cant connect to cluster.")
    mur.auth_list()
    p = presenter.mdl_presentor(m)
    return p.auth_list()


def pool_list(**kwargs):
    """
    List all cephx authorization keys

    CLI Example:

        salt '*' sesceph.pool_list \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_name
        Set the cluster name. Defaults to "ceph".

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.
    """
    m = model.model(**kwargs)
    u = mdl_updater.model_updater(m)
    u.hostname_refresh()
    try:
        u.defaults_refresh()
    except:
        return {}
    u.load_confg(m.cluster_name)
    u.mon_members_refresh()
    mur = mdl_updater_remote.model_updater_remote(m)
    can_connect = mur.connect()
    if not can_connect:
        raise Error("Cant connect to cluster.")
    mur.pool_list()
    p = presenter.mdl_presentor(m)
    return p.pool_list()



def pool_add(pool_name, **kwargs):
    """
    List all cephx authorization keys

    CLI Example:

        salt '*' sesceph.pool_add pool_name \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_name
        Set the cluster name. Defaults to "ceph".

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    pg_num
        Default to 8

    pgp_num
        Default to pg_num

    pool_type
        can take values "replicated" or "erasure"

    erasure_code_profile
        Set the "erasure_code_profile"

    crush_ruleset
        Set the crush map rule set
    """
    m = model.model(**kwargs)
    u = mdl_updater.model_updater(m)
    u.hostname_refresh()
    u.defaults_refresh()
    u.load_confg(m.cluster_name)
    u.mon_members_refresh()
    mur = mdl_updater_remote.model_updater_remote(m)
    can_connect = mur.connect()
    if not can_connect:
        raise Error("Cant connect to cluster.")
    mur.pool_list()
    return mur.pool_add(pool_name, **kwargs)


def pool_del(pool_name, **kwargs):
    """
    List all cephx authorization keys

    CLI Example:

        salt '*' sesceph.pool_del pool_name \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:

    cluster_name
        Set the cluster name. Defaults to "ceph".

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.
    """
    m = model.model(**kwargs)
    u = mdl_updater.model_updater(m)
    u.hostname_refresh()
    u.defaults_refresh()
    u.load_confg(m.cluster_name)
    u.mon_members_refresh()
    mur = mdl_updater_remote.model_updater_remote(m)
    can_connect = mur.connect()
    if not can_connect:
        raise Error("Cant connect to cluster.")
    mur.pool_list()
    return mur.pool_del(pool_name)


def purge(**kwargs):
    """
    purge ceph configuration on the node

    CLI Example:

        salt '*' sesceph.purge
    """
    m = model.model(**kwargs)
    purger.purge(m, **kwargs)


def ceph_version():
    """
    Get the version of ceph installed
    """
    m = model.model()
    u = mdl_updater.model_updater(m)
    u.ceph_version_refresh()
    p = presenter.mdl_presentor(m)
    return p.ceph_version()


def cluster_quorum(**kwargs):
    """
    Get the cluster status

    CLI Example:

        salt '*' sesceph.cluster_status \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:
    Get the cluster quorum status.

    Scope:
    Cluster wide

    Arguments:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    m = model.model(**kwargs)
    u = mdl_updater.model_updater(m)
    u.hostname_refresh()
    u.defaults_refresh()
    u.load_confg(m.cluster_name)
    u.mon_members_refresh()
    mur = mdl_updater_remote.model_updater_remote(m)
    can_connect = mur.connect()
    if not can_connect:
        return False
    q = mdl_query.mdl_query(m)
    return q.cluster_quorum()


def cluster_status(**kwargs):
    """
    Get the cluster status

    CLI Example:

        salt '*' sesceph.cluster_status \\
                'cluster_name'='ceph' \\
                'cluster_uuid'='cluster_uuid'
    Notes:
    Get the cluster status including health if in quorum.

    Scope:
    Cluster wide

    Arguments:

    cluster_uuid
        Set the cluster UUID. Defaults to value found in ceph config file.

    cluster_name
        Set the cluster name. Defaults to "ceph".
    """
    m = model.model(**kwargs)
    u = mdl_updater.model_updater(m)
    u.hostname_refresh()
    u.defaults_refresh()
    u.load_confg(m.cluster_name)
    u.mon_members_refresh()
    mur = mdl_updater_remote.model_updater_remote(m)
    can_connect = mur.connect()
    if not can_connect:
        raise Error("Cant connect to cluster.")
    p = presenter.mdl_presentor(m)
    return p.cluster_status()


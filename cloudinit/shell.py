import os
import shutil
import subprocess

from StringIO import StringIO

from cloudinit import exceptions as excp
from cloudinit import log as logging

try:
    import selinux
    HAVE_LIBSELINUX = True
except ImportError:
    HAVE_LIBSELINUX = False


LOG = logging.getLogger(__name__)


class SeLinuxGuard(object):
    def __init__(self, path, recursive=False):
        self.path = path
        self.recursive = recursive
        self.engaged = False
        if HAVE_LIBSELINUX and selinux.is_selinux_enabled():
            self.engaged = True

    def __enter__(self):
        return self.engaged

    def __exit__(self, type, value, traceback):
        if self.engaged:
            LOG.debug("Disengaging selinux mode for %s: %s", self.path, self.recursive)
            selinux.restorecon(self.path, recursive=self.recursive)


def read_file(fname, read_cb=None):
    LOG.debug("Reading from %s", fname)
    with open(fname, 'rb') as fh:
        ofh = StringIO()
        pipe_in_out(fh, ofh, chunk_cb=read_cb)
        return ofh.getvalue()


def pipe_in_out(in_fh, out_fh, chunk_size=1024, chunk_cb=None):
    bytes_piped = 0
    LOG.debug("Transferring the contents of %s to %s in chunks of size %s.", in_fh, out_fh, chunk_size)
    while True:
        data = in_fh.read(chunk_size)
        if data == '':
            break
        else:
            out_fh.write(data)
            bytes_piped += len(data)
            if chunk_cb:
                chunk_cb(bytes_piped)
    out_fh.flush()
    return bytes_piped


def chownbyname(fname, user=None, group=None):
    uid = -1
    gid = -1
    if user == None and group == None:
        return
    if user:
        # TODO: why is this late imported
        import pwd
        uid = pwd.getpwnam(user).pw_uid
    if group:
        # TODO: why is this late imported
        import grp
        gid = grp.getgrnam(group).gr_gid

    os.chown(fname, uid, gid)


def ensure_dirs(dirlist, mode=0755):
    for d in dirlist:
        ensure_dir(d, mode)


def ensure_dir(path, mode=0755):
    if not os.path.isdir(path):
        fixmodes = []
        LOG.debug("Ensuring directory exists at path %s", dir_name)
        try:
            os.makedirs(path)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise e
        if mode is not None:
            os.chmod(path, mode)

def del_file(path):
    LOG.debug("Attempting to remove %s", path)
    os.unlink(path)


def ensure_file(path):
    if not os.path.isfile(path):
        write_file(path, content='')


def write_file(filename, content, mode=0644, omode="wb"):
    """
    Writes a file with the given content and sets the file mode as specified.
    Resotres the SELinux context if possible.

    @param filename: The full path of the file to write.
    @param content: The content to write to the file.
    @param mode: The filesystem mode to set on the file.
    @param omode: The open mode used when opening the file (r, rb, a, etc.)
    """
    try:
        os.makedirs(os.path.dirname(filename))
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise e

    LOG.debug("Writing to %s (%o) %s bytes", filename, mode, len(content))
    with open(filename, omode) as fh:
        with SeLinuxGuard(filename):
            fh.write(content)
            if mode is not None:
                os.chmod(filename, mode)

def delete_dir_contents(dirname):
    """
    Deletes all contents of a directory without deleting the directory itself.

    @param dirname: The directory whose contents should be deleted.
    """
    for node in os.listdir(dirname):
        node_fullpath = os.path.join(dirname, node)
        if os.path.isdir(node_fullpath):
            shutil.rmtree(node_fullpath)
        else:
            os.unlink(node_fullpath)


def subp(args, input_data=None, allowed_rc=None):
    if allowed_rc is None:
        allowed_rc = [0]
    try:
        sp = subprocess.Popen(args, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, stdin=subprocess.PIPE)
        (out, err) = sp.communicate(input_data)
    except OSError as e:
        raise excp.ProcessExecutionError(cmd=args, reason=e)
    rc = sp.returncode
    if rc not in allowed_rc:
        raise excp.ProcessExecutionError(stdout=out, stderr=err,
                                         exit_code=rc,
                                         cmd=args)
    # Just ensure blank instead of none??
    if not out:
        out = ''
    if not err:
        err = ''
    return (out, err)


# shellify, takes a list of commands
#  for each entry in the list
#    if it is an array, shell protect it (with single ticks)
#    if it is a string, do nothing
def shellify(cmdlist, add_header=True):
    content = ''
    if add_header:
        content += "#!/bin/sh\n"
    escaped = "%s%s%s%s" % ("'", '\\', "'", "'")
    for args in cmdlist:
        # if the item is a list, wrap all items in single tick
        # if its not, then just write it directly
        if isinstance(args, list):
            fixed = []
            for f in args:
                fixed.append("'%s'" % str(f).replace("'", escaped))
            content = "%s%s\n" % (content, ' '.join(fixed))
        else:
            content = "%s%s\n" % (content, str(args))
    return content

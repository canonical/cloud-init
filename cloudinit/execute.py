def run(list,cfg):
    import subprocess
    retcode = subprocess.call(list)

    if retcode == 0:
        return

    if retcode < 0:
        str="Cmd terminated by signal %s\n" % -retcode
    else:
        str="Cmd returned %s\n" % retcode
    str+=' '.join(list)
    raise Exception(str)

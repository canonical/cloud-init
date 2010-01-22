import yaml

def read_conf(fname):
	stream = file(fname)
	conf = yaml.load(stream)
	stream.close()
	return conf

def get_cfg_option_bool(yobj, key, default=False):
    if not yobj.has_key(key): return default
    val = yobj[key]
    if yobj[key] in [ True, '1', 'on', 'yes', 'true']:
        return True
    return False

def get_cfg_option_str(yobj, key, default=None):
    if not yobj.has_key(key): return default
    return yobj[key]

# merge values from src into cand.
# if src has a key, cand will not override
def mergedict(src,cand):
    if isinstance(src,dict) and isinstance(cand,dict):
        for k,v in cand.iteritems():
            if k not in src:
                src[k] = v
            else:
                src[k] = mergedict(src[k],v)
    return src

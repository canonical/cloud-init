#!/usr/bin/python
# largely taken from python examples
# http://docs.python.org/library/email-examples.html

import os
import sys
import smtplib
# For guessing MIME type based on file name extension
import mimetypes

from email import encoders
from email.message import Message
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from optparse import OptionParser
import gzip

COMMASPACE = ', '

starts_with_mappings={
    '#include' : 'text/x-include-url',
    '#!' : 'text/x-shellscript',
    '#cloud-config' : 'text/cloud-config',
    '#upstart-job'  : 'text/upstart-job',
    '#part-handler' : 'text/part-handler',
    '#cloud-boothook' : 'text/cloud-boothook'
}

def get_type(fname,deftype):
    f = file(fname,"rb")
    line = f.readline()
    f.close()
    rtype = deftype
    for str,mtype in starts_with_mappings.items():
        if line.startswith(str):
            rtype = mtype
            break
    return(rtype)

def main():
    outer = MIMEMultipart()
    #outer['Subject'] = 'Contents of directory %s' % os.path.abspath(directory)
    #outer['To'] = COMMASPACE.join(opts.recipients)
    #outer['From'] = opts.sender
    #outer.preamble = 'You will not see this in a MIME-aware mail reader.\n'

    parser = OptionParser()
    
    parser.add_option("-o", "--output", dest="output",
        help="write output to FILE [default %default]", metavar="FILE", 
        default="-")
    parser.add_option("-z", "--gzip", dest="compress", action="store_true",
        help="compress output", default=False)
    parser.add_option("-d", "--default", dest="deftype",
        help="default mime type [default %default]", default="text/plain")
    parser.add_option("--delim", dest="delim",
        help="delimiter [default %default]", default=":")

    (options, args) = parser.parse_args()

    if (len(args)) < 1:
        parser.error("Must give file list see '--help'")

    for arg in args:
        t = arg.split(options.delim, 1)
        path=t[0]
        if len(t) > 1:
            mtype = t[1]
        else:
            mtype = get_type(path,options.deftype)

        maintype, subtype = mtype.split('/', 1)
        if maintype == 'text':
            fp = open(path)
            # Note: we should handle calculating the charset
            msg = MIMEText(fp.read(), _subtype=subtype)
            fp.close()
        else:
            fp = open(path, 'rb')
            msg = MIMEBase(maintype, subtype)
            msg.set_payload(fp.read())
            fp.close()
            # Encode the payload using Base64
            encoders.encode_base64(msg)

        # Set the filename parameter
        msg.add_header('Content-Disposition', 'attachment',
            filename=os.path.basename(path))

        outer.attach(msg)

    if options.output is "-":
        ofile = sys.stdout
    else:
        ofile = file(options.output,"wb")
        
    if options.compress:
        gfile = gzip.GzipFile(fileobj=ofile, filename = options.output )
        gfile.write(outer.as_string())
        gfile.close()
    else:
        ofile.write(outer.as_string())

    ofile.close()

if __name__ == '__main__':
    main()

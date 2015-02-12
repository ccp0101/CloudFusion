'''
Created on 12.05.2011

'''
from cloudfusion.fuse import FUSE
import os, sys
import logging.config
from mylogging import db_logging_thread
from cloudfusion.mylogging.nullhandler import NullHandler
import cloudfusion
from cloudfusion.pyfusebox.transparent_configurable_pyfusebox import TransparentConfigurablePyFuseBox
import shutil
import argparse
import time
import multiprocessing
import signal
from cloudfusion.util.string import get_uuid

class MyParser(argparse.ArgumentParser):
    def error(self, message):
        args= sys.argv
        print_help(args)
        sys.exit(1)

def print_help(args):
    print ''
    print '  usage1: %s [--config path/to/config.ini] mountpoint [foreground] [log] [profile]' % args[0]
    print '      This command will start Cloudfusion.'
    print '          --config configfile.ini: initialization file to automatically start Cloudfusion with a storage provider like Dropbox or Sugarsync'
    print '          mountpoint: empty folder in which the virtual file system is created'
    print '          foreground: run program in foreground'
    print '          log: write logs to the directory .cloudfusion/logs'
    print '          profile: (for developers) create a performance profile file cloudfusion_profile'
    print '          big_write option of fuse is used automatically to optimize throughput if the system supports it (requires fuse 2.8 or higher)\n'
    print '  usage2: %s mountpoint stop' % args[0]
    print '      This command will stop Cloudfusion.'
    print '          mountpoint: The same folder in which the virtual file system has been created with usage1'
    print '  usage3: %s uuid' % args[0]
    print '      This command will output a unique name that can be used as bucket_name for google storage or amazon S3.'
    print ''

def check_arguments(args):
    if not len(args) in [1,2,3,4,5,6,7]:
        print_help(args)
        exit(1)

def set_configuration(mountpoint, config_file):
    '''Wait until the file system is mounted, then overwrite the virtual configuration file.
    This will configure Cloudfusion so that it can be used.'''
    virtual_configuration_file = mountpoint+'/config/config'
    while not os.path.exists(virtual_configuration_file):
        time.sleep(1)
    shutil.copyfile(config_file, virtual_configuration_file)
    
def remove_configuration(mountpoint):
    '''Delete the configuration virtual file, wich will automatically stop Cloudfusion.'''
    virtual_configuration_file = mountpoint+'/config/config'
    if not os.path.exists(virtual_configuration_file):
        print "The mountpoint you specified is not correct, or Cloudfusion has been stopped, already."
    print "Trying to stop Cloudfusion. This may take a while. \n    If it does not work try fusermount -zu mountpoint; kill -9 "+str(os.getpid())
    try:
        os.remove(virtual_configuration_file)
    except OSError:
        pass
    print "Successfully stopped Cloudfusion!"
        
    
def start_configuration_thread(mountpoint, config_file):
    '''Start a thread to write the configuration file 
    to config/config, after the file system has been mounted.'''
    process = multiprocessing.Process(target=set_configuration, args=(mountpoint, config_file))
    process.daemon = True
    process.start()
            

def start_stopping_thread(mountpoint):
    '''Start a thread to delete the configuration file 
    config/config, which automatically stops Cloudfusion.'''
    process = multiprocessing.Process(target=remove_configuration, args=(mountpoint,))
    process.daemon = True
    process.start()
    process.join()
            
def set_umask():
    '''Set umask to prevent cloudfusion to write files that are readable by all users.'''
    os.umask(007)
    
def handle_ipdb(sig, frame):
    import ipdb
    ipdb.set_trace(frame)

    

def main():
    signal.signal(signal.SIGUSR1, handle_ipdb)
    set_umask()
    check_arguments(sys.argv)
    if sys.argv[1] == 'uuid':
        print "You can use the following unique name as your bucket name for amazon S3 or google storage:"
        print "cloudfusion_"+get_uuid()
        sys.exit()
    parser = MyParser()
    parser.add_argument('mountpoint')
    parser.add_argument('--config', help='Configuration file.')
    parser.add_argument('args', nargs=argparse.REMAINDER) #collect all arguments positioned after positional and optional parameters 
    args = parser.parse_args()
    foreground  = 'foreground' in args.args 
    profiling_enabled = 'profile' in args.args
    mountpoint = args.mountpoint
    if "stop" in args.args:
        start_stopping_thread(mountpoint)
        exit(0)
    if not "log" in args.args:
        logging.getLogger().addHandler(NullHandler())
    else:
        if not os.path.exists(".cloudfusion/logs"):
            os.makedirs(".cloudfusion/logs")
        logging.config.fileConfig(os.path.dirname(cloudfusion.__file__)+'/config/logging.conf')
        db_logging_thread.start()    
    if args.config: #evaluates to false
        if not os.path.exists(args.config):
            exit(1)
        start_configuration_thread(mountpoint, args.config)
    if not os.path.exists(mountpoint):
        os.makedirs(mountpoint)
    if profiling_enabled:
        import inspect
        from profilehooks import profile
        import types
        for name, fn in inspect.getmembers(TransparentConfigurablePyFuseBox):
            if isinstance(fn, types.UnboundMethodType):
                if not name.startswith('_'):
                    setattr(TransparentConfigurablePyFuseBox, name, profile(fn, filename='/tmp/cloudfusion_profile'))
    fuse_operations = TransparentConfigurablePyFuseBox(mountpoint)
    allow_other = True
    try:
        #first try to mount file system with big_writes option (more performant)
        FUSE(fuse_operations, mountpoint, allow_other=allow_other, foreground=foreground, nothreads=True, big_writes=True, max_read=131072, max_write=131072) 
    except RuntimeError, e:
        FUSE(fuse_operations, mountpoint, allow_other=allow_other, foreground=foreground, nothreads=True)
    
if __name__ == '__main__':
    main()
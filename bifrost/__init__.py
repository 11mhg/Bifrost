# MODULES

# python standard library
import atexit
import os
import signal
import sys
import warnings

# pypi modules
import posix_ipc

# local modules
from .py_utils import is_notebook
from .py_nodejs import Npm, Node
from .Dcp import Dcp

# PROGRAM

npm = Npm()
node = Node()

memName = node.vs.SHARED_MEMORY_NAME

if utils.is_notebook():

    # ipython modules
    from IPython.core.error import TryNext
    from IPython.display import display, HTML

    # local modules
    from .notebook import BifrostMagics

    def shutdown_hook(ipython):
        '''
        This is a hook that will execute when ipython closes.
        '''
        global node
        node.cancel(restart=False)
        raise TryNext

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ip = get_ipython()
            magics = BifrostMagics(ip, node)
            ip.register_magics(magics)
            ip.set_hook('shutdown_hook', shutdown_hook)
    except Exception as e:
        print(e)
        raise EnvironmentError("Environment is not as was expected")

#When python exits please do the following
@atexit.register
def onEnd():
    global memName
    global node

    #Clean up everything.... Include shm file and mmap stuff.
    try:
        if hasattr(node, 'process'):
            os.kill(node.process.pid, signal.SIGSTOP)
    except:
        print("Could not kill process. May already be dead.")
    try:
        if hasattr(node, 'nstdproc'):
            node.nstdproc.stop()
    except:
        print("Could not stop nstdproc. May already be dead.")

    posix_ipc.unlink_shared_memory(memName)
    print("Memory map has been destroyed")

# set up our DCP bridge interface
dcp = Dcp()


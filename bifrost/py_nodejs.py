# MODULES

# python standard library
import contextlib
import io
import json
import os
import shutil
import signal
import time
from pathlib import Path
from subprocess import Popen, PIPE, check_output
from threading import Thread, Event

# local modules
from .py_storage import VariableSync
from .py_utils import is_windows, is_darwin, has_mp_shared
from .ReadWriteLock import ReadWriteLock

# PROGRAM

#Simple python global read write lock
NODE_LOCK       = ReadWriteLock()
#variable that is being locked
NODE_IS_RUNNING = False

class Npm():
    '''
    Npm is a class that manages all calls to npm.
    '''
    def __init__(self, cwd = os.getcwd()):
        self.cwd = cwd
        self.npm_exec_path = shutil.which('npm')
        self.nodejs_major_version = int(self.nodejs_version().split(".")[0])

        self.js_needs_mmap = not os.path.exists(cwd + '/node_modules/@raygun-nickj/mmap-io')
        self.js_needs_xxhash = not os.path.exists(cwd + '/node_modules/xxhash-wasm')
        self.js_needs_shm = has_mp_shared() and not is_windows() and not is_darwin() and not os.path.exists(cwd + '/node_modules/shmmap') and self.nodejs_major_version < 16

        # TODO: find better terminology than "js needs", but favour this pattern over the previous not-and-chain approach
        if self.js_needs_mmap or self.js_needs_xxhash or self.js_needs_shm:
            npm_init_args = [
              self.npm_exec_path,
              'init',
              '--yes',
            ]
            self.run(npm_init_args)

            if self.js_needs_mmap:
                if self.nodejs_major_version < 16:
                  self.install('@raygun-nickj/mmap-io@1.2.2')
                else:
                  self.install('@raygun-nickj/mmap-io@1.3.0')
                self.js_needs_mmap = False
            if self.js_needs_xxhash:
                self.install('xxhash-wasm@0.4.2')
                self.js_needs_xxhash = False
            if self.js_needs_shm:
                self.install('git+https://github.com/chris-c-mcintyre/shmmap.js')
                self.js_needs_shm = False

    def run(self, cmd, warn=False, log=False):
        '''
        Helper function to run some command using npm.
        Useful for managing working directory of npm and where the 
        stdout pipes are pointing.

        Also helpful to block until command completes.
        '''

        # npm version notice can disrupt parsing of command outputs
        cmd.append("--no-update-notifier")
        
        process = Popen(
          cmd,
          cwd = self.cwd,
          stdout = PIPE,
          stderr = PIPE,
        )

        while True:
            output = process.stdout.readline().decode('utf-8')
            if output == '' and process.poll() is not None:
                break
            if output and log:
                print(output.strip())
            error = process.stderr.readline().decode('utf-8')
            if error and warn:
                print(error.strip())
        returnCode = process.poll()
        return returnCode

    def install(self,*args):
        self.run([self.npm_exec_path, '--quiet', 'install', *args])

    def uninstall(self, *args):
        self.run([self.npm_exec_path, '--quiet', 'uninstall', *args])

    def list_modules(self, *args):
        self.run([self.npm_exec_path, 'list', *args], warn=True, log=True)

    def package_current_version(self, package_name):
        npm_io = io.StringIO()
        with contextlib.redirect_stdout(npm_io):
            self.run([self.npm_exec_path, 'ls', package_name, '--json=true'], warn=True, log=True)
        version_json = npm_io.getvalue()
        version_dict = json.loads(version_json)
        try:
            version_string = version_dict["dependencies"][package_name]["version"]
        except KeyError:
            version_string = '0.0.0'
        return version_string.strip()

    def package_latest_version(self, package_name):
        npm_io = io.StringIO()
        with contextlib.redirect_stdout(npm_io):
            self.run([self.npm_exec_path, 'view', package_name, 'version'], warn=True, log=True)
        version_string = npm_io.getvalue()
        return version_string.strip()

    def nodejs_version(self):
        npm_io = io.StringIO()
        with contextlib.redirect_stdout(npm_io):
            self.run([self.npm_exec_path, 'version', '--json=true'], warn=True, log=True)
        version_json = npm_io.getvalue()
        version_dict = json.loads(version_json)
        version_string = version_dict["node"]
        return version_string.strip()

class NodeSTDProc(Thread):
    '''
    Helper class that is run in another thread from the main thread.
    This runs in the background collecting information from the node
    process and deciding how to manage it.

    In particular, this manages stdout and completion of node process
    execution.
    '''
    def __init__(self, process):
        super(NodeSTDProc, self).__init__()
        self.process     = process
        self._stop_event = Event()
        self.daemon      = True
        self.start()

    def stop(self):
        '''
        Stop this thread.
        '''
        self._stop_event.set()

    def run(self):
        '''Main loop for the thread.'''
        while not self._stop_event.is_set():

            global NODE_IS_RUNNING
            global NODE_LOCK
            output = self.process.stdout.readline().decode('utf-8')
            #if process.poll() returns something,
            #this means that the process has ended. End this thread too.
            if self.process.poll() is not None:
                NODE_LOCK.acquire_write()
                NODE_IS_RUNNING = False
                NODE_LOCK.release_write()
                break
            #if our output is an empty string, do nothing.
            if output == '':
                continue
            #'if our output is not an empty string, try processing it.
            if output:
                try:
                    #if our output is json serializeable, check if
                    #it has type=== done before setting NODE_IS_RUNNING to false
                    output_json = json.loads(output)
                    if output_json['type'] == 'done':
                        NODE_LOCK.acquire_write()
                        NODE_IS_RUNNING = False
                        NODE_LOCK.release_write()
                    else:
                        #otherwise print out the json
                        if (output and len(output.strip()) > 0):
                            print(output.strip())
                    continue
                except Exception as e:
                    #otherwise print out the json
                    if (output and len(output.strip()) > 0):
                        print(output.strip())
                    continue


class Node():
    '''
    This class is a helper class to manage the node process. 
    '''
    def __init__(self, cwd= os.getcwd()):
        self.cwd = cwd
        self.node_exec_path = shutil.which('node')
        self.serializer_custom_funcs = {}
        self.deserializer_custom_funcs = {}
        #the replFile is the main file that preps the node runtime for use with this module
        self.replFile = os.path.dirname(os.path.realpath(__file__)) + '/main.js'
        #The variable synchronization manager
        self.vs = VariableSync()

        self.init_process()

    def init_process(self):
        '''
        Initialize the process by running node with a larger
        max-old-space-size and with all the important information
        regarding the shared memory name and the repl file.
        '''
        env = os.environ
        #make sure to add the current path to the node_path
        env["NODE_PATH"] = self.cwd + '/node_modules'

        #ready the node process
        self.process = Popen(
          [
            self.node_exec_path,
            '--max-old-space-size=32000',
            self.replFile,
            str(self.vs.shared),
            str(self.vs.mp_shared),
            str(self.vs.notebook),
            str(self.vs.windows),
            self.vs.SHARED_MEMORY_NAME
          ],
          cwd = self.cwd,
          stdin = PIPE,
          env = env,
          stdout = PIPE
        )

        #ready the node stdout manager
        self.nstdproc = NodeSTDProc(self.process)

    def register_custom_serializer(self, func, var_type):
        '''
        Register a custom serializer for a particular variable type
        '''
        if var_type is not str:
            var_type = str(var_type)
        self.serializer_custom_funcs[var_type] = func
        return

    def register_custom_deserializer(self, func, var_type):
        '''
        Register a custom deserializer for a particular variable type
        '''
        if var_type is not str:
            var_type = str(var_type)
        self.deserializer_custom_funcs[var_type] = func

    def run_file(self, filename, vars = {}, timeout=None):

        script = Path(filename).read_text()
        
        vars = self.run(script, vars, timeout)

        return vars

    def run(self, script, vars = {}, timeout=None):
        '''
        The main function which runs some node script.

        Will synchronize variables and wait a max of timeout before cancelling job
        run. Note that timeout is default to None and if it is None will never timeout.

        '''

        #synchronize variables first
        self.vs.syncto(vars, self.serializer_custom_funcs, warn=False)

        #get the lock and mark as running.
        global NODE_IS_RUNNING
        global NODE_LOCK
        NODE_LOCK.acquire_write()
        NODE_IS_RUNNING = True
        NODE_LOCK.release_write()
        #Send script to process.
        retCode = self.write(script)

        if retCode < 0:
            print("Could not run script")
            return

        #Keep running until the stdout process marks
        #NODE_IS_RUNNING to False.
        #This is a little dangerous as we need to make sure that NODE_IS_RUNNING
        #Will, at some point, resolve to False.
        flag = NODE_IS_RUNNING
        start = time.time()
        while flag:
            try:
                NODE_LOCK.acquire_read()
                flag = NODE_IS_RUNNING
                NODE_LOCK.release_read()
                if timeout is not None:
                    if (time.time() - start) > timeout:
                        self.cancel()
                        NODE_LOCK.acquire_write()
                        NODE_IS_RUNNING = False
                        NODE_LOCK.release_write()
                        print("Process took longer than " + str(timeout))
            except KeyboardInterrupt:
                self.cancel()
                NODE_LOCK.acquire_write()
                NODE_IS_RUNNING = False
                NODE_LOCK.release_write()
                print("Process was interrupted.")
                raise KeyboardInterrupt
        new_vars = self.vs.syncfrom(self.deserializer_custom_funcs, warn=False)
        for key in new_vars.keys():
            vars[key] = new_vars[key]
        return vars

    def clean_lock(self):
        global NODE_LOCK
        global NODE_IS_RUNNING
        NODE_IS_RUNNING = False
        NODE_LOCK = ReadWriteLock()


    def write(self, s):
        '''
        Helper function to submit node script to node process.
        '''
        try:
            msg_json = json.dumps(
                {'script': s}
            )

            # Each message begins with header from E00000000C to EffffffffC
            # : E in position 0, indicating extended message
            # : C in position 9, indicating concatenated message
            # : hexademical digits from 0 to f in positions 1 to 8, together indicating message total length
            # : message length in header includes Bifrost's JSON wrapping, but does not include header itself

            msg_length_int = len(msg_json)
            msg_length_hex = hex(msg_length_int)
            msg_length_str = str(msg_length_hex)[2:]
            if (len(msg_length_str) > 8 or msg_length_int >= 16**8):
              raise("Script size exceeds Node.js string limit:", str(msg_length_int))
            msg_head = 'E' + msg_length_str.zfill(8) + 'C'
            string_to_send = msg_head + msg_json
            string_encoded = string_to_send.encode('utf-8')
            self.process.stdin.write(string_encoded)
            self.process.stdin.flush()
        except Exception as e:
            global NODE_IS_RUNNING
            global NODE_LOCK
            if 'Broken pipe' in str(e):
                self.cancel()
                print("Pipe broke and was restarted")
            else:
                self.cancel()
                print("Pipe died for some reason: ")
                print(str(e))
            NODE_LOCK.acquire_write()
            NODE_IS_RUNNING = False
            NODE_LOCK.release_write()
            return -1
        return 1

    def cancel(self, restart=True):
        try:
            os.kill(self.process.pid, signal.SIGTERM)
            self.nstdproc.stop()
        except Exception as e:
            print(e)
        try:
            self.nstdproc.stop()
        except Exception as e:
            print(e)
        if restart:
            self.init_process()

    def clear(self):
        self.cancel()


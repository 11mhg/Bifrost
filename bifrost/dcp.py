from bifrost import node, npm

import io
import contextlib

import cloudpickle
import codecs

import random

import zlib

from .Job import Job
from .Dcp import Dcp

def dcp_run(
    _job_input,
    _job_arguments,
    _job_function,
    _job_packages,
    _job_groups,
    _job_imports,
    _job_modules,
    _job_public,
    _job_multiplier,
    _job_local,
    _job_nodejs,
):

    global _dcp_init_worker
    global _dcp_compute_worker

    _run_parameters = {
        'dcp_data': _job_input,
        'dcp_multiplier': _job_multiplier,
        'dcp_local': _job_local,
        'dcp_groups': _job_groups,
        'dcp_public': _job_public,
        'python_init_worker': _dcp_init_worker,
        'python_compute_worker': _dcp_compute_worker,
        'python_parameters': _job_arguments,
        'python_function': _job_function,
        'python_packages': _job_packages,
        'python_modules': _job_modules,
        'python_imports': _job_imports,
    }

    _node_output = node.run('./dcp.js', _run_parameters)

    _job_output = _node_output['jobOutput']
    
    return _job_output

def node_deploy(
        _dcp_slices,
        _dcp_function,
        _dcp_arguments = {},
        _dcp_packages = [],
        _dcp_groups = [],
        _dcp_imports = [],
        _dcp_public = { 'name': 'Bifrost Deployment'},
        _dcp_local = 0,
        _dcp_multiplier = 1):

    print('node_deploy')

def job_deploy(self):

#        _dcp_slices,
#        _dcp_function,
#        _dcp_arguments = {},
#        _dcp_packages = [],
#        _dcp_groups = [],
#        _dcp_imports = [],
#        _dcp_public = { 'name': 'Bifrost Deployment'},
#        _dcp_local = 0,
#        _dcp_multiplier = 1,
#        _dcp_nodejs = False

    _job_slices = _dcp_slices
    _job_function = _dcp_function
    _job_arguments = _dcp_arguments
    _job_packages = _dcp_packages
    _job_groups = _dcp_groups
    _job_imports = _dcp_imports
    _job_public = _dcp_public
    _job_local = _dcp_local
    _job_multiplier = _dcp_multiplier
    _job_nodejs = _dcp_nodejs

    def _input_encoder(_input_data):

        _data_encoded = codecs.encode( _input_data, 'base64' ).decode()

        return _data_encoded

    def _function_writer(_function):

        import inspect

        _function_name = _function.__name__
        _function_code = inspect.getsource(_function)

        return [_function_name, _function_code]

    def _module_writer(_module_name):

        _module_filename = _module_name + '.py'

        with open(_module_filename, 'rb') as _module:
            _module_data = _module.read()

        _module_encoded = _input_encoder( _module_data )

        return _module_encoded

    def _pickle_jar(_input_data):

        _data_pickled = cloudpickle.dumps( _input_data )
        _data_encoded = _input_encoder( _data_pickled )

        return _data_encoded

    if _job_nodejs == True:

        _job_arguments = _input_encoder(_job_arguments)

        _job_slices_encoded = []
        for _block_index, _block_slice in enumerate(_job_slices):

            _block_slice_encoded = _input_encoder(_block_slice)

            _job_slices_encoded.append({
                'index': _block_index,
                'data': _block_slice_encoded })

    else:

        _job_modules = {}
        for _module_name in _job_imports:
            _job_modules[_module_name] = _module_writer(_module_name)

        _job_function = _function_writer(_job_function)

        _job_arguments = _pickle_jar(_job_arguments)

        _job_slices_encoded = []
        for _block_index, _block_slice in enumerate(_job_slices):

            _block_slice_encoded = _pickle_jar(_block_slice)

            _job_slices_encoded.append({
                'index': _block_index,
                'data': _block_slice_encoded })
            
    _job_input = []
    for i in range(_job_multiplier):
        _job_input.extend(_job_slices_encoded)

    #random.shuffle(_job_input)

    if _job_nodejs == True:

        _job_results = dcp_run(
            _job_input,
            _job_arguments,
            _job_function,
            _job_packages,
            _job_groups,
            _job_public,
            _job_multiplier,
            _job_local,
        )

    else:

        _job_results = dcp_run(
            _job_input,
            _job_arguments,
            _job_function,
            _job_packages,
            _job_groups,
            _job_imports,
            _job_modules,
            _job_public,
            _job_multiplier,
            _job_local,
        )

    return _job_results

    #_final_results = []

    #for _results_index, _results_slice in enumerate(_job_results):

        #_results_slice_decoded = codecs.decode( _results_slice.encode(), 'base64' )

        #_results_slice_unpickled = cloudpickle.loads( _results_slice )

        #_final_results[_results_index] = _results_slice_unpickled

    #print(_final_results)

    #return _final_results

dcp = Dcp()

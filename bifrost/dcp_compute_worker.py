# input serialization
import codecs
import cloudpickle
import zlib

# js proxy module for dcp progress calls
from js import dcp

if (pickle_arguments == True):
  # decode and unpickle secondary arguments to compute function
  parameters_decoded = codecs.decode( input_parameters.encode(), 'base64' )
  if (compress_arguments == True):
    parameters_decompressed = zlib.decompress( parameters_decoded )
    parameters_unpickled = cloudpickle.loads( parameters_decompressed )
  else:
    parameters_unpickled = cloudpickle.loads( parameters_decoded )
elif (encode_arguments == True):
  # decode and secondary arguments to compute function
  parameters_unpickled = codecs.decode( input_parameters.encode(), 'base64' )
else:
  # degenerate pythonic EAFP pattern; consider purging in favour of JsProxy type check
  try:
    parameters_unpickled = input_parameters.to_py()
  except AttributeError:
    parameters_unpickled = input_parameters

if (pickle_input == True):
  # decode and unpickle primary argument to compute function
  data_decoded = codecs.decode( input_data.encode(), 'base64' )
  if (compress_input == True):
    data_decompressed = zlib.decompress( data_decoded )
    data_unpickled = cloudpickle.loads( data_decompressed )
  else:
    data_unpickled = cloudpickle.loads( data_decoded )
elif (encode_input == True):
  # decode and primary argument to compute function
  data_unpickled = codecs.decode( input_data.encode(), 'base64' )
else:
  # degenerate pythonic EAFP pattern; consider purging in favour of JsProxy type check
  try:
    data_unpickled = input_data.to_py()
  except AttributeError:
    data_unpickled = input_data

if (pickle_function == True):
  # decode and unpickle compute_function from input cloudpickle object
  function_decoded = codecs.decode( input_function.encode(), 'base64' )
  if (compress_function == True):
    function_decompressed = zlib.decompress( function_decoded )
    compute_function = cloudpickle.loads( function_decompressed )
  else:
    compute_function = cloudpickle.loads( function_decoded )
else:
  # assign compute_function to previously evaluated function definition
  compute_function = locals()[input_function]

dcp.progress()

output_data_raw = compute_function( data_unpickled, **parameters_unpickled )

if (pickle_output == True):
  output_data_pickled = cloudpickle.dumps( output_data_raw )
  if (compress_output == True):
    output_compressed = zlib.compress( output_data_pickled )
    output_data = codecs.encode( output_compressed, 'base64' ).decode()
  else:
    output_data = codecs.encode( output_data_pickled, 'base64' ).decode()
elif (encode_output == True):
  output_data = codecs.encode( output_data_raw, 'base64' ).decode()
else:
  output_data = output_data_raw


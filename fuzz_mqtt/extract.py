import re

funcs_to_extract = [
    'unpack_variable_int',
    'unpack_uint8',
    'unpack_uint16',
    'unpack_uint32',
    'unpack_utf8_str',
    'unpack_binary_data',
    'decode_uint32_property',
    'decode_uint16_property',
    'decode_uint8_property',
    'decode_string_property',
    'decode_binary_property',
    'decode_user_property',
    'decode_sub_id_property',
    'properties_decode'
]

with open('zephyr-src/subsys/net/lib/mqtt/mqtt_decoder.c', 'r') as f:
    content = f.read()

out = []
# simple regex to grab function bodies.
for func in funcs_to_extract:
    # Match static int func_name(args) { ... }
    # This regex is a bit naive but works for these C functions.
    pattern = r"(static\s+int\s+" + func + r"\s*\([^)]*\)\s*\{.*?\n\})"
    m = re.search(pattern, content, re.DOTALL)
    if m:
        out.append(m.group(1))
    else:
        print(f"Could not find {func}")

with open('fuzz_mqtt/extracted_funcs.c', 'w') as f:
    f.write('\n\n'.join(out))


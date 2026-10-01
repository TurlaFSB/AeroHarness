import sys
import json
import os
import subprocess

def parse_file(c_file, out_json):
    print(f"Parsing {c_file}...")
    cmd = [
        "python", "stage1_ast_parser.py",
        c_file,
        out_json
    ]
    # We need to temporarily modify stage1_ast_parser.py to accept arguments if it doesn't already.
    pass


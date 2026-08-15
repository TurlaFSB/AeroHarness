"""
C AST and Header Parsing Module for AeroHarness
Extracts functions, types, structs, enums, MMIO registers, and magic constants.
"""
import re
from pathlib import Path
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


class Parameter(BaseModel):
    name: str
    type_str: str
    is_pointer: bool = False
    is_const: bool = False
    is_struct: bool = False
    is_size_param: bool = False
    is_buffer_param: bool = False


class StructField(BaseModel):
    name: str
    type_str: str
    array_size: Optional[str] = None


class StructDefinition(BaseModel):
    name: str
    fields: List[StructField] = Field(default_factory=list)
    raw_decl: str = ""


class EnumDefinition(BaseModel):
    name: str
    members: Dict[str, Optional[int]] = Field(default_factory=dict)


class FunctionSignature(BaseModel):
    name: str
    return_type: str
    parameters: List[Parameter] = Field(default_factory=list)
    raw_declaration: str = ""
    is_exported: bool = True
    context_struct: Optional[str] = None
    target_buffer_param: Optional[str] = None
    target_size_param: Optional[str] = None


class MMIORegister(BaseModel):
    name: str
    address: str
    description: Optional[str] = None


class ExtractedHeaderContext(BaseModel):
    file_path: str
    functions: List[FunctionSignature] = Field(default_factory=list)
    structs: List[StructDefinition] = Field(default_factory=list)
    enums: List[EnumDefinition] = Field(default_factory=list)
    mmio_registers: List[MMIORegister] = Field(default_factory=list)
    magic_constants: Dict[str, str] = Field(default_factory=dict)
    raw_content: str = ""


class CASTExtractor:
    """Extracts semantic metadata and signatures from C header and source files."""

    def __init__(self):
        pass

    def extract_from_header(self, header_path: Path) -> ExtractedHeaderContext:
        """Parses a C header file and extracts structured type information."""
        content = header_path.read_text(encoding="utf-8", errors="ignore")
        cleaned_content = self._strip_comments(content)

        enums = self._extract_enums(cleaned_content)
        structs = self._extract_structs(cleaned_content)
        mmio_regs = self._extract_mmio_registers(cleaned_content)
        magic_consts = self._extract_magic_constants(cleaned_content)
        functions = self._extract_functions(cleaned_content, structs)

        return ExtractedHeaderContext(
            file_path=str(header_path),
            functions=functions,
            structs=structs,
            enums=enums,
            mmio_registers=mmio_regs,
            magic_constants=magic_consts,
            raw_content=content
        )

    def _strip_comments(self, code: str) -> str:
        """Removes single-line and multi-line comments from C code."""
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        code = re.sub(r'//.*', '', code)
        return code

    def _extract_mmio_registers(self, code: str) -> List[MMIORegister]:
        """Detects #define MMIO_... 0x4000... style register addresses."""
        registers = []
        pattern = re.compile(r'#define\s+([A-Za-z0-9_]*(?:MMIO|REG|HW|ADDR)[A-Za-z0-9_]*)\s+(0x[0-9A-Fa-f]+U?)')
        for match in pattern.finditer(code):
            name, addr = match.group(1), match.group(2)
            registers.append(MMIORegister(name=name, address=addr))
        return registers

    def _extract_magic_constants(self, code: str) -> Dict[str, str]:
        """Extracts magic byte/word definitions for seed corpus generation."""
        constants = {}
        pattern = re.compile(r'#define\s+([A-Za-z0-9_]*(?:MAGIC|HEADER|SYNC)[A-Za-z0-9_]*)\s+(0x[0-9A-Fa-f]+|\d+|\'[^\']\')')
        for match in pattern.finditer(code):
            constants[match.group(1)] = match.group(2)
        return constants

    def _extract_enums(self, code: str) -> List[EnumDefinition]:
        """Extracts typedef enum definitions."""
        enums = []
        pattern = re.compile(r'typedef\s+enum\s*(?:[A-Za-z0-9_]+)?\s*\{([^}]+)\}\s*([A-Za-z0-9_]+)\s*;', re.MULTILINE)
        for match in pattern.finditer(code):
            body, enum_name = match.group(1), match.group(2)
            members = {}
            for item in body.split(','):
                item = item.strip()
                if not item:
                    continue
                if '=' in item:
                    k, v = item.split('=', 1)
                    try:
                        members[k.strip()] = int(v.strip(), 0)
                    except ValueError:
                        members[k.strip()] = None
                else:
                    members[item] = None
            enums.append(EnumDefinition(name=enum_name, members=members))
        return enums

    def _extract_structs(self, code: str) -> List[StructDefinition]:
        """Extracts struct declarations and fields."""
        structs = []
        pattern = re.compile(r'typedef\s+struct\s*(?:[A-Za-z0-9_]+)?\s*\{([^}]+)\}\s*([A-Za-z0-9_]+)\s*;', re.MULTILINE)
        for match in pattern.finditer(code):
            body, struct_name = match.group(1), match.group(2)
            fields = []
            for line in body.split(';'):
                line = line.strip()
                if not line:
                    continue
                # Match type and field name, optionally with array size e.g. uint8_t buf[64]
                field_match = re.search(r'([A-Za-z0-9_\s\*]+?)\s+([A-Za-z0-9_]+)(?:\[([^\]]+)\])?$', line)
                if field_match:
                    ftype = field_match.group(1).strip()
                    fname = field_match.group(2).strip()
                    farr = field_match.group(3).strip() if field_match.group(3) else None
                    fields.append(StructField(name=fname, type_str=ftype, array_size=farr))
            structs.append(StructDefinition(name=struct_name, fields=fields, raw_decl=match.group(0)))
        return structs

    def _extract_functions(self, code: str, structs: List[StructDefinition]) -> List[FunctionSignature]:
        """Extracts exported function signatures and categorizes parameters."""
        functions = []
        struct_names = {s.name for s in structs}

        # Match function declarations: return_type func_name(param1, param2);
        func_pattern = re.compile(r'([A-Za-z0-9_\s\*]+?)\s+([A-Za-z0-9_]+)\s*\(([^)]*)\)\s*;', re.MULTILINE)
        for match in func_pattern.finditer(code):
            ret_type = match.group(1).strip()
            fname = match.group(2).strip()
            param_str = match.group(3).strip()

            # Ignore preprocessor macros or typedefs that matched accidentally
            if ret_type.startswith('#') or ret_type.startswith('typedef'):
                continue

            params = []
            context_struct = None
            target_buf_param = None
            target_sz_param = None

            if param_str and param_str != "void":
                raw_params = [p.strip() for p in param_str.split(',') if p.strip()]
                for raw_p in raw_params:
                    p_match = re.search(r'([A-Za-z0-9_\s\*]+?)\s+([A-Za-z0-9_]+)$', raw_p)
                    if p_match:
                        ptype = p_match.group(1).strip()
                        pname = p_match.group(2).strip()
                        is_ptr = '*' in ptype or '*' in raw_p
                        is_const = 'const' in ptype
                        
                        clean_type = ptype.replace('const', '').replace('*', '').strip()
                        is_struct = clean_type in struct_names or 'struct' in clean_type
                        
                        is_size = any(s in pname.lower() for s in ['size', 'len', 'length', 'count', 'bytes']) or 'size_t' in ptype
                        is_buf = any(b in pname.lower() for b in ['data', 'buf', 'buffer', 'payload', 'frame', 'packet']) and is_ptr

                        param_obj = Parameter(
                            name=pname,
                            type_str=ptype,
                            is_pointer=is_ptr,
                            is_const=is_const,
                            is_struct=is_struct,
                            is_size_param=is_size,
                            is_buffer_param=is_buf
                        )
                        params.append(param_obj)

                        # Context detection (e.g. protocol_context_t *ctx)
                        if is_ptr and is_struct and any(c in pname.lower() for c in ['ctx', 'context', 'handle', 'self']):
                            context_struct = clean_type

                        if is_buf:
                            target_buf_param = pname
                        if is_size:
                            target_sz_param = pname

            functions.append(FunctionSignature(
                name=fname,
                return_type=ret_type,
                parameters=params,
                raw_declaration=match.group(0).strip(),
                context_struct=context_struct,
                target_buffer_param=target_buf_param,
                target_size_param=target_sz_param
            ))
        return functions

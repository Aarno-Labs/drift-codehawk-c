# TODO License

"""Implementation of commands for DRIFT toolchain output"""

import argparse
from dataclasses import dataclass, field, asdict
import codecs
import json
import os
import shutil
import subprocess
import sys
import time
from enum import Enum

from typing import (
    Any,
    cast,
    Dict,
    Generator,
    List,
    Sequence,
    Optional,
    NoReturn,
    Tuple,
    TYPE_CHECKING,
)

from chc.app.CApplication import CApplication

from chc.cmdline.AnalysisManager import AnalysisManager
from chc.cmdline.ParseManager import ParseManager
import chc.cmdline.jsonresultutil as JU

from chc.linker.CLinker import CLinker

import chc.reporting.ProofObligations as RP

from chc.util.Config import Config
import chc.util.fileutil as UF
from chc.util.loggingutil import chklogger, LogLevel

from chc.app.CExp import CExp

from chc.proof.CPOPredicate import CPOPredicate

if TYPE_CHECKING:
    from chc.app.CFile import CFile
    from chc.app.CFunction import CFunction
    from chc.app.CInstr import CInstr
    from chc.app.CStmt import CInstrsStmt, CStmt
    from chc.proof.CFunctionPO import CFunctionPO


def print_error(m: str) -> None:
    sys.stderr.write(("*" * 80) + "\n")
    sys.stderr.write(m + "\n")
    sys.stderr.write(("*" * 80) + "\n")

# enum of PO types
class POConclusion(Enum):
    SAFE = "safe"
    OPEN = "open"
    VIOLATION = "violation"
    DELEGATED_API = "delegated-API"
    DELEGATED_CONTRACT = "delegated-contract"

@dataclass
class PO:
    type: str
    conclusion: POConclusion

@dataclass
class UnSafeLine:
    line: int
    pos: List[PO] = field(default_factory=list)

@dataclass
class Function:
    name: str
    line: int = -1
    unsafeLines: List[UnSafeLine] = field(default_factory=list)

@dataclass
class File:
    path: str
    name: str
    functions: List[Function] = field(default_factory=list)

def function_to_Function(fn: "CFunction") -> Function:
    lines: List[str] = []
    ppos = fn.get_ppos()

    fun_start_line = -1
    
    if not fn.has_line_number():
        print_error(f"Function {fn.name} has no source code!")
    else: 
        fun_start_line = fn.get_line_number()
    
    lines: Dict[int, UnSafeLine] = {}
    for ppo in ppos:
        po_cons: POConclusion = POConclusion.SAFE
        if ppo.is_violated:
            po_cons = POConclusion.VIOLATION
        elif ppo.is_open:
            po_cons = POConclusion.OPEN
        elif ppo.is_delegated and ppo.get_assumptions_type() != "contract":
            po_cons = POConclusion.DELEGATED_API

        if po_cons != POConclusion.SAFE:    
            line = ppo.line
            po = PO(type = ppo.predicate.predicate_name, conclusion=po_cons)
            if line in lines:
                lines[line].pos.append(po)
            else:
                lines[line] = UnSafeLine(line=line, pos=[po])

    sorted_lines = dict(sorted(lines.items(), key=lambda item: item[0]))

    function = Function(name=fn.name, 
                        line=fun_start_line,
                        unsafeLines=list(sorted_lines.values()))

    return function

class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Enum):
            return obj.value
        if hasattr(obj, "__dataclass_fields__"):
            return asdict(obj)
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        print(obj.__class__.__name__)
        return super().default(obj)

def drift_asan(args: argparse.Namespace) -> NoReturn:
    """CLI command to extract outputs for DRIFT toolchain for the project."""

    # arguments
    tgtpath: str = args.tgtpath
    projectname: str = args.projectname

    targetpath = os.path.abspath(tgtpath)
    contractpath = os.path.join(targetpath, "chc_contracts")
    projectpath = targetpath

    if not UF.has_analysisresults_path(targetpath, projectname):
        print_error(f"No analysis results found for {projectname} in {targetpath}")
        exit(1)

    capp = CApplication(projectpath, projectname, targetpath, contractpath)

    def f(cfile: "CFile") -> None:
        file = File(path=cfile.targetpath, name=cfile.name + ".c")
        for cf in cfile.get_functions():
            function = function_to_Function(cf)
            file.functions.append(function)
        # assume that we can concatenate the path and name to get the full path
        # and assume we should append
        output = os.path.join(file.path, file.name + ".codehawk.json")
        with open(output, "w") as of:
            json.dump(file, of, cls=CustomEncoder)
            
    capp.iter_files(f)

    exit(0)
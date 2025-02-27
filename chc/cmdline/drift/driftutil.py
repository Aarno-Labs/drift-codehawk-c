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

@dataclass
class UnSafeLine:
    line: int
    openPPOTypes: List[str]
    violationPPOTypes: List[str]
    delegatedPPOTypes: List[str]

@dataclass
class Function:
    name: str
    line: int
    unsafeLines: List[UnSafeLine] = field(default_factory=list)

@dataclass
class File:
    path: str
    name: str
    functions: List[Function] = field(default_factory=list)

@dataclass
class Project:
    totalUnsafeLines: int = 0
    files: List[File] = field(default_factory=list)

def function_to_Function(fn: "CFunction") -> Function:
    lines: List[str] = []
    ppos = fn.get_ppos()
    
    if not fn.has_line_number():
        print_error(f"Function {fn.name} has no source code!")
        exit(1)

    fnstartlinenr = fn.get_line_number()
    
    
    lines: Dict[int, UnSafeLine] = {}
    for ppo in ppos:
        if ppo.is_violated or ppo.is_open or ppo.is_delegated:
            line = ppo.line
            if line not in lines:
                lines[line] = UnSafeLine(line=line, openPPOTypes=[], violationPPOTypes=[], delegatedPPOTypes=[])
            if ppo.is_violated:
                lines[line].violationPPOTypes.append(ppo.predicate.predicate_name)
            elif ppo.is_open:
                lines[line].openPPOTypes.append(ppo.predicate.predicate_name)
            elif ppo.is_delegated:
                lines[line].delegatedPPOTypes.append(ppo.predicate.predicate_name)


    sorted_lines = dict(sorted(lines.items(), key=lambda item: item[0]))

    function = Function(name=fn.name, 
                        line=fnstartlinenr,
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
    output = args.output

    targetpath = os.path.abspath(tgtpath)
    contractpath = os.path.join(targetpath, "chc_contracts")
    projectpath = targetpath

    if not UF.has_analysisresults_path(targetpath, projectname):
        print_error(f"No analysis results found for {projectname} in {targetpath}")
        exit(1)

    capp = CApplication(projectpath, projectname, targetpath, contractpath)

    project = Project()

    def f(cfile: "CFile") -> None:
        project.files.append(File(path=cfile.targetpath, name=cfile.name))
        for cf in cfile.get_functions():
            function = function_to_Function(cf)
            project.totalUnsafeLines += len(function.unsafeLines)
            project.files[-1].functions.append(function)
            
    capp.iter_files(f)

    if output is None:
        project_json = json.dumps(project, cls=CustomEncoder, indent=2)
        print(project_json)
    else:
        with open(output, "w") as of:
            json.dump(project, of, cls=CustomEncoder)

    exit(0)
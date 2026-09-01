# -*- coding: utf-8 -*-
# Analyze cinematic camera path: exact native funcs + decompile.
# @category WC3VR
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
from ghidra.program.util import DefinedDataIterator
import struct as _s

prog=currentProgram; fm=prog.getFunctionManager(); base=prog.getImageBase()
listing=prog.getListing()
dec=DecompInterface(); dec.openProgram(prog); mon=ConsoleTaskMonitor()

def find_str(name):
    for d in DefinedDataIterator.definedStrings(prog):
        if d.getValue()==name: return d.getAddress()
    return None

def disasm_around(va_int, before=40, after=10):
    a=toAddr(va_int)
    ins=getInstructionBefore(a)
    # шагаем назад
    lst=[]
    cur=a
    for _ in range(before):
        p=getInstructionBefore(cur)
        if p is None: break
        cur=p
    for _ in range(before+after):
        if cur is None: break
        rva=cur.getAddress().getOffset()-base.getOffset()
        note=""
        if cur.getMnemonicString()=="CALL":
            fl=cur.getFlows()
            if fl:
                tf=fm.getFunctionContaining(fl[0])
                note=" -> %s"%(tf.getName() if tf else str(fl[0]))
        print("  +0x%06x %-38s%s"%(rva,cur.toString(),note))
        cur=cur.getNext()

def decompile(rva,label):
    a=base.add(rva); f=fm.getFunctionContaining(a)
    print("\n===== %s : %s ====="%(label,str(a)))
    if not f: print(" none"); return
    r=dec.decompileFunction(f,90,mon)
    print(r.getDecompiledFunction().getC() if r and r.decompileCompleted() else " fail")

# 1) регистрация SetCameraField: дизасм вокруг xref строки
s=find_str("SetCameraField")
print("SetCameraField str @ %s"%str(s))
if s:
    for r in getReferencesTo(s):
        fa=r.getFromAddress()
        # только первая (в .text регистрации)
        if base.getOffset()<=fa.getOffset()<base.getOffset()+0x900000:
            print("\n--- disasm around xref %s ---"%str(fa))
            disasm_around(fa.getOffset())
            break

# 2) SetCameraPosition (двигает камеру в кат-сценах — свободно)
sp=find_str("SetCameraPosition")
if sp:
    for r in getReferencesTo(sp):
        fa=r.getFromAddress()
        if base.getOffset()<=fa.getOffset()<base.getOffset()+0x900000:
            print("\n--- disasm around SetCameraPosition reg %s ---"%str(fa))
            disasm_around(fa.getOffset())
            break

print("\n=== DONE ===")

# -*- coding: utf-8 -*-
# @category WC3VR
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
prog=currentProgram; fm=prog.getFunctionManager(); base=prog.getImageBase()
dec=DecompInterface(); dec.openProgram(prog); mon=ConsoleTaskMonitor()
def ensure(rva):
    a=base.add(rva); f=fm.getFunctionContaining(a)
    if f is None:
        try: f=createFunction(a,None)
        except: f=None
    return f,a
def dec_f(rva,label):
    f,a=ensure(rva); print("\n===== %s : %s ====="%(label,str(a)))
    if not f: print(" none"); return
    r=dec.decompileFunction(f,120,mon)
    print(r.getDecompiledFunction().getC() if r and r.decompileCompleted() else " fail")
dec_f(0x303df0,"StoreCameraBounds")
dec_f(0x2f5ed0,"GetCameraHolder")
print("\n=== DONE ===")

# -*- coding: utf-8 -*-
# @category WC3VR
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
prog=currentProgram; fm=prog.getFunctionManager(); base=prog.getImageBase()
dec=DecompInterface(); dec.openProgram(prog); mon=ConsoleTaskMonitor()
def d(rva,label):
    a=base.add(rva); f=fm.getFunctionContaining(a)
    print("\n===== %s : %s (%s) ====="%(label,str(a),f.getName() if f else "?"))
    if not f: print(" none"); return
    r=dec.decompileFunction(f,120,mon)
    print(r.getDecompiledFunction().getC() if r and r.decompileCompleted() else " fail")
d(0x3b48b0,"REAL SetCameraField native")
d(0x3b86f0,"SetCameraPosition native")
d(0x3b4820,"native@0x3b4820 (prev)")
print("\n=== DONE ===")

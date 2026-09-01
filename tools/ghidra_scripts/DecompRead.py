# -*- coding: utf-8 -*-
# Decompile the angle/float goal readers to find the exact field offset rendered.
# @category WC3VR
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
prog = currentProgram; fm = prog.getFunctionManager(); base = prog.getImageBase()
dec = DecompInterface(); dec.openProgram(prog); mon = ConsoleTaskMonitor()
def d(rva,label):
    a=base.add(rva); f=fm.getFunctionContaining(a)
    print("\n===== %s : %s ====="%(label,str(a)))
    if not f: print("  none"); return
    r=dec.decompileFunction(f,90,mon)
    print(r.getDecompiledFunction().getC() if r and r.decompileCompleted() else "  fail")
d(0x47c4d0,"FUN_6f47c4d0 angle goal reader")
d(0x4773a0,"FUN_6f4773a0 float/dist goal reader")
print("=== DONE ===")

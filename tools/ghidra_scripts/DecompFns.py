# -*- coding: utf-8 -*-
# Decompile candidate camera-field writer functions.
# @category WC3VR
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor

prog = currentProgram
fm = prog.getFunctionManager()
base = prog.getImageBase()
decomp = DecompInterface(); decomp.openProgram(prog)
monitor = ConsoleTaskMonitor()

def decompile(rva, label):
    addr = base.add(rva)
    f = fm.getFunctionContaining(addr)
    print("\n================ %s : RVA 0x%x (%s) ================" % (label, rva, str(addr)))
    if f is None:
        print("  <no function>"); return
    print("  entry %s  callers:" % str(f.getEntryPoint()))
    for c in f.getCallingFunctions(monitor):
        print("    <- %s @ %s" % (c.getName(), str(c.getEntryPoint())))
    res = decomp.decompileFunction(f, 90, monitor)
    if res and res.decompileCompleted():
        print(res.getDecompiledFunction().getC())
    else:
        print("  <decompile failed>")

for rva, label in [(0x3063d0, "writer A (FST 5b0/5b4/5b8)"),
                   (0x307b00, "writer B (FST 5b0/5b4/5b8)"),
                   (0x300ab0, "MOV-writer 5b8"),
                   (0x3453a0, "FSTP 5b8 + FLD 5b8")]:
    decompile(rva, label)
print("\n=== DONE ===")

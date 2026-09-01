# -*- coding: utf-8 -*-
# Ghidra headless post-script (Jython). Decompiles WC3 1.26 game.dll camera
# functions and finds global access to the camera object.
# @category WC3VR
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
from ghidra.program.util import DefinedDataIterator

prog = currentProgram
fm = prog.getFunctionManager()
base = prog.getImageBase()
print("=== IMAGE BASE: %s ===" % str(base))

decomp = DecompInterface()
decomp.openProgram(prog)
monitor = ConsoleTaskMonitor()

def func_at(rva):
    addr = base.add(rva)
    f = fm.getFunctionContaining(addr)
    if f is None:
        try:
            f = createFunction(addr, None)
        except:
            f = None
    return f, addr

def decompile_rva(rva, label):
    f, addr = func_at(rva)
    print("\n================ %s : RVA 0x%x (%s) ================" % (label, rva, str(addr)))
    if f is None:
        print("  <no function here>")
        return
    print("  entry: %s  name: %s  cc: %s" % (str(f.getEntryPoint()), f.getName(), f.getCallingConventionName()))
    res = decomp.decompileFunction(f, 90, monitor)
    if res and res.decompileCompleted():
        print(res.getDecompiledFunction().getC())
    else:
        print("  <decompile failed: %s>" % (res.getErrorMessage() if res else "null"))

# 1) confirm native via string
print("\n### string SetCameraField and its refs ###")
found = None
for d in DefinedDataIterator.definedStrings(prog):
    if d.getValue() == "SetCameraField":
        found = d.getAddress()
        print("  string @ %s" % str(found))
        break
if found:
    for r in getReferencesTo(found):
        fa = r.getFromAddress()
        fn = fm.getFunctionContaining(fa)
        print("    xref from %s (func %s @ %s)" % (str(fa), fn.getName() if fn else "?", str(fn.getEntryPoint()) if fn else "?"))

# 2) decompile key functions (RVAs from manual RE)
for rva, label in [(0x3b4820, "SetCameraField native"),
                   (0x3074c0, "INTERNAL camera apply fn (thiscall)"),
                   (0x300710, "getJassContext (TLS?)"),
                   (0x2f5ed0, "get [ctx+0x254] = camera")]:
    decompile_rva(rva, label)

# 3) who calls the internal camera fn 0x3074c0 (find global camera pointer)
print("\n### callers of internal camera fn 0x3074c0 ###")
cam_fn, cam_addr = func_at(0x3074c0)
if cam_fn:
    cnt = 0
    for c in cam_fn.getCallingFunctions(monitor):
        print("  called from %s @ %s" % (c.getName(), str(c.getEntryPoint())))
        cnt += 1
        if cnt >= 25:
            break
print("\n=== DONE ===")

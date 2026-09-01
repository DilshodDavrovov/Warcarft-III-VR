# -*- coding: utf-8 -*-
# @category WC3VR
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
prog=currentProgram; fm=prog.getFunctionManager(); base=prog.getImageBase()
dec=DecompInterface(); dec.openProgram(prog); mon=ConsoleTaskMonitor()
listing=prog.getListing()
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
def dis(rva,label,n=40):
    f,a=ensure(rva); print("\n##### DISASM %s : %s #####"%(label,str(a)))
    cur=listing.getInstructionAt(a)
    if cur is None:
        try: disassemble(a); cur=listing.getInstructionAt(a)
        except: pass
    c=0
    while cur is not None and c<n:
        rr=cur.getAddress().getOffset()-base.getOffset(); note=""
        if cur.getMnemonicString()=="CALL":
            fl=cur.getFlows()
            if fl: tf=fm.getFunctionContaining(fl[0]); note=" -> %s"%(tf.getName() if tf else str(fl[0]))
        print("  +0x%06x %-40s%s"%(rr,cur.toString(),note))
        if cur.getMnemonicString()=="RET": break
        cur=cur.getNext(); c+=1
dec_f(0x3b45d0,"SetCameraPosition (real)")
dis(0x3b45d0,"SetCameraPosition (real)",45)
print("\n=== DONE ===")

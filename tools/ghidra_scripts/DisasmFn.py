# -*- coding: utf-8 -*-
# Dump disassembly of FUN_6f3063d0 (camera per-frame writer) with ecx/this context
# to find which camera-offset Angle object holds the rotation/AoA goal.
# @category WC3VR
prog = currentProgram
listing = prog.getListing()
fm = prog.getFunctionManager()
base = prog.getImageBase()

rva = 0x3063d0
addr = base.add(rva)
f = fm.getFunctionContaining(addr)
print("=== disasm FUN @ %s (%s) ===" % (str(addr), f.getName() if f else "?"))
if f:
    body = f.getBody()
    it = listing.getInstructions(body, True)
    while it.hasNext():
        insn = it.next()
        a = insn.getAddress()
        r = a.getOffset() - base.getOffset()
        # annotate calls with target name
        note = ""
        flows = insn.getFlows()
        if insn.getMnemonicString() == "CALL" and flows:
            tf = fm.getFunctionContaining(flows[0])
            note = " -> %s" % (tf.getName() if tf else str(flows[0]))
        print("  +0x%06x  %-40s%s" % (r, insn.toString(), note))
print("=== DONE ===")

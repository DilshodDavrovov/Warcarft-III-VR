# -*- coding: utf-8 -*-
# Find instructions accessing camera field displacements (0x5b8 rotation,
# 0x5b4 AoA, 0x5b0 distance) to locate the per-frame writer.
# @category WC3VR
from ghidra.program.model.scalar import Scalar

listing = currentProgram.getListing()
fm = currentProgram.getFunctionManager()
base = currentProgram.getImageBase()
targets = set([0x5b8, 0x5b4, 0x5b0, 0x5a4])
MN = set(["MOV","FSTP","MOVSS","FST","FLD","MOVAPS","MOVUPS","LEA"])

print("=== instructions with camera-field displacement ===")
cnt = 0
it = listing.getInstructions(True)
while it.hasNext():
    insn = it.next()
    mn = insn.getMnemonicString()
    if mn not in MN:
        continue
    hit = None
    for opi in range(insn.getNumOperands()):
        for obj in insn.getOpObjects(opi):
            if isinstance(obj, Scalar):
                v = obj.getUnsignedValue()
                if v in targets:
                    hit = v
    if hit is not None:
        fn = fm.getFunctionContaining(insn.getAddress())
        rva = insn.getAddress().getOffset() - base.getOffset()
        print("  %s (RVA +0x%x) : %-28s [disp 0x%x] func=%s @%s" % (
            str(insn.getAddress()), rva, insn.toString(), hit,
            fn.getName() if fn else "?",
            str(fn.getEntryPoint()) if fn else "?"))
        cnt += 1
        if cnt > 200:
            print("  ... stop at 200")
            break
print("=== DONE (%d hits) ===" % cnt)

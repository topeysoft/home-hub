#!/usr/bin/env python3
"""Compare KiCad-exported nets and component identities with the routed PCB and PARTS."""
from pathlib import Path
import re,runpy,json
D=Path(__file__).parent;g=runpy.run_path(str(D/'gen_sch.py'));s=(D/'puck-revA.kicad_pcb').read_text();n=(D/'after.net').read_text()
def blocks(text,tag):
 for m in re.finditer(r'\('+tag+r'(?=\s)',text):yield g['sexp_block'](text[m.start():],'('+tag)
fps={re.search(r'\(property "Reference" "([^"]+)"',b).group(1):b for b in blocks(s,'footprint')}
expected={}
for b in blocks(n,'net'):
 name=re.search(r'\(name "([^"]+)"',b).group(1)
 for ref,pin in re.findall(r'\(node\s+\(ref "([^"]+)"\)\s+\(pin "([^"]+)"\)',b):expected[ref,pin]=name
errors=[]
for ref,(_,_,value,fp,nets) in g['PARTS'].items():
 if ref.startswith('#'):continue
 b=fps.get(ref)
 if not b:errors.append(f'missing {ref}');continue
 if re.search(r'\(footprint "([^"]+)"',b).group(1)!=fp:errors.append(f'{ref} footprint')
 if re.search(r'\(property "Value" "([^"]+)"',b).group(1)!=value:errors.append(f'{ref} value')
 sid=g['SYMBOL_IDS'].get(ref)
 if sid and ('/'+sid) not in b:errors.append(f'{ref} schematic UUID link')
 pads={}
 for pad in blocks(b,'pad'):
  pin=re.search(r'\(pad "([^"]*)"',pad).group(1);net=re.search(r'\(net "([^"]+)"',pad);actual=net.group(1) if net else ''
  if pin and (ref,pin) in expected and actual!=expected[ref,pin]:errors.append(f'{ref}.{pin}: {actual} != {expected[ref,pin]}')
  pads.setdefault(pin,[]).append(actual)
 for pin in nets:
  if pin not in pads:errors.append(f'{ref}.{pin} missing pad')
for ref in fps:
 if ref not in g['PARTS']:errors.append(f'extra board component {ref}')
anchors={r:re.search(r'\(at ([^)]+)\)',fps[r]).group(1) for r in ['SW3','J1','H1','H2','H3']}
result={'component_count':len(fps),'functional_nets':30,'exported_pin_assignments':len(expected),'errors':errors,'mechanical_anchors':anchors}
(D/'sync-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));raise SystemExit(bool(errors))

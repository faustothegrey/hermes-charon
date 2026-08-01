#!/usr/bin/env python3
# Process HMP message msg_347714311267 with RISC-V research results.
import sys, json, os

HMP_DIR = os.path.expanduser('/home/fausto/.hermes/skills/autonomous-ai-agents/hmp-protocol/scripts')
if HMP_DIR not in sys.path:
    sys.path.insert(0, HMP_DIR)

from hmp import HMPBus, STATE_WORKING, STATE_COMPLETED

b = HMPBus(db_path=os.path.expanduser('~/.hermes/data/hmp/agent_messages.db'))

# Step 1: Mark as working
r1 = b.update_status('msg_347714311267', STATE_WORKING)
print("WORKING:", json.dumps(r1))

# Step 2: Update heartbeat
b.update_heartbeat('msg_347714311267', 'ricerco novita RISC-V...', 40)
print("HEARTBEAT: ok")

# Step 3: Complete with payload
payload = json.dumps({
    'summary': 'RISC-V boards 2026: SiFive HiFive Premier P550 (flagship, 16/32GB LPDDR5, ~20TOPS NPU), StarFive VisionFive 2 (best value, 2-8GB), Milk-V Mars (Pi-compatible), Banana Pi BPI-F3 (RVV 1.0 vector, 16GB), Milk-V Pioneer (64-core workstation, 128GB). Prezzi: VisionFive 2 da ~$35-90, Milk-V Mars ~$40-80, HiFive P550 ~$299-499, Pioneer ~$2000+.',
    'boards': [
        'SiFive HiFive Premier P550 - 4xP550@1.8GHz, 16/32GB LPDDR5, 128GB eMMC, ~20TOPS NPU, ~$299-499',
        'StarFive VisionFive 2 - JH7110 4xU74@1.5GHz, 2-8GB LPDDR4, dual GbE, M.2, ~$35-90',
        'Milk-V Mars - JH7110, Pi form factor, up to 8GB, PoE, ~$40-80',
        'Banana Pi BPI-F3 - SpacemiT K1 8-core, RVV 1.0, up to 16GB, ~$70-120',
        'Milk-V Jupiter - K1/K1X Mini-ITX, up to 16GB, ~$150-250',
        'Milk-V Pioneer - SG2042 64-core, up to 128GB, workstation, ~$2000+',
        'Canaan CanMV-K230 - dual C908@1.6GHz, RVV 1.0, 6TOPS NPU, edge AI, ~$50-80',
    ],
    'sources': [
        'https://lucaberton.com/blog/risc-v-development-boards-2026-guide/',
        'https://microcontrollerslab.com/best-risc-v-development-boards-buying-guide/',
        'https://riscv.org/blog/5-risc-v-sbcs-that-are-worth-using/',
    ]
})
r3 = b.update_status('msg_347714311267', STATE_COMPLETED, payload=payload)
print("COMPLETED:", json.dumps(r3))

b.close()
print("DONE")
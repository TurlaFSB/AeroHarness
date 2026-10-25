import os
import struct

corpus_dir = '/mnt/d/aeroharness/targets/crtp_trajectory_write/output/crtpCommanderHighLevelWriteTrajectory/corpus_seeded'
os.makedirs(corpus_dir, exist_ok=True)

seeds = [
    ('seed1_0_10', 0, 10, b'A' * 10),
    ('seed2_100_20', 100, 20, b'B' * 20),
    ('seed3_2000_50', 2000, 50, b'C' * 50),
    ('seed4_3000_32', 3000, 32, b'D' * 32),
    ('seed5_4080_16', 4080, 16, b'E' * 16),
]

for name, offset, length, data in seeds:
    payload = struct.pack('<IB', offset, length) + data
    filepath = os.path.join(corpus_dir, name)
    with open(filepath, 'wb') as f:
        f.write(payload)
    print(f'Wrote {name}: size={len(payload)}, offset={offset}, length={length}, sum={offset+length}')

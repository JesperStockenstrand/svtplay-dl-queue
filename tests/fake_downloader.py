#!/usr/bin/env python3
"""Stand-in for svtplay-dl in tests.

Prints svtplay-dl-style progress, writes a file to the current directory.
URLs containing "fail" exit with an error; "slow" takes a long time.
"""
import sys
import time

url = sys.argv[-1]
steps = 200 if "slow" in url else 5
print("INFO: Outfile: fake-video.mp4", flush=True)
for i in range(1, steps + 1):
    sys.stderr.write("\r[%02d/%02d][====] ETA: 0:00:01" % (i, steps))
    sys.stderr.flush()
    time.sleep(0.05)
sys.stderr.write("\n")
if "fail" in url:
    print("ERROR: That site is not supported. Make a ticket or pull request", flush=True)
    sys.exit(1)
with open("fake-video.mp4", "w") as f:
    f.write(" ".join(sys.argv[1:]))

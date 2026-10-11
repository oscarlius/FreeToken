import pathlib
import subprocess
import sys

script = pathlib.Path(sys.argv[1]).read_bytes().removeprefix(b"\xef\xbb\xbf").replace(b"\r\n", b"\n")
raise SystemExit(subprocess.run(
    ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "9", "bash", "-s"],
    input=script,
).returncode)

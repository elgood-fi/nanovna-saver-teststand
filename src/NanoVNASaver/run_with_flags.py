# run_with_flags.py
import sys
flags = ["--no-save-config","--no-load-config","--test-stand","--debug-file","tester_log.log"]
sys.argv = [sys.argv[0]] + flags + sys.argv[1:]
from NanoVNASaver.__main__ import main
if __name__ == "__main__":
    main()
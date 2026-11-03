import argparse

import uvicorn

parser = argparse.ArgumentParser(description="Shannon's Hoard")
parser.add_argument("--port", type=int, default=5245)
args = parser.parse_args()
uvicorn.run("shannon.app:app", host="127.0.0.1", port=args.port)

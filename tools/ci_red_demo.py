"""Planted fault for step 0.8: a self-test that always fails. Never merged."""
import argparse
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--self-test", action="store_true")
parser.parse_args()
sys.exit(1)

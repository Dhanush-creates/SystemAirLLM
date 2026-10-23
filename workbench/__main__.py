"""Command-line run: python -m workbench "your task" """
import json
import sys

from .agent import Agent
from .registry import Registry

if len(sys.argv) < 2:
    sys.exit('usage: python -m workbench "task text" [attachment ...]')
for event in Agent(Registry.load()).run(sys.argv[1], tuple(sys.argv[2:])):
    print(json.dumps(event, indent=2))

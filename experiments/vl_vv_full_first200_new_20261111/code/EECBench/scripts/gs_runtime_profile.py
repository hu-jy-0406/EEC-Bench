"""Explicit audited runtime choices, including the selected expected-motion protocol."""
import json
from pathlib import Path
CONFIG=Path(__file__).resolve().parents[1]/'configs/gs-runtime-profiles.v1.json'
def profile(name=None):
 config=json.loads(CONFIG.read_text());name=name or config['selected']
 if name not in config['profiles']:raise ValueError('Unknown runtime profile: '+name)
 return dict(config['profiles'][name],name=name)
def names():return list(json.loads(CONFIG.read_text())['profiles'])

IDENTITY_REVIEW_INPUTS = ('minimal', 'full')
def resolve_identity_review_input(runtime, override=None):
 """Resolve evidence choice independently of model, transport and scoring gates."""
 choice = override if override is not None else runtime.get('identity_review_input', 'full')
 if choice not in IDENTITY_REVIEW_INPUTS:
  raise ValueError('Unknown identity-review input: ' + str(choice))
 if choice == 'minimal' and runtime.get('identity_review_protocol') != 'identity_scoring_v1':
  raise ValueError('Minimal identity input requires identity_scoring_v1; use full for legacy runtime profiles')
 return choice

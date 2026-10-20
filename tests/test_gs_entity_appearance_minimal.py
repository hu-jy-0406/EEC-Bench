import json
from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import gs_entity_appearance_minimal as m
class MinimalTests(unittest.TestCase):
    def test_only_invocation_base_changes(self):
        seen=[];old=m.ORIGINAL_RUN_PROCESS
        try:
            m.ORIGINAL_RUN_PROCESS=lambda *args:seen.append(args)
            with tempfile.TemporaryDirectory() as d:
                command=['codex','exec','--model','gpt-6-astra','-c','model_reasoning_effort="medium"','-']
                m.evaluation_process(command,'prompt',Path(d),Path(d)/'events.jsonl',Path(d)/'stderr',600)
                actual=seen[0][0]
                self.assertEqual(actual[:-3],command[:-1]);self.assertEqual(actual[-3],'-c')
                self.assertEqual(actual[-2],'model_instructions_file='+json.dumps(str(m.BASE)))
                self.assertEqual(command[-1],'-');self.assertEqual(seen[0][1],'prompt')
                record=json.loads((Path(d)/'execution_override.json').read_text())
                self.assertEqual(record['actual_command'],actual)
        finally:m.ORIGINAL_RUN_PROCESS=old
if __name__=='__main__':unittest.main()

set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib,tarfile
root=pathlib.Path('/data2/FreeToken/runs/dev_D04/candidate')
root.mkdir(parents=True,exist_ok=True)
source=pathlib.Path('/data2/FreeToken/runs/plan_batches')
expected=json.loads((source/'d04-source.sha256.json').read_text())
with tarfile.open(source/'d04-source.tar.gz') as archive:
    assert set(archive.getnames())==set(expected)
    for member in archive.getmembers():
        assert member.isfile() and root in (root/member.name).resolve().parents
    archive.extractall(root,filter='data')
for name,sha in expected.items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==sha,name
print('D04 candidate package SHA verified; global scripts unchanged')
PY
cd /data2/FreeToken/runs/dev_D04/candidate
CUDA_VISIBLE_DEVICES='' FT_D04_ORIGINAL_STATE_EQ=$PWD/original/state_eq.py /data2/FreeToken/venv/bin/python -m unittest discover -s scripts/tests -p 'test_*.py' -v > ../stdlib_run1.log 2>&1 || { tail -n 65 ../stdlib_run1.log; exit 1; }
tail -n 12 ../stdlib_run1.log
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,pathlib,subprocess
root=pathlib.Path('/data2/FreeToken/runs/dev_D04')
history=pathlib.Path('/data2/_shared/runs/ft_rounds/E1-R003-stateeq')
py='/data2/FreeToken/venv/bin/python'
for name,test in [('B_B2','dump_B2'),('B_A','dump_A')]:
    outputs=[]
    for version,script in [('old',root/'candidate/original/state_eq.py'),('new',root/'candidate/scripts/state_eq.py')]:
        result=subprocess.run([py,str(script),str(history/'dump_B'),str(history/test)],text=True,capture_output=True)
        assert result.returncode in (0,1),(version,result.stderr)
        p=root/f'g3_{name}_{version}.txt'
        with p.open('x') as handle:
            handle.write(result.stdout)
        outputs.append(result)
    assert outputs[0].returncode==outputs[1].returncode
    old,new=([line for line in result.stdout.splitlines() if line.startswith('len=')] for result in outputs)
    assert old==new,(name,old,new)
    conclusion=next(line for line in outputs[1].stdout.splitlines() if line.startswith('结论'))
    assert ('恢复' in conclusion)==(test=='dump_A'),conclusion
    assert f'E1-R003-stateeq/{test}' in conclusion,conclusion
    print('D04 G3',name,'rc',outputs[1].returncode,'unchanged_length_lines',len(new))
    print(conclusion)
    print('output_sha256',hashlib.sha256(outputs[1].stdout.encode()).hexdigest())
print('D04 G2 TRANSACTION + G3 REAL LABEL REGRESSION PASS')
PY

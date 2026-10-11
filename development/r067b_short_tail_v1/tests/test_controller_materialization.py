"""Execute the actual corrected copy loop and guard its enclosing service identity."""
import ast
import json
from pathlib import Path
import shutil
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]


def service_loop(source):
    tree = ast.parse(source.replace('__ADMISSION_SHA256__', '0' * 64))
    return next(node for node in ast.walk(tree)
                if isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                and node.target.id == 'service')


def overwritten_service_names(source):
    loop = service_loop(source)
    return [node.target.id for node in ast.walk(loop)
            if isinstance(node, (ast.For, ast.AsyncFor))
            and isinstance(node.target, ast.Name) and node.target.id == 'name']


class ControllerMaterializationTest(unittest.TestCase):
    def setUp(self):
        self.original = json.loads((HERE / 'R067B_COMMAND_TEMPLATE.json').read_text())['child_source']
        self.corrected = json.loads((HERE / 'R067B_COMMAND_TEMPLATE_V2_CPU_ONLY.json').read_text())['child_source']

    def test_original_failure_is_reproduced(self):
        self.assertEqual(overwritten_service_names(self.original), ['name'])
        self.assertEqual(overwritten_service_names(self.corrected), [])

    def test_real_corrected_copy_loop_preserves_each_service_identity(self):
        node = next(node for node in ast.walk(service_loop(self.corrected))
                    if isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                    and node.target.id == 'artifact_name')
        code = compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
                       '<actual corrected materialization loop>', 'exec')
        filenames = ('t17_d14_startup.py', 't17_d14_exact_ids.py', 't17_d14_observe.py')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            source.mkdir()
            for filename in filenames:
                (source / filename).write_bytes(filename.encode())
            config = json.loads((HERE / 'R067B_CONFIG.json').read_text())
            self.assertEqual(len(config['services']), 10)
            for service in config['services']:
                arm = root / service['name']
                arm.mkdir()
                namespace = {'patch_tool': source, 'arm': arm, 'shutil': shutil,
                             'name': service['name']}
                exec(code, namespace)
                self.assertEqual(namespace['name'], service['name'])
                self.assertEqual(sorted(path.name for path in arm.iterdir()), sorted(filenames))
                for filename in filenames:
                    self.assertEqual((arm / filename).read_bytes(), (source / filename).read_bytes())


if __name__ == '__main__':
    unittest.main()

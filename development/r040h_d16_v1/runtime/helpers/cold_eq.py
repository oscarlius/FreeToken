import importlib.util, pathlib, runpy, sys
root=pathlib.Path(__file__).resolve().parent/'raw'
path=root/'probe_ft_cold32k.py'
spec=importlib.util.spec_from_file_location('probe_ft_cold32k',path)
module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module
spec.loader.exec_module(module)
assert pathlib.Path(module.__file__).resolve()==path.resolve()
runpy.run_path(str(root/'cold_eq.py'),run_name='__main__')

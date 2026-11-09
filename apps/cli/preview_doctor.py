"""Read-only startup diagnostics; never creates a catalog or a build job."""
import argparse
import importlib.metadata
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def diagnose(root, model_root, config, full_check=False):
    root=Path(root).resolve(); checks=[]
    def add(name,passed,detail,action=''):
        checks.append({'name':name,'status':'passed' if passed else 'failed','detail':detail,'action':action if not passed else ''})
    add('python',sys.version_info[:2]==(3,14),sys.version.split()[0],'使用项目Python 3.14环境。')
    for name in ('numpy','fastapi','pydantic','uvicorn'):
        try:
            importlib.import_module(name)
            add(name,True,importlib.metadata.version(name))
        except (ImportError,importlib.metadata.PackageNotFoundError) as exc:
            add(name,False,str(exc),'执行 uv sync --locked --extra preview。')
    def tool(name,expected):
        command=shutil.which(name)
        if not command:
            add(name,False,'未找到命令',f'安装{expected}后重试。'); return
        # Windows npm/pnpm command shims require cmd.exe; no user input is interpolated.
        args=['cmd','/c',name,'--version'] if sys.platform=='win32' else [command,'--version']
        try:
            version=subprocess.run(args,capture_output=True,text=True,timeout=10,check=True).stdout.strip()
            valid=version.lstrip('v').split('.')[0]=='24' if name=='node' else version=='10.32.1'
            add(name,valid,version,f'使用{expected}。')
        except (OSError,subprocess.SubprocessError) as exc:
            add(name,False,str(exc),f'检查{expected}命令。')
    tool('node','Node.js 24'); tool('pnpm','pnpm 10.32.1')
    try:
        from packages.data.preview_source_config import load_sources
        _,status=load_sources(root/config,root,full_check)
        status['loaded_at_startup']=False
        add('sources',True,status)
    except (ImportError,ValueError,OSError,KeyError,TypeError,IndexError) as exc:
        add('sources',False,str(exc),'检查来源配置和封存文件。')
    try:
        from packages.construction.preview_model import PreviewModel
        model=PreviewModel(root/model_root)
        add('initial_model',True,{'model_id':model.manifest['id'],'members':len(model.manifest['members'])})
    except (ImportError,ValueError,OSError,KeyError,TypeError) as exc:
        add('initial_model',False,str(exc),'按运行指南生成初始预览产物。')
    front=(root/'apps/workbench/dist/index.html').is_file()
    add('workbench',front,'检查 dist/index.html 是否存在','在 apps/workbench 执行 pnpm install --frozen-lockfile 和 pnpm run build。')
    return {'profile':'cospace.preview-doctor/0.1','status':'passed' if all(c['status']=='passed' for c in checks) else 'failed',
            'full_source_check':full_check,'checks':checks,
            'scope':'local_files_and_runtime_only; no HTTP, port or browser check'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path.cwd())
    p.add_argument('--model',type=Path,default=Path('var/nyu/office-0001a-flow-001'))
    p.add_argument('--config',type=Path,default=Path('deploy/config/preview-sources.json'))
    p.add_argument('--full-check',action='store_true')
    a=p.parse_args(); report=diagnose(a.root,a.model,a.config,a.full_check)
    print(json.dumps(report,ensure_ascii=True)); return 0 if report['status']=='passed' else 1


if __name__=='__main__': sys.exit(main())

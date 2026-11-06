"""Cold backup/verify/restore CLI. Stop the managed server before backup.

Restore requires an absent original absolute root. Sessions and credentials are
not included; retain the printed SHA-256 separately and log in after restarting.
"""
import argparse
import json
import sqlite3
import zipfile
from pathlib import Path
from packages.infrastructure.preview_backup import backup,verify,restore
from packages.infrastructure.platform_identity import IdentityUnavailable


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    b=sub.add_parser('backup');b.add_argument('--root',type=Path,required=True);b.add_argument('--output',type=Path,required=True)
    b.add_argument('--actor',required=True);b.add_argument('--reason',required=True)
    for name in ('verify','restore'):
        s=sub.add_parser(name);s.add_argument('--archive',type=Path,required=True);s.add_argument('--sha256',required=True)
        if name=='restore':s.add_argument('--root',type=Path,required=True)
    a=p.parse_args()
    try:
        if a.command=='backup':result=backup(a.root,a.output,actor=a.actor,reason=a.reason)
        elif a.command=='verify':result=verify(a.archive,a.sha256)
        else:result=restore(a.archive,a.root,a.sha256)
        # Detailed file inventory stays inside the archive; CLI prints the receipt.
        print(json.dumps({k:v for k,v in result.items() if k!='manifest'},ensure_ascii=False))
    except (ValueError,OSError,KeyError,TypeError,sqlite3.Error,zipfile.BadZipFile,IdentityUnavailable) as exc:
        p.exit(2,'backup_rejected: '+str(exc)+'\n')


if __name__=='__main__':main()

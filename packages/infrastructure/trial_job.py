"""Windows trial process tree dies with its owner, including abrupt termination.

The non-inheritable handle is held for process lifetime, not closed in a context
manager (the owner is itself a member). Fail before serving on unsupported hosts.
"""
import ctypes as c
from ctypes import wintypes as w
import os

_handle=None


def bind_trial_process():
    global _handle
    if _handle is not None:return
    if os.name!='nt':raise RuntimeError('windows_trial_host_required')
    size=c.c_size_t
    class Basic(c.Structure):
        _fields_=[('process_time',c.c_longlong),('job_time',c.c_longlong),('flags',w.DWORD),
            ('min_ws',size),('max_ws',size),('active_limit',w.DWORD),('affinity',size),('priority',w.DWORD),('scheduling',w.DWORD)]
    class IO(c.Structure):
        _fields_=[(n,c.c_ulonglong) for n in ('ro','wo','oo','rb','wb','ob')]
    class Limits(c.Structure):
        _fields_=[('basic',Basic),('io',IO),('process_memory',size),('job_memory',size),('peak_process',size),('peak_job',size)]
    kernel=c.WinDLL('kernel32',use_last_error=True)
    def fn(name,result,*args):
        value=getattr(kernel,name);value.restype=result;value.argtypes=args;return value
    create=fn('CreateJobObjectW',w.HANDLE,c.c_void_p,w.LPCWSTR)
    set_info=fn('SetInformationJobObject',w.BOOL,w.HANDLE,c.c_int,c.c_void_p,w.DWORD)
    assign=fn('AssignProcessToJobObject',w.BOOL,w.HANDLE,w.HANDLE)
    current=fn('GetCurrentProcess',w.HANDLE)
    close=fn('CloseHandle',w.BOOL,w.HANDLE)
    handle=create(None,None)
    if not handle:raise OSError('trial_job_create_failed')
    limits=Limits();limits.basic.flags=0x2000 # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not set_info(handle,9,c.byref(limits),c.sizeof(limits)) or not assign(handle,current()):
        close(handle);raise OSError('trial_job_assignment_failed')
    _handle=handle

"""Request-local durations only. No identity, credentials, URLs or payloads."""
from contextvars import ContextVar
from time import perf_counter

_current=ContextVar('request_timings',default=None)


def timed_call(name,function,*args,**kwargs):
    started=perf_counter()
    try:return function(*args,**kwargs)
    finally:
        values=_current.get()
        if values is not None:values[name]=values.get(name,0)+(perf_counter()-started)*1000


def begin():
    values={}
    return _current.set(values),values,perf_counter()


def finish(token,values,started):
    _current.reset(token)
    values['total']=(perf_counter()-started)*1000
    return ', '.join(f'{name};dur={duration:.2f}' for name,duration in values.items())

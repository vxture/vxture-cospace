"""J4 child-process barriers around a real synthetic file-session query."""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

from experiments.scripts.recovery_state import RecoveryStore
from experiments.scripts.recovery_session import RecoverySession
from experiments.scripts.validity_probe import Policy, IntervalClock, GateError
from experiments.scripts.trust_proof import load_test_trust
from packages.infrastructure.agent_files import FilePackages

REPO = Path(__file__).resolve().parents[2]


def emit(value):
    print(json.dumps({'pid': os.getpid(), **value}), flush=True)


def actor(request):
    data = json.loads(Path(request).read_text(encoding='utf-8'))
    def opened():
        return RecoveryStore(data['journal'], load_test_trust(json.dumps(data['trust']).encode()), Policy(**data['policy']))
    ledger = opened()
    files = FilePackages(data['files'])
    clock = IntervalClock(lambda: ('child', 0), ('child', 0, 110, 110))
    def new_session(store):
        return RecoverySession(files, data['binding']['scene_id'], store, data['binding'], clock)
    session = new_session(ledger)
    def pause(stage):
        emit({'barrier': stage})
        if sys.stdin.readline().strip() != 'release':
            raise RuntimeError('barrier was not released')
    emit({'opened': True, 'generation': ledger.generation})
    try:
        for command in sys.stdin:
            command = command.strip()
            if command == 'exit':
                break
            if command == 'query_locked':
                ledger._decision_snapshot = lambda: pause('decision_locked')
            elif command == 'query_after_gate':
                original = session.session.query
                def query(point):
                    pause('gate_passed')
                    return original(point)
                session.session.query = query
            elif command == 'fresh_query':
                session.close()
                ledger = opened()
                try:
                    session = new_session(ledger)
                except GateError as error:
                    emit({'error': error.code})
                    continue
            elif command != 'query':
                raise RuntimeError('unknown child command')
            try:
                emit({'query': session.query([1, 0, 1])})
            except GateError as error:
                emit({'error': error.code})
            finally:
                ledger._decision_snapshot = lambda: None
                if command == 'query_after_gate':
                    session.session.query = original
    finally:
        session.close()


class SessionChild:
    def __init__(self, request):
        paths = [str(REPO), str(Path(sys.prefix) / 'Lib/site-packages')]
        code = 'import sys,runpy;sys.path[:0]=' + repr(paths) + ";runpy.run_module('experiments.scripts.recovery_concurrency',run_name='__main__')"
        self.process = subprocess.Popen([sys._base_executable, '-c', code, str(request)], cwd=REPO,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
        self.messages = queue.Queue()
        def read():
            try:
                for line in self.process.stdout:
                    self.messages.put(json.loads(line))
            finally:
                self.messages.put(None)
        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()

    def receive(self):
        value = self.messages.get(timeout=15)
        if value is None:
            raise AssertionError('session child exited: ' + self.process.stderr.read())
        assert value['pid'] == self.process.pid
        return value

    def send(self, command):
        self.process.stdin.write(command + '\n')
        self.process.stdin.flush()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=10)
        self.reader.join(timeout=2)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request')
    actor(parser.parse_args().request)

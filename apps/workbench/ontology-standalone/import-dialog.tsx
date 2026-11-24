import {useEffect, useRef, useState} from 'react';
import {Button, Drawer, Input} from '@vxture/design-system';
import {explain, maxPackageBytes, type Client, type Preflight} from './client';

export function ImportDialog({client, close, imported}: {client: Client; close: () => void; imported: (id: string) => void}) {
  const [file, setFile] = useState<File|null>(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [ready, setReady] = useState<{text:string; plan:Preflight; requestId:string}|null>(null);
  const active = useRef<AbortController|null>(null);
  useEffect(() => () => active.current?.abort(), []);
  async function run(save: boolean) {
    if (active.current || !file || save && !ready?.plan.can_import) return;
    const c = new AbortController();active.current = c;setBusy(true);setError('');
    try {
      if (save && ready) {
        await client.importDraft(ready.text, ready.plan.expected_revision, ready.requestId, c.signal);
        if (!c.signal.aborted) imported(ready.plan.reference.module_id);
      } else {
        setReady(null);
        if (file.size > maxPackageBytes) throw Error('定义包超过大小限制。');
        let text: string;
        try {text = new TextDecoder('utf-8', {fatal:true, ignoreBOM:true}).decode(await file.arrayBuffer());}
        catch {throw Error('请选择有效的 UTF-8 JSON 文件。');}
        const plan = await client.preflight(text, c.signal);
        if (!c.signal.aborted) setReady({text, plan, requestId:crypto.randomUUID().replaceAll('-', '')});
      }
    } catch (e) {if (!c.signal.aborted) setError((e as Error).message);}
    finally {active.current = null;if (!c.signal.aborted) setBusy(false);}
  }
  return <Drawer open onClose={() => {if (!busy) close();}} side="right" width="md" title="导入定义包"
    footer={<div className="ontology-membership-footer"><Button variant="outline" size="sm" disabled={busy} onClick={close}>取消</Button>
      {ready?.plan.can_import ? <Button size="sm" disabled={busy} onClick={() => void run(true)}>保存为草稿</Button> :
        <Button size="sm" disabled={!file || busy} onClick={() => void run(false)}>预检</Button>}</div>}>
    <div className="ontology-form-stack">
      <label>原生定义包<Input type="file" accept=".json,application/json" disabled={busy} onChange={e => {setFile(e.target.files?.[0] || null);setReady(null);setError('');}} /></label>
      {error && <p role="alert" className="ontology-form-error">{error}</p>}
      {ready && <section className="standalone-stack" aria-label="预检结果">
        <h3 className="standalone-section-title">{ready.plan.reference.module_id} · {ready.plan.reference.version}</h3>
        <p role="status">{ready.plan.can_import ? '可以保存为草稿。' : '预检未通过。'}</p>
        {ready.plan.expected_revision > 0 && <p>当前已有草稿修订 {ready.plan.expected_revision}，保存后更新为新修订。</p>}
        {ready.plan.diagnostics.map(d => <p key={d.code + d.path} className="ontology-form-error">{explain(d.code)} {d.path}</p>)}
        {!!ready.plan.dependencies.length && <ul>{ready.plan.dependencies.map(d => <li key={d.reference.module_id}>
          {d.reference.module_id} · {d.reference.version} · {d.state === 'published' ? '已发布' : '待发布后才能送审'}
        </li>)}</ul>}
      </section>}
    </div>
  </Drawer>;
}

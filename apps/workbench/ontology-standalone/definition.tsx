import {useEffect, useRef, useState} from 'react';
import {CaretLeft} from '@phosphor-icons/react';
import {Button, NativeSelect} from '@vxture/design-system';
import {OntologyLibrary, type LibrarySelection} from '@vxture/ontology-ui';
import type {WorkbenchState} from '@vxture/ontology-ui/authoring-contract';
import type {Entry, Library, Reference} from '@vxture/ontology-ui/contract';
import type {Client} from './client';
import {dateLabel} from './catalog';

export function Definition({client, entry, onBack}: {client: Client; entry: Entry; onBack: () => void}) {
  const identity = entry.reference.module_id;
  const [reference, setReference] = useState(entry.reference), [library, setLibrary] = useState<Library|null>(null);
  const [selection, setSelection] = useState<LibrarySelection>({moduleId: identity});
  const [versions, setVersions] = useState<WorkbenchState['releases']>([]), [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0), [exporting, setExporting] = useState(false);
  const exportCall = useRef<AbortController|null>(null);
  useEffect(() => {
    const c = new AbortController();
    void client.authoring.read(identity, c.signal).then(data => {if (!c.signal.aborted) setVersions(data.releases);})
      .catch(e => {if (!c.signal.aborted) setError(e.message);});
    return () => {c.abort();exportCall.current?.abort();};
  }, [client, identity, refresh]);
  useEffect(() => {
    const c = new AbortController();
    void client.definition(reference, c.signal).then(value => {if (!c.signal.aborted) setLibrary(value);})
      .catch(e => {if (!c.signal.aborted) setError(e.message);});
    return () => c.abort();
  }, [client, reference, refresh]);
  const released = versions.find(v => v.reference.sha256 === reference.sha256) ||
    (entry.published_at && entry.reference.sha256 === reference.sha256 ? {published_at: entry.published_at, reference} : undefined);
  const options = versions.some(v => v.reference.sha256 === entry.reference.sha256) ? versions :
    [{reference: entry.reference, published_at: entry.published_at}, ...versions];
  function select(next: Reference) {
    setError('');setLibrary(null);setReference(next);setSelection({moduleId:identity});
  }
  async function download() {
    const c = new AbortController();exportCall.current = c;setExporting(true);setError('');
    try {
      const raw = await client.export(reference, c.signal);
      if (c.signal.aborted) return;
      const url = URL.createObjectURL(new Blob([raw], {type:'application/json'}));
      const link = document.createElement('a');link.href=url;link.download=`${identity}-${reference.version}.ontology.json`;link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {if (!c.signal.aborted) setError((e as Error).message);}
    finally {if (!c.signal.aborted) setExporting(false);}
  }
  return <section className="standalone-stack" aria-label="固定定义">
    <div className="standalone-toolbar standalone-version-bar">
      <Button variant="ghost" size="icon-sm" aria-label="返回本体清单" title="返回本体清单" onClick={onBack}><CaretLeft size={20} /></Button>
      <span className="standalone-count">{released ? `发布于 ${dateLabel(released.published_at)}` : '候选定义'}</span>
      <NativeSelect wrapperClassName="standalone-filter" aria-label="选择固定版本" value={reference.sha256} disabled={exporting}
        onChange={e => {const next = options.find(v => v.reference.sha256 === e.target.value);if(next) select(next.reference);}}>
        {options.map(v => <option key={v.reference.sha256} value={v.reference.sha256}>{v.reference.version}{v.published_at ? ' · 已发布' : ' · 候选'}</option>)}
      </NativeSelect>
      {released && <Button variant="outline" size="sm" disabled={exporting} onClick={() => void download()}>导出固定定义</Button>}
    </div>
    {error && <div className="standalone-toolbar"><p role="alert" className="ontology-form-error">{error}</p><Button variant="outline" size="sm" onClick={() => {setError('');setRefresh(v => v + 1);}}>重试</Button></div>}
    {!library && !error && <p role="status">正在读取固定定义…</p>}
    {library && <OntologyLibrary library={library} selection={selection} onSelect={setSelection} completeLibrary={false}
      definitionStatus={selection.moduleId !== identity ? 'dependency' : released ? 'published' : undefined}
      onBack={selection.kind || selection.moduleId !== identity ? () => setSelection({moduleId: identity}) : undefined} actions={<></>} />}
  </section>;
}

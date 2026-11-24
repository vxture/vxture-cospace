import {useEffect, useMemo, useRef, useState, type FormEvent} from 'react';
import {createRoot} from 'react-dom/client';
import {Books, CaretLeft, GearSix, PaperPlaneTilt, PencilSimple, SidebarSimple, SignOut} from '@phosphor-icons/react';
import {Button, Drawer, Input, ShellPageContainer, ShellSidebarFrame, ShellSidebarNav, useMediaQuery, type ShellNavSection} from '@vxture/design-system';
import {DefinitionWorkspace} from '@vxture/ontology-ui/authoring';
import {OntologyGroupConfiguration} from '@vxture/ontology-ui/group-configuration';
import type {Library} from '@vxture/ontology-ui/contract';
import {Catalog, type CatalogItem} from './catalog';
import {createClient, moduleId, type DraftSummary, type Session} from './client';
import {Definition} from './definition';
import {ImportDialog} from './import-dialog';
import './styles.css';

const navigation = [
  {id:'view', label:'查看', icon:Books, title:'本体清单', description:'查看通用核心、领域定义及固定发布版本。'},
  {id:'edit', label:'编辑', icon:PencilSimple, title:'编辑本体', description:'维护概念、属性、关系和固定依赖，或导入原生定义包。'},
  {id:'release', label:'发布', icon:PaperPlaneTilt, title:'本体发布', description:'校验、送审和发布固定版本，保留历史定义。'},
  {id:'settings', label:'系统配置', icon:GearSix, title:'系统配置', description:'维护本机本体作用域的分组和顺序。'},
] as const;
type View = typeof navigation[number]['id'];
type Route = {view:View; id:string};
const discard = '有未保存的更改或正在处理的操作。确定离开当前页面？';

function allowed(session: Session) {
  const grants = session.permissions;
  const read = grants.includes('read'), privateRead = read && grants.includes('read_private');
  return navigation.filter(n => n.id === 'view' ? read : n.id === 'edit' ? privateRead && grants.includes('edit') :
    n.id === 'release' ? privateRead && grants.some(p => p === 'submit' || p === 'review' || p === 'publish') : grants.includes('configure_groups'));
}

function href({view, id}: Route) {return `#/${view}${id ? '/' + id : ''}`;}
function route(views: ReturnType<typeof allowed>): Route {
  const [view, id, extra] = location.hash.replace(/^#\//, '').split('/');
  return {view:views.find(n => n.id === view)?.id || views[0].id,
    id:views.some(n => n.id === view) && view !== 'settings' && !extra && moduleId.test(id || '') ? id : ''};
}

function Workbench({token, session, signOut}: {token:string;session:Session;signOut:()=>void}) {
  const client = useMemo(() => createClient(token, signOut), [token, signOut]);
  const views = useMemo(() => allowed(session), [session]);
  const [current, setCurrent] = useState(() => route(views)), [dirty, setDirty] = useState(false);
  const [loaded, setLoaded] = useState<{key:string; library?:Library; drafts?:DraftSummary[]; error?:string}|null>(null);
  const [refresh, setRefresh] = useState(0), [importOpen, setImportOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false), [collapsed, setCollapsed] = useState(false);
  const narrow = useMediaQuery('(max-width:639px)');
  const outlet = useRef<HTMLElement|null>(null);
  const active = views.find(n => n.id === current.view)!;
  const loadKey = `${current.view}:${current.id ? 'detail' : 'list'}:${refresh}`;
  const {library, drafts, error} = loaded?.key === loadKey ? loaded : {};
  useEffect(() => {
    if (location.hash !== href(current)) history.replaceState(null, '', href(current));
    function changed() {
      const next = route(views);
      if (href(next) === href(current)) return;
      if (dirty && !window.confirm(discard)) {history.replaceState(null, '', href(current));return;}
      setDirty(false);setImportOpen(false);setCurrent(next);
    }
    function leave(event: BeforeUnloadEvent) {if(dirty){event.preventDefault();event.returnValue='';}}
    window.addEventListener('hashchange', changed);window.addEventListener('beforeunload', leave);
    return () => {window.removeEventListener('hashchange', changed);window.removeEventListener('beforeunload', leave);};
  }, [views, current, dirty]);
  useEffect(() => {outlet.current?.scrollTo(0,0);}, [current]);
  useEffect(() => {
    const c = new AbortController();
    if (current.view === 'settings') return () => c.abort();
    void Promise.all([client.directory(c.signal), current.view === 'view' ? Promise.resolve([]) : client.drafts(c.signal)])
      .then(([library, drafts]) => {if(!c.signal.aborted)setLoaded({key:loadKey,library,drafts});})
      .catch(e => {if(!c.signal.aborted)setLoaded({key:loadKey,error:e.message});});
    return () => c.abort();
  }, [client, current.view, loadKey]);
  function go(next: Route) {
    if (href(next) === href(current)) return;
    if (dirty && !window.confirm(discard)) return;
    history.pushState(null, '', href(next));setImportOpen(false);setNavOpen(false);setDirty(false);setCurrent(next);
  }
  const back = () => go({view:current.view,id:''});
  const listed = new Map<string, CatalogItem>(library?.modules.map(entry => [entry.reference.module_id,
    {entry, id:entry.reference.module_id, title:entry.definition.title}]));
  if (current.view !== 'view' && drafts) for (const draft of drafts) {
    listed.set(draft.module_id, {...listed.get(draft.module_id), id:draft.module_id, title:draft.title || draft.module_id, draft});
  }
  const selected = listed.get(current.id);
  const items = [...listed.values()].filter(item => current.view !== 'release' || item.draft || item.entry?.published_at);
  const icons = {view:'database',edit:'edit',release:'upload',settings:'settings'} as const;
  const sections:ShellNavSection[] = ['本体资源','系统管理'].flatMap((title,index) => {
    const items = views.filter(n => (n.id === 'settings') === !!index).map(n => ({href:href({view:n.id,id:''}), label:n.label, icon:icons[n.id]}));
    return items.length ? [{title,items}] : [];
  });
  const nav = <div className="standalone-sidebar-content" onClickCapture={e => {
    const anchor = (e.target as HTMLElement).closest('a');
    if (!anchor || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const next = views.find(n => anchor.getAttribute('href') === href({view:n.id,id:''}));
    if(next){e.preventDefault();go({view:next.id,id:''});}
  }}><ShellSidebarNav domainName="语义本体" sections={sections} collapsed={!narrow && collapsed}
    onToggleCollapsed={() => narrow ? setNavOpen(false) : setCollapsed(v => !v)} isActive={url => url === href({view:current.view,id:''})}
    storageKeyPrefix="vxture.ontology.navigation" labels={{expandNav:'展开本体导航',collapseNav:'收起本体导航',expandAllGroups:'展开分组',collapseAllGroups:'收起分组'}} /></div>;
  return <div className="standalone-shell">
    <header className="standalone-header"><div className="standalone-brand">{narrow && <Button size="icon-sm" variant="ghost" aria-label="展开本体导航" onClick={() => setNavOpen(true)}><SidebarSimple size={20} /></Button>}<Books size={24} aria-hidden="true" /><strong>语义本体</strong></div>
      <div className="standalone-account"><span>{session.actor} · {session.scope}</span><Button variant="ghost" size="icon-sm" title="退出" aria-label="退出" onClick={() => {if(!dirty || window.confirm(discard))signOut();}}><SignOut size={20} /></Button></div>
    </header>
    {narrow ? <Drawer open={navOpen} onClose={() => setNavOpen(false)} side="left" width="sm" title="本体导航">{nav}</Drawer> :
      <div className="standalone-sidebar"><ShellSidebarFrame mode={collapsed?'collapsed':'expanded'}>{nav}</ShellSidebarFrame></div>}
    <main className="standalone-content" ref={outlet}>
      <ShellPageContainer width="wide-2xl" className="standalone-frame">
        {!(current.view === 'view' && current.id && selected?.entry) && <header className="standalone-heading">
          <div className="standalone-title-line">{!!current.id && <Button variant="ghost" size="icon-sm" aria-label="返回清单" onClick={back}><CaretLeft size={20} /></Button>}
            <h1>{selected && current.id ? selected.title : active.title}</h1></div>
          <p>{selected && current.id ? `${selected.id} · ${active.label}` : active.description}</p>
        </header>}
        {current.view === 'settings' ? <OntologyGroupConfiguration client={client.configuration} onDirtyChange={setDirty} /> :
          error ? <div className="standalone-toolbar"><p role="alert" className="ontology-form-error">{error}</p><Button size="sm" variant="outline" onClick={() => setRefresh(v => v+1)}>重试</Button></div> :
          (!library || !drafts) ? <p role="status">正在读取本体清单…</p> :
          !current.id ? <Catalog key={current.view} items={items} mode={current.view} onOpen={id => go({view:current.view,id})}
            actions={<><Button size="sm" variant="outline" onClick={() => setRefresh(v => v+1)}>刷新</Button>
              {current.view === 'edit' && <Button size="sm" onClick={() => setImportOpen(true)}>导入定义包</Button>}</>} /> :
          !selected ? <p role="alert">此本体不在当前清单中。</p> :
          current.view === 'view' && selected.entry ? <Definition key={selected.id} client={client} entry={selected.entry} onBack={back} /> :
          current.view !== 'view' && <DefinitionWorkspace key={current.view + ':' + current.id} client={client.authoring} selection={{moduleId:current.id}}
            mode={current.view} permissions={session.permissions} onDirtyChange={setDirty} />}
        {importOpen && <ImportDialog client={client} close={() => setImportOpen(false)} imported={id => {setRefresh(v => v+1);go({view:'edit',id});}} />}
      </ShellPageContainer>
    </main>
  </div>;
}

function App() {
  const [token, setToken] = useState(''), [input, setInput] = useState(''), [session, setSession] = useState<Session|null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const signOut = useRef(() => {setSession(null);setToken('');setInput('');}).current;
  async function login(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const value = input.trim();
    if (!/^[a-zA-Z0-9_-]{43}$/.test(value)) {setError('请输入本机管理员签发的访问令牌。');return;}
    setBusy(true);setError('');
    try {
      const current = await createClient(value).session(AbortSignal.timeout(10000));
      if (!allowed(current).length) throw Error('该身份没有可用的工作台权限。');
      setInput('');setToken(value);setSession(current);
    } catch (e) {setError((e as Error).message);}
    finally {setBusy(false);}
  }
  if (session) return <Workbench token={token} session={session} signOut={signOut} />;
  return <main className="standalone-sign-in">
    <form className="standalone-stack" onSubmit={e => void login(e)}>
      <div className="standalone-brand"><Books size={28} aria-hidden="true" /><h1>语义本体</h1></div>
      <p>使用本机访问令牌进入独立工作台。</p>
      <label>访问令牌<Input type="password" autoComplete="off" spellCheck={false} value={input} maxLength={96}
        disabled={busy} onChange={e => setInput(e.target.value)} required /></label>
      {error && <p role="alert" className="ontology-form-error">{error}</p>}
      <Button type="submit" disabled={busy}>{busy ? '正在验证…' : '进入工作台'}</Button>
    </form>
  </main>;
}

createRoot(document.getElementById('root')!).render(<App />);

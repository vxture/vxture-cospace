import {useState, type ReactNode} from 'react';
import {DotsThreeVertical, Eye, PaperPlaneTilt, PencilSimple} from '@phosphor-icons/react';
import {Button, Input, NativeSelect, StatusBadge, Table, TableHeader, TableBody, TableHead, TableRow, TableCell,
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem} from '@vxture/design-system';
import type {Entry} from '@vxture/ontology-ui/contract';
import type {DraftSummary} from './client';

export type CatalogItem = {id: string; title: string; entry?: Entry; draft?: DraftSummary};
export const dateLabel = (date: string) => new Date(date).toLocaleDateString('zh-CN');

export function Catalog({items, mode, onOpen, actions}: {items: CatalogItem[]; mode: 'view'|'edit'|'release';
  onOpen: (id: string) => void; actions?: ReactNode}) {
  const [query, setQuery] = useState(''), [layer, setLayer] = useState(''), [page, setPage] = useState(1);
  const q = query.trim().toLocaleLowerCase();
  const matches = items.filter(({id, title, entry}) => (!layer || entry?.definition.layer === layer) &&
    [id, title, entry?.definition.description || ''].some(value => value.toLocaleLowerCase().includes(q)))
    .sort((a, b) => a.title.localeCompare(b.title, 'zh-CN') || a.id.localeCompare(b.id));
  const size = 12, pages = Math.max(1, Math.ceil(matches.length / size)), current = Math.min(page, pages);
  const ActionIcon = mode === 'view' ? Eye : mode === 'edit' ? PencilSimple : PaperPlaneTilt;
  return <section className="standalone-stack" aria-label="本体清单">
    <div className="standalone-toolbar">
      <span role="status" className="standalone-count">共 {matches.length} 项</span>
      <Input aria-label="搜索本体" placeholder="搜索本体" value={query} maxLength={160} onChange={e => {setQuery(e.target.value);setPage(1);}} />
      {mode === 'view' && <NativeSelect wrapperClassName="standalone-filter" aria-label="筛选层级" value={layer} onChange={e => {setLayer(e.target.value);setPage(1);}}>
        <option value="">全部层级</option><option value="core">通用核心</option><option value="domain">领域本体</option>
      </NativeSelect>}
      {actions}
    </div>
    <div className="standalone-table">
      <Table><TableHeader><TableRow>
        <TableHead className="standalone-index">序号</TableHead><TableHead>本体名称 / 标识</TableHead>
        <TableHead>{mode === 'view' ? '层级' : '草稿修订'}</TableHead><TableHead>版本</TableHead><TableHead className="standalone-index" data-table-actions>操作</TableHead>
      </TableRow></TableHeader><TableBody>
        {matches.slice((current - 1) * size, current * size).map(({id, title, entry, draft}, index) => <TableRow key={id}>
          <TableCell className="standalone-index">{(current - 1) * size + index + 1}</TableCell>
          <TableCell className="standalone-name"><div className="standalone-name-line"><Button variant="link" size="sm" onClick={() => onOpen(id)}>{title}</Button>
            {mode === 'view' && <StatusBadge tone={entry?.published_at ? 'success' : 'warning'}>{entry?.published_at ? '已发布' : '草案'}</StatusBadge>}</div>
            <span className="ontology-identity">{id}</span>{mode === 'view' && <p className="standalone-description">{entry?.definition.description}</p>}
          </TableCell>
          <TableCell>{mode === 'view' ? entry?.definition.layer === 'core' ? '通用核心' : '领域本体' : draft ? `修订 ${draft.revision}` : '—'}</TableCell>
          <TableCell>{draft?.version || entry?.reference.version || '—'}{mode === 'view' && entry?.published_at && <small className="standalone-description">{dateLabel(entry.published_at)}</small>}</TableCell>
          <TableCell className="standalone-index" data-table-actions><DropdownMenu>
            <DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" className="standalone-row-menu" aria-label={title + '更多操作'}><DotsThreeVertical size={24} /></Button></DropdownMenuTrigger>
            <DropdownMenuContent align="end"><DropdownMenuItem onSelect={() => onOpen(id)}><ActionIcon size={16} />{mode === 'view' ? '查看本体' : mode === 'edit' ? '编辑本体' : '打开发布记录'}</DropdownMenuItem></DropdownMenuContent>
          </DropdownMenu></TableCell>
        </TableRow>)}
      </TableBody></Table>
    </div>
    {!matches.length && <p className="standalone-empty">{q || layer ? '没有匹配的本体。' : '当前没有可用的本体。'}</p>}
    {pages > 1 && <div className="standalone-toolbar"><span className="standalone-count">第 {current} / {pages} 页</span>
      <Button variant="outline" size="sm" disabled={current === 1} onClick={() => setPage(current - 1)}>上一页</Button>
      <Button variant="outline" size="sm" disabled={current === pages} onClick={() => setPage(current + 1)}>下一页</Button>
    </div>}
  </section>;
}

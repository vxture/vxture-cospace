"""Portable resource organization, independent of definition content and host identity."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import re

from .group_configuration import GroupConfigurationStore, PRESETS, clean_text
from .kernel import canonical_bytes


class ResourceDirectoryError(ValueError):
    pass


class ResourceDirectory:
    def __init__(self, root, library):
        self.configuration = GroupConfigurationStore(root)
        self.library = library
        self.entries = {e['reference']['module_id']: e for e in library['modules']}

    def connect(self):
        connection = self.configuration.connect()
        try:
            connection.execute('CREATE TABLE IF NOT EXISTS resource_memberships (scope TEXT NOT NULL, module_id TEXT NOT NULL, revision INTEGER NOT NULL, groups_json TEXT NOT NULL, PRIMARY KEY(scope,module_id))')
            connection.execute('CREATE TABLE IF NOT EXISTS resource_events (scope TEXT NOT NULL, request_id TEXT NOT NULL, payload_hash TEXT NOT NULL, actor TEXT NOT NULL, changed_at TEXT NOT NULL, module_id TEXT NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL, PRIMARY KEY(scope,request_id))')
            connection.commit()
            return connection
        except BaseException:
            connection.close()
            raise

    def membership(self, connection, scope, identity):
        row = connection.execute('SELECT revision,groups_json FROM resource_memberships WHERE scope=? AND module_id=?', (scope, identity)).fetchone()
        if row is None:
            # Virtual seed: an explicit empty override remains empty forever.
            return {'revision': 0, 'group_ids': ['preset-'+identity] if identity in dict(PRESETS) else []}
        try:
            ids = json.loads(row[1])
            if type(row[0]) is not int or row[0] < 1 or not isinstance(ids, list) or len(ids) > 100 or any(not isinstance(g, str) for g in ids) or len(ids) != len(set(ids)):
                raise ValueError()
            return {'revision': row[0], 'group_ids': ids}
        except (ValueError, TypeError) as exc:
            raise ResourceDirectoryError('ontology_directory_unavailable') from exc

    def read(self, scope, query):
        if set(query)-{'layer','q','group','sort','page','page_size','snapshot'}:
            raise ResourceDirectoryError('ontology_directory_invalid_request')
        layer, term, group, sort = (query.get(k, '') for k in ('layer','q','group','sort'))
        if layer not in ('','core','domain') or sort not in ('','title','id') or len(term)>160 or len(group)>80:
            raise ResourceDirectoryError('ontology_directory_invalid_request')
        try:
            page, size = int(query.get('page','1')), int(query.get('page_size','10'))
            if not 1 <= page <= 1000000 or not 1 <= size <= 50: raise ValueError()
        except (TypeError, ValueError) as exc:
            raise ResourceDirectoryError('ontology_directory_invalid_request') from exc
        scope = self.configuration.scope_key(scope)
        with closing(self.connect()) as connection, connection:
            connection.execute('BEGIN')
            config_revision, groups = self.configuration.state(connection, scope)
            groups = sorted(groups, key=lambda g:(g['sort_order'],g['group_id']))
            known = {g['group_id'] for g in groups}
            if group and group != 'ungrouped' and group not in known:
                raise ResourceDirectoryError('ontology_directory_invalid_request')
            all_entries = []
            for identity, entry in self.entries.items():
                d=entry['definition']; membership=self.membership(connection,scope,identity)
                if not set(membership['group_ids']) <= known:
                    raise ResourceDirectoryError('ontology_directory_unavailable')
                searchable=json.dumps(d,ensure_ascii=False).casefold()
                all_entries.append({'reference':entry['reference'],'title':d['title'],'description':d['description'],
                    'layer':d['layer'],'status':d['status'],'published_at':entry.get('published_at'),'concept_count':len(d['concepts']),
                    'relation_count':len(d['relations']),**membership,'_search':searchable})
            snapshot=hashlib.sha256(json.dumps([self.library['library_sha256'],config_revision,[(e['reference']['module_id'],e['revision']) for e in all_entries]],sort_keys=True).encode()).hexdigest()
            if query.get('snapshot') and query['snapshot']!=snapshot:
                raise ResourceDirectoryError('ontology_directory_changed')
            entries=[e for e in all_entries if (not layer or e['layer']==layer) and (not term.strip() or term.strip().casefold() in e['_search']) and (not group or (not e['group_ids'] if group=='ungrouped' else group in e['group_ids']))]
            entries.sort(key=lambda e:((e['reference']['module_id'] if sort=='id' else e['title']),e['reference']['module_id']))
            total=len(entries)
            page=min(page,max(1,(total+size-1)//size))
            items=[{k:v for k,v in e.items() if k!='_search'} for e in entries[(page-1)*size:page*size]]
            return {'profile':'vxture.ontology-directory/0.1','snapshot':snapshot,'page':page,'page_size':size,'total':total,
                'items':items,'groups':[{k:g[k] for k in ('group_id','name','status')} for g in groups]}

    def change(self, scope, actor, body):
        fields={'request_id','module_id','expected_revision','group_ids'}
        if not isinstance(body,dict) or set(body)!=fields or not isinstance(body['request_id'],str) or not re.fullmatch('[a-f0-9]{32}',body['request_id']) or not isinstance(body['module_id'],str) or body['module_id'] not in self.entries or type(body['expected_revision']) is not int or body['expected_revision']<0:
            raise ResourceDirectoryError('ontology_directory_invalid_request')
        ids=body['group_ids']
        if not isinstance(ids,list) or len(ids)>100 or any(not isinstance(g,str) or len(g)>80 for g in ids) or len(set(ids))!=len(ids):
            raise ResourceDirectoryError('ontology_directory_invalid_request')
        scope=self.configuration.scope_key(scope);actor=clean_text(actor,500,True)
        payload={**body,'group_ids':sorted(ids)}
        digest=hashlib.sha256(json.dumps([actor,payload],sort_keys=True).encode()).hexdigest()
        with closing(self.connect()) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            previous=connection.execute('SELECT payload_hash,after_json FROM resource_events WHERE scope=? AND request_id=?',(scope,body['request_id'])).fetchone()
            if previous:
                if previous[0]!=digest:raise ResourceDirectoryError('ontology_directory_request_conflict')
                return json.loads(previous[1])
            before=self.membership(connection,scope,body['module_id'])
            if before['revision']!=body['expected_revision']:
                raise ResourceDirectoryError('ontology_directory_revision_changed')
            _,groups=self.configuration.state(connection,scope)
            statuses={g['group_id']:g['status'] for g in groups}
            if any(g not in statuses or statuses[g]!='active' and g not in before['group_ids'] for g in ids):
                raise ResourceDirectoryError('ontology_directory_group_inactive')
            after={'module_id':body['module_id'],'revision':before['revision']+1,'group_ids':sorted(ids)}
            connection.execute('INSERT INTO resource_memberships VALUES (?,?,?,?) ON CONFLICT(scope,module_id) DO UPDATE SET revision=excluded.revision,groups_json=excluded.groups_json',(scope,body['module_id'],after['revision'],json.dumps(after['group_ids'])))
            connection.execute('INSERT INTO resource_events VALUES (?,?,?,?,?,?,?,?)',(scope,body['request_id'],digest,actor,datetime.now(timezone.utc).isoformat(),body['module_id'],json.dumps(before),json.dumps(after)))
            return after

    def definition(self, query):
        if set(query)!={'module_id','version','sha256'}:
            raise ResourceDirectoryError('ontology_directory_invalid_request')
        entry=self.entries.get(query['module_id'])
        if not entry or entry['reference']!=query:
            raise ResourceDirectoryError('ontology_directory_definition_changed')
        wanted=set()
        def include(identity):
            if identity in wanted:return
            wanted.add(identity)
            for dependency in self.entries[identity]['definition']['requires']:include(dependency['module_id'])
        include(query['module_id'])
        entries=[e for e in self.library['modules'] if e['reference']['module_id'] in wanted]
        document={'profile':'vxture.ontology-library/0.1','modules':sorted([e['definition'] for e in entries],key=lambda d:d['module_id'])}
        return {**self.library,'library_sha256':hashlib.sha256(canonical_bytes(document)).hexdigest(),'modules':entries}

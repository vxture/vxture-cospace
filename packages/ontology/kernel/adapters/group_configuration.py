"""Portable group configuration adapter; no platform or scene dependencies."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata
from uuid import uuid4

PRESETS = (
    ('built_environment', '建筑与空间'), ('outdoor', '室外空间与设施'),
    ('electrical', '供配电'), ('water', '给排水'), ('fire_safety', '安全消防'),
    ('monitoring', '环境与监测'), ('operations', '组织与运营'),
)

class GroupConfigurationError(ValueError):
    pass


def clean_text(value, maximum, required=False):
    if not isinstance(value, str) or len(value) > maximum or any(unicodedata.category(c).startswith('C') for c in value):
        raise GroupConfigurationError('ontology_group_invalid_request')
    value = value.strip()
    if required and not value:
        raise GroupConfigurationError('ontology_group_invalid_request')
    return value


def normalize(value):
    return unicodedata.normalize('NFKC', value).casefold()


def validate_change(body):
    if isinstance(body,dict) and 'move' in body:
        if set(body)!={'request_id','expected_revision','group_id','move','reason'} or body['move'] not in ('top','up','down','bottom') or body['group_id'] is None:
            raise GroupConfigurationError('ontology_group_invalid_request')
        validate_change({**{k:body[k] for k in ('request_id','expected_revision','group_id','reason')},'name':'move','description':'','sort_order':0,'status':'active'})
        return {**body,'reason':clean_text(body['reason'],500,True)}
    fields = {'request_id','expected_revision','group_id','name','description','sort_order','status','reason'}
    if not isinstance(body, dict) or set(body) != fields:
        raise GroupConfigurationError('ontology_group_invalid_request')
    result = dict(body)
    for field, maximum, required in [('name',60,True),('description',500,False),('reason',500,True)]:
        result[field] = clean_text(body[field], maximum, required)
    if not isinstance(body['request_id'],str) or not re.fullmatch('[a-f0-9]{32}',body['request_id']):
        raise GroupConfigurationError('ontology_group_invalid_request')
    if body['group_id'] is not None and (not isinstance(body['group_id'],str) or not re.fullmatch(r'(preset-[a-z_]+|group-[a-f0-9]{32})',body['group_id'])):
        raise GroupConfigurationError('ontology_group_invalid_request')
    if type(body['expected_revision']) is not int or body['expected_revision'] < 0 or type(body['sort_order']) is not int or not 0 <= body['sort_order'] <= 999999 or body['status'] not in ('active','inactive'):
        raise GroupConfigurationError('ontology_group_invalid_request')
    return result


def initial_groups():
    return [{'group_id':'preset-'+identity,'name':name,'description':'','origin':'preset',
             'status':'active','sort_order':(i+1)*10} for i,(identity,name) in enumerate(PRESETS)]


class GroupConfigurationStore:
    def __init__(self, root, *, filename='ontology-group-configuration.sqlite3'):
        self.path = Path(root) / filename

    def connect(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        connection = sqlite3.connect(self.path,timeout=10)
        try:
            connection.execute('CREATE TABLE IF NOT EXISTS configuration (scope TEXT PRIMARY KEY, revision INTEGER NOT NULL, groups_json TEXT NOT NULL)')
            connection.execute('CREATE TABLE IF NOT EXISTS events (scope TEXT NOT NULL, revision INTEGER NOT NULL, request_id TEXT NOT NULL, payload_hash TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL, changed_at TEXT NOT NULL, before_json TEXT, after_json TEXT NOT NULL, PRIMARY KEY(scope,revision), UNIQUE(scope,request_id))')
            connection.commit()
            return connection
        except BaseException:
            connection.close()
            raise

    @staticmethod
    def scope_key(scope):
        if not isinstance(scope,str) or not scope.strip():
            raise GroupConfigurationError('ontology_group_scope_required')
        return hashlib.sha256(scope.encode()).hexdigest()

    @staticmethod
    def state(connection, scope):
        row = connection.execute('SELECT revision,groups_json FROM configuration WHERE scope=?',(scope,)).fetchone()
        if row is None:
            return 0,initial_groups()
        try:
            groups = json.loads(row[1])
            if type(row[0]) is not int or row[0] < 1 or not isinstance(groups,list):raise ValueError()
            ids=set();names=set()
            for group in groups:
                if set(group)!={'group_id','name','description','origin','status','sort_order'}:raise ValueError()
                validate_change({'request_id':'a'*32,'expected_revision':0,'reason':'read',**{k:group[k] for k in ('group_id','name','description','sort_order','status')}})
                if group['origin'] not in ('preset','custom') or group['group_id'] in ids or normalize(group['name']) in names:raise ValueError()
                preset = next((name for identity,name in PRESETS if 'preset-'+identity==group['group_id']),None)
                if (group['origin']=='preset') != (preset is not None) or preset and group['name']!=preset:raise ValueError()
                if group['origin']=='custom' and not group['group_id'].startswith('group-'):raise ValueError()
                ids.add(group['group_id']);names.add(normalize(group['name']))
            if not {'preset-'+identity for identity,_ in PRESETS} <= ids:raise ValueError()
            return row[0],groups
        except (ValueError,TypeError,KeyError) as exc:
            raise GroupConfigurationError('ontology_group_configuration_invalid') from exc

    @classmethod
    def result(cls, connection, scope):
        revision,groups=cls.state(connection,scope)
        events=connection.execute('SELECT revision,actor,reason,changed_at,before_json,after_json FROM events WHERE scope=? ORDER BY revision DESC LIMIT 50',(scope,)).fetchall()
        try:
            history=[{'revision':r,'actor':a,'reason':reason,'changed_at':at,'before':json.loads(before) if before else None,'after':json.loads(after)} for r,a,reason,at,before,after in events]
            for event in history:
                for group in [event['before'],event['after']]:
                    if group is not None:
                        validate_change({'request_id':'a'*32,'expected_revision':0,'reason':'audit',**{k:group[k] for k in ('group_id','name','description','sort_order','status')}})
        except (ValueError,TypeError,KeyError) as exc:
            raise GroupConfigurationError('ontology_group_configuration_invalid') from exc
        return {'profile':'vxture.ontology-group-configuration/0.1','revision':revision,
                'groups':sorted(groups,key=lambda g:(g['sort_order'],g['group_id'])),
                'history':history,'history_limit':50}

    def read(self, scope):
        scope=self.scope_key(scope)
        with closing(self.connect()) as connection, connection:
            connection.execute('BEGIN')
            return self.result(connection,scope)

    def change(self, scope, actor, body):
        scope=self.scope_key(scope);actor=clean_text(actor,500,True);change=validate_change(body)
        digest=hashlib.sha256(json.dumps([actor,change],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        with closing(self.connect()) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            previous=connection.execute('SELECT payload_hash FROM events WHERE scope=? AND request_id=?',(scope,change['request_id'])).fetchone()
            if previous:
                if previous[0]!=digest:raise GroupConfigurationError('ontology_group_request_conflict')
                return self.result(connection,scope)
            revision,groups=self.state(connection,scope)
            if revision!=change['expected_revision']:raise GroupConfigurationError('ontology_group_revision_changed')
            before=next((g for g in groups if g['group_id']==change['group_id']),None)
            if change['group_id'] and before is None:raise GroupConfigurationError('ontology_group_not_found')
            if 'move' in change:
                ordered=sorted(groups,key=lambda g:(g['sort_order'],g['group_id']))
                original=[{'group_id':g['group_id'],'name':g['name']} for g in ordered]
                index=next(i for i,g in enumerate(ordered) if g['group_id']==change['group_id'])
                target={'top':0,'up':max(0,index-1),'down':min(len(ordered)-1,index+1),'bottom':len(ordered)-1}[change['move']]
                if index==target:return self.result(connection,scope)
                ordered.insert(target,ordered.pop(index))
                groups=[{**g,'sort_order':(i+1)*10} for i,g in enumerate(ordered)]
                after=next(g for g in groups if g['group_id']==change['group_id'])
                audit_before={**before,'sequence':original}
                audit_after={**after,'sequence':[{'group_id':g['group_id'],'name':g['name']} for g in groups]}
            else:
                if before and before['origin']=='preset' and change['name']!=before['name']:raise GroupConfigurationError('ontology_group_preset_name_fixed')
                if any(normalize(g['name'])==normalize(change['name']) and g['group_id']!=change['group_id'] for g in groups):raise GroupConfigurationError('ontology_group_name_exists')
                after={k:change[k] for k in ('name','description','status')}
                after['sort_order']=before['sort_order'] if before else max((g['sort_order'] for g in groups),default=0)+10
                after.update(group_id=before['group_id'] if before else 'group-'+uuid4().hex,origin=before['origin'] if before else 'custom')
                groups=[g for g in groups if g['group_id']!=after['group_id']]+[after]
                audit_before=before;audit_after=after
            revision+=1
            connection.execute('INSERT INTO configuration VALUES (?,?,?) ON CONFLICT(scope) DO UPDATE SET revision=excluded.revision,groups_json=excluded.groups_json',(scope,revision,json.dumps(groups,ensure_ascii=False)))
            connection.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)',(scope,revision,change['request_id'],digest,actor,change['reason'],datetime.now(timezone.utc).isoformat(),json.dumps(audit_before,ensure_ascii=False) if audit_before else None,json.dumps(audit_after,ensure_ascii=False)))
            return self.result(connection,scope)

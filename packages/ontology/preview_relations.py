"""Bounded manual assertions; containment rules do not prove geometric inclusion."""
def inspect_relations(definition,objects,relations):
    issues=[];types={o['object_id']:o['type_id'] for o in objects};ids=set();assertions=set();parents={}
    rules=definition.get('relations',{})
    def issue(index,relation,code,message):
        issues.append({'code':code,'path':f'/relations/{index}','relation_id':relation.get('relation_id'),
                       'object_id':None,'message':message})
    for index,r in enumerate(relations):
        identity=r['relation_id'];source=r['source_id'];target=r['target_id'];kind=r['type_id'];rule=rules.get(kind)
        if identity in ids:issue(index,r,'duplicate_relation_id','关系ID重复。')
        ids.add(identity)
        if rule is None:issue(index,r,'unknown_relation_type','所选本体未定义该关系类型。');continue
        if source not in types or target not in types:issue(index,r,'relation_endpoint_missing','关系端点必须属于本次完整对象集。');continue
        if source==target:issue(index,r,'relation_self_link','对象不能与自身建立关系。');continue
        if types[source] not in rule['source_types'] or types[target] not in rule['target_types']:
            issue(index,r,'relation_endpoint_type','关系方向或端点类型不符合固定本体规则。');continue
        if rule['family']=='containment':
            parent,child=(source,target) if rule['parent_endpoint']=='source' else (target,source)
            assertion=('containment',parent,child)
            if child in parents and parents[child]!=parent:issue(index,r,'relation_multiple_parents','同一对象只能声明一个直接父空间。')
            else:parents[child]=parent
        else:assertion=(kind,*sorted((source,target)))
        if assertion in assertions:issue(index,r,'duplicate_relation_assertion','重复关系声明（包括包含/位于的反向等价声明和连接的反向声明）。')
        assertions.add(assertion)
    # Every accepted child has at most one parent. Walk the combined containment graph.
    cyclic=set()
    for child in parents:
        path=set();node=child
        while node in parents:
            if node in path:cyclic.update(path);break
            path.add(node);node=parents[node]
    if cyclic:issues.append({'code':'relation_containment_cycle','path':'/relations','relation_id':None,'object_id':None,'message':'包含/位于关系形成循环，请人工核对空间归属。'})
    return {'status':'failed' if issues else 'passed','relation_count':len(relations),'issues':issues,
            'saved':False,'quality':'unverified','robot_ready':False}

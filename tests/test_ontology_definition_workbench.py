from itertools import count
from packages.service.ontology_definition_workbench import DefinitionWorkbench
from packages.ontology.kernel import builtin_catalog
from packages.ontology.resource_directory import ResourceDirectory


def test_directory_overlay_keeps_historical_dependency_versions_independent(tmp_path):
    workbench = DefinitionWorkbench(tmp_path,'scope','editor',True)
    service = workbench.service
    ids=(f'{i:032x}' for i in count(1))

    def publish(identity,bundle,revision=0,base=None):
        service.save('scope','editor',next(ids),module_id=identity,expected_revision=revision,bundle=bundle,base_reference=base)
        review=service.submit('scope','editor',next(ids),module_id=identity,expected_revision=revision+1)
        # Trusted service authorizer here is bound to editor: assemble a separate reviewer.
        other=DefinitionWorkbench(tmp_path,'scope','reviewer',True).service
        other.decide('scope','reviewer',next(ids),review_id=review['review_id'],decision='approved',reason='test')
        return service.publish('scope','editor',next(ids),review_id=review['review_id'],expected_revision=revision+1)

    core=builtin_catalog().export('core');first=publish('core',core)
    electrical=publish('electrical',builtin_catalog().export('electrical'))
    core['modules'][0]['version']='0.2.0'
    publish('core',core,revision=1,base=first['reference'])
    directory=ResourceDirectory(tmp_path,workbench.released_library())
    current=next(i for i in directory.read('scope',{})['items'] if i['reference']['module_id']=='core')
    assert current['reference']['version']=='0.2.0' and current['published_at']
    historical=workbench.definition(electrical['reference'])
    assert next(m for m in historical['modules'] if m['reference']['module_id']=='core')['reference']['version']=='0.1.0'
    assert workbench.definition(first['reference'])['modules'][0]['reference']['version']=='0.1.0'
    # Neither new publication nor a mutable draft leaks to a different library partition.
    other=DefinitionWorkbench(tmp_path,'other-scope','reader',False)
    assert other.read('core')['releases']==[]

from concurrent.futures import ThreadPoolExecutor
import json
import numpy as np
import pytest
from test_preview_offline import setup_bundle
from packages.service.preview_publications import PreviewPublications
from packages.views.agent.preview_offline import export_bundle, sha
from packages.views.agent.preview_consumer import PreviewConsumer
from packages.construction.preview_model import digest


def deliveries(tmp_path):
    _,jobs,old,old_data=setup_bundle(tmp_path)
    # Fixture-only changed surface cells prove sessions use their own payload.
    root=jobs.root/'build-two'/'output'
    np.savez_compressed(root/'agent.npz',cells=np.array([[5,5,5]],dtype=np.int64))
    manifest=json.loads((root/'model.json').read_bytes())
    manifest['members']['agent.npz']['sha256']=digest(root/'agent.npz')
    (root/'model.json').write_text(json.dumps(manifest),encoding='utf-8')
    jobs.select('build-two',1)
    pubs=PreviewPublications(jobs)
    new=pubs.publish('build-two',2)
    new_data=export_bundle(*pubs.read(new['id']))
    result=[]
    for record,data in [(old,old_data),(new,new_data)]:
        path=tmp_path/(record['id']+'.zip'); path.write_bytes(data)
        result.append((path,record['id'],sha(data)))
    return result


def test_download_does_not_activate_and_sessions_stay_fixed(tmp_path):
    old,new=deliveries(tmp_path); consumer=PreviewConsumer()
    assert consumer.status()['revision']==0
    with pytest.raises(ValueError,match='no_active'): consumer.session()
    first=consumer.activate(*old,expected_revision=0)
    assert consumer.status()['publication_id']==old[1]
    point=[-.05,.05,.05]; before=first.query(point)
    second=consumer.activate(*new,expected_revision=1)
    assert consumer.session()==second
    assert first.query(point)==before
    assert second.query(point)['publication_id']==new[1]
    assert second.query(point)['consumer_revision']==2
    assert before['model_id']=='build-one' and second.query(point)['model_id']=='build-two'
    assert before['state']=='surface_candidate' and second.query(point)['state']=='unknown'
    # Old packages remain explicitly loadable for historical review.
    review=consumer.activate(*old,expected_revision=2)
    assert review.query(point)['publication_id']==old[1] and review.revision==3
    assert second.query(point)['publication_id']==new[1]


def test_failed_activation_preserves_current_session(tmp_path):
    old,new=deliveries(tmp_path); consumer=PreviewConsumer()
    session=consumer.activate(*old,expected_revision=0); before=consumer.status()
    with pytest.raises(ValueError,match='revision_changed'):
        consumer.activate(*new,expected_revision=0)
    new[0].write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='package_integrity'):
        consumer.activate(*new,expected_revision=1)
    assert consumer.status()==before and consumer.session() is session


def test_only_one_concurrent_activation_wins(tmp_path):
    old,new=deliveries(tmp_path); consumer=PreviewConsumer()
    consumer.activate(*old,expected_revision=0)
    def attempt():
        try: return consumer.activate(*new,expected_revision=1).revision
        except ValueError as exc: return str(exc)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _: attempt(),range(2)))
    assert sorted(map(str,results))==['2','consumer_revision_changed']
    assert consumer.status()['revision']==2

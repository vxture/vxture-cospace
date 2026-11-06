"""Server-configured source pairs; browser supplies an opaque key, never paths."""
from threading import Lock
from pathlib import Path
from packages.data.preview_inputs import inspect
from packages.lifecycle.preview_scope import scope,owned


class PreviewRegistration:
    def __init__(self, catalog, sources, registration_ref=None):
        self.catalog = catalog
        self.sources = sources
        self.lock = Lock()
        self.registration_ref=registration_ref

    def list(self):
        return [{'id': key, 'label': value['label'],
                 'format': value.get('format','nyu_rgbd_with_existing_poses')}
                for key, value in self.sources.items()]

    def register(self, source_id, label, space_id=None):
        ownership=scope(self.catalog.directory,space_id)
        if source_id not in self.sources:
            raise ValueError('registration_source_not_allowed')
        if not 1 <= len(label.strip()) <= 100:
            raise ValueError('invalid_input_label')
        source = self.sources[source_id]
        with self.lock:
            format=source.get('format','nyu_rgbd_with_existing_poses')
            checked = inspect(source['snapshot'], source.get('tracking'),format)
            # Repeated clicks do not manufacture duplicate versions of the same input.
            # A changed label alone is not an input revision.
            for item in self.catalog.list():
                record = self.catalog.read_original(item['id'])
                if (owned(record) == ownership and Path(record['snapshot']).resolve() == Path(source['snapshot']).resolve()
                        and record.get('format')==format
                        and (Path(record['tracking']).resolve() if record.get('tracking') else None) == (Path(source['tracking']).resolve() if source.get('tracking') else None)
                        and all(record[k] == v for k, v in checked.items())):
                    return {'created': False, 'input': item}
            kwargs={'registration_ref':self.registration_ref} if self.registration_ref is not None else {}
            record = self.catalog.register(label, source['snapshot'], source.get('tracking'),space_id,format,**kwargs)
            return {'created': True, 'input': {k:v for k,v in record.items()
                                             if k not in ('snapshot','tracking')}}

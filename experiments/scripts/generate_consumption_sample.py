"""Generate inspectable F06a requests/responses, no HTTP server or authority."""
import json
from pathlib import Path

from packages.service.consumption_contract import InspectionConsumer
from packages.service.consumption_sample import build_consumption_sample

if __name__=='__main__':
    root=Path('examples/consumption')
    root.mkdir(parents=True,exist_ok=True)
    for mode in ('historical','operational'):
        source,files,request=build_consumption_sample(mode)
        response=InspectionConsumer(source,files,now='2026-10-28T00:30:00Z').consume(request,now='2026-10-28T00:30:00Z')
        for suffix,doc in (('request',request),('response',response)):
            (root/f'{mode}-{suffix}.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf-8')
        print({'mode':mode,'status':response['status'],'refusal':response['refusal'],'completeness':response['completeness']})

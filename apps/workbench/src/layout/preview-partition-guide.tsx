import React,{useEffect,useState} from 'react';
import {Button} from '@vxture/design-system';
import {getJSON} from './real-space-data';
import {businessEndpoint} from './business-endpoint';

type Info={profile:string;publication_id:string;space_id?:string;index_sha256:string;sha256:string;frame_id:string;partitions:number;total_cells:number;bytes:number;quality:string;robot_ready:boolean};
export function PreviewPartitionGuide({publication,space}:{publication:string;space:string}){
 const [info,setInfo]=useState<Info|null>(null),[error,setError]=useState('');
 useEffect(()=>{const controller=new AbortController();setInfo(null);setError('');
  getJSON<Info>(`/publications/${encodeURIComponent(publication)}/partitions.json`,controller.signal).then(value=>{
   if(value.profile!=='cospace.partitioned-agent/0.1'||value.publication_id!==publication||(value.space_id||'')!==space||!/^preview-[a-f0-9]{16}$/.test(publication)||(space&&!/^space-[a-f0-9]{16}$/.test(space))||!(/^[a-f0-9]{64}$/).test(value.index_sha256)||!(/^[a-f0-9]{64}$/).test(value.sha256)||typeof value.frame_id!=='string'||value.frame_id.length>256||!value.frame_id||value.quality!=='unverified'||value.robot_ready!==false)throw Error('分区交付绑定不一致，请重新获取。');
   if(!controller.signal.aborted)setInfo(value);
  }).catch(e=>{if(!controller.signal.aborted)setError(e.message);});return()=>controller.abort();
 },[publication,space]);
 // Quote arbitrary frame names as PowerShell single-quoted literals.
 const frame=info?`'${info.frame_id.replaceAll("'","''")}'`:'';
 const command=info?`.venv/Scripts/python.exe -m experiments.scripts.query_partitioned_preview "D:/Downloads/PARTITIONS.zip" --publication ${publication} ${space?`--space-id ${space}`:'--legacy'} --index-sha256 ${info.index_sha256} --frame-id ${frame} --bounds MIN_X MIN_Y MIN_Z MAX_X MAX_Y MAX_Z --limit 1024`:'';
 return <section aria-label={`分区交付 ${publication}`} className="rounded-md border border-border p-lg"><div className="flex flex-col gap-md"><h3 className="text-body-small font-medium">按范围读取智能体表面数据</h3><p className="text-body-small text-muted-foreground">下载固定版本后可离线查询点或范围。每次只解码命中分区；未观测区域为未知，不代表可通行。本包只包含表面网格和来源清单，语义对象及关联请使用原离线交付包。</p>{error&&<p role="alert" className="text-body-small">{error}</p>}{!info&&!error&&<p role="status" className="text-body-small">正在核对分区交付…</p>}{info&&<><p className="text-body-small">{info.total_cells.toLocaleString()} 个表面网格 · {info.partitions} 个分区 · {(info.bytes/1024).toFixed(1)} KiB</p><div><Button asChild size="sm"><a href={`${businessEndpoint}/publications/${encodeURIComponent(publication)}/partitions.zip`} download>下载分区交付包</a></Button></div><p className="text-label-small text-muted-foreground">在项目根目录的 PowerShell 中运行；替换 ZIP 路径和范围数值，使用模型坐标系及米制单位。保留以下索引摘要作为校验依据。</p><pre aria-label="分区查询命令" className="max-h-96 overflow-auto whitespace-pre-wrap break-all rounded-md bg-muted p-md text-label-small">{command}</pre><p className="text-label-small text-muted-foreground">返回结果包含实际读取分区数。超出读取或结果上限时不会返回部分网格，请缩小范围。版本需显式选择，已下载副本无法远程撤回；精度与设备可用性尚未验收。</p></>}</div></section>;
}

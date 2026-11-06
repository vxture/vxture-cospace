import React,{useEffect,useState} from 'react';
import {getJSON} from './real-space-data';
type Info={publication_id:string;sha256:string;space_id?:string;quality:string;robot_ready:boolean};
export function PreviewConsumerGuide({publication,space}:{publication:string;space:string}){
 const [info,setInfo]=useState<Info|null>(null),[error,setError]=useState('');
 useEffect(()=>{const controller=new AbortController();setInfo(null);setError('');getJSON<Info>(`/publications/${encodeURIComponent(publication)}/offline.json`,controller.signal).then(value=>{
  if(value.publication_id!==publication||(value.space_id||'')!==space||!/^preview-[a-zA-Z0-9-]+$/.test(value.publication_id)||!(/^[0-9a-f]{64}$/).test(value.sha256)||(space&&!/^space-[a-zA-Z0-9-]+$/.test(space))||value.quality!=='unverified'||value.robot_ready!==false)throw Error('离线交付绑定不一致，未生成消费命令。');
  if(!controller.signal.aborted)setInfo(value);
 }).catch(e=>{if(!controller.signal.aborted)setError(e.message);});return()=>controller.abort();},[publication,space]);
 const root=`var/consumers/${space||'legacy'}-001`;
 const cli=`.venv/Scripts/python.exe -m apps.cli.preview_consumer --root "${root}"`;
 const binding=info?`--publication ${info.publication_id} --sha256 ${info.sha256}`:'';
 return <section aria-label={`本地消费 ${publication}`} className="rounded-md border border-border p-lg"><div className="flex flex-col gap-md"><h3 className="text-body-small font-medium">消费版本保存与恢复</h3><p className="text-body-small text-muted-foreground">在项目根目录运行命令。消费库保存在消费机器；此页面仅提供操作说明，不读取机器人或本机消费库状态。</p>{error&&<p role="alert" className="text-body-small">{error}</p>}{!info&&!error&&<p role="status" className="text-body-small">正在核对固定离线包…</p>}{info&&<><p className="text-label-small text-muted-foreground">首次使用新目录执行初始化；已有目录跳过。安装只保存包，激活才切换版本。回切时打开旧发布的本地消费说明，用旧包绑定和当前消费修订再次激活。以下包路径和版本序号须按实际情况填写。</p><pre aria-label="本地消费命令" className="max-h-96 overflow-auto whitespace-pre-wrap break-all rounded-md bg-muted p-md text-label-small">{[
 '# 1. 首次创建独立消费库；已有库跳过，目录后缀可自行修改',
 `${cli} init ${space?`--space-id ${space}`:'--legacy'}`,
 '# 2. 将下载ZIP保存后，替换下面的包路径',
 `${cli} install "D:/Downloads/PACKAGE.zip" ${binding}`,
 '# 3. 查看保存的引用与 revision；此操作不恢复查询会话',
 `${cli} status`,
 '# 4. 主动切换：将 N 替换为 status 返回的 revision（新库为0）',
 `${cli} activate ${binding} --expected-revision N`,
 '# 5. 重启后再读 status，将 R 替换为当前 revision，显式恢复并查询对象',
 `${cli} restore ${binding} --expected-revision R --objects`,
 ].join('\n')}</pre><p className="text-label-small text-muted-foreground">每次命令都是独立进程；激活命令结束后保存引用仍在，下次查询需要显式恢复。恢复会重新检查包内容及绑定，不增加版本序号。旧无语义对象包可改用 --point X Y Z。精度、时效与设备授权仍未验收。</p></>}</div></section>;
}

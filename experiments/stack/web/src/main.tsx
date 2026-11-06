import { createRoot } from 'react-dom/client';
import { Button, Card, Descriptions } from 'antd';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { Vector3 } from 'three';
import { WebGPURenderer } from 'three/webgpu';

function Evaluation() {
  const sample = useQuery({ queryKey: ['sample', 'release-sample-001'],
    queryFn: async () => ({ release: 'release-sample-001', length: new Vector3(3, 4, 0).length() }) });
  return <Card title="技术栈兼容验证">
    <Descriptions items={[{ key: 'release', label: '固定版本', children: sample.data?.release },
      { key: 'three', label: 'Three.js计算', children: sample.data?.length },
      { key: 'gpu', label: 'WebGPU入口', children: typeof WebGPURenderer }]} />
    <Button onClick={() => void sample.refetch()}>重新读取</Button>
    <p>仅验证组件组合；不表示GPU渲染或真实空间能力通过。</p>
  </Card>;
}
createRoot(document.getElementById('root')!).render(
  <QueryClientProvider client={new QueryClient()}><Evaluation /></QueryClientProvider>);

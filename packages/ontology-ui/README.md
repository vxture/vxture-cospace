# Ontology UI

独立 React 本体清单与详情组件，包名 `@vxture/ontology-ui`。导出 TypeScript 源码，由宿主构建；依赖 React 19 和 Vxture Design System 15.6。

```tsx
import {OntologyCatalog, OntologyLibrary, useOntologyLibrary} from '@vxture/ontology-ui';
import '@vxture/ontology-ui/styles';

function LibraryContent({client, category, selection, onSelect}) {
  const {library, loading, error} = useOntologyLibrary(client);
  if (loading) return <p>读取中…</p>;
  if (error) return <p role="alert">{error}</p>;
  if (!library) return null;
  return selection.moduleId
    ? <OntologyLibrary library={library} selection={selection} onSelect={onSelect}/>
    : <OntologyCatalog library={library} category={category} onSelect={onSelect}/>;
}
```

宿主使用自己的 DS 导航，固定分类为 all / core / domain，禁止按数据生成导航条目。`OntologyCatalog` 在内容区展示本体清单、搜索、名称/标识排序及每页十条的本地分页。`OntologyLibrary` 展示当前模块及概念/关系清单，打开术语后显示详情。宿主控制 URL、返回和 `LibrarySelection`，不再导出术语目录树。

当前契约用于有上限的内置定义集（最多 32 模块），搜索和分页只针对已加载数据。它不是大规模注册库接口。扩展时需提供服务端分类、检索、稳定排序/游标分页、模块摘要列表及按固定版本加载详情；不得拉取全部定义后在浏览器模拟海量数据分页。

`client` 保持稳定引用，实现 `LibraryClient.load(signal)`；宿主负责 transport、认证、授权与错误转换。Hook 负责取消、刷新和错误清空。新模块目前只读并可导出，所有导出保持 draft，编辑和发布入口处于未开放状态。

组件不读取平台会话、Workspace、场景、URL 或 CoSpace API，不直接发起网络请求，可脱离 CoSpace Shell 挂载。`parseLibrary` 检查响应结构、引用及依赖/继承边界，不验证来源签名，也不替代 Python 内核完整语义检查。

## 分组配置组件

`@vxture/ontology-ui/group-configuration` 导出 `OntologyGroupConfiguration`、`GroupConfigurationClient`、数据类型与响应解析器。宿主注入 load/save、处理鉴权及错误转换，通过 onDirtyChange 接入自己的未保存导航保护。

配置列表支持新建、编辑、停用/启用，以及置顶、上移、下移、置底。没有用户编辑的排序数字；搜索/筛选时禁用移动。所有提交都带修订和幂等标识。组件不提供资源归组操作，也不把配置入口放进本体业务导航。契约见[本体分组配置](../../contracts/schemas/ontology-group-configuration-v0.1.md)。

表格首列序号固定 64px，末列操作使用 32px 图标按钮，内部三竖点图标为 24px。操作面板的编辑与四个移动操作之间仅使用分隔线，不显示分组标题；每项采用图标加操作名称。

序号列与操作列均固定 64px，表头与内容居中，两侧各保留 16px 内边距。页面不展示修改记录。

`@vxture/ontology-ui/directory` 导出 `OntologyDirectory`；`directory-contract` 导出注入客户端、查询/摘要/归组类型与响应解析。宿主提供 list / definition / assign，以及 onDirtyChange 未保存保护。目录分页与筛选调用服务端；详情按固定引用获取依赖闭包，导出限定当前模块与依赖，不把部分详情称为完整库。组件不引入路由、身份或 HTTP。参见[目录契约](../../contracts/schemas/ontology-resource-directory-v0.1.md)。
# B04b 编制工作面

`@vxture/ontology-ui/authoring` 导出 `DefinitionWorkspace`；通过注入的 AuthoringClient 读取/保存草稿、校验、送审、查看送审快照、审批、发布及查看固定版本。业务组件不导入宿主路由、身份、场景、endpoint 或 fetch。

从既有模块详情进入编辑，主内容区表格与 DS 右侧抽屉编辑概念、属性和关系；不提供 JSON 原文业务编辑器，不增加导航或二次导航。“版本与发布”抽屉单独承担治理操作；本体成熟度仍为候选草案。旧固定定义/依赖通过整包查看，发布与归组不会重写定义内容。

onDirtyChange 必须接入宿主未保存离开保护。当前模块整体保存保留修订/幂等；保存成功但刷新失败时重放原请求，避免重复保存。原始错误不作为身份或授权依据，宿主始终验证真实权限。

本批支持已有模块的内容编制，不含新模块向导或批量导入。HTTP 和 SQLite 是宿主装配，组件没有独立账号/审批身份；工程预览不会伪造第二审批人。

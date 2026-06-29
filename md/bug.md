&#x20;1. 后端 upload\_paper 增加前置 key 校验：没 key 直接返回明确错误，而不是收下文件、200、再异步失败。（papers.py，B

&#x20; 角色范围）

&#x20; 2. updateConfig 不要吞错：后端保存失败就 success:false，让用户知道没存上。（user.js）

&#x20; 3. 前端展示 parse\_error：在 PaperCard / 详情页把失败原因显示出来。（前端）

&#x20; 4. 统一 key 的真相源：要么 key 只存后端（前端不再用本地 llm\_api\_key 当作「已配置」判据，改用 GET /config 的

&#x20; api\_key\_configured）；要么明确只走本地——二选一，别两套并行。这是根因，建议优先。




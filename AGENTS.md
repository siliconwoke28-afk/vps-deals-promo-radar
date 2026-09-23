::ILANG
[TYPE:agent-policy][PROJECT:vps-deals][LANG:zh]
::STATE{@PROJECT, role:公开VPS价格及优惠目录, runtime:Python标准库和静态HTML, locale:en-US}
::MODULE{CONFIG|title:配置唯一真源}
::RULE{必须读取 .ilang/site.ilang; 厂商 域名 字段 提取规则 更新频率不得在代码里复制硬编码}
::MODULE{ALLOWED|title:允许的维护动作}
::ALLOW{修复官方公开源解析器; 更新模板; 增加测试; 检查robots; 运行scraper.py和build.py; 修复失效来源}
::RULE{新增厂商须在配置登记 官网 来源 和解析规则; 无可靠价格则不发布优惠}
::RULE{修改后运行 python -m unittest discover -s tests; python build.py; python verify.py}
::RULE{改cron后运行 python build.py --sync-workflow 并提交生成的workflow}
::RULE{用户明确要求发布时可提交部署; 不得购买域名 开通付费服务 擅自申请联盟或接受新条款}
::MODULE{DATA|title:来源与失效}
::RULE{只抓公开官方页面; 尊重robots和速率; TLS验证不能关闭; 403或429不能绕过}
::RULE{每条价格必须带原始证据 来源URL 抓取时间和内容哈希; 不把试用金当售价}
::RULE{失败或解析不匹配即撤下该来源当前价格; 过期或陈旧优惠不进入活跃列表或Offer结构化数据}
::RULE{普通价格标标准价; 限定期限及续费必须展示; 无到期日就省略}
::RULE{联盟链接仅在用户提供且审核获批后填写; 标sponsored并披露; 不编佣金和收入}
::BOUNDARY{never:编优惠 编价格 编评价 编佣金 刷量 绕反爬 cookie注入 品牌词竞价 自买自推 提交密钥|scope:permanent}

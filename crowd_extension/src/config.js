// 构建配置（v3.3.0 起随仓库分发）：Supabase 连接参数。
// anon key 为 Supabase publishable key，按设计随插件公开分发（RLS 在服务端收口），
// 与线上已发布的 crowd-extension-v3.2.3.zip 内一致。service_role 等机密绝不进本文件。
self.CROWD_CONFIG = {
  API_BASE: "https://bdwrhshgdeghgyzwpxnl.supabase.co",
  API_KEY: "sb_publishable_c93XenGzZsoa308e3bTg6A__lfaqQ-B",
};

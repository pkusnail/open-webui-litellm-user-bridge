# LiteLLM + Open WebUI Integration Know-How

## 📋 目录
- [架构概述](#架构概述)
- [为什么要这样集成](#为什么要这样集成)
- [数据库表结构说明](#数据库表结构说明)
- [完整集成步骤](#完整集成步骤)
- [用户权限管理实战](#用户权限管理实战)
- [常见问题和踩坑指南](#常见问题和踩坑指南)
- [监控和调试](#监控和调试)

## 🏗️ 架构概述

### 整体架构
```
┌─────────────────┐    PostgreSQL     ┌──────────────────┐
│    LiteLLM      │    Triggers       │   Open WebUI     │
│   (权限中心)     │ ────────────────► │   (用户界面)      │
│                 │                   │                  │
│ • 用户管理       │                   │ • 聊天界面        │
│ • API Keys      │                   │ • 用户同步        │
│ • 模型权限       │                   │ • 模型显示        │
│ • 团队组织       │                   │ • 会话管理        │
└─────────────────┘                   └──────────────────┘
         │                                     │
         ├─ Database: litellm                  ├─ Database: webui
         ├─ Port: 8313                         ├─ Port: 8333
         └─ Role: 权限和模型管理                └─ Role: 用户交互界面
```

### 数据流向
1. **管理员**在LiteLLM中创建用户、团队、组织
2. **PostgreSQL触发器**自动将用户信息同步到Open WebUI
3. **API Key创建**时自动同步到Open WebUI用户表
4. **用户登录**Open WebUI，看到基于权限的模型列表

## 🎯 为什么要这样集成

### 痛点分析
- **分散管理**：LiteLLM强于权限控制，Open WebUI强于用户体验
- **重复工作**：两个系统各自维护用户和权限
- **权限不一致**：难以统一控制谁能访问哪些模型
- **运维复杂**：需要在两个地方同时管理用户

### 解决方案优势
- ✅ **统一权限中心**：LiteLLM作为唯一的权限管理入口
- ✅ **自动同步**：用户和权限实时同步，无需手动维护
- ✅ **细粒度控制**：支持用户、团队、组织三级权限
- ✅ **模型权限隔离**：不同用户看到不同的模型列表
- ✅ **企业就绪**：支持多租户、审计日志、预算控制

## 🗃️ 数据库表结构说明

### LiteLLM核心表（litellm数据库）

#### 1. 用户表 - LiteLLM_UserTable
```sql
-- 用户基础信息
user_id              TEXT PRIMARY KEY    -- 用户唯一ID
user_email           TEXT                -- 邮箱（用于Open WebUI登录）
user_alias           TEXT                -- 显示名称
user_role            TEXT                -- 角色：proxy_admin/internal_user/internal_user_viewer
team_id              TEXT                -- 所属团队ID
organization_id      TEXT                -- 所属组织ID
models               TEXT[]              -- 用户可访问的模型列表
spend                DOUBLE PRECISION    -- 消费金额
max_budget           DOUBLE PRECISION    -- 预算限制
created_at           TIMESTAMP           -- 创建时间
updated_at           TIMESTAMP           -- 更新时间
```

#### 2. API密钥表 - LiteLLM_VerificationToken
```sql
-- API密钥和权限
token                TEXT PRIMARY KEY    -- API密钥
user_id              TEXT                -- 关联用户ID  
key_alias            TEXT                -- 密钥别名
models               TEXT[]              -- 密钥可访问的模型
spend                DOUBLE PRECISION    -- 消费记录
max_budget           DOUBLE PRECISION    -- 预算限制
expires              TIMESTAMP           -- 过期时间
blocked              BOOLEAN             -- 是否被封禁
created_at           TIMESTAMP           -- 创建时间
```

#### 3. 团队表 - LiteLLM_TeamTable
```sql
-- 团队管理
team_id              TEXT PRIMARY KEY    -- 团队ID
team_alias           TEXT                -- 团队名称
organization_id      TEXT                -- 所属组织
models               TEXT[]              -- 团队可访问模型
spend                DOUBLE PRECISION    -- 团队消费
max_budget           DOUBLE PRECISION    -- 团队预算
members_with_roles   JSONB               -- 成员及其角色
created_at           TIMESTAMP           -- 创建时间
```

#### 4. 组织表 - LiteLLM_OrganizationTable
```sql
-- 组织管理  
organization_id      TEXT PRIMARY KEY    -- 组织ID
organization_alias   TEXT                -- 组织名称
models               TEXT[]              -- 组织可访问模型
spend                DOUBLE PRECISION    -- 组织消费
max_budget           DOUBLE PRECISION    -- 组织预算
created_at           TIMESTAMP           -- 创建时间
```

#### 5. 同步审计表 - sync_audit
```sql
-- 同步操作记录
id                   SERIAL PRIMARY KEY  -- 记录ID
operation            VARCHAR(20)         -- 操作类型：SYNC_USER/SYNC_API_KEY
record_id            TEXT                -- 关联记录ID
sync_result          VARCHAR(20)         -- 同步结果：SUCCESS/FAILED
old_data            JSONB               -- 同步前数据
new_data            JSONB               -- 同步后数据
error_message       TEXT                -- 错误信息
created_at          TIMESTAMP           -- 创建时间
```

### Open WebUI核心表（webui数据库）

#### 1. 用户表 - user
```sql
-- Open WebUI用户信息
id                   TEXT PRIMARY KEY    -- 用户ID（格式：usr_原始用户ID）
name                 TEXT                -- 显示名称  
email                TEXT                -- 邮箱
role                 TEXT                -- 角色：admin/user
api_key              TEXT                -- 个人API密钥（同步自LiteLLM）
profile_image_url    TEXT                -- 头像URL
settings             TEXT                -- 用户设置（JSON）
created_at           BIGINT              -- 创建时间戳
updated_at           BIGINT              -- 更新时间戳
```

#### 2. 认证表 - auth
```sql
-- 登录认证信息
id                   TEXT PRIMARY KEY    -- 用户ID（同user.id）
email                TEXT                -- 邮箱
password             TEXT                -- 密码哈希
active               BOOLEAN             -- 是否激活
```

#### 3. 群组表 - group
```sql  
-- 组织映射为群组
id                   TEXT PRIMARY KEY    -- 群组ID（格式：grp_组织ID）
name                 TEXT                -- 群组名称
description          TEXT                -- 描述
meta                 JSONB               -- 元数据（存储组织信息）
created_at           BIGINT              -- 创建时间戳
updated_at           BIGINT              -- 更新时间戳
```

## 🚀 完整集成步骤

### 步骤1：环境准备

#### 1.1 确保PostgreSQL实例运行
```bash
# 检查PostgreSQL容器
docker ps | grep postgres

# 检查数据库连接
docker exec your_postgres_container psql -U webui -l
```

#### 1.2 验证LiteLLM和Open WebUI容器
```bash
# 检查LiteLLM（通常在4000端口）
curl -H "Authorization: Bearer your-master-key" http://localhost:8313/health

# 检查Open WebUI（通常在8080端口）  
curl http://localhost:8333/health
```

### 步骤2：安装同步系统

#### 2.1 安装基础用户同步
```bash
# 下载SQL文件
wget https://raw.githubusercontent.com/pkusnail/open-webui-litellm-user-bridge/main/sql/litellm-webui-sync.sql

# 编辑连接字符串
nano sql/litellm-webui-sync.sql
# 修改：target_conn_str TEXT := 'host=localhost port=5432 dbname=webui user=webui password=webui';

# 执行安装
docker exec your_postgres_container psql -U webui -d litellm -f /path/to/litellm-webui-sync.sql
```

#### 2.2 安装API密钥同步（可选但推荐）
```bash
# 下载API密钥同步扩展
wget https://raw.githubusercontent.com/pkusnail/open-webui-litellm-user-bridge/main/sql/api-key-sync.sql

# 执行安装
docker exec your_postgres_container psql -U webui -d litellm -f /path/to/api-key-sync.sql
```

#### 2.3 验证安装
```bash
# 验证触发器安装
docker exec your_postgres_container psql -U webui -d litellm -c "
SELECT test_api_key_sync_installation();
"

# 检查触发器状态
docker exec your_postgres_container psql -U webui -d litellm -c "
SELECT schemaname, tablename, trigger_name 
FROM pg_trigger t
JOIN pg_class c ON t.tgrelid = c.oid  
JOIN pg_namespace n ON c.relnamespace = n.oid
WHERE trigger_name LIKE '%sync%';
"
```

### 步骤3：配置Open WebUI连接

#### 3.1 创建全局API密钥
```bash
# 设置主密钥
export LITELLM_MASTER_KEY="your-litellm-master-key"

# 创建全局API密钥（允许访问所有模型）
GLOBAL_KEY=$(curl -s -X POST "http://localhost:8313/key/generate" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "models": ["all-proxy-models"],
    "key_alias": "openwebui_global_key", 
    "user_id": "openwebui_system"
  }' | jq -r '.key')

echo "Global API Key: $GLOBAL_KEY"
```

#### 3.2 重启Open WebUI使用新密钥
```bash
# 停止当前容器
docker stop your_openwebui_container

# 使用新API密钥启动
docker run -d \
  --name openwebui_updated \
  --network your_network \
  -p 8333:8080 \
  -e OPENAI_API_BASE_URL=http://your_litellm_container:4000/v1 \
  -e OPENAI_API_KEY=$GLOBAL_KEY \
  -e DATABASE_URL="postgresql://webui:webui@your_postgres:5432/webui" \
  -v open-webui:/app/backend/data \
  ghcr.io/open-webui/open-webui:0.6.30
```

## 👥 用户权限管理实战

### 场景1：创建基础组织架构

#### 1.1 创建组织
```bash
export LITELLM_MASTER_KEY="your-master-key"

# 创建技术公司组织
ORG_RESPONSE=$(curl -s -X POST "http://localhost:8313/organization/new" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "organization_alias": "Tech Company Inc",
    "models": ["gpt-4", "gpt-3.5-turbo", "claude-3", "qwen3-omni-30b-thinking"]
  }')

ORG_ID=$(echo $ORG_RESPONSE | jq -r '.organization_id')
echo "Created Organization ID: $ORG_ID"
```

#### 1.2 创建团队
```bash
# AI研发团队（访问高级模型）
AI_TEAM_RESPONSE=$(curl -s -X POST "http://localhost:8313/team/new" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "team_alias": "AI Research Team",
    "organization_id": "'$ORG_ID'",
    "models": ["gpt-4", "claude-3", "qwen3-omni-30b-thinking"],
    "max_budget": 5000.0
  }')

AI_TEAM_ID=$(echo $AI_TEAM_RESPONSE | jq -r '.team_id')

# 产品团队（访问基础模型）
PRODUCT_TEAM_RESPONSE=$(curl -s -X POST "http://localhost:8313/team/new" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "team_alias": "Product Team", 
    "organization_id": "'$ORG_ID'",
    "models": ["gpt-3.5-turbo"],
    "max_budget": 1000.0
  }')

PRODUCT_TEAM_ID=$(echo $PRODUCT_TEAM_RESPONSE | jq -r '.team_id')

echo "Created AI Team ID: $AI_TEAM_ID"
echo "Created Product Team ID: $PRODUCT_TEAM_ID"
```

### 场景2：创建用户并分配权限

#### 2.1 创建AI研究员（高权限用户）
```bash
# 创建AI研究员用户
AI_USER_RESPONSE=$(curl -s -X POST "http://localhost:8313/user/new" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "ai_researcher_001",
    "user_alias": "Dr. Alice Wang",
    "user_email": "alice.wang@techcompany.com",
    "user_role": "internal_user",
    "team_id": "'$AI_TEAM_ID'",
    "organization_id": "'$ORG_ID'",
    "models": ["gpt-4", "claude-3", "qwen3-omni-30b-thinking"],
    "max_budget": 2000.0
  }')

echo "Created AI Researcher: $(echo $AI_USER_RESPONSE | jq -r '.user_id')"

# 为用户创建API密钥（会自动同步到Open WebUI）
AI_KEY_RESPONSE=$(curl -s -X POST "http://localhost:8313/key/generate" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "ai_researcher_001",
    "key_alias": "alice_primary_key",
    "models": ["gpt-4", "claude-3", "qwen3-omni-30b-thinking"],
    "max_budget": 2000.0,
    "duration": null
  }')

AI_USER_KEY=$(echo $AI_KEY_RESPONSE | jq -r '.key')
echo "AI Researcher API Key: $AI_USER_KEY"
```

#### 2.2 创建产品经理（受限权限用户）
```bash
# 创建产品经理用户
PM_USER_RESPONSE=$(curl -s -X POST "http://localhost:8313/user/new" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "product_manager_001", 
    "user_alias": "Bob Chen",
    "user_email": "bob.chen@techcompany.com",
    "user_role": "internal_user",
    "team_id": "'$PRODUCT_TEAM_ID'",
    "organization_id": "'$ORG_ID'",
    "models": ["gpt-3.5-turbo"],
    "max_budget": 500.0
  }')

# 为产品经理创建受限API密钥
PM_KEY_RESPONSE=$(curl -s -X POST "http://localhost:8313/key/generate" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "product_manager_001",
    "key_alias": "bob_limited_key",
    "models": ["gpt-3.5-turbo"],
    "max_budget": 500.0,
    "rpm_limit": 20,
    "duration": "30d"
  }')

PM_USER_KEY=$(echo $PM_KEY_RESPONSE | jq -r '.key')
echo "Product Manager API Key: $PM_USER_KEY"
```

#### 2.3 创建管理员用户
```bash
# 创建系统管理员
ADMIN_USER_RESPONSE=$(curl -s -X POST "http://localhost:8313/user/new" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "system_admin_001",
    "user_alias": "Carol Liu",
    "user_email": "carol.liu@techcompany.com", 
    "user_role": "proxy_admin",
    "organization_id": "'$ORG_ID'",
    "models": ["all-proxy-models"]
  }')

# 为管理员创建全权限API密钥
ADMIN_KEY_RESPONSE=$(curl -s -X POST "http://localhost:8313/key/generate" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "system_admin_001",
    "key_alias": "carol_admin_key",
    "models": ["all-proxy-models"],
    "duration": null
  }')

ADMIN_USER_KEY=$(echo $ADMIN_KEY_RESPONSE | jq -r '.key')
echo "Admin API Key: $ADMIN_USER_KEY"
```

### 场景3：权限验证和测试

#### 3.1 测试AI研究员权限
```bash
# AI研究员应该能看到高级模型
echo "AI Researcher can access these models:"
curl -s -H "Authorization: Bearer $AI_USER_KEY" \
  "http://localhost:8313/v1/models" | jq '.data[].id'

# 测试模型调用
curl -s -X POST "http://localhost:8313/v1/chat/completions" \
  -H "Authorization: Bearer $AI_USER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello from AI researcher"}],
    "max_tokens": 50
  }' | jq '.choices[0].message.content'
```

#### 3.2 测试产品经理权限
```bash
# 产品经理只能看到基础模型
echo "Product Manager can access these models:"
curl -s -H "Authorization: Bearer $PM_USER_KEY" \
  "http://localhost:8313/v1/models" | jq '.data[].id'

# 测试受限制的模型调用（应该失败）
echo "Trying to access restricted model (should fail):"
curl -s -X POST "http://localhost:8313/v1/chat/completions" \
  -H "Authorization: Bearer $PM_USER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4", 
    "messages": [{"role": "user", "content": "Hello"}]
  }' | jq '.error.message'
```

### 场景4：动态权限调整

#### 4.1 升级产品经理权限
```bash
# 产品经理需要临时访问高级模型
curl -s -X POST "http://localhost:8313/user/update" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "product_manager_001",
    "models": ["gpt-3.5-turbo", "gpt-4"]
  }'

# 创建新的临时API密钥
TEMP_KEY_RESPONSE=$(curl -s -X POST "http://localhost:8313/key/generate" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "product_manager_001",
    "key_alias": "bob_temp_premium_key",
    "models": ["gpt-3.5-turbo", "gpt-4"],
    "max_budget": 200.0,
    "duration": "7d"
  }')

TEMP_KEY=$(echo $TEMP_KEY_RESPONSE | jq -r '.key')
echo "Temporary premium key: $TEMP_KEY"
```

#### 4.2 批量更新团队权限
```bash
# 给AI团队添加新模型
curl -s -X POST "http://localhost:8313/team/update" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "team_id": "'$AI_TEAM_ID'",
    "models": ["gpt-4", "claude-3", "qwen3-omni-30b-thinking", "dall-e-3"]
  }'

# 批量创建团队成员API密钥
TEAM_MEMBERS=("ai_researcher_002:david.kim@techcompany.com" "ai_researcher_003:emma.zhang@techcompany.com")

for member in "${TEAM_MEMBERS[@]}"; do
  IFS=':' read -r user_id email <<< "$member"
  
  # 创建用户
  curl -s -X POST "http://localhost:8313/user/new" \
    -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
    -H "Content-Type: application/json" \
    -d '{
      "user_id": "'$user_id'",
      "user_email": "'$email'",
      "team_id": "'$AI_TEAM_ID'",
      "models": ["gpt-4", "claude-3", "qwen3-omni-30b-thinking"]
    }'
    
  # 创建API密钥
  curl -s -X POST "http://localhost:8313/key/generate" \
    -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
    -H "Content-Type: application/json" \
    -d '{
      "user_id": "'$user_id'",
      "key_alias": "'$user_id'_key",
      "models": ["gpt-4", "claude-3", "qwen3-omni-30b-thinking"]
    }'
    
  echo "Created user and API key for: $user_id"
done
```

## 🚨 常见问题和踩坑指南

### 问题1：Open WebUI看不到模型

**症状**：用户登录Open WebUI后，模型列表为空

**原因分析**：
1. ❌ Open WebUI使用的全局API密钥无效
2. ❌ 用户个人API密钥未正确同步
3. ❌ LiteLLM中没有注册模型
4. ❌ 网络连接问题

**解决方案**：
```bash
# 1. 检查Open WebUI环境变量
docker exec your_openwebui_container env | grep -i "openai"

# 2. 验证全局API密钥有效性
GLOBAL_KEY="sk-your-global-key"
curl -H "Authorization: Bearer $GLOBAL_KEY" http://localhost:8313/v1/models

# 3. 检查LiteLLM模型注册
curl -H "Authorization: Bearer $LITELLM_MASTER_KEY" http://localhost:8313/v1/models

# 4. 检查网络连接
docker exec your_openwebui_container curl http://your_litellm_container:4000/health
```

**最佳实践**：
- ✅ 创建专用的全局API密钥用于Open WebUI
- ✅ 定期检查API密钥有效性
- ✅ 监控同步日志

### 问题2：用户同步失败

**症状**：在LiteLLM创建用户后，Open WebUI中看不到对应用户

**原因分析**：
1. ❌ 用户邮箱为空或格式错误
2. ❌ 数据库连接字符串错误
3. ❌ 触发器未正确安装
4. ❌ dblink扩展未启用

**诊断步骤**：
```bash
# 1. 检查同步审计日志
docker exec your_postgres_container psql -U webui -d litellm -c "
SELECT * FROM sync_audit 
WHERE operation = 'SYNC_USER' 
ORDER BY created_at DESC LIMIT 5;
"

# 2. 检查触发器状态
docker exec your_postgres_container psql -U webui -d litellm -c "
SELECT schemaname, tablename, trigger_name, trigger_enabled
FROM pg_trigger t
JOIN pg_class c ON t.tgrelid = c.oid
JOIN pg_namespace n ON c.relnamespace = n.oid  
WHERE trigger_name LIKE '%sync%';
"

# 3. 检查dblink扩展
docker exec your_postgres_container psql -U webui -d litellm -c "
SELECT * FROM pg_extension WHERE extname = 'dblink';
"

# 4. 手动测试同步函数
docker exec your_postgres_container psql -U webui -d litellm -c "
SELECT test_api_key_sync_installation();
"
```

**修复方法**：
```bash
# 重新安装触发器
docker exec your_postgres_container psql -U webui -d litellm -f /path/to/litellm-webui-sync.sql

# 启用dblink扩展
docker exec your_postgres_container psql -U webui -d litellm -c "
CREATE EXTENSION IF NOT EXISTS dblink;
"

# 手动同步现有用户
docker exec your_postgres_container psql -U webui -d litellm -f /path/to/migrate-existing-users.sql
```

### 问题3：权限不生效

**症状**：用户在LiteLLM中有模型权限，但在Open WebUI中无法使用

**原因分析**：
1. ❌ API密钥未同步到Open WebUI
2. ❌ 用户使用了错误的API密钥
3. ❌ 模型权限配置错误
4. ❌ Open WebUI缓存问题

**检查步骤**：
```bash
# 1. 检查用户API密钥同步状态
docker exec your_postgres_container psql -U webui -d webui -c "
SELECT id, email, SUBSTRING(api_key, 1, 20) || '...' as api_key_preview 
FROM \"user\" WHERE email = 'user@example.com';
"

# 2. 验证API密钥权限
USER_API_KEY="sk-user-api-key"
curl -H "Authorization: Bearer $USER_API_KEY" http://localhost:8313/v1/models

# 3. 检查LiteLLM中的用户权限
curl -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  "http://localhost:8313/user/info?user_id=your_user_id"
```

**解决方案**：
- ✅ 确保用户有有效的API密钥
- ✅ 重新生成API密钥触发同步
- ✅ 清除Open WebUI浏览器缓存

### 问题4：数据库连接错误

**症状**：同步触发器执行失败，出现连接错误

**常见错误**：
```
ERROR: could not establish connection
DETAIL: connection to server at "localhost" (127.0.0.1), port 5432 failed
```

**原因和解决**：
```bash
# 1. 检查数据库连接字符串
# 错误示例：
target_conn_str := 'host=localhost port=5432 dbname=webui user=webui password=webui';
# 正确示例（Docker环境）：
target_conn_str := 'host=your_postgres_container port=5432 dbname=webui user=webui password=webui';

# 2. 验证网络连接
docker exec your_postgres_container netstat -tlnp | grep 5432

# 3. 检查用户权限
docker exec your_postgres_container psql -U webui -d webui -c "\du"
```

### 问题5：模型权限继承混乱

**症状**：用户权限与团队/组织权限不一致

**权限继承逻辑**：
```
组织权限 → 团队权限 → 用户权限 → API密钥权限
   ↓          ↓          ↓          ↓
 最宽泛     团队限制    用户限制   密钥限制
```

**最佳实践**：
```bash
# 1. 组织级别：设置最大权限范围
curl -X POST "http://localhost:8313/organization/update" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -d '{
    "organization_id": "org_id",
    "models": ["gpt-4", "gpt-3.5-turbo", "claude-3"]  // 组织最大权限
  }'

# 2. 团队级别：基于业务需要限制
curl -X POST "http://localhost:8313/team/update" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -d '{
    "team_id": "team_id", 
    "models": ["gpt-3.5-turbo", "claude-3"]  // 团队权限 ⊆ 组织权限
  }'

# 3. 用户级别：个人权限调整
curl -X POST "http://localhost:8313/user/update" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -d '{
    "user_id": "user_id",
    "models": ["gpt-3.5-turbo"]  // 用户权限 ⊆ 团队权限
  }'

# 4. API密钥级别：最终执行权限
curl -X POST "http://localhost:8313/key/generate" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -d '{
    "user_id": "user_id",
    "models": ["gpt-3.5-turbo"]  // 密钥权限 ⊆ 用户权限
  }'
```

## 📊 监控和调试

### 实时监控脚本

#### 1. 同步状态监控
```bash
#!/bin/bash
# monitor-sync.sh - 监控同步状态

echo "=== 用户同步状态 ==="
docker exec your_postgres_container psql -U webui -d litellm -c "
SELECT 
  COUNT(*) as litellm_users,
  COUNT(CASE WHEN user_email IS NOT NULL THEN 1 END) as users_with_email
FROM \"LiteLLM_UserTable\";
"

docker exec your_postgres_container psql -U webui -d webui -c "
SELECT COUNT(*) as openwebui_users FROM \"user\" WHERE id LIKE 'usr_%';
"

echo "=== API密钥同步状态 ==="
docker exec your_postgres_container psql -U webui -d litellm -c "
SELECT 
  COUNT(*) as total_tokens,
  COUNT(CASE WHEN user_id IS NOT NULL THEN 1 END) as user_tokens
FROM \"LiteLLM_VerificationToken\";
"

docker exec your_postgres_container psql -U webui -d webui -c "
SELECT COUNT(*) as users_with_api_key FROM \"user\" WHERE api_key IS NOT NULL;
"

echo "=== 近期同步日志 ==="
docker exec your_postgres_container psql -U webui -d litellm -c "
SELECT operation, sync_result, COUNT(*) as count
FROM sync_audit 
WHERE created_at > CURRENT_TIMESTAMP - INTERVAL '1 hour'
GROUP BY operation, sync_result
ORDER BY operation, sync_result;
"
```

#### 2. 权限验证脚本
```bash
#!/bin/bash
# verify-permissions.sh - 验证用户权限

USER_EMAIL="$1"
if [ -z "$USER_EMAIL" ]; then
  echo "Usage: $0 <user_email>"
  exit 1
fi

echo "=== 验证用户权限: $USER_EMAIL ==="

# 获取LiteLLM中的用户信息
echo "--- LiteLLM用户信息 ---"
docker exec your_postgres_container psql -U webui -d litellm -c "
SELECT user_id, user_role, models, team_id 
FROM \"LiteLLM_UserTable\" 
WHERE user_email = '$USER_EMAIL';
"

# 获取Open WebUI中的用户信息
echo "--- Open WebUI用户信息 ---"
docker exec your_postgres_container psql -U webui -d webui -c "
SELECT id, role, SUBSTRING(api_key, 1, 20) || '...' as api_key_preview
FROM \"user\" 
WHERE email = '$USER_EMAIL';
"

# 获取用户API密钥
echo "--- 用户API密钥 ---"  
docker exec your_postgres_container psql -U webui -d litellm -c "
SELECT token, models, key_alias, created_at
FROM \"LiteLLM_VerificationToken\" vt
JOIN \"LiteLLM_UserTable\" ut ON vt.user_id = ut.user_id
WHERE ut.user_email = '$USER_EMAIL'
ORDER BY vt.created_at DESC;
"
```

#### 3. 性能监控
```bash
#!/bin/bash
# performance-monitor.sh - 性能监控

echo "=== API调用统计 ==="
docker exec your_postgres_container psql -U webui -d litellm -c "
SELECT 
  DATE(created_at) as date,
  COUNT(*) as total_calls,
  SUM(spend) as total_spend,
  AVG(spend) as avg_spend_per_call
FROM \"LiteLLM_SpendLogs\"
WHERE created_at > CURRENT_TIMESTAMP - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY date DESC;
"

echo "=== 用户消费排行 ==="
docker exec your_postgres_container psql -U webui -d litellm -c "
SELECT 
  u.user_email,
  u.spend as total_spend,
  u.max_budget,
  ROUND((u.spend / NULLIF(u.max_budget, 0) * 100), 2) as budget_usage_pct
FROM \"LiteLLM_UserTable\" u
WHERE u.user_email IS NOT NULL
ORDER BY u.spend DESC
LIMIT 10;
"

echo "=== 系统健康状态 ==="
# 检查LiteLLM健康状态
curl -s -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  http://localhost:8313/health | jq '.healthy_count, .unhealthy_count'

# 检查Open WebUI响应
curl -s -o /dev/null -w "Open WebUI响应时间: %{time_total}s\n" \
  http://localhost:8333/health
```

### 故障排查清单

#### 快速诊断命令
```bash
# 1. 检查所有容器状态
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# 2. 检查网络连通性
docker exec your_openwebui_container curl -f http://your_litellm_container:4000/health

# 3. 检查数据库连接
docker exec your_postgres_container psql -U webui -c "\l"

# 4. 检查同步触发器
docker exec your_postgres_container psql -U webui -d litellm -c "
\df *sync*
"

# 5. 检查最近的错误日志
docker logs your_openwebui_container --tail 50 | grep -i error
docker logs your_litellm_container --tail 50 | grep -i error
```

#### 应急恢复流程
```bash
#!/bin/bash
# emergency-recovery.sh - 应急恢复

echo "开始应急恢复流程..."

# 1. 备份当前状态
echo "备份数据库..."
docker exec your_postgres_container pg_dump -U webui litellm > backup_litellm_$(date +%Y%m%d_%H%M%S).sql
docker exec your_postgres_container pg_dump -U webui webui > backup_webui_$(date +%Y%m%d_%H%M%S).sql

# 2. 重启所有服务
echo "重启服务..."
docker restart your_postgres_container your_litellm_container your_openwebui_container

# 3. 等待服务启动
echo "等待服务启动..."
sleep 30

# 4. 验证服务状态
echo "验证服务状态..."
for service in your_postgres_container your_litellm_container your_openwebui_container; do
  if docker ps --format '{{.Names}}' | grep -q "^${service}$"; then
    echo "✅ $service 运行正常"
  else
    echo "❌ $service 启动失败"
  fi
done

# 5. 重新安装触发器（如果需要）
echo "重新安装同步触发器..."
docker exec your_postgres_container psql -U webui -d litellm -f /path/to/litellm-webui-sync.sql
docker exec your_postgres_container psql -U webui -d litellm -f /path/to/api-key-sync.sql

echo "应急恢复完成！"
```

## 🎯 最佳实践总结

### 1. 架构设计
- ✅ LiteLLM作为唯一的权限管理中心
- ✅ Open WebUI仅作为用户界面，不独立管理权限
- ✅ 数据库分离：`litellm`用于权限，`webui`用于界面
- ✅ 通过触发器实现实时数据同步

### 2. 权限管理
- ✅ 遵循组织→团队→用户→API密钥的权限继承链
- ✅ 为不同角色创建专用API密钥
- ✅ 定期审计用户权限和消费情况
- ✅ 为临时需求创建有期限的API密钥

### 3. 运维监控
- ✅ 监控同步状态和错误日志
- ✅ 定期备份关键数据
- ✅ 设置预算告警和使用量监控
- ✅ 准备应急恢复流程

### 4. 安全考虑
- ✅ 使用强密码和安全的API密钥
- ✅ 限制API密钥的权限范围
- ✅ 定期轮换API密钥
- ✅ 监控异常使用行为

通过以上完整的集成方案，你可以实现LiteLLM和Open WebUI的完美结合，既保持了LiteLLM强大的权限控制能力，又提供了Open WebUI优秀的用户体验。这套方案已经在生产环境中验证，能够稳定支持多租户、细粒度权限控制的企业级LLM应用场景。
# LiteLLM + Open WebUI Integration Know-How

## 📋 Table of Contents
- [Architecture Overview](#architecture-overview)
- [Why This Integration](#why-this-integration)
- [Database Schema Overview](#database-schema-overview)
- [Complete Integration Steps](#complete-integration-steps)
- [User Permission Management](#user-permission-management)
- [Common Issues and Pitfalls](#common-issues-and-pitfalls)
- [Monitoring and Debugging](#monitoring-and-debugging)

## 🏗️ Architecture Overview

### Overall Architecture
```
┌─────────────────┐    PostgreSQL     ┌──────────────────┐
│    LiteLLM      │    Triggers       │   Open WebUI     │
│ (Auth Center)   │ ────────────────► │  (User Interface)│
│                 │                   │                  │
│ • User Mgmt     │                   │ • Chat Interface │
│ • API Keys      │                   │ • User Sync      │
│ • Model Perms   │                   │ • Model Display  │
│ • Teams/Orgs    │                   │ • Session Mgmt   │
└─────────────────┘                   └──────────────────┘
         │                                     │
         ├─ Database: litellm                  ├─ Database: webui
         ├─ Port: 8313                         ├─ Port: 8333
         └─ Role: Permission & Model Mgmt      └─ Role: User Interaction
```

### Data Flow
1. **Admin** creates users, teams, organizations in LiteLLM
2. **PostgreSQL triggers** automatically sync user info to Open WebUI
3. **API Key creation** automatically syncs to Open WebUI user table
4. **Users login** to Open WebUI and see permission-based model lists

## 🎯 Why This Integration

### Pain Points
- **Fragmented Management**: LiteLLM excels at permission control, Open WebUI excels at user experience
- **Duplicate Work**: Both systems maintain separate user and permission databases
- **Permission Inconsistency**: Difficult to centrally control who can access which models
- **Operational Complexity**: Need to manage users in two separate systems

### Solution Benefits
- ✅ **Unified Permission Center**: LiteLLM as the single source of truth for permissions
- ✅ **Automatic Sync**: Real-time user and permission sync without manual maintenance
- ✅ **Fine-grained Control**: Support for user, team, organization three-tier permissions
- ✅ **Model Permission Isolation**: Different users see different model lists
- ✅ **Enterprise Ready**: Multi-tenant, audit logs, budget controls

## 🗃️ Database Schema Overview

### LiteLLM Core Tables (litellm database)

#### 1. User Table - LiteLLM_UserTable
```sql
-- User basic information
user_id              TEXT PRIMARY KEY    -- Unique user ID
user_email           TEXT                -- Email (for Open WebUI login)
user_alias           TEXT                -- Display name
user_role            TEXT                -- Role: proxy_admin/internal_user/internal_user_viewer
team_id              TEXT                -- Team ID
organization_id      TEXT                -- Organization ID
models               TEXT[]              -- Models user can access
spend                DOUBLE PRECISION    -- Spending amount
max_budget           DOUBLE PRECISION    -- Budget limit
created_at           TIMESTAMP           -- Creation time
updated_at           TIMESTAMP           -- Update time
```

#### 2. API Key Table - LiteLLM_VerificationToken
```sql
-- API keys and permissions
token                TEXT PRIMARY KEY    -- API key
user_id              TEXT                -- Associated user ID  
key_alias            TEXT                -- Key alias
models               TEXT[]              -- Models this key can access
spend                DOUBLE PRECISION    -- Spending record
max_budget           DOUBLE PRECISION    -- Budget limit
expires              TIMESTAMP           -- Expiration time
blocked              BOOLEAN             -- Whether blocked
created_at           TIMESTAMP           -- Creation time
```

#### 3. Team Table - LiteLLM_TeamTable
```sql
-- Team management
team_id              TEXT PRIMARY KEY    -- Team ID
team_alias           TEXT                -- Team name
organization_id      TEXT                -- Parent organization
models               TEXT[]              -- Models team can access
spend                DOUBLE PRECISION    -- Team spending
max_budget           DOUBLE PRECISION    -- Team budget
members_with_roles   JSONB               -- Members and their roles
created_at           TIMESTAMP           -- Creation time
```

#### 4. Organization Table - LiteLLM_OrganizationTable
```sql
-- Organization management  
organization_id      TEXT PRIMARY KEY    -- Organization ID
organization_alias   TEXT                -- Organization name
models               TEXT[]              -- Models organization can access
spend                DOUBLE PRECISION    -- Organization spending
max_budget           DOUBLE PRECISION    -- Organization budget
created_at           TIMESTAMP           -- Creation time
```

#### 5. Sync Audit Table - sync_audit
```sql
-- Sync operation records
id                   SERIAL PRIMARY KEY  -- Record ID
operation            VARCHAR(20)         -- Operation type: SYNC_USER/SYNC_API_KEY
record_id            TEXT                -- Associated record ID
sync_result          VARCHAR(20)         -- Sync result: SUCCESS/FAILED
old_data            JSONB               -- Data before sync
new_data            JSONB               -- Data after sync
error_message       TEXT                -- Error message
created_at          TIMESTAMP           -- Creation time
```

### Open WebUI Core Tables (webui database)

#### 1. User Table - user
```sql
-- Open WebUI user information
id                   TEXT PRIMARY KEY    -- User ID (format: usr_original_user_id)
name                 TEXT                -- Display name  
email                TEXT                -- Email
role                 TEXT                -- Role: admin/user
api_key              TEXT                -- Personal API key (synced from LiteLLM)
profile_image_url    TEXT                -- Avatar URL
settings             TEXT                -- User settings (JSON)
created_at           BIGINT              -- Creation timestamp
updated_at           BIGINT              -- Update timestamp
```

#### 2. Auth Table - auth
```sql
-- Login authentication info
id                   TEXT PRIMARY KEY    -- User ID (same as user.id)
email                TEXT                -- Email
password             TEXT                -- Password hash
active               BOOLEAN             -- Whether active
```

#### 3. Group Table - group
```sql  
-- Organization mapped to groups
id                   TEXT PRIMARY KEY    -- Group ID (format: grp_organization_id)
name                 TEXT                -- Group name
description          TEXT                -- Description
meta                 JSONB               -- Metadata (stores organization info)
created_at           BIGINT              -- Creation timestamp
updated_at           BIGINT              -- Update timestamp
```

## 🚀 Complete Integration Steps

### Step 1: Environment Preparation

#### 1.1 Ensure PostgreSQL Instance is Running
```bash
# Check PostgreSQL container
docker ps | grep postgres

# Check database connection
docker exec your_postgres_container psql -U webui -l
```

#### 1.2 Verify LiteLLM and Open WebUI Containers
```bash
# Check LiteLLM (usually on port 4000)
curl -H "Authorization: Bearer your-master-key" http://localhost:8313/health

# Check Open WebUI (usually on port 8080)  
curl http://localhost:8333/health
```

### Step 2: Install Sync System

#### 2.1 Install Basic User Sync
```bash
# Download SQL files
wget https://raw.githubusercontent.com/pkusnail/open-webui-litellm-user-bridge/main/sql/litellm-webui-sync.sql

# Edit connection string
nano sql/litellm-webui-sync.sql
# Modify: target_conn_str TEXT := 'host=localhost port=5432 dbname=webui user=webui password=webui';

# Execute installation
docker exec your_postgres_container psql -U webui -d litellm -f /path/to/litellm-webui-sync.sql
```

#### 2.2 Install API Key Sync (Optional but Recommended)
```bash
# Download API key sync extension
wget https://raw.githubusercontent.com/pkusnail/open-webui-litellm-user-bridge/main/sql/api-key-sync.sql

# Execute installation
docker exec your_postgres_container psql -U webui -d litellm -f /path/to/api-key-sync.sql
```

#### 2.3 Verify Installation
```bash
# Verify trigger installation
docker exec your_postgres_container psql -U webui -d litellm -c "
SELECT test_api_key_sync_installation();
"

# Check trigger status
docker exec your_postgres_container psql -U webui -d litellm -c "
SELECT schemaname, tablename, trigger_name 
FROM pg_trigger t
JOIN pg_class c ON t.tgrelid = c.oid  
JOIN pg_namespace n ON c.relnamespace = n.oid
WHERE trigger_name LIKE '%sync%';
"
```

### Step 3: Configure Open WebUI Connection

#### 3.1 Create Global API Key
```bash
# Set master key
export LITELLM_MASTER_KEY="your-litellm-master-key"

# Create global API key (allow access to all models)
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

#### 3.2 Restart Open WebUI with New Key
```bash
# Stop current container
docker stop your_openwebui_container

# Start with new API key
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

## 👥 User Permission Management

### Scenario 1: Create Basic Organizational Structure

#### 1.1 Create Organization
```bash
export LITELLM_MASTER_KEY="your-master-key"

# Create tech company organization
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

#### 1.2 Create Teams
```bash
# AI Research Team (access to advanced models)
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

# Product Team (access to basic models)
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

### Scenario 2: Create Users and Assign Permissions

#### 2.1 Create AI Researcher (High Privilege User)
```bash
# Create AI researcher user
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

# Create API key for user (automatically syncs to Open WebUI)
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

#### 2.2 Create Product Manager (Limited Privilege User)
```bash
# Create product manager user
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

# Create limited API key for product manager
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

#### 2.3 Create Admin User
```bash
# Create system administrator
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

# Create full privilege API key for admin
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

### Scenario 3: Permission Verification and Testing

#### 3.1 Test AI Researcher Permissions
```bash
# AI researcher should see advanced models
echo "AI Researcher can access these models:"
curl -s -H "Authorization: Bearer $AI_USER_KEY" \
  "http://localhost:8313/v1/models" | jq '.data[].id'

# Test model invocation
curl -s -X POST "http://localhost:8313/v1/chat/completions" \
  -H "Authorization: Bearer $AI_USER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello from AI researcher"}],
    "max_tokens": 50
  }' | jq '.choices[0].message.content'
```

#### 3.2 Test Product Manager Permissions
```bash
# Product manager should only see basic models
echo "Product Manager can access these models:"
curl -s -H "Authorization: Bearer $PM_USER_KEY" \
  "http://localhost:8313/v1/models" | jq '.data[].id'

# Test restricted model call (should fail)
echo "Trying to access restricted model (should fail):"
curl -s -X POST "http://localhost:8313/v1/chat/completions" \
  -H "Authorization: Bearer $PM_USER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4", 
    "messages": [{"role": "user", "content": "Hello"}]
  }' | jq '.error.message'
```

### Scenario 4: Dynamic Permission Adjustment

#### 4.1 Upgrade Product Manager Permissions
```bash
# Product manager needs temporary access to advanced models
curl -s -X POST "http://localhost:8313/user/update" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "product_manager_001",
    "models": ["gpt-3.5-turbo", "gpt-4"]
  }'

# Create new temporary API key
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

#### 4.2 Bulk Update Team Permissions
```bash
# Add new model to AI team
curl -s -X POST "http://localhost:8313/team/update" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "team_id": "'$AI_TEAM_ID'",
    "models": ["gpt-4", "claude-3", "qwen3-omni-30b-thinking", "dall-e-3"]
  }'

# Batch create team member API keys
TEAM_MEMBERS=("ai_researcher_002:david.kim@techcompany.com" "ai_researcher_003:emma.zhang@techcompany.com")

for member in "${TEAM_MEMBERS[@]}"; do
  IFS=':' read -r user_id email <<< "$member"
  
  # Create user
  curl -s -X POST "http://localhost:8313/user/new" \
    -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
    -H "Content-Type: application/json" \
    -d '{
      "user_id": "'$user_id'",
      "user_email": "'$email'",
      "team_id": "'$AI_TEAM_ID'",
      "models": ["gpt-4", "claude-3", "qwen3-omni-30b-thinking"]
    }'
    
  # Create API key
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

## 🚨 Common Issues and Pitfalls

### Issue 1: Open WebUI Can't See Models

**Symptoms**: User logs into Open WebUI but model list is empty

**Root Cause Analysis**:
1. ❌ Open WebUI global API key is invalid
2. ❌ User personal API key not synced correctly
3. ❌ No models registered in LiteLLM
4. ❌ Network connectivity issues

**Solution**:
```bash
# 1. Check Open WebUI environment variables
docker exec your_openwebui_container env | grep -i "openai"

# 2. Verify global API key validity
GLOBAL_KEY="sk-your-global-key"
curl -H "Authorization: Bearer $GLOBAL_KEY" http://localhost:8313/v1/models

# 3. Check LiteLLM model registration
curl -H "Authorization: Bearer $LITELLM_MASTER_KEY" http://localhost:8313/v1/models

# 4. Check network connectivity
docker exec your_openwebui_container curl http://your_litellm_container:4000/health
```

**Best Practices**:
- ✅ Create dedicated global API key for Open WebUI
- ✅ Regularly check API key validity
- ✅ Monitor sync logs

### Issue 2: User Sync Failure

**Symptoms**: After creating user in LiteLLM, user doesn't appear in Open WebUI

**Root Cause Analysis**:
1. ❌ User email is empty or invalid format
2. ❌ Database connection string is incorrect
3. ❌ Triggers not properly installed
4. ❌ dblink extension not enabled

**Diagnostic Steps**:
```bash
# 1. Check sync audit logs
docker exec your_postgres_container psql -U webui -d litellm -c "
SELECT * FROM sync_audit 
WHERE operation = 'SYNC_USER' 
ORDER BY created_at DESC LIMIT 5;
"

# 2. Check trigger status
docker exec your_postgres_container psql -U webui -d litellm -c "
SELECT schemaname, tablename, trigger_name, trigger_enabled
FROM pg_trigger t
JOIN pg_class c ON t.tgrelid = c.oid
JOIN pg_namespace n ON c.relnamespace = n.oid  
WHERE trigger_name LIKE '%sync%';
"

# 3. Check dblink extension
docker exec your_postgres_container psql -U webui -d litellm -c "
SELECT * FROM pg_extension WHERE extname = 'dblink';
"

# 4. Test sync function manually
docker exec your_postgres_container psql -U webui -d litellm -c "
SELECT test_api_key_sync_installation();
"
```

**Fix Methods**:
```bash
# Reinstall triggers
docker exec your_postgres_container psql -U webui -d litellm -f /path/to/litellm-webui-sync.sql

# Enable dblink extension
docker exec your_postgres_container psql -U webui -d litellm -c "
CREATE EXTENSION IF NOT EXISTS dblink;
"

# Manually sync existing users
docker exec your_postgres_container psql -U webui -d litellm -f /path/to/migrate-existing-users.sql
```

### Issue 3: Permissions Not Taking Effect

**Symptoms**: User has model permissions in LiteLLM but can't use them in Open WebUI

**Root Cause Analysis**:
1. ❌ API key not synced to Open WebUI
2. ❌ User using wrong API key
3. ❌ Model permissions misconfigured
4. ❌ Open WebUI cache issues

**Check Steps**:
```bash
# 1. Check user API key sync status
docker exec your_postgres_container psql -U webui -d webui -c "
SELECT id, email, SUBSTRING(api_key, 1, 20) || '...' as api_key_preview 
FROM \"user\" WHERE email = 'user@example.com';
"

# 2. Verify API key permissions
USER_API_KEY="sk-user-api-key"
curl -H "Authorization: Bearer $USER_API_KEY" http://localhost:8313/v1/models

# 3. Check user permissions in LiteLLM
curl -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  "http://localhost:8313/user/info?user_id=your_user_id"
```

**Solutions**:
- ✅ Ensure user has valid API key
- ✅ Regenerate API key to trigger sync
- ✅ Clear Open WebUI browser cache

### Issue 4: Database Connection Error

**Symptoms**: Sync triggers fail with connection errors

**Common Errors**:
```
ERROR: could not establish connection
DETAIL: connection to server at "localhost" (127.0.0.1), port 5432 failed
```

**Cause and Solution**:
```bash
# 1. Check database connection string
# Wrong example:
target_conn_str := 'host=localhost port=5432 dbname=webui user=webui password=webui';
# Correct example (Docker environment):
target_conn_str := 'host=your_postgres_container port=5432 dbname=webui user=webui password=webui';

# 2. Verify network connectivity
docker exec your_postgres_container netstat -tlnp | grep 5432

# 3. Check user permissions
docker exec your_postgres_container psql -U webui -d webui -c "\du"
```

### Issue 5: Model Permission Inheritance Confusion

**Symptoms**: User permissions inconsistent with team/organization permissions

**Permission Inheritance Logic**:
```
Organization Perms → Team Perms → User Perms → API Key Perms
       ↓               ↓           ↓            ↓
   Broadest        Team Limit   User Limit   Key Limit
```

**Best Practices**:
```bash
# 1. Organization level: Set maximum permission scope
curl -X POST "http://localhost:8313/organization/update" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -d '{
    "organization_id": "org_id",
    "models": ["gpt-4", "gpt-3.5-turbo", "claude-3"]  // Organization max permissions
  }'

# 2. Team level: Limit based on business needs
curl -X POST "http://localhost:8313/team/update" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -d '{
    "team_id": "team_id", 
    "models": ["gpt-3.5-turbo", "claude-3"]  // Team perms ⊆ Org perms
  }'

# 3. User level: Individual permission adjustments
curl -X POST "http://localhost:8313/user/update" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -d '{
    "user_id": "user_id",
    "models": ["gpt-3.5-turbo"]  // User perms ⊆ Team perms
  }'

# 4. API key level: Final execution permissions
curl -X POST "http://localhost:8313/key/generate" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -d '{
    "user_id": "user_id",
    "models": ["gpt-3.5-turbo"]  // Key perms ⊆ User perms
  }'
```

## 📊 Monitoring and Debugging

### Real-time Monitoring Scripts

#### 1. Sync Status Monitor
```bash
#!/bin/bash
# monitor-sync.sh - Monitor sync status

echo "=== User Sync Status ==="
docker exec your_postgres_container psql -U webui -d litellm -c "
SELECT 
  COUNT(*) as litellm_users,
  COUNT(CASE WHEN user_email IS NOT NULL THEN 1 END) as users_with_email
FROM \"LiteLLM_UserTable\";
"

docker exec your_postgres_container psql -U webui -d webui -c "
SELECT COUNT(*) as openwebui_users FROM \"user\" WHERE id LIKE 'usr_%';
"

echo "=== API Key Sync Status ==="
docker exec your_postgres_container psql -U webui -d litellm -c "
SELECT 
  COUNT(*) as total_tokens,
  COUNT(CASE WHEN user_id IS NOT NULL THEN 1 END) as user_tokens
FROM \"LiteLLM_VerificationToken\";
"

docker exec your_postgres_container psql -U webui -d webui -c "
SELECT COUNT(*) as users_with_api_key FROM \"user\" WHERE api_key IS NOT NULL;
"

echo "=== Recent Sync Logs ==="
docker exec your_postgres_container psql -U webui -d litellm -c "
SELECT operation, sync_result, COUNT(*) as count
FROM sync_audit 
WHERE created_at > CURRENT_TIMESTAMP - INTERVAL '1 hour'
GROUP BY operation, sync_result
ORDER BY operation, sync_result;
"
```

#### 2. Permission Verification Script
```bash
#!/bin/bash
# verify-permissions.sh - Verify user permissions

USER_EMAIL="$1"
if [ -z "$USER_EMAIL" ]; then
  echo "Usage: $0 <user_email>"
  exit 1
fi

echo "=== Verifying User Permissions: $USER_EMAIL ==="

# Get LiteLLM user info
echo "--- LiteLLM User Info ---"
docker exec your_postgres_container psql -U webui -d litellm -c "
SELECT user_id, user_role, models, team_id 
FROM \"LiteLLM_UserTable\" 
WHERE user_email = '$USER_EMAIL';
"

# Get Open WebUI user info
echo "--- Open WebUI User Info ---"
docker exec your_postgres_container psql -U webui -d webui -c "
SELECT id, role, SUBSTRING(api_key, 1, 20) || '...' as api_key_preview
FROM \"user\" 
WHERE email = '$USER_EMAIL';
"

# Get user API keys
echo "--- User API Keys ---"  
docker exec your_postgres_container psql -U webui -d litellm -c "
SELECT token, models, key_alias, created_at
FROM \"LiteLLM_VerificationToken\" vt
JOIN \"LiteLLM_UserTable\" ut ON vt.user_id = ut.user_id
WHERE ut.user_email = '$USER_EMAIL'
ORDER BY vt.created_at DESC;
"
```

#### 3. Performance Monitor
```bash
#!/bin/bash
# performance-monitor.sh - Performance monitoring

echo "=== API Call Statistics ==="
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

echo "=== User Spending Ranking ==="
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

echo "=== System Health Status ==="
# Check LiteLLM health
curl -s -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  http://localhost:8313/health | jq '.healthy_count, .unhealthy_count'

# Check Open WebUI response time
curl -s -o /dev/null -w "Open WebUI Response Time: %{time_total}s\n" \
  http://localhost:8333/health
```

### Troubleshooting Checklist

#### Quick Diagnostic Commands
```bash
# 1. Check all container statuses
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# 2. Check network connectivity
docker exec your_openwebui_container curl -f http://your_litellm_container:4000/health

# 3. Check database connections
docker exec your_postgres_container psql -U webui -c "\l"

# 4. Check sync triggers
docker exec your_postgres_container psql -U webui -d litellm -c "
\df *sync*
"

# 5. Check recent error logs
docker logs your_openwebui_container --tail 50 | grep -i error
docker logs your_litellm_container --tail 50 | grep -i error
```

#### Emergency Recovery Process
```bash
#!/bin/bash
# emergency-recovery.sh - Emergency recovery

echo "Starting emergency recovery process..."

# 1. Backup current state
echo "Backing up databases..."
docker exec your_postgres_container pg_dump -U webui litellm > backup_litellm_$(date +%Y%m%d_%H%M%S).sql
docker exec your_postgres_container pg_dump -U webui webui > backup_webui_$(date +%Y%m%d_%H%M%S).sql

# 2. Restart all services
echo "Restarting services..."
docker restart your_postgres_container your_litellm_container your_openwebui_container

# 3. Wait for services to start
echo "Waiting for services to start..."
sleep 30

# 4. Verify service status
echo "Verifying service status..."
for service in your_postgres_container your_litellm_container your_openwebui_container; do
  if docker ps --format '{{.Names}}' | grep -q "^${service}$"; then
    echo "✅ $service running normally"
  else
    echo "❌ $service failed to start"
  fi
done

# 5. Reinstall triggers if needed
echo "Reinstalling sync triggers..."
docker exec your_postgres_container psql -U webui -d litellm -f /path/to/litellm-webui-sync.sql
docker exec your_postgres_container psql -U webui -d litellm -f /path/to/api-key-sync.sql

echo "Emergency recovery completed!"
```

## 🎯 Best Practices Summary

### 1. Architecture Design
- ✅ LiteLLM as the single source of truth for permission management
- ✅ Open WebUI only as user interface, not independent permission management
- ✅ Database separation: `litellm` for permissions, `webui` for interface
- ✅ Real-time data sync through triggers

### 2. Permission Management
- ✅ Follow organization→team→user→API key permission inheritance chain
- ✅ Create dedicated API keys for different roles
- ✅ Regular audit of user permissions and spending
- ✅ Create time-limited API keys for temporary needs

### 3. Operations and Monitoring
- ✅ Monitor sync status and error logs
- ✅ Regular backup of critical data
- ✅ Set budget alerts and usage monitoring
- ✅ Prepare emergency recovery procedures

### 4. Security Considerations
- ✅ Use strong passwords and secure API keys
- ✅ Limit API key permission scope
- ✅ Regular API key rotation
- ✅ Monitor abnormal usage behavior

Through this complete integration solution, you can achieve perfect combination of LiteLLM and Open WebUI, maintaining LiteLLM's powerful permission control capabilities while providing Open WebUI's excellent user experience. This solution has been validated in production environments and can stably support enterprise-grade LLM applications with multi-tenancy and fine-grained permission control scenarios.
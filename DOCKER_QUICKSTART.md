# Docker Quick Start Guide

Complete Docker setup for LiteLLM + Open WebUI + User Bridge integration.

## 🐳 Prerequisites

- Docker & Docker Compose installed
- At least 4GB RAM available
- Ports 3000, 8000, 5432, 8777 available

## 🚀 Quick Setup

### 1. Create Docker Compose File

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  # PostgreSQL Database (shared by both services)
  postgres:
    image: postgres:16
    container_name: postgres_litellm_webui
    environment:
      POSTGRES_USER: webui
      POSTGRES_PASSWORD: webui
      POSTGRES_DB: webui
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init-databases.sql:/docker-entrypoint-initdb.d/init-databases.sql
    restart: unless-stopped

  # LiteLLM Proxy
  litellm:
    image: ghcr.io/berriai/litellm:main-latest
    container_name: litellm_proxy
    environment:
      DATABASE_URL: "postgresql://webui:webui@postgres:5432/litellm"
      STORE_MODEL_IN_DB: "True"
    ports:
      - "8000:4000"
    depends_on:
      - postgres
    volumes:
      - ./litellm_config.yaml:/app/config.yaml
    command: ["--config", "/app/config.yaml", "--port", "4000", "--num_workers", "1"]
    restart: unless-stopped

  # Open WebUI
  open-webui:
    image: ghcr.io/open-webui/open-webui:0.6.30
    container_name: open_webui
    environment:
      DATABASE_URL: "postgresql://webui:webui@postgres:5432/webui"
      OPENAI_API_BASE_URL: "http://litellm:4000/v1"
      OPENAI_API_KEY: "sk-1234567890abcdefghijklmnopqrstuvwxyz"
      WEBUI_AUTH: "True"
    ports:
      - "3000:8080"
    depends_on:
      - postgres
      - litellm
    volumes:
      - open_webui_data:/app/backend/data
    restart: unless-stopped

  # pgAdmin (optional - for database management)
  pgadmin:
    image: dpage/pgadmin4:latest
    container_name: pgadmin_webui
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@example.com
      PGADMIN_DEFAULT_PASSWORD: admin123
      PGADMIN_LISTEN_PORT: 80
    ports:
      - "8777:80"
    depends_on:
      - postgres
    restart: unless-stopped

volumes:
  postgres_data:
  open_webui_data:
```

### 2. Create Database Initialization Script

Create `init-databases.sql`:

```sql
-- Create databases for LiteLLM and WebUI
CREATE DATABASE litellm;
GRANT ALL PRIVILEGES ON DATABASE litellm TO webui;
GRANT ALL PRIVILEGES ON DATABASE webui TO webui;

-- Enable dblink extension in litellm database for sync bridge
\\c litellm;
CREATE EXTENSION IF NOT EXISTS dblink;
```

### 3. Create LiteLLM Configuration

Create `litellm_config.yaml`:

```yaml
model_list:
  - model_name: gpt-4o-mini
    litellm_params:
      model: openai/gpt-4o-mini
      api_key: "os.environ/OPENAI_API_KEY"

  - model_name: claude-3-sonnet
    litellm_params:
      model: anthropic/claude-3-sonnet-20240229
      api_key: "os.environ/ANTHROPIC_API_KEY"

general_settings:
  store_model_in_db: true
  
litellm_settings:
  success_callback: ["postgres"]
  failure_callback: ["postgres"]
```

### 4. Set Environment Variables

Create `.env` file:

```bash
# LLM Provider API Keys
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
GOOGLE_API_KEY=your_google_api_key_here

# Database Configuration
POSTGRES_USER=webui
POSTGRES_PASSWORD=webui
POSTGRES_DB=webui
```

### 5. Start the Stack

```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

## 🔗 Install User Bridge

After the stack is running:

### 1. Download the Bridge Script

```bash
# Download from GitHub
wget https://github.com/pkusnail/open-webui-litellm-user-bridge/raw/main/sql/litellm-webui-sync.sql

# Or clone the repo
git clone https://github.com/pkusnail/open-webui-litellm-user-bridge.git
```

### 2. Install the Bridge

```bash
# Copy script to PostgreSQL container
docker cp litellm-webui-sync.sql postgres_litellm_webui:/tmp/

# Execute the script
docker exec postgres_litellm_webui psql -U webui -d litellm -f /tmp/litellm-webui-sync.sql
```

### 3. Verify Installation

```bash
# Check sync status
docker exec postgres_litellm_webui psql -U webui -d litellm -c "SELECT * FROM check_sync_status();"

# Expected output:
#        metric         |  value  
# -----------------------+---------
#  LiteLLM Organizations | 0
#  LiteLLM Teams         | 0
#  LiteLLM Users         | 1
#  Sync Mappings         | 0
#  Total Audit Records   | 1
#  Success Rate          | 100.00%
```

## 🌐 Access Your Services

| Service | URL | Default Credentials |
|---------|-----|---------------------|
| **Open WebUI** | http://localhost:3000 | Register first user (becomes admin) |
| **LiteLLM Proxy** | http://localhost:8000 | API endpoint |
| **LiteLLM Admin UI** | http://localhost:8000/ui | Swagger interface |
| **pgAdmin** | http://localhost:8777 | admin@example.com / admin123 |

### pgAdmin Database Connection

When setting up pgAdmin connection:
- **Host**: postgres (container name)
- **Port**: 5432
- **Username**: webui
- **Password**: webui
- **Database**: litellm (or webui)

## 📊 Testing the Bridge

### 1. Create Organization in LiteLLM

```bash
# Connect to database
docker exec -it postgres_litellm_webui psql -U webui -d litellm

# Create budget first
INSERT INTO "LiteLLM_BudgetTable" (budget_id, max_budget, created_at, updated_at, created_by, updated_by) 
VALUES ('budget-demo', 1000.0, NOW(), NOW(), 'system', 'system');

# Create organization
INSERT INTO "LiteLLM_OrganizationTable" 
(organization_id, organization_alias, budget_id, created_by, updated_by, created_at, updated_at) 
VALUES ('demo-org', 'Demo Organization', 'budget-demo', 'admin', 'admin', NOW(), NOW());
```

### 2. Verify Sync in Open WebUI

```bash
# Check if group was created
docker exec postgres_litellm_webui psql -U webui -d webui -c "SELECT id, name FROM \"group\";"

# Expected output:
#       id       |      name       
# ---------------+----------------
#  grp_demo-org  | Demo Organization
```

### 3. Monitor Sync Activity

```bash
# Check sync audit logs
docker exec postgres_litellm_webui psql -U webui -d litellm -c "
SELECT operation, record_id, sync_result, created_at 
FROM sync_audit 
ORDER BY created_at DESC 
LIMIT 5;"
```

## 🛠️ Troubleshooting

### Database Connection Issues
```bash
# Check if databases exist
docker exec postgres_litellm_webui psql -U webui -c "\\l"

# Check if bridge tables exist
docker exec postgres_litellm_webui psql -U webui -d litellm -c "\\dt sync_*"
```

### Service Health Checks
```bash
# Check all container status
docker-compose ps

# Check specific service logs
docker-compose logs litellm
docker-compose logs open-webui
docker-compose logs postgres
```

### Bridge Sync Issues
```bash
# Check trigger existence
docker exec postgres_litellm_webui psql -U webui -d litellm -c "
SELECT trigger_name, event_manipulation, event_object_table 
FROM information_schema.triggers 
WHERE trigger_schema = 'public';"

# Check sync mappings
docker exec postgres_litellm_webui psql -U webui -d litellm -c "SELECT * FROM sync_mapping;"
```

## 🔄 Data Flow Architecture

```
┌─────────────────┐    Docker Network    ┌──────────────────┐
│    LiteLLM      │◄─────────────────────┤   Open WebUI     │
│   (port 8000)   │                      │   (port 3000)    │
└─────────┬───────┘                      └──────────┬───────┘
          │                                         │
          │            PostgreSQL                   │
          │         (port 5432)                     │
          ▼                                         ▼
┌─────────────────────────────────────────────────────────────┐
│                 postgres_litellm_webui                      │
│  ┌─────────────────┐    sync bridge    ┌─────────────────┐  │
│  │  litellm DB     │ ──────────────────► │   webui DB      │  │
│  │ • Organizations │   triggers         │ • groups        │  │  
│  │ • Teams         │   real-time        │ • users         │  │
│  │ • Users         │                    │                 │  │
│  └─────────────────┘                    └─────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## 🎯 Production Considerations

### Security
- Change default passwords in production
- Use environment variables for sensitive data
- Enable SSL/TLS for database connections
- Restrict database access to application containers only

### Performance
- Allocate sufficient resources (CPU/Memory)
- Consider database connection pooling
- Monitor sync performance via audit logs
- Set up proper database indices

### Backup
```bash
# Backup databases
docker exec postgres_litellm_webui pg_dump -U webui litellm > litellm_backup.sql
docker exec postgres_litellm_webui pg_dump -U webui webui > webui_backup.sql

# Backup volumes
docker run --rm -v postgres_data:/source -v $(pwd):/backup alpine tar czf /backup/postgres_backup.tar.gz -C /source .
```

## ✅ Verification Checklist

- [ ] All containers are running (`docker-compose ps`)
- [ ] LiteLLM proxy is accessible at http://localhost:8000
- [ ] Open WebUI is accessible at http://localhost:3000  
- [ ] Database is accessible via pgAdmin at http://localhost:8777
- [ ] Bridge triggers are installed (`check_sync_status()` returns data)
- [ ] Test organization sync works
- [ ] Test user sync works
- [ ] Audit logs are being created

🎉 **Your LiteLLM + Open WebUI integration with real-time user bridge is now ready!**
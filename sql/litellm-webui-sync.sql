-- LiteLLM WebUI Bridge - Production SQL Script
-- Version: 1.0.0
-- Compatible with: LiteLLM Latest + Open WebUI Latest
-- 
-- This script creates PostgreSQL triggers to synchronize data between
-- LiteLLM (proxy backend) and Open WebUI (user interface) in real-time.
--
-- BEFORE RUNNING:
-- 1. Update the target_conn_str variable below with your Open WebUI database details
-- 2. Ensure dblink extension is available
-- 3. Run this script on your LiteLLM database

-- =============================================================================
-- CONFIGURATION - UPDATE THIS SECTION
-- =============================================================================

-- TODO: Update this connection string to point to your Open WebUI database
-- Format: 'host=your-host port=5432 dbname=your-openwebui-db user=your-user password=your-password'
-- Example: 'host=localhost port=5432 dbname=openwebui user=webui password=secret'

-- NOTE: This connection string will be used in all sync functions below.
--       You can also update individual functions if you need different connections.

-- =============================================================================
-- EXTENSIONS AND SETUP
-- =============================================================================

-- Enable dblink for cross-database operations
CREATE EXTENSION IF NOT EXISTS dblink;

-- =============================================================================
-- AUDIT AND MAPPING TABLES
-- =============================================================================

-- Table to track sync operations (success/failure)
CREATE TABLE IF NOT EXISTS sync_audit (
    id SERIAL PRIMARY KEY,
    operation VARCHAR(20) NOT NULL,
    record_id TEXT NOT NULL,
    sync_result VARCHAR(20) NOT NULL,
    old_data JSONB,
    new_data JSONB,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table to maintain mapping between LiteLLM and Open WebUI entities
CREATE TABLE IF NOT EXISTS sync_mapping (
    id SERIAL PRIMARY KEY,
    litellm_type VARCHAR(20) NOT NULL,
    litellm_id TEXT NOT NULL,
    openwebui_type VARCHAR(20) NOT NULL,
    openwebui_id TEXT NOT NULL,
    sync_data JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(litellm_type, litellm_id)
);

-- =============================================================================
-- SYNC FUNCTIONS
-- =============================================================================

-- Function to sync organizations to Open WebUI groups
CREATE OR REPLACE FUNCTION sync_organization_to_group()
RETURNS TRIGGER AS $$
DECLARE 
    target_conn_str TEXT := 'host=YOUR_HOST port=5432 dbname=YOUR_OPENWEBUI_DB user=YOUR_USER password=YOUR_PASSWORD';
    group_id TEXT;
BEGIN
    -- Generate group ID with prefix
    group_id := 'grp_' || NEW.organization_id;
    
    BEGIN
        -- Sync to target database group table
        PERFORM dblink_exec(target_conn_str, format('
            INSERT INTO "group" (id, name, description, meta, created_at, updated_at)
            VALUES (%L, %L, %L, %L::jsonb, %L, %L)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                meta = EXCLUDED.meta,
                updated_at = EXCLUDED.updated_at
        ', group_id, NEW.organization_alias, 
           COALESCE(NEW.organization_alias || ' organization', ''),
           json_build_object(
               'organization_id', NEW.organization_id,
               'budget_id', NEW.budget_id,
               'models', NEW.models,
               'spend', NEW.spend,
               'model_spend', NEW.model_spend,
               'metadata', NEW.metadata
           )::text,
           NEW.created_at, COALESCE(NEW.updated_at, CURRENT_TIMESTAMP)));
        
        -- Update mapping table
        INSERT INTO sync_mapping (litellm_type, litellm_id, openwebui_type, openwebui_id, sync_data)
        VALUES ('organization', NEW.organization_id, 'group', group_id, 
               json_build_object('organization_alias', NEW.organization_alias))
        ON CONFLICT (litellm_type, litellm_id) 
        DO UPDATE SET 
            sync_data = EXCLUDED.sync_data,
            updated_at = CURRENT_TIMESTAMP;
        
        -- Log success
        INSERT INTO sync_audit (operation, record_id, sync_result, new_data)
        VALUES ('SYNC_ORG', NEW.organization_id, 'SUCCESS', to_jsonb(NEW));
        
    EXCEPTION WHEN OTHERS THEN
        -- Log failure
        INSERT INTO sync_audit (operation, record_id, sync_result, error_message, new_data)
        VALUES ('SYNC_ORG', NEW.organization_id, 'FAILED', SQLERRM, to_jsonb(NEW));
    END;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Function to sync users to Open WebUI users
CREATE OR REPLACE FUNCTION sync_user_to_openwebui()
RETURNS TRIGGER AS $$
DECLARE 
    target_conn_str TEXT := 'host=YOUR_HOST port=5432 dbname=YOUR_OPENWEBUI_DB user=YOUR_USER password=YOUR_PASSWORD';
    user_id_mapped TEXT;
    display_name TEXT;
    user_role_mapped VARCHAR;
    team_alias_val VARCHAR;
BEGIN
    -- Generate mapped user ID with prefix
    user_id_mapped := 'usr_' || NEW.user_id;
    
    -- Get team alias for name mapping
    IF NEW.team_id IS NOT NULL THEN
        SELECT team_alias INTO team_alias_val 
        FROM "LiteLLM_TeamTable" 
        WHERE team_id = NEW.team_id;
        
        display_name := COALESCE(team_alias_val || '-' || NEW.user_alias, NEW.user_alias, 'User');
    ELSE
        display_name := COALESCE(NEW.user_alias, 'User');
    END IF;
    
    -- Map user roles
    user_role_mapped := CASE 
        WHEN NEW.user_role IN ('proxy_admin', 'proxy_admin_viewer') THEN 'admin'
        ELSE 'user'
    END;
    
    BEGIN
        -- Sync to target database user table
        PERFORM dblink_exec(target_conn_str, format('
            INSERT INTO "user" (id, email, name, role, oauth_sub, settings, info, created_at, updated_at)
            VALUES (%L, %L, %L, %L, %L, %L::jsonb, %L::jsonb, %L, %L)
            ON CONFLICT (id) DO UPDATE SET
                email = EXCLUDED.email,
                name = EXCLUDED.name,
                role = EXCLUDED.role,
                oauth_sub = EXCLUDED.oauth_sub,
                settings = EXCLUDED.settings,
                info = EXCLUDED.info,
                updated_at = EXCLUDED.updated_at
        ', user_id_mapped, NEW.user_email, display_name, user_role_mapped, NEW.sso_user_id,
           json_build_object(
               'max_budget', NEW.max_budget,
               'spend', NEW.spend,
               'models', NEW.models,
               'metadata', NEW.metadata,
               'model_spend', NEW.model_spend,
               'model_max_budget', NEW.model_max_budget
           )::text,
           json_build_object(
               'organization_id', NEW.organization_id,
               'team_id', NEW.team_id,
               'original_user_id', NEW.user_id,
               'user_role', NEW.user_role
           )::text,
           NEW.created_at, COALESCE(NEW.updated_at, CURRENT_TIMESTAMP)));
        
        -- Update mapping table
        INSERT INTO sync_mapping (litellm_type, litellm_id, openwebui_type, openwebui_id, sync_data)
        VALUES ('user', NEW.user_id, 'user', user_id_mapped, 
               json_build_object('display_name', display_name, 'original_role', NEW.user_role))
        ON CONFLICT (litellm_type, litellm_id) 
        DO UPDATE SET 
            sync_data = EXCLUDED.sync_data,
            updated_at = CURRENT_TIMESTAMP;
        
        -- Log success
        INSERT INTO sync_audit (operation, record_id, sync_result, new_data)
        VALUES ('SYNC_USER', NEW.user_id, 'SUCCESS', to_jsonb(NEW));
        
    EXCEPTION WHEN OTHERS THEN
        -- Log failure
        INSERT INTO sync_audit (operation, record_id, sync_result, error_message, new_data)
        VALUES ('SYNC_USER', NEW.user_id, 'FAILED', SQLERRM, to_jsonb(NEW));
    END;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Function to handle organization deletion
CREATE OR REPLACE FUNCTION handle_organization_deletion()
RETURNS TRIGGER AS $$
DECLARE 
    target_conn_str TEXT := 'host=YOUR_HOST port=5432 dbname=YOUR_OPENWEBUI_DB user=YOUR_USER password=YOUR_PASSWORD';
    group_id TEXT;
BEGIN
    group_id := 'grp_' || OLD.organization_id;
    
    BEGIN
        -- Delete from target database
        PERFORM dblink_exec(target_conn_str, format('DELETE FROM "group" WHERE id = %L', group_id));
        
        -- Remove mapping
        DELETE FROM sync_mapping WHERE litellm_type = 'organization' AND litellm_id = OLD.organization_id;
        
        -- Log success
        INSERT INTO sync_audit (operation, record_id, sync_result, old_data)
        VALUES ('DELETE_ORG', OLD.organization_id, 'SUCCESS', to_jsonb(OLD));
        
    EXCEPTION WHEN OTHERS THEN
        -- Log failure
        INSERT INTO sync_audit (operation, record_id, sync_result, error_message, old_data)
        VALUES ('DELETE_ORG', OLD.organization_id, 'FAILED', SQLERRM, to_jsonb(OLD));
    END;
    
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

-- Function to handle user deletion
CREATE OR REPLACE FUNCTION handle_user_deletion()
RETURNS TRIGGER AS $$
DECLARE 
    target_conn_str TEXT := 'host=YOUR_HOST port=5432 dbname=YOUR_OPENWEBUI_DB user=YOUR_USER password=YOUR_PASSWORD';
    user_id_mapped TEXT;
BEGIN
    user_id_mapped := 'usr_' || OLD.user_id;
    
    BEGIN
        -- Delete from target database
        PERFORM dblink_exec(target_conn_str, format('DELETE FROM "user" WHERE id = %L', user_id_mapped));
        
        -- Remove mapping
        DELETE FROM sync_mapping WHERE litellm_type = 'user' AND litellm_id = OLD.user_id;
        
        -- Log success
        INSERT INTO sync_audit (operation, record_id, sync_result, old_data)
        VALUES ('DELETE_USER', OLD.user_id, 'SUCCESS', to_jsonb(OLD));
        
    EXCEPTION WHEN OTHERS THEN
        -- Log failure
        INSERT INTO sync_audit (operation, record_id, sync_result, error_message, old_data)
        VALUES ('DELETE_USER', OLD.user_id, 'FAILED', SQLERRM, to_jsonb(OLD));
    END;
    
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- TRIGGERS
-- =============================================================================

-- Organization table triggers
DROP TRIGGER IF EXISTS organization_sync_trigger ON "LiteLLM_OrganizationTable";
CREATE TRIGGER organization_sync_trigger
    AFTER INSERT OR UPDATE ON "LiteLLM_OrganizationTable"
    FOR EACH ROW EXECUTE FUNCTION sync_organization_to_group();

DROP TRIGGER IF EXISTS organization_delete_trigger ON "LiteLLM_OrganizationTable";
CREATE TRIGGER organization_delete_trigger
    BEFORE DELETE ON "LiteLLM_OrganizationTable"
    FOR EACH ROW EXECUTE FUNCTION handle_organization_deletion();

-- User table triggers
DROP TRIGGER IF EXISTS user_sync_trigger ON "LiteLLM_UserTable";
CREATE TRIGGER user_sync_trigger
    AFTER INSERT OR UPDATE ON "LiteLLM_UserTable"
    FOR EACH ROW EXECUTE FUNCTION sync_user_to_openwebui();

DROP TRIGGER IF EXISTS user_delete_trigger ON "LiteLLM_UserTable";
CREATE TRIGGER user_delete_trigger
    BEFORE DELETE ON "LiteLLM_UserTable"
    FOR EACH ROW EXECUTE FUNCTION handle_user_deletion();

-- =============================================================================
-- MONITORING AND UTILITY FUNCTIONS
-- =============================================================================

-- Function to check sync status
CREATE OR REPLACE FUNCTION check_sync_status()
RETURNS TABLE(metric TEXT, value TEXT) AS $$
BEGIN
    RETURN QUERY SELECT 'LiteLLM Organizations', COUNT(*)::TEXT FROM "LiteLLM_OrganizationTable";
    RETURN QUERY SELECT 'LiteLLM Teams', COUNT(*)::TEXT FROM "LiteLLM_TeamTable";
    RETURN QUERY SELECT 'LiteLLM Users', COUNT(*)::TEXT FROM "LiteLLM_UserTable";
    RETURN QUERY SELECT 'Sync Mappings', COUNT(*)::TEXT FROM sync_mapping;
    RETURN QUERY SELECT 'Total Audit Records', COUNT(*)::TEXT FROM sync_audit;
    RETURN QUERY 
        SELECT 'Success Rate', 
               ROUND(
                   COUNT(CASE WHEN sync_result = 'SUCCESS' THEN 1 END) * 100.0 / COUNT(*), 2
               )::TEXT || '%' 
        FROM sync_audit;
END;
$$ LANGUAGE plpgsql;

-- Function to get recent sync activities
CREATE OR REPLACE FUNCTION get_recent_sync_activities(limit_count INTEGER DEFAULT 10)
RETURNS TABLE(operation TEXT, record_id TEXT, result TEXT, created_at TIMESTAMP) AS $$
BEGIN
    RETURN QUERY 
    SELECT sa.operation, sa.record_id, sa.sync_result, sa.created_at
    FROM sync_audit sa
    ORDER BY sa.created_at DESC
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- INSTALLATION COMPLETE
-- =============================================================================

-- Insert installation marker
INSERT INTO sync_audit (operation, record_id, sync_result, new_data)
VALUES ('INSTALL', 'litellm-webui-bridge', 'SUCCESS', 
        json_build_object('version', '1.0.0', 'installed_at', CURRENT_TIMESTAMP));

-- Display installation summary
SELECT 'LiteLLM WebUI Bridge Installation Complete!' AS message;
SELECT 'Next Steps:' AS info;
SELECT '1. Update target_conn_str in all functions above' AS step1;
SELECT '2. Test with: SELECT * FROM check_sync_status();' AS step2;
SELECT '3. Monitor with: SELECT * FROM get_recent_sync_activities();' AS step3;
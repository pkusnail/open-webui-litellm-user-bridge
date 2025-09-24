-- LiteLLM to Open WebUI - One-time Existing User Migration Script
-- Version: 1.0.0
-- Purpose: Migrate existing LiteLLM users to Open WebUI (before sync bridge installation)
--
-- IMPORTANT: This script should be run AFTER installing the main sync bridge
-- It will process all existing users that have valid email addresses

-- =============================================================================
-- CONFIGURATION - UPDATE THESE VALUES
-- =============================================================================

-- Target Open WebUI database connection
-- Update this to match your Open WebUI database connection details
-- Format: 'host=your-host port=5432 dbname=your-openwebui-db user=your-user password=your-password'

-- =============================================================================
-- ENABLE REQUIRED EXTENSIONS
-- =============================================================================

-- Enable pgcrypto for password hashing (on target database)
-- This will be executed via dblink to the target database

-- =============================================================================
-- ONE-TIME MIGRATION FUNCTION
-- =============================================================================

CREATE OR REPLACE FUNCTION migrate_existing_users_to_openwebui()
RETURNS TABLE(
    user_id TEXT,
    user_email TEXT,
    sync_status TEXT,
    error_message TEXT
) AS $$
DECLARE 
    target_conn_str TEXT := 'host=localhost port=5432 dbname=webui user=webui password=webui';
    user_record RECORD;
    user_id_mapped TEXT;
    display_name TEXT;
    user_role_mapped VARCHAR;
    team_alias_val VARCHAR;
    migration_count INTEGER := 0;
    skipped_count INTEGER := 0;
    error_count INTEGER := 0;
BEGIN
    -- Log migration start
    INSERT INTO sync_audit (operation, record_id, sync_result, new_data)
    VALUES ('MIGRATE_START', 'batch_migration', 'SUCCESS', 
            json_build_object('started_at', CURRENT_TIMESTAMP, 'type', 'existing_users'));
    
    -- Enable pgcrypto extension on target database for password hashing
    BEGIN
        PERFORM dblink_exec(target_conn_str, 'CREATE EXTENSION IF NOT EXISTS pgcrypto;');
    EXCEPTION WHEN OTHERS THEN
        -- Log warning but continue (extension might already exist or user lacks permission)
        INSERT INTO sync_audit (operation, record_id, sync_result, error_message)
        VALUES ('MIGRATE_WARNING', 'pgcrypto_extension', 'WARNING', 
                'Could not enable pgcrypto extension: ' || SQLERRM);
    END;

    -- Process each existing user
    FOR user_record IN 
        SELECT u.user_id, u.user_alias, u.user_email, u.user_role, u.team_id, u.sso_user_id,
               u.max_budget, u.spend, u.models, u.metadata, u.model_spend, u.model_max_budget,
               u.organization_id, u.created_at, u.updated_at
        FROM "LiteLLM_UserTable" u
        WHERE u.user_email IS NOT NULL AND u.user_email != ''  -- Only sync users with valid email
        AND NOT EXISTS (
            -- Skip users that are already synced
            SELECT 1 FROM sync_mapping sm 
            WHERE sm.litellm_type = 'user' AND sm.litellm_id = u.user_id
        )
    LOOP
        BEGIN
            -- Generate mapped user ID with prefix
            user_id_mapped := 'usr_' || user_record.user_id;
            
            -- Get team alias for name mapping
            team_alias_val := NULL;
            IF user_record.team_id IS NOT NULL THEN
                SELECT team_alias INTO team_alias_val 
                FROM "LiteLLM_TeamTable" 
                WHERE team_id = user_record.team_id;
                
                display_name := COALESCE(
                    team_alias_val || '-' || user_record.user_alias, 
                    user_record.user_alias, 
                    'User-' || user_record.user_id
                );
            ELSE
                display_name := COALESCE(
                    user_record.user_alias, 
                    'User-' || user_record.user_id
                );
            END IF;
            
            -- Map user roles  
            user_role_mapped := CASE 
                WHEN user_record.user_role IN ('proxy_admin', 'proxy_admin_viewer') THEN 'admin'
                ELSE 'user'
            END;
            
            -- Sync to target database user table
            PERFORM dblink_exec(target_conn_str, format('
                INSERT INTO "user" (id, email, name, role, oauth_sub, settings, info, profile_image_url, last_active_at, created_at, updated_at)
                VALUES (%L, %L, %L, %L, %L, %L, %L, %L, %L, %L, %L)
                ON CONFLICT (id) DO UPDATE SET
                    email = EXCLUDED.email,
                    name = EXCLUDED.name,
                    role = EXCLUDED.role,
                    oauth_sub = EXCLUDED.oauth_sub,
                    settings = EXCLUDED.settings,
                    info = EXCLUDED.info,
                    updated_at = EXCLUDED.updated_at
            ', user_id_mapped, user_record.user_email, display_name, user_role_mapped, user_record.sso_user_id,
               json_build_object(
                   'max_budget', user_record.max_budget,
                   'spend', user_record.spend,
                   'models', user_record.models,
                   'metadata', user_record.metadata,
                   'model_spend', user_record.model_spend,
                   'model_max_budget', user_record.model_max_budget
               )::text,
               json_build_object(
                   'organization_id', user_record.organization_id,
                   'team_id', user_record.team_id,
                   'original_user_id', user_record.user_id,
                   'user_role', user_record.user_role
               )::text,
               '/static/profile-user.png',
               EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)::bigint,
               EXTRACT(EPOCH FROM user_record.created_at)::bigint, 
               EXTRACT(EPOCH FROM COALESCE(user_record.updated_at, CURRENT_TIMESTAMP))::bigint));
            
            -- Create authentication record with email as initial password
            PERFORM dblink_exec(target_conn_str, format('
                INSERT INTO auth (id, email, password, active)
                VALUES (%L, %L, crypt(%L, gen_salt(''bf'', 12)), true)
                ON CONFLICT (id) DO UPDATE SET
                    email = EXCLUDED.email,
                    active = EXCLUDED.active
            ', user_id_mapped, user_record.user_email, user_record.user_email));
            
            -- Update mapping table
            INSERT INTO sync_mapping (litellm_type, litellm_id, openwebui_type, openwebui_id, sync_data)
            VALUES ('user', user_record.user_id, 'user', user_id_mapped, 
                   json_build_object(
                       'display_name', display_name, 
                       'original_role', user_record.user_role,
                       'migrated_at', CURRENT_TIMESTAMP,
                       'migration_type', 'batch_existing'
                   ))
            ON CONFLICT (litellm_type, litellm_id) 
            DO UPDATE SET 
                sync_data = EXCLUDED.sync_data,
                updated_at = CURRENT_TIMESTAMP;
            
            -- Log success
            INSERT INTO sync_audit (operation, record_id, sync_result, new_data)
            VALUES ('MIGRATE_USER', user_record.user_id, 'SUCCESS', 
                    json_build_object(
                        'user_email', user_record.user_email,
                        'display_name', display_name,
                        'mapped_id', user_id_mapped
                    ));
            
            migration_count := migration_count + 1;
            
            -- Return success result
            RETURN QUERY SELECT 
                user_record.user_id,
                user_record.user_email,
                'SUCCESS'::TEXT,
                NULL::TEXT;
                
        EXCEPTION WHEN OTHERS THEN
            -- Log failure
            INSERT INTO sync_audit (operation, record_id, sync_result, error_message, new_data)
            VALUES ('MIGRATE_USER', user_record.user_id, 'FAILED', SQLERRM, 
                    json_build_object('user_email', user_record.user_email));
            
            error_count := error_count + 1;
            
            -- Return error result  
            RETURN QUERY SELECT 
                user_record.user_id,
                user_record.user_email,
                'FAILED'::TEXT,
                SQLERRM::TEXT;
        END;
    END LOOP;
    
    -- Count skipped users (those without email)
    SELECT COUNT(*) INTO skipped_count 
    FROM "LiteLLM_UserTable" u
    WHERE u.user_email IS NULL OR u.user_email = '';
    
    -- Log migration completion
    INSERT INTO sync_audit (operation, record_id, sync_result, new_data)
    VALUES ('MIGRATE_COMPLETE', 'batch_migration', 'SUCCESS', 
            json_build_object(
                'completed_at', CURRENT_TIMESTAMP,
                'migrated_count', migration_count,
                'error_count', error_count,
                'skipped_count', skipped_count,
                'total_users', migration_count + error_count + skipped_count
            ));
    
    RETURN;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- HELPER FUNCTIONS
-- =============================================================================

-- Function to check migration status
CREATE OR REPLACE FUNCTION check_migration_status()
RETURNS TABLE(
    metric TEXT,
    count BIGINT
) AS $$
BEGIN
    RETURN QUERY SELECT 'Total LiteLLM Users'::TEXT, COUNT(*) FROM "LiteLLM_UserTable";
    RETURN QUERY SELECT 'Users with Email'::TEXT, COUNT(*) FROM "LiteLLM_UserTable" WHERE user_email IS NOT NULL AND user_email != '';
    RETURN QUERY SELECT 'Users without Email'::TEXT, COUNT(*) FROM "LiteLLM_UserTable" WHERE user_email IS NULL OR user_email = '';
    RETURN QUERY SELECT 'Already Synced Users'::TEXT, COUNT(*) FROM sync_mapping WHERE litellm_type = 'user';
    RETURN QUERY SELECT 'Open WebUI Users (usr_ prefix)'::TEXT, 
                 (SELECT COUNT(*) FROM dblink('host=localhost port=5432 dbname=webui user=webui password=webui',
                                              'SELECT id FROM "user" WHERE id LIKE ''usr_%''') AS t(id TEXT));
    RETURN QUERY SELECT 'Migration Operations'::TEXT, COUNT(*) FROM sync_audit WHERE operation LIKE 'MIGRATE_%';
END;
$$ LANGUAGE plpgsql;

-- Function to get migration audit log
CREATE OR REPLACE FUNCTION get_migration_audit_log(limit_count INTEGER DEFAULT 20)
RETURNS TABLE(
    operation VARCHAR,
    record_id VARCHAR,
    sync_result VARCHAR,
    error_message TEXT,
    created_at TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY 
    SELECT sa.operation::VARCHAR, sa.record_id::VARCHAR, sa.sync_result::VARCHAR, sa.error_message, sa.created_at
    FROM sync_audit sa
    WHERE sa.operation LIKE 'MIGRATE_%'
    ORDER BY sa.created_at DESC
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- EXECUTION INSTRUCTIONS
-- =============================================================================

-- To run this migration, execute the following commands in order:

-- 1. Check current status BEFORE migration
SELECT 'Pre-Migration Status' AS phase;
SELECT * FROM check_migration_status();

-- 2. Run the migration (this processes all eligible users)
SELECT 'Migration Results' AS phase;
SELECT * FROM migrate_existing_users_to_openwebui();

-- 3. Check status AFTER migration  
SELECT 'Post-Migration Status' AS phase;
SELECT * FROM check_migration_status();

-- 4. Review migration audit log
SELECT 'Migration Audit Log' AS phase;
SELECT * FROM get_migration_audit_log(10);

-- =============================================================================
-- CLEANUP (Optional)
-- =============================================================================

-- Uncomment these lines if you want to clean up the migration functions after use:
-- DROP FUNCTION IF EXISTS migrate_existing_users_to_openwebui();
-- DROP FUNCTION IF EXISTS check_migration_status();  
-- DROP FUNCTION IF EXISTS get_migration_audit_log(INTEGER);

-- =============================================================================
-- NOTES
-- =============================================================================

-- This script will:
-- 1. Only migrate users that have valid email addresses (not NULL or empty)
-- 2. Skip users that are already synced (exist in sync_mapping table)
-- 3. Create proper user mappings with 'usr_' prefix
-- 4. Handle team alias mapping for display names
-- 5. Map LiteLLM roles to Open WebUI roles (proxy_admin → admin)
-- 6. Log all operations to sync_audit table for tracking
-- 7. Provide detailed status and audit reporting functions

-- Users without email will be skipped and counted in the final report.
-- The sync bridge triggers will handle any future user changes automatically.
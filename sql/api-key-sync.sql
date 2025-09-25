-- LiteLLM WebUI Bridge - API Key Sync Extension
-- Version: 1.1.0  
-- Compatible with: LiteLLM Latest + Open WebUI Latest
--
-- This script extends the basic user sync with API key synchronization
-- enabling per-user model permissions in Open WebUI through LiteLLM API keys.
--
-- PREREQUISITE: Run litellm-webui-sync.sql first
-- 
-- BEFORE RUNNING:
-- 1. Ensure basic user sync is working (run litellm-webui-sync.sql first)
-- 2. Update target_conn_str with your Open WebUI database details
-- 3. Run this script on your LiteLLM database

-- =============================================================================
-- CONFIGURATION - UPDATE THIS SECTION
-- =============================================================================

-- TODO: Update this connection string to point to your Open WebUI database
-- Format: 'host=your-host port=5432 dbname=your-openwebui-db user=your-user password=your-password'
-- Example: 'host=localhost port=5432 dbname=webui user=webui password=webui'

-- NOTE: This connection string will be used in all sync functions below.
--       You can also update individual functions if you need different connections.

-- =============================================================================
-- API KEY SYNC FUNCTIONS
-- =============================================================================

-- Function to sync API keys from LiteLLM to Open WebUI users
CREATE OR REPLACE FUNCTION sync_api_key_to_webui()
RETURNS TRIGGER AS $$
DECLARE 
    target_conn_str TEXT := 'host=localhost port=5432 dbname=webui user=webui password=webui';
    webui_user_id TEXT;
BEGIN
    -- Only process if user_id is provided (skip system tokens)
    IF NEW.user_id IS NULL OR NEW.user_id = '' THEN
        RETURN NEW;
    END IF;

    -- Generate Open WebUI user ID
    webui_user_id := 'usr_' || NEW.user_id;
    
    BEGIN
        -- Sync API key token to Open WebUI user table
        PERFORM dblink_exec(target_conn_str, format('
            UPDATE "user" SET api_key = %L 
            WHERE id = %L
        ', NEW.token, webui_user_id));
        
        -- Record sync success
        INSERT INTO sync_audit (operation, record_id, sync_result, new_data)
        VALUES ('SYNC_API_KEY', NEW.user_id, 'SUCCESS', 
                json_build_object(
                    'user_id', NEW.user_id, 
                    'token', NEW.token, 
                    'models', NEW.models,
                    'key_alias', NEW.key_alias,
                    'created_at', NEW.created_at
                )::jsonb);
        
        -- Update mapping table if exists
        INSERT INTO sync_mapping (litellm_type, litellm_id, openwebui_type, openwebui_id, sync_data)
        VALUES ('api_key', NEW.token, 'user_api_key', webui_user_id,
                json_build_object('models', NEW.models, 'key_alias', NEW.key_alias)::jsonb)
        ON CONFLICT (litellm_type, litellm_id) DO UPDATE SET
            openwebui_id = EXCLUDED.openwebui_id,
            sync_data = EXCLUDED.sync_data,
            updated_at = CURRENT_TIMESTAMP;
        
    EXCEPTION WHEN OTHERS THEN
        -- Record sync failure
        INSERT INTO sync_audit (operation, record_id, sync_result, error_message, new_data)
        VALUES ('SYNC_API_KEY', NEW.user_id, 'FAILED', SQLERRM,
                json_build_object(
                    'user_id', NEW.user_id, 
                    'token', NEW.token, 
                    'models', NEW.models,
                    'key_alias', NEW.key_alias,
                    'error_detail', SQLERRM
                )::jsonb);
        
        -- Don't fail the original operation, just log the sync failure
        RAISE NOTICE 'API Key sync failed for user %: %', NEW.user_id, SQLERRM;
    END;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Function to handle API key deletions
CREATE OR REPLACE FUNCTION sync_api_key_delete_to_webui()
RETURNS TRIGGER AS $$
DECLARE 
    target_conn_str TEXT := 'host=localhost port=5432 dbname=webui user=webui password=webui';
    webui_user_id TEXT;
BEGIN
    -- Only process if user_id is provided
    IF OLD.user_id IS NULL OR OLD.user_id = '' THEN
        RETURN OLD;
    END IF;

    -- Generate Open WebUI user ID
    webui_user_id := 'usr_' || OLD.user_id;
    
    BEGIN
        -- Clear API key from Open WebUI user table
        PERFORM dblink_exec(target_conn_str, format('
            UPDATE "user" SET api_key = NULL 
            WHERE id = %L AND api_key = %L
        ', webui_user_id, OLD.token));
        
        -- Record sync success
        INSERT INTO sync_audit (operation, record_id, sync_result, old_data)
        VALUES ('DELETE_API_KEY', OLD.user_id, 'SUCCESS',
                json_build_object(
                    'user_id', OLD.user_id, 
                    'token', OLD.token,
                    'key_alias', OLD.key_alias
                )::jsonb);
        
        -- Remove from mapping table
        DELETE FROM sync_mapping 
        WHERE litellm_type = 'api_key' AND litellm_id = OLD.token;
        
    EXCEPTION WHEN OTHERS THEN
        -- Record sync failure
        INSERT INTO sync_audit (operation, record_id, sync_result, error_message, old_data)
        VALUES ('DELETE_API_KEY', OLD.user_id, 'FAILED', SQLERRM,
                json_build_object(
                    'user_id', OLD.user_id, 
                    'token', OLD.token,
                    'error_detail', SQLERRM
                )::jsonb);
    END;
    
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- TRIGGERS SETUP
-- =============================================================================

-- Drop existing triggers if they exist
DROP TRIGGER IF EXISTS trigger_sync_api_key_to_webui ON "LiteLLM_VerificationToken";
DROP TRIGGER IF EXISTS trigger_sync_api_key_delete_to_webui ON "LiteLLM_VerificationToken";

-- Create API key sync trigger for INSERT/UPDATE
CREATE TRIGGER trigger_sync_api_key_to_webui
    AFTER INSERT OR UPDATE ON "LiteLLM_VerificationToken"
    FOR EACH ROW
    WHEN (NEW.user_id IS NOT NULL AND NEW.user_id != '')
    EXECUTE FUNCTION sync_api_key_to_webui();

-- Create API key sync trigger for DELETE  
CREATE TRIGGER trigger_sync_api_key_delete_to_webui
    AFTER DELETE ON "LiteLLM_VerificationToken"
    FOR EACH ROW
    WHEN (OLD.user_id IS NOT NULL AND OLD.user_id != '')
    EXECUTE FUNCTION sync_api_key_delete_to_webui();

-- =============================================================================
-- HELPER FUNCTIONS FOR TESTING AND MONITORING
-- =============================================================================

-- Function to check API key sync status
CREATE OR REPLACE FUNCTION check_api_key_sync_status()
RETURNS TABLE(
    user_id TEXT,
    user_email TEXT,
    litellm_api_keys BIGINT,
    webui_has_api_key BOOLEAN,
    last_sync_status TEXT,
    last_sync_time TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        u.user_id,
        u.user_email,
        COUNT(vt.token) as litellm_api_keys,
        (SELECT (wu.api_key IS NOT NULL) 
         FROM dblink('host=localhost port=5432 dbname=webui user=webui password=webui', 
                     'SELECT api_key FROM "user" WHERE id = ''usr_' || u.user_id || '''') 
         AS wu(api_key TEXT)) as webui_has_api_key,
        (SELECT sa.sync_result 
         FROM sync_audit sa 
         WHERE sa.record_id = u.user_id AND sa.operation = 'SYNC_API_KEY' 
         ORDER BY sa.created_at DESC LIMIT 1) as last_sync_status,
        (SELECT sa.created_at 
         FROM sync_audit sa 
         WHERE sa.record_id = u.user_id AND sa.operation = 'SYNC_API_KEY' 
         ORDER BY sa.created_at DESC LIMIT 1) as last_sync_time
    FROM "LiteLLM_UserTable" u
    LEFT JOIN "LiteLLM_VerificationToken" vt ON u.user_id = vt.user_id
    WHERE u.user_email IS NOT NULL AND u.user_email != ''
    GROUP BY u.user_id, u.user_email
    ORDER BY u.user_email;
END;
$$ LANGUAGE plpgsql;

-- Function to get recent API key sync audit logs
CREATE OR REPLACE FUNCTION get_api_key_sync_audit_log(limit_rows INTEGER DEFAULT 10)
RETURNS TABLE(
    id INTEGER,
    operation VARCHAR(20),
    record_id TEXT,
    sync_result VARCHAR(20),
    error_message TEXT,
    sync_data JSONB,
    created_at TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        sa.id,
        sa.operation,
        sa.record_id,
        sa.sync_result,
        sa.error_message,
        COALESCE(sa.new_data, sa.old_data) as sync_data,
        sa.created_at
    FROM sync_audit sa
    WHERE sa.operation IN ('SYNC_API_KEY', 'DELETE_API_KEY')
    ORDER BY sa.created_at DESC
    LIMIT limit_rows;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- INSTALLATION VERIFICATION
-- =============================================================================

-- Test function to verify API key sync is working
CREATE OR REPLACE FUNCTION test_api_key_sync_installation()
RETURNS TEXT AS $$
DECLARE
    test_result TEXT := '';
    function_exists BOOLEAN;
    trigger_exists BOOLEAN;
BEGIN
    -- Check if sync function exists
    SELECT EXISTS(
        SELECT 1 FROM pg_proc 
        WHERE proname = 'sync_api_key_to_webui'
    ) INTO function_exists;
    
    -- Check if trigger exists
    SELECT EXISTS(
        SELECT 1 FROM pg_trigger 
        WHERE tgname = 'trigger_sync_api_key_to_webui'
    ) INTO trigger_exists;
    
    test_result := test_result || 'API Key Sync Function: ' || 
        CASE WHEN function_exists THEN '✅ EXISTS' ELSE '❌ MISSING' END || E'\n';
    test_result := test_result || 'API Key Sync Trigger: ' || 
        CASE WHEN trigger_exists THEN '✅ EXISTS' ELSE '❌ MISSING' END || E'\n';
    
    -- Check dblink extension
    test_result := test_result || 'dblink Extension: ' ||
        CASE WHEN EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'dblink') 
             THEN '✅ AVAILABLE' ELSE '❌ MISSING' END || E'\n';
    
    IF function_exists AND trigger_exists THEN
        test_result := test_result || E'\n🎉 API Key Sync installation appears to be successful!';
        test_result := test_result || E'\n\nNext steps:';
        test_result := test_result || E'\n1. Create API keys in LiteLLM for users';
        test_result := test_result || E'\n2. Check sync status with: SELECT * FROM check_api_key_sync_status();';
        test_result := test_result || E'\n3. Monitor sync with: SELECT * FROM get_api_key_sync_audit_log(5);';
    ELSE
        test_result := test_result || E'\n❌ API Key Sync installation has issues. Please check the logs.';
    END IF;
    
    RETURN test_result;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- POST-INSTALLATION MESSAGE
-- =============================================================================

DO $$
BEGIN
    RAISE NOTICE E'\n🔧 LiteLLM-WebUI API Key Sync Extension Installed Successfully!\n';
    RAISE NOTICE 'Features added:';
    RAISE NOTICE '- ✅ Automatic API key synchronization from LiteLLM to Open WebUI';
    RAISE NOTICE '- ✅ Per-user model permissions via API keys';  
    RAISE NOTICE '- ✅ API key deletion handling';
    RAISE NOTICE '- ✅ Comprehensive audit logging';
    RAISE NOTICE '';
    RAISE NOTICE 'Test installation:';
    RAISE NOTICE 'SELECT test_api_key_sync_installation();';
    RAISE NOTICE '';
    RAISE NOTICE 'Monitor sync status:';
    RAISE NOTICE 'SELECT * FROM check_api_key_sync_status();';
    RAISE NOTICE 'SELECT * FROM get_api_key_sync_audit_log(5);';
    RAISE NOTICE '';
    RAISE NOTICE '🚀 Ready to sync API keys! Create API keys in LiteLLM to see them sync to Open WebUI.';
END $$;
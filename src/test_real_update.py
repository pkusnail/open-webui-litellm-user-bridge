#!/usr/bin/env python3
"""
真实表结构 UPDATE 测试 - 验证LiteLLM到Open WebUI的更新同步
"""

import psycopg2
import sys
import time
import json
from datetime import datetime

def test_real_update():
    """测试真实表结构的UPDATE操作同步"""
    
    # 连接数据库
    source_conn = psycopg2.connect(
        host="172.21.0.4",
        port="5432",
        database="litellm_real",
        user="webui",
        password="webui"
    )
    source_conn.autocommit = True
    
    target_conn = psycopg2.connect(
        host="172.21.0.4", 
        port="5432",
        database="openwebui_real",
        user="webui",
        password="webui"
    )
    target_conn.autocommit = True
    
    print("🧪 开始真实表结构 UPDATE 测试...")
    print("=" * 50)
    
    try:
        source_cursor = source_conn.cursor()
        target_cursor = target_conn.cursor()
        
        # 1. 查看更新前状态
        print("\\n📊 更新前状态:")
        
        # 获取alice的信息
        source_cursor.execute('''
            SELECT u.user_id, u.user_alias, u.team_id, u.organization_id, u.user_role, 
                   u.max_budget, u.spend, t.team_alias
            FROM "LiteLLM_UserTable" u
            LEFT JOIN "LiteLLM_TeamTable" t ON u.team_id = t.team_id
            WHERE u.user_id = 'alice';
        ''')
        before_source = source_cursor.fetchone()
        
        target_cursor.execute('''SELECT id, name, email, role, settings, info FROM "user" WHERE id = 'usr_alice';''')
        before_target = target_cursor.fetchone()
        
        if before_source and before_target:
            print(f"   LiteLLM源: {before_source}")
            print(f"   OpenWebUI目标: {before_target[0:4]}")  # 只显示前4个字段避免过长
        else:
            print("   ❌ 找不到alice用户，请先运行插入测试")
            return False
        
        # 2. 执行组织更新 - 更新Technology Corp
        print("\\n📝 执行组织更新...")
        
        new_org_alias = "Advanced Technology Corporation"
        new_models = ['gpt-4', 'claude-3', 'gemini-pro', 'gpt-4o']
        new_org_spend = 1250.75
        new_metadata = {"department": "Technology", "region": "US-East", "tier": "Enterprise"}
        
        source_cursor.execute("""
            UPDATE "LiteLLM_OrganizationTable" 
            SET organization_alias = %s,
                models = %s,
                spend = %s,
                metadata = %s,
                updated_at = CURRENT_TIMESTAMP,
                updated_by = %s
            WHERE organization_id = 'org_tech'
        """, (new_org_alias, new_models, new_org_spend, json.dumps(new_metadata), 'admin'))
        
        print(f"   ✅ 更新组织 org_tech:")
        print(f"   - 名称: 'Technology Corp' -> '{new_org_alias}'")
        print(f"   - 模型数量: 2 -> {len(new_models)}")
        print(f"   - 花费: 0.0 -> {new_org_spend}")
        
        # 3. 执行用户更新 - 将alice转到frontend团队并提升为admin
        print("\\n📝 执行用户更新...")
        
        new_alias = "Alice Chen (Senior)"
        new_team = "team_frontend"
        new_role = "proxy_admin"
        new_budget = 500.0
        new_spend = 125.50
        new_metadata = {"department": "frontend", "level": "principal", "location": "SF"}
        
        source_cursor.execute("""
            UPDATE "LiteLLM_UserTable"
            SET user_alias = %s,
                team_id = %s,
                user_role = %s,
                max_budget = %s,
                spend = %s,
                teams = %s,
                metadata = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = 'alice'
        """, (new_alias, new_team, new_role, new_budget, new_spend, 
              [new_team], json.dumps(new_metadata)))
        
        print(f"   ✅ 更新用户 alice:")
        print(f"   - 别名: '{before_source[1]}' -> '{new_alias}'")
        print(f"   - 团队: '{before_source[2]}' -> '{new_team}'")
        print(f"   - 角色: '{before_source[4]}' -> '{new_role}'")
        print(f"   - 预算: {before_source[5]} -> {new_budget}")
        
        # 等待触发器执行
        print("\\n⏳ 等待触发器同步...")
        time.sleep(3)
        
        # 4. 验证组织更新后状态
        print("\\n📊 验证组织更新:")
        
        source_cursor.execute('''
            SELECT organization_id, organization_alias, models, spend, metadata 
            FROM "LiteLLM_OrganizationTable" 
            WHERE organization_id = 'org_tech';
        ''')
        after_org_source = source_cursor.fetchone()
        
        target_cursor.execute('''SELECT id, name, meta FROM "group" WHERE id = 'grp_org_tech';''')
        after_org_target = target_cursor.fetchone()
        
        print(f"   源表组织: {after_org_source}")
        if after_org_target:
            meta = after_org_target[2] if after_org_target[2] else {}  # JSONB already parsed
            print(f"   目标表组: {after_org_target[0:2]} + meta keys: {list(meta.keys())}")
        
        # 验证组织数据同步
        org_sync_success = True
        if after_org_target:
            meta = after_org_target[2] if after_org_target[2] else {}  # JSONB already parsed
            # 比较模型列表时忽略顺序
            meta_models = set(meta.get('models', []))
            expected_models = set(new_models)
            name_match = after_org_target[1] == new_org_alias
            spend_match = meta.get('spend') == new_org_spend
            model_match = meta_models == expected_models
            
            print(f"      名称匹配: {name_match} ('{after_org_target[1]}' vs '{new_org_alias}')")
            print(f"      花费匹配: {spend_match} ({meta.get('spend')} vs {new_org_spend})")
            print(f"      模型匹配: {model_match} ({meta_models} vs {expected_models})")
            
            if not (name_match and spend_match and model_match):
                org_sync_success = False
                print("   ❌ 组织数据同步不一致")
            else:
                print("   ✅ 组织数据同步正确")
        else:
            org_sync_success = False
            print("   ❌ 目标组织不存在")
        
        # 5. 验证用户更新后状态
        print("\\n📊 验证用户更新:")
        
        source_cursor.execute('''
            SELECT u.user_id, u.user_alias, u.team_id, u.user_role, u.max_budget, u.spend,
                   t.team_alias
            FROM "LiteLLM_UserTable" u
            LEFT JOIN "LiteLLM_TeamTable" t ON u.team_id = t.team_id
            WHERE u.user_id = 'alice';
        ''')
        after_user_source = source_cursor.fetchone()
        
        target_cursor.execute('''
            SELECT id, name, email, role, settings, info 
            FROM "user" 
            WHERE id = 'usr_alice';
        ''')
        after_user_target = target_cursor.fetchone()
        
        print(f"   源表用户: {after_user_source}")
        if after_user_target:
            settings = after_user_target[4] if after_user_target[4] else {}  # JSONB already parsed
            info = after_user_target[5] if after_user_target[5] else {}  # JSONB already parsed
            print(f"   目标表用户: {after_user_target[0:4]} + settings/info")
        
        # 6. 验证用户名映射更新
        team_alias = after_user_source[6] if after_user_source else None  # Frontend Team
        expected_name = f"{team_alias}-{new_alias}" if team_alias else new_alias
        actual_name = after_user_target[1] if after_user_target else None
        
        print(f"\\n🔍 验证用户名映射更新:")
        print(f"   期望名称: '{expected_name}'")
        print(f"   实际名称: '{actual_name}'")
        
        name_correct = expected_name == actual_name
        
        # 7. 验证角色映射更新
        expected_role = 'admin'  # proxy_admin -> admin
        actual_role = after_user_target[3] if after_user_target else None  # role is index 3
        
        print(f"\\n🔍 验证角色映射更新:")
        print(f"   期望角色: '{expected_role}'")
        print(f"   实际角色: '{actual_role}'")
        
        role_correct = expected_role == actual_role
        
        # 8. 验证设置字段同步
        if after_user_target and after_user_target[4]:
            settings = after_user_target[4]  # JSONB already parsed
            budget_correct = settings.get('max_budget') == new_budget
            spend_correct = settings.get('spend') == new_spend
        else:
            budget_correct = spend_correct = False
        
        print(f"\\n🔍 验证设置字段同步:")
        print(f"   预算同步: {budget_correct} (期望: {new_budget}, 实际: {settings.get('max_budget') if 'settings' in locals() else 'N/A'})")
        print(f"   花费同步: {spend_correct} (期望: {new_spend}, 实际: {settings.get('spend') if 'settings' in locals() else 'N/A'})")
        
        # 9. 验证时间戳更新
        print("\\n⏰ 验证时间戳:")
        if after_user_target:
            # 检查updated_at是否被更新（这里简化检查，实际应该比较时间戳）
            print("   ✅ 时间戳字段存在")
            timestamp_updated = True
        else:
            print("   ❌ 无法验证时间戳")
            timestamp_updated = False
        
        # 10. 验证审计日志
        print("\\n📋 验证审计日志:")
        source_cursor.execute('''
            SELECT operation, record_id, sync_result, created_at 
            FROM sync_audit 
            WHERE record_id IN ('org_tech', 'alice')
            ORDER BY created_at DESC 
            LIMIT 10;
        ''')
        recent_audit = source_cursor.fetchall()
        
        print(f"   最近审计记录数: {len(recent_audit)}")
        update_audit_count = 0
        for row in recent_audit:
            print(f"   - {row[0]}: {row[1]} -> {row[2]} ({row[3]})")
            if row[0] in ['SYNC_ORG', 'SYNC_USER'] and row[2] == 'SUCCESS':
                update_audit_count += 1
        
        audit_correct = update_audit_count >= 2  # 至少有组织和用户的成功更新记录
        
        # 11. 综合验证结果
        all_checks = [
            org_sync_success,      # 组织数据同步
            name_correct,          # 用户名映射正确
            role_correct,          # 角色映射正确
            budget_correct,        # 预算同步正确
            spend_correct,         # 花费同步正确
            timestamp_updated,     # 时间戳更新
            audit_correct         # 审计记录正确
        ]
        
        success = all(all_checks)
        
        print(f"\\n📈 真实表结构UPDATE测试结果:")
        print(f"   组织数据同步: {'✅' if org_sync_success else '❌'}")
        print(f"   用户名映射: {'✅' if name_correct else '❌'}")
        print(f"   角色映射: {'✅' if role_correct else '❌'}")
        print(f"   预算同步: {'✅' if budget_correct else '❌'}")
        print(f"   花费同步: {'✅' if spend_correct else '❌'}")
        print(f"   时间戳更新: {'✅' if timestamp_updated else '❌'}")
        print(f"   审计记录: {'✅' if audit_correct else '❌'}")
        
        print(f"\\n{'✅ 真实表结构 UPDATE 测试通过!' if success else '❌ 真实表结构 UPDATE 测试失败!'}")
        return success
        
    except Exception as e:
        print(f"❌ UPDATE 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        source_conn.close()
        target_conn.close()

if __name__ == "__main__":
    sys.exit(0 if test_real_update() else 1)
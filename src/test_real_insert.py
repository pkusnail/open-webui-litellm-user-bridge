#!/usr/bin/env python3
"""
真实表结构 INSERT 测试 - 验证LiteLLM到Open WebUI的同步
"""

import psycopg2
import sys
import time
import json
from datetime import datetime

def test_real_insert():
    """测试真实表结构的INSERT操作同步"""
    
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
    
    print("🧪 开始真实表结构 INSERT 测试...")
    print("=" * 50)
    
    try:
        source_cursor = source_conn.cursor()
        target_cursor = target_conn.cursor()
        
        # 1. 创建测试组织
        print("\\n📝 创建测试组织...")
        
        org_data = [
            ('org_tech', 'Technology Corp', 'budget_tech', ['gpt-4', 'claude-3']),
            ('org_sales', 'Sales Division', 'budget_sales', ['gpt-3.5-turbo']),
            ('org_research', 'Research Lab', 'budget_research', ['gpt-4', 'claude-3', 'gemini-pro'])
        ]
        
        for org_id, org_alias, budget_id, models in org_data:
            source_cursor.execute("""
                INSERT INTO "LiteLLM_OrganizationTable" 
                (organization_id, organization_alias, budget_id, models, spend, metadata, created_by, updated_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (org_id, org_alias, budget_id, models, 0.0, 
                  json.dumps({"department": org_alias.split()[0]}), 'admin', 'admin'))
            print(f"   ✅ 创建组织: {org_id} ({org_alias})")
        
        # 2. 创建测试团队
        print("\\n📝 创建测试团队...")
        
        team_data = [
            ('team_backend', 'Backend Team', 'org_tech', ['alice', 'bob'], 1000.0),
            ('team_frontend', 'Frontend Team', 'org_tech', ['charlie'], 800.0),
            ('team_enterprise', 'Enterprise Sales', 'org_sales', ['diana'], 1500.0)
        ]
        
        for team_id, team_alias, org_id, members, max_budget in team_data:
            source_cursor.execute("""
                INSERT INTO "LiteLLM_TeamTable"
                (team_id, team_alias, organization_id, members, max_budget, spend, models)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (team_id, team_alias, org_id, members, max_budget, 0.0, 
                  ['gpt-4', 'gpt-3.5-turbo']))
            print(f"   ✅ 创建团队: {team_id} ({team_alias}) -> {org_id}")
        
        # 等待组织同步
        print("\\n⏳ 等待组织同步...")
        time.sleep(2)
        
        # 3. 创建测试用户
        print("\\n📝 创建测试用户...")
        
        user_data = [
            ('alice', 'Alice Chen', 'team_backend', 'org_tech', 'alice@techcorp.com', 'internal_user', None, 200.0),
            ('bob', 'Bob Wilson', 'team_backend', 'org_tech', 'bob@techcorp.com', 'internal_user', 'sso_bob_123', 300.0),
            ('charlie', 'Charlie Davis', 'team_frontend', 'org_tech', 'charlie@techcorp.com', 'proxy_admin', None, 250.0),
            ('diana', 'Diana Rodriguez', 'team_enterprise', 'org_sales', 'diana@salesdiv.com', 'proxy_admin_viewer', 'sso_diana_456', 500.0),
            ('eve', 'Eve Thompson', None, 'org_research', 'eve@research.lab', 'internal_user', None, 400.0)
        ]
        
        for user_id, alias, team_id, org_id, email, role, sso_id, max_budget in user_data:
            # 构建用户的teams数组
            teams_array = [team_id] if team_id else []
            
            source_cursor.execute("""
                INSERT INTO "LiteLLM_UserTable"
                (user_id, user_alias, team_id, organization_id, user_email, user_role, 
                 sso_user_id, teams, max_budget, spend, models, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (user_id, alias, team_id, org_id, email, role, sso_id, teams_array, 
                  max_budget, 0.0, ['gpt-4', 'gpt-3.5-turbo'], 
                  json.dumps({"department": team_id or "research", "level": "senior"})))
            print(f"   ✅ 创建用户: {user_id} ({alias}) -> {team_id or 'no-team'}")
        
        # 等待用户同步
        print("\\n⏳ 等待用户同步...")
        time.sleep(3)
        
        # 4. 验证LiteLLM源表数据
        print("\\n📊 验证LiteLLM源表数据:")
        
        # 组织数据
        source_cursor.execute('SELECT organization_id, organization_alias, spend FROM "LiteLLM_OrganizationTable" ORDER BY organization_id;')
        org_results = source_cursor.fetchall()
        print(f"   组织记录数: {len(org_results)}")
        for row in org_results:
            print(f"   - {row[0]}: {row[1]} (spend: ${row[2]})")
        
        # 团队数据
        source_cursor.execute('SELECT team_id, team_alias, organization_id, max_budget FROM "LiteLLM_TeamTable" ORDER BY team_id;')
        team_results = source_cursor.fetchall()
        print(f"   团队记录数: {len(team_results)}")
        for row in team_results:
            print(f"   - {row[0]}: {row[1]} -> {row[2]} (budget: ${row[3]})")
        
        # 用户数据
        source_cursor.execute('SELECT user_id, user_alias, team_id, organization_id, user_role FROM "LiteLLM_UserTable" ORDER BY user_id;')
        user_results = source_cursor.fetchall()
        print(f"   用户记录数: {len(user_results)}")
        for row in user_results:
            print(f"   - {row[0]}: {row[1]} [{row[4]}] -> team:{row[2]} org:{row[3]}")
        
        # 5. 验证Open WebUI目标表数据
        print("\\n📊 验证Open WebUI目标表数据:")
        
        # 组数据
        target_cursor.execute('SELECT id, name, meta FROM "group" ORDER BY id;')
        group_results = target_cursor.fetchall()
        print(f"   组记录数: {len(group_results)}")
        for row in group_results:
            meta = row[2] if row[2] else {}  # JSONB already parsed as dict
            org_id = meta.get('organization_id', 'unknown')
            spend = meta.get('spend', 0)
            print(f"   - {row[0]}: {row[1]} (org_id: {org_id}, spend: ${spend})")
        
        # 用户数据
        target_cursor.execute('SELECT id, name, email, role, info FROM "user" ORDER BY id;')
        target_user_results = target_cursor.fetchall()
        print(f"   用户记录数: {len(target_user_results)}")
        for row in target_user_results:
            info = row[4] if row[4] else {}  # JSONB already parsed as dict
            orig_id = info.get('original_user_id', 'unknown')
            team_id = info.get('team_id', 'no-team')
            print(f"   - {row[0]}: {row[1]} [{row[3]}] (orig: {orig_id}, team: {team_id})")
        
        # 6. 验证同步映射
        print("\\n📊 验证同步映射:")
        source_cursor.execute('SELECT litellm_type, litellm_id, openwebui_type, openwebui_id FROM sync_mapping ORDER BY litellm_type, litellm_id;')
        mapping_results = source_cursor.fetchall()
        print(f"   映射记录数: {len(mapping_results)}")
        for row in mapping_results:
            print(f"   - {row[0]}:{row[1]} -> {row[2]}:{row[3]}")
        
        # 7. 验证审计日志
        print("\\n📋 验证审计日志:")
        source_cursor.execute("SELECT operation, COUNT(*), COUNT(CASE WHEN sync_result = 'SUCCESS' THEN 1 END) FROM sync_audit GROUP BY operation ORDER BY operation;")
        audit_results = source_cursor.fetchall()
        print(f"   审计记录统计:")
        total_ops = 0
        total_success = 0
        for row in audit_results:
            success_rate = (row[2] / row[1] * 100) if row[1] > 0 else 0
            print(f"   - {row[0]}: {row[2]}/{row[1]} ({success_rate:.1f}%)")
            total_ops += row[1]
            total_success += row[2]
        
        overall_success_rate = (total_success / total_ops * 100) if total_ops > 0 else 0
        print(f"   总计: {total_success}/{total_ops} ({overall_success_rate:.1f}%)")
        
        # 8. 数据一致性检查
        print("\\n🔍 数据一致性检查:")
        success = True
        
        # 检查组织->组映射
        expected_groups = len(org_results)
        actual_groups = len(group_results)
        if expected_groups != actual_groups:
            print(f"   ❌ 组织->组映射不一致: 期望{expected_groups} vs 实际{actual_groups}")
            success = False
        else:
            print(f"   ✅ 组织->组映射一致: {expected_groups}个")
        
        # 检查用户->用户映射
        expected_users = len(user_results)
        actual_users = len(target_user_results)
        if expected_users != actual_users:
            print(f"   ❌ 用户->用户映射不一致: 期望{expected_users} vs 实际{actual_users}")
            success = False
        else:
            print(f"   ✅ 用户->用户映射一致: {expected_users}个")
        
        # 检查同步映射完整性
        expected_mappings = expected_groups + expected_users
        actual_mappings = len(mapping_results)
        if expected_mappings != actual_mappings:
            print(f"   ❌ 同步映射不完整: 期望{expected_mappings} vs 实际{actual_mappings}")
            success = False
        else:
            print(f"   ✅ 同步映射完整: {expected_mappings}条")
        
        # 9. 验证用户名映射逻辑
        print("\\n🔍 验证用户名映射逻辑:")
        mapping_success = True
        
        for source_user, target_user in zip(user_results, target_user_results):
            source_id, source_alias, source_team, source_org, source_role = source_user
            target_id, target_name, target_email, target_role, target_info = target_user
            
            # 获取团队别名
            team_alias = None
            if source_team:
                for team_row in team_results:
                    if team_row[0] == source_team:
                        team_alias = team_row[1]
                        break
            
            # 计算期望的显示名称
            if team_alias:
                expected_name = f"{team_alias}-{source_alias}"
            else:
                expected_name = source_alias
            
            # 计算期望的角色
            expected_role = 'admin' if source_role in ['proxy_admin', 'proxy_admin_viewer'] else 'user'
            
            if target_name != expected_name:
                print(f"   ❌ 用户名映射错误 {source_id}: 期望'{expected_name}' 实际'{target_name}'")
                mapping_success = False
            elif target_role != expected_role:
                print(f"   ❌ 角色映射错误 {source_id}: 期望'{expected_role}' 实际'{target_role}'")
                mapping_success = False
            else:
                print(f"   ✅ {source_id}: '{source_alias}' -> '{target_name}' [{target_role}]")
        
        if mapping_success:
            print("   ✅ 所有用户名和角色映射正确")
        else:
            success = False
        
        # 10. 检查系统状态
        print("\\n📈 检查系统状态:")
        source_cursor.execute("SELECT * FROM check_real_sync_status();")
        status_results = source_cursor.fetchall()
        for metric, value in status_results:
            print(f"   {metric}: {value}")
        
        print(f"\\n{'✅ 真实表结构 INSERT 测试通过!' if success and mapping_success and overall_success_rate >= 95 else '❌ 真实表结构 INSERT 测试失败!'}")
        
        return success and mapping_success and overall_success_rate >= 95
        
    except Exception as e:
        print(f"❌ INSERT 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        source_conn.close()
        target_conn.close()

if __name__ == "__main__":
    sys.exit(0 if test_real_insert() else 1)
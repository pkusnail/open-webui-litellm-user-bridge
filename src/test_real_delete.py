#!/usr/bin/env python3
"""
真实表结构 DELETE 测试 - 验证LiteLLM到Open WebUI的删除同步
"""

import psycopg2
import sys
import time
import json
from datetime import datetime

def test_real_delete():
    """测试真实表结构的DELETE操作同步"""
    
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
    
    print("🧪 开始真实表结构 DELETE 测试...")
    print("=" * 50)
    
    try:
        source_cursor = source_conn.cursor()
        target_cursor = target_conn.cursor()
        
        # 1. 查看删除前状态
        print("\\n📊 删除前状态:")
        
        # 统计记录数
        source_cursor.execute('SELECT COUNT(*) FROM "LiteLLM_OrganizationTable";')
        org_count_before = source_cursor.fetchone()[0]
        
        source_cursor.execute('SELECT COUNT(*) FROM "LiteLLM_UserTable";')
        user_count_before = source_cursor.fetchone()[0]
        
        target_cursor.execute('SELECT COUNT(*) FROM "group";')
        group_count_before = target_cursor.fetchone()[0]
        
        target_cursor.execute('SELECT COUNT(*) FROM "user";')
        target_user_count_before = target_cursor.fetchone()[0]
        
        print(f"   LiteLLM组织数: {org_count_before}")
        print(f"   LiteLLM用户数: {user_count_before}")
        print(f"   OpenWebUI组数: {group_count_before}")
        print(f"   OpenWebUI用户数: {target_user_count_before}")
        
        # 2. 获取要删除的用户详情
        source_cursor.execute('''
            SELECT u.user_id, u.user_alias, u.user_email, u.team_id, u.organization_id,
                   t.team_alias, o.organization_alias
            FROM "LiteLLM_UserTable" u
            LEFT JOIN "LiteLLM_TeamTable" t ON u.team_id = t.team_id
            LEFT JOIN "LiteLLM_OrganizationTable" o ON u.organization_id = o.organization_id
            WHERE u.user_id = 'charlie';
        ''')
        user_to_delete = source_cursor.fetchone()
        
        if user_to_delete:
            print(f"\\n📝 准备删除用户:")
            print(f"   用户ID: {user_to_delete[0]}")
            print(f"   用户名: {user_to_delete[1]}")
            print(f"   邮箱: {user_to_delete[2]}")
            print(f"   团队: {user_to_delete[5]} ({user_to_delete[3]})")
            print(f"   组织: {user_to_delete[6]} ({user_to_delete[4]})")
        else:
            print("   ❌ 找不到要删除的用户 charlie，请先运行插入测试")
            return False
        
        # 验证目标表中存在对应记录
        target_cursor.execute("SELECT id, name, email, role FROM \"user\" WHERE id = 'usr_charlie';")
        target_user_before = target_cursor.fetchone()
        
        if target_user_before:
            print(f"   OpenWebUI对应用户: {target_user_before}")
        else:
            print("   ❌ OpenWebUI中找不到对应用户记录")
            return False
        
        # 3. 执行用户删除
        print("\\n📝 执行用户删除...")
        
        delete_sql = 'DELETE FROM "LiteLLM_UserTable" WHERE user_id = %s'
        source_cursor.execute(delete_sql, ('charlie',))
        print(f"   ✅ 删除LiteLLM用户: charlie")
        
        # 等待触发器执行
        print("\\n⏳ 等待删除触发器同步...")
        time.sleep(2)
        
        # 4. 验证删除后状态
        print("\\n📊 删除后状态:")
        
        source_cursor.execute('SELECT COUNT(*) FROM "LiteLLM_UserTable";')
        user_count_after = source_cursor.fetchone()[0]
        
        target_cursor.execute('SELECT COUNT(*) FROM "user";')
        target_user_count_after = target_cursor.fetchone()[0]
        
        print(f"   LiteLLM用户数: {user_count_after} (减少 {user_count_before - user_count_after})")
        print(f"   OpenWebUI用户数: {target_user_count_after} (减少 {target_user_count_before - target_user_count_after})")
        
        # 5. 验证源表删除
        source_cursor.execute("SELECT COUNT(*) FROM \"LiteLLM_UserTable\" WHERE user_id = 'charlie';")
        source_deleted = source_cursor.fetchone()[0] == 0
        
        # 6. 验证目标表同步删除
        target_cursor.execute("SELECT COUNT(*) FROM \"user\" WHERE id = 'usr_charlie';")
        target_deleted = target_cursor.fetchone()[0] == 0
        
        print(f"\\n🔍 验证删除结果:")
        print(f"   LiteLLM源表删除: {'✅' if source_deleted else '❌'}")
        print(f"   OpenWebUI目标表删除: {'✅' if target_deleted else '❌'}")
        
        # 7. 验证同步映射删除
        source_cursor.execute("SELECT COUNT(*) FROM sync_mapping WHERE litellm_type = 'user' AND litellm_id = 'charlie';")
        mapping_deleted = source_cursor.fetchone()[0] == 0
        print(f"   同步映射删除: {'✅' if mapping_deleted else '❌'}")
        
        # 8. 验证数据一致性
        counts_consistent = user_count_after == target_user_count_after
        print(f"   用户数量一致: {'✅' if counts_consistent else '❌'}")
        
        # 9. 验证删除审计日志
        print("\\n📋 验证删除审计日志:")
        source_cursor.execute('''
            SELECT operation, record_id, sync_result, old_data, created_at 
            FROM sync_audit 
            WHERE operation = 'DELETE_USER' AND record_id = 'charlie'
            ORDER BY created_at DESC
            LIMIT 1;
        ''')
        delete_audit = source_cursor.fetchone()
        
        if delete_audit:
            print(f"   删除审计记录: {delete_audit[0]} -> {delete_audit[2]}")
            print(f"   删除时间: {delete_audit[4]}")
            
            if delete_audit[3]:  # old_data存在
                old_data = delete_audit[3]  # JSONB already parsed as dict
                deleted_email = old_data.get('user_email', 'N/A')
                print(f"   删除用户邮箱: {deleted_email}")
            
            audit_correct = delete_audit[2] == 'SUCCESS'
        else:
            print("   ❌ 未找到删除审计记录")
            audit_correct = False
        
        # 10. 验证剩余用户完整性
        print("\\n🔍 验证剩余用户完整性:")
        
        source_cursor.execute('SELECT user_id, user_alias, user_email FROM "LiteLLM_UserTable" ORDER BY user_id;')
        remaining_source = source_cursor.fetchall()
        
        target_cursor.execute('SELECT id, name, email FROM "user" ORDER BY id;') 
        remaining_target = target_cursor.fetchall()
        
        print(f"   LiteLLM剩余用户: {[r[0] for r in remaining_source]}")
        print(f"   OpenWebUI剩余用户: {[r[0] for r in remaining_target]}")
        
        # 验证剩余用户的映射关系
        remaining_consistent = True
        if len(remaining_source) == len(remaining_target):
            # 检查每个LiteLLM用户是否都有对应的OpenWebUI用户（带usr_前缀）
            source_ids = {r[0] for r in remaining_source}
            target_ids = {r[0].replace('usr_', '') for r in remaining_target if r[0].startswith('usr_')}
            
            if source_ids != target_ids:
                remaining_consistent = False
                print(f"   ❌ 剩余用户ID不匹配: {source_ids} vs {target_ids}")
            else:
                print(f"   ✅ 剩余用户ID匹配")
        else:
            remaining_consistent = False
            print(f"   ❌ 剩余用户数量不一致")
        
        # 11. 测试组织删除
        print("\\n📝 测试组织删除...")
        
        # 选择一个组织进行删除测试
        source_cursor.execute("SELECT organization_id, organization_alias FROM \"LiteLLM_OrganizationTable\" WHERE organization_id = 'org_research';")
        org_to_delete = source_cursor.fetchone()
        
        if org_to_delete:
            print(f"   准备删除组织: {org_to_delete[0]} ({org_to_delete[1]})")
            
            # 先删除该组织下的用户 (eve)
            source_cursor.execute("DELETE FROM \"LiteLLM_UserTable\" WHERE organization_id = 'org_research';")
            print(f"   ✅ 先删除组织下的用户")
            
            # 等待用户删除同步
            time.sleep(1)
            
            # 删除组织
            source_cursor.execute("DELETE FROM \"LiteLLM_OrganizationTable\" WHERE organization_id = 'org_research';")
            print(f"   ✅ 删除LiteLLM组织: {org_to_delete[0]}")
            
            # 等待同步
            time.sleep(2)
            
            # 验证组织删除
            source_cursor.execute("SELECT COUNT(*) FROM \"LiteLLM_OrganizationTable\" WHERE organization_id = 'org_research';")
            org_source_deleted = source_cursor.fetchone()[0] == 0
            
            target_cursor.execute("SELECT COUNT(*) FROM \"group\" WHERE id = 'grp_org_research';")
            org_target_deleted = target_cursor.fetchone()[0] == 0
            
            print(f"   LiteLLM组织删除: {'✅' if org_source_deleted else '❌'}")
            print(f"   OpenWebUI组删除: {'✅' if org_target_deleted else '❌'}")
            
            # 验证组织删除的审计记录
            source_cursor.execute("SELECT sync_result FROM sync_audit WHERE operation = 'DELETE_ORG' AND record_id = 'org_research' ORDER BY created_at DESC LIMIT 1;")
            org_audit = source_cursor.fetchone()
            org_audit_correct = org_audit and org_audit[0] == 'SUCCESS'
        else:
            print("   ❌ 找不到测试组织org_research")
            org_source_deleted = org_target_deleted = org_audit_correct = False
        
        # 12. 综合验证结果
        all_checks = [
            source_deleted,           # 源表用户删除成功
            target_deleted,           # 目标表用户删除成功
            mapping_deleted,          # 同步映射删除成功
            counts_consistent,        # 记录数一致
            audit_correct,           # 用户删除审计记录正确
            remaining_consistent,    # 剩余数据一致
            user_count_after == user_count_before - 1,  # 用户数确实减少1
            target_user_count_after == target_user_count_before - 1,  # 目标用户数确实减少1
            org_source_deleted,      # 组织删除成功
            org_target_deleted,      # 目标组删除成功
            org_audit_correct       # 组织删除审计正确
        ]
        
        success = all(all_checks)
        
        print(f"\\n📈 真实表结构DELETE测试结果:")
        print(f"   用户源表删除: {'✅' if source_deleted else '❌'}")
        print(f"   用户目标表删除: {'✅' if target_deleted else '❌'}")
        print(f"   同步映射清理: {'✅' if mapping_deleted else '❌'}")
        print(f"   记录数一致性: {'✅' if counts_consistent else '❌'}")
        print(f"   用户删除审计: {'✅' if audit_correct else '❌'}")
        print(f"   剩余数据完整性: {'✅' if remaining_consistent else '❌'}")
        print(f"   组织删除: {'✅' if org_source_deleted and org_target_deleted else '❌'}")
        print(f"   组织删除审计: {'✅' if org_audit_correct else '❌'}")
        
        print(f"\\n{'✅ 真实表结构 DELETE 测试通过!' if success else '❌ 真实表结构 DELETE 测试失败!'}")
        return success
        
    except Exception as e:
        print(f"❌ DELETE 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        source_conn.close()
        target_conn.close()

if __name__ == "__main__":
    sys.exit(0 if test_real_delete() else 1)
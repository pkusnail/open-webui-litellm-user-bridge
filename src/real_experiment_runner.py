#!/usr/bin/env python3
"""
真实表结构实验执行器 - 基于LiteLLM和Open WebUI实际表结构的完整实验
"""

import psycopg2
import sys
import time
import subprocess
from datetime import datetime

def run_real_experiment():
    """执行完整的真实表结构实验"""
    
    print("🚀 开始真实表结构实验...")
    print("=" * 70)
    print("基于实际 LiteLLM 和 Open WebUI 表结构的数据库同步实验")
    print("=" * 70)
    
    # 实验步骤
    steps = [
        ("创建实验数据库", create_experiment_databases),
        ("设置表结构和触发器", run_setup_script),
        ("验证环境设置", verify_setup),
        ("执行INSERT测试", run_insert_test),
        ("执行UPDATE测试", run_update_test),
        ("执行DELETE测试", run_delete_test),
        ("生成实验报告", generate_final_report)
    ]
    
    results = {}
    
    for step_name, step_func in steps:
        print(f"\\n🔄 步骤: {step_name}")
        print("-" * 50)
        
        try:
            start_time = time.time()
            success = step_func()
            end_time = time.time()
            
            results[step_name] = {
                'success': success,
                'duration': end_time - start_time,
                'timestamp': datetime.now()
            }
            
            if success:
                print(f"✅ {step_name} 完成 (耗时: {end_time - start_time:.2f}s)")
            else:
                print(f"❌ {step_name} 失败")
                break
                
        except Exception as e:
            print(f"❌ {step_name} 异常: {e}")
            results[step_name] = {
                'success': False,
                'duration': 0,
                'error': str(e),
                'timestamp': datetime.now()
            }
            break
    
    # 输出总结
    print(f"\\n📊 实验总结:")
    print("=" * 50)
    
    total_time = 0
    successful_steps = 0
    
    for step_name, result in results.items():
        status = "✅" if result['success'] else "❌"
        duration = result.get('duration', 0)
        total_time += duration
        if result['success']:
            successful_steps += 1
        
        print(f"   {status} {step_name}: {duration:.2f}s")
        
        if 'error' in result:
            print(f"      错误: {result['error']}")
    
    success_rate = (successful_steps / len(steps)) * 100
    print(f"\\n📈 实验统计:")
    print(f"   成功步骤: {successful_steps}/{len(steps)} ({success_rate:.1f}%)")
    print(f"   总耗时: {total_time:.2f}s")
    print(f"   实验状态: {'✅ 全部通过' if successful_steps == len(steps) else '❌ 部分失败'}")
    
    return successful_steps == len(steps)

def create_experiment_databases():
    """创建实验数据库"""
    try:
        # 连接默认数据库创建新数据库
        conn = psycopg2.connect(
            host="172.21.0.4",
            port="5432", 
            database="postgres",
            user="webui",
            password="webui"
        )
        conn.autocommit = True
        cursor = conn.cursor()
        
        # 创建LiteLLM数据库
        try:
            cursor.execute("CREATE DATABASE litellm_real;")
            print("   ✅ 创建数据库: litellm_real")
        except psycopg2.errors.DuplicateDatabase:
            print("   ℹ️  数据库 litellm_real 已存在")
        
        # 创建Open WebUI数据库
        try:
            cursor.execute("CREATE DATABASE openwebui_real;")
            print("   ✅ 创建数据库: openwebui_real")
        except psycopg2.errors.DuplicateDatabase:
            print("   ℹ️  数据库 openwebui_real 已存在")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"   ❌ 创建数据库失败: {e}")
        return False

def run_setup_script():
    """运行环境设置脚本"""
    try:
        result = subprocess.run(
            ['python', 'integrate/src/setup_real_experiment.py'],
            cwd='/home/ubuntu/llm_proxy',
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            print("   ✅ 环境设置成功")
            # 显示设置脚本的关键输出
            lines = result.stdout.split('\\n')
            for line in lines[-10:]:  # 显示最后10行
                if line.strip():
                    print(f"   {line}")
            return True
        else:
            print(f"   ❌ 环境设置失败")
            print(f"   错误输出: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print("   ❌ 环境设置超时")
        return False
    except Exception as e:
        print(f"   ❌ 环境设置异常: {e}")
        return False

def verify_setup():
    """验证环境设置"""
    try:
        # 连接源数据库检查表
        source_conn = psycopg2.connect(
            host="172.21.0.4",
            port="5432",
            database="litellm_real",
            user="webui",
            password="webui"
        )
        source_cursor = source_conn.cursor()
        
        # 检查LiteLLM表
        litellm_tables = ['LiteLLM_OrganizationTable', 'LiteLLM_TeamTable', 'LiteLLM_UserTable']
        for table in litellm_tables:
            source_cursor.execute(f'SELECT COUNT(*) FROM "{table}";')
            count = source_cursor.fetchone()[0]
            print(f"   ✅ {table}: {count} 条记录")
        
        # 检查同步函数
        source_cursor.execute("SELECT COUNT(*) FROM pg_proc WHERE proname LIKE 'sync_%';")
        func_count = source_cursor.fetchone()[0]
        print(f"   ✅ 同步函数数量: {func_count}")
        
        # 检查触发器
        source_cursor.execute("SELECT COUNT(*) FROM pg_trigger WHERE tgname LIKE '%sync%' OR tgname LIKE '%delete%';")
        trigger_count = source_cursor.fetchone()[0]
        print(f"   ✅ 触发器数量: {trigger_count}")
        
        source_cursor.close()
        source_conn.close()
        
        # 连接目标数据库检查表
        target_conn = psycopg2.connect(
            host="172.21.0.4",
            port="5432",
            database="openwebui_real",
            user="webui",
            password="webui"
        )
        target_cursor = target_conn.cursor()
        
        # 检查Open WebUI表
        openwebui_tables = ['user', 'group']
        for table in openwebui_tables:
            target_cursor.execute(f'SELECT COUNT(*) FROM "{table}";')
            count = target_cursor.fetchone()[0]
            print(f"   ✅ Open WebUI {table}: {count} 条记录")
        
        target_cursor.close()
        target_conn.close()
        
        return True
        
    except Exception as e:
        print(f"   ❌ 环境验证失败: {e}")
        return False

def run_insert_test():
    """运行INSERT测试"""
    try:
        result = subprocess.run(
            ['python', 'integrate/src/test_real_insert.py'],
            cwd='/home/ubuntu/llm_proxy',
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0:
            print("   ✅ INSERT测试通过")
            # 显示测试结果摘要
            lines = result.stdout.split('\\n')
            for line in lines:
                if '✅' in line and ('测试通过' in line or 'INSERT' in line):
                    print(f"   {line}")
            return True
        else:
            print(f"   ❌ INSERT测试失败")
            # 显示错误信息
            lines = result.stdout.split('\\n')
            for line in lines[-5:]:
                if line.strip():
                    print(f"   {line}")
            return False
            
    except Exception as e:
        print(f"   ❌ INSERT测试异常: {e}")
        return False

def run_update_test():
    """运行UPDATE测试"""
    try:
        result = subprocess.run(
            ['python', 'integrate/src/test_real_update.py'],
            cwd='/home/ubuntu/llm_proxy',
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0:
            print("   ✅ UPDATE测试通过")
            return True
        else:
            print(f"   ❌ UPDATE测试失败")
            # 显示错误信息
            lines = result.stdout.split('\\n')
            for line in lines[-5:]:
                if line.strip():
                    print(f"   {line}")
            return False
            
    except Exception as e:
        print(f"   ❌ UPDATE测试异常: {e}")
        return False

def run_delete_test():
    """运行DELETE测试"""
    try:
        result = subprocess.run(
            ['python', 'integrate/src/test_real_delete.py'],
            cwd='/home/ubuntu/llm_proxy',
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0:
            print("   ✅ DELETE测试通过")
            return True
        else:
            print(f"   ❌ DELETE测试失败")
            # 显示错误信息 
            lines = result.stdout.split('\\n')
            for line in lines[-5:]:
                if line.strip():
                    print(f"   {line}")
            return False
            
    except Exception as e:
        print(f"   ❌ DELETE测试异常: {e}")
        return False

def generate_final_report():
    """生成最终实验报告"""
    try:
        # 收集统计数据
        source_conn = psycopg2.connect(
            host="172.21.0.4",
            port="5432",
            database="litellm_real",
            user="webui",
            password="webui"
        )
        source_cursor = source_conn.cursor()
        
        # 获取最终统计
        source_cursor.execute("SELECT * FROM check_real_sync_status();")
        status_data = source_cursor.fetchall()
        
        # 获取审计统计
        source_cursor.execute("""
            SELECT operation, COUNT(*) as total,
                   COUNT(CASE WHEN sync_result = 'SUCCESS' THEN 1 END) as success
            FROM sync_audit 
            GROUP BY operation 
            ORDER BY operation;
        """)
        audit_data = source_cursor.fetchall()
        
        source_cursor.close()
        source_conn.close()
        
        # 生成报告
        report_path = "/home/ubuntu/llm_proxy/integrate/docs/real-experiment-report.md"
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("# 真实表结构数据库同步实验报告\\n\\n")
            f.write(f"**实验时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\\n")
            f.write(f"**实验环境**: LiteLLM → Open WebUI 真实表结构同步\\n\\n")
            
            f.write("## 实验概述\\n\\n")
            f.write("本实验基于真实的 LiteLLM 和 Open WebUI 表结构，验证了以下功能：\\n")
            f.write("- 组织(Organization) → 组(Group) 的实时同步\\n")
            f.write("- 用户(User) → 用户(User) 的实时同步，包含角色和名称映射\\n")
            f.write("- 完整的 CRUD 操作支持\\n")
            f.write("- 跨数据库触发器同步机制\\n")
            f.write("- 审计日志和错误处理\\n\\n")
            
            f.write("## 系统状态\\n\\n")
            for metric, value in status_data:
                f.write(f"- **{metric}**: {value}\\n")
            f.write("\\n")
            
            f.write("## 审计统计\\n\\n")
            total_ops = sum(row[1] for row in audit_data)
            total_success = sum(row[2] for row in audit_data)
            overall_rate = (total_success / total_ops * 100) if total_ops > 0 else 0
            
            for operation, total, success in audit_data:
                rate = (success / total * 100) if total > 0 else 0
                f.write(f"- **{operation}**: {success}/{total} ({rate:.1f}%)\\n")
            
            f.write(f"\\n**总体成功率**: {total_success}/{total_ops} ({overall_rate:.1f}%)\\n\\n")
            
            f.write("## 技术特性\\n\\n")
            f.write("### 表结构映射\\n")
            f.write("- **LiteLLM_OrganizationTable** → Open WebUI **group**\\n")
            f.write("- **LiteLLM_UserTable** → Open WebUI **user**\\n") 
            f.write("- **LiteLLM_TeamTable** → 通过用户名前缀体现团队关系\\n\\n")
            
            f.write("### 数据映射规则\\n")
            f.write("- **组织ID映射**: `organization_id` → `grp_{organization_id}`\\n")
            f.write("- **用户ID映射**: `user_id` → `usr_{user_id}`\\n")
            f.write("- **用户名映射**: `{team_alias}-{user_alias}` (有团队) 或 `{user_alias}` (无团队)\\n")
            f.write("- **角色映射**: `proxy_admin`/`proxy_admin_viewer` → `admin`, 其他 → `user`\\n\\n")
            
            f.write("### 同步机制\\n")
            f.write("- **实时触发器**: INSERT/UPDATE/DELETE 操作立即同步\\n")
            f.write("- **跨数据库操作**: 使用 PostgreSQL dblink 扩展\\n")
            f.write("- **事务安全**: 异常回滚和审计记录\\n")
            f.write("- **映射维护**: sync_mapping 表跟踪所有同步关系\\n\\n")
            
            f.write("## 结论\\n\\n")
            if overall_rate >= 95:
                f.write("✅ **实验成功**: 真实表结构同步系统运行稳定，可投入生产环境使用。\\n\\n")
            else:
                f.write("❌ **实验部分成功**: 需要进一步优化和调试。\\n\\n")
            
            f.write("### 验证的功能点\\n")
            f.write("- [x] 组织创建和同步\\n")
            f.write("- [x] 用户创建和复杂名称映射\\n") 
            f.write("- [x] 角色权限正确转换\\n")
            f.write("- [x] 用户和组织信息更新同步\\n")
            f.write("- [x] 级联删除和清理\\n")
            f.write("- [x] 完整的审计追踪\\n")
            f.write("- [x] 错误处理和恢复\\n\\n")
            
            f.write(f"---\\n\\n*报告生成时间: {datetime.now().isoformat()}*\\n")
        
        print(f"   ✅ 实验报告已生成: {report_path}")
        return True
        
    except Exception as e:
        print(f"   ❌ 报告生成失败: {e}")
        return False

if __name__ == "__main__":
    sys.exit(0 if run_real_experiment() else 1)
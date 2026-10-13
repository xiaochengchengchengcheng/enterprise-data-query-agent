# -*- coding: utf-8 -*-
"""
企业内网自主取数智能体 - 数据库一键重建脚本
作用：彻底修复中文乱码问题
原理：用 pymysql 强制 utf8mb4 连接执行建库建表语句，
      绕开 mysql 命令行客户端在 Windows cmd 下的编码问题。
用法：
    python rebuild_db.py
执行后会：
    1. 删除并重建 enterprise_data 数据库（utf8mb4）
    2. 创建 4 张业务表（含中文注释）
    3. 插入测试数据（中文正常）
    4. 创建只读账号 readonly_user（仅 SELECT 权限）
    5. 打印验证结果
"""
import os
import sys
import pymysql
from dotenv import load_dotenv

load_dotenv()

# ---------- 管理员连接配置（仅用于初始化，日常业务用只读账号）----------
ADMIN_HOST = os.environ.get("ADMIN_HOST", "127.0.0.1")
ADMIN_PORT = int(os.environ.get("ADMIN_PORT", "3306"))
ADMIN_USER = os.environ.get("ADMIN_USER", "root")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "")
DB_NAME = "enterprise_data"

# ---------- 只读账号配置 ----------
RO_USER = "readonly_user"
RO_PASS = os.environ.get("READONLY_PASSWORD", os.environ.get("DB_PASSWORD", ""))

# ---------- 建库 + 建账号 ----------
DDL_INIT = [
    "DROP DATABASE IF EXISTS enterprise_data",
    "CREATE DATABASE enterprise_data "
    "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci",
    "CREATE USER IF NOT EXISTS 'readonly_user'@'localhost' IDENTIFIED BY %s",
    "CREATE USER IF NOT EXISTS 'readonly_user'@'127.0.0.1' IDENTIFIED BY %s",
    "GRANT SELECT ON enterprise_data.* TO 'readonly_user'@'localhost'",
    "GRANT SELECT ON enterprise_data.* TO 'readonly_user'@'127.0.0.1'",
    "FLUSH PRIVILEGES",
]

# ---------- 建表语句（全部 utf8mb4）----------
DDL_TABLES = [
    # 员工信息表
    """CREATE TABLE employees (
        id INT AUTO_INCREMENT PRIMARY KEY COMMENT '员工ID',
        employee_no VARCHAR(20) NOT NULL COMMENT '工号',
        name VARCHAR(50) NOT NULL COMMENT '姓名',
        department VARCHAR(50) NOT NULL COMMENT '部门',
        position VARCHAR(50) NOT NULL COMMENT '职位',
        phone VARCHAR(20) COMMENT '手机号',
        id_card VARCHAR(20) COMMENT '身份证号',
        bank_card VARCHAR(30) COMMENT '银行卡号',
        hire_date DATE COMMENT '入职日期',
        status VARCHAR(20) DEFAULT '在职' COMMENT '状态(在职/离职)'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='员工信息表'""",

    # 部门表
    """CREATE TABLE departments (
        id INT AUTO_INCREMENT PRIMARY KEY COMMENT '部门ID',
        dept_name VARCHAR(50) NOT NULL COMMENT '部门名称',
        manager VARCHAR(50) COMMENT '部门负责人',
        parent_dept VARCHAR(50) COMMENT '上级部门',
        budget DECIMAL(12,2) COMMENT '年度预算',
        headcount INT COMMENT '编制人数'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='部门信息表'""",

    # 产品信息表
    """CREATE TABLE products (
        id INT AUTO_INCREMENT PRIMARY KEY COMMENT '产品ID',
        product_code VARCHAR(20) NOT NULL COMMENT '产品编码',
        product_name VARCHAR(100) NOT NULL COMMENT '产品名称',
        category VARCHAR(50) NOT NULL COMMENT '产品类别',
        cost_price DECIMAL(10,2) NOT NULL COMMENT '成本价',
        sale_price DECIMAL(10,2) NOT NULL COMMENT '销售价',
        stock INT DEFAULT 0 COMMENT '库存数量',
        supplier VARCHAR(100) COMMENT '供应商',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='产品信息表'""",

    # 客户信息表
    """CREATE TABLE customers (
        id INT AUTO_INCREMENT PRIMARY KEY COMMENT '客户ID',
        customer_name VARCHAR(100) NOT NULL COMMENT '客户名称',
        contact_person VARCHAR(50) NOT NULL COMMENT '联系人',
        phone VARCHAR(20) NOT NULL COMMENT '联系电话',
        region VARCHAR(50) NOT NULL COMMENT '所在区域',
        customer_level VARCHAR(20) DEFAULT 'normal' COMMENT '客户等级(vip/normal/basic)',
        bank_account VARCHAR(30) COMMENT '银行账号',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客户信息表'""",

    # 销售订单表
    """CREATE TABLE sales_orders (
        id INT AUTO_INCREMENT PRIMARY KEY COMMENT '订单ID',
        order_no VARCHAR(30) NOT NULL COMMENT '订单编号',
        customer_name VARCHAR(50) NOT NULL COMMENT '客户姓名',
        region VARCHAR(50) NOT NULL COMMENT '销售区域',
        product_name VARCHAR(100) NOT NULL COMMENT '产品名称',
        quantity INT NOT NULL COMMENT '数量',
        unit_price DECIMAL(10,2) NOT NULL COMMENT '单价',
        total_amount DECIMAL(12,2) NOT NULL COMMENT '总金额',
        order_date DATE NOT NULL COMMENT '订单日期',
        sales_person VARCHAR(50) COMMENT '销售人员',
        status VARCHAR(20) DEFAULT '已完成' COMMENT '订单状态'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='销售订单表'""",
]

# ---------- 测试数据 ----------
DATA = {
    "departments": [
        "INSERT INTO departments (dept_name, manager, parent_dept, budget, headcount) VALUES "
        "('华东销售大区','张伟','销售总部',5000000.00,50),"
        "('华南销售大区','李娜','销售总部',4500000.00,45),"
        "('华北销售大区','王强','销售总部',4800000.00,48),"
        "('西南销售大区','刘洋','销售总部',3000000.00,30),"
        "('技术部','陈明','总部',8000000.00,60),"
        "('人力资源部','赵丽','总部',2000000.00,15),"
        "('财务部','孙杰','总部',3000000.00,20)",
    ],
    "employees": [
        "INSERT INTO employees (employee_no, name, department, position, phone, id_card, bank_card, hire_date, status) VALUES "
        "('EMP001','张伟','华东销售大区','大区经理','13812345678','310101199001011234','6222021234567890123','2018-03-15','在职'),"
        "('EMP002','李娜','华南销售大区','大区经理','13987654321','440106198805156789','6225880123456789','2017-07-01','在职'),"
        "('EMP003','王强','华北销售大区','大区经理','13700112233','110101198512253456','6217001234567890123','2019-01-10','在职'),"
        "('EMP004','刘洋','西南销售大区','大区经理','13655667788','510104199203084567','6228480123456789012','2020-06-20','在职'),"
        "('EMP005','陈明','技术部','技术总监','13522334455','320105198707309876','6226660123456789','2016-09-05','在职'),"
        "('EMP006','赵丽','人力资源部','HR总监','13466778899','420106199101015432','6225900123456789','2018-11-15','在职'),"
        "('EMP007','孙杰','财务部','财务总监','13388990011','330102198606152109','6230580123456789','2015-04-01','在职'),"
        "('EMP008','周婷','华东销售大区','销售专员','13211223344','310104199507203210','6222020123456789','2021-03-01','在职'),"
        "('EMP009','吴昊','华南销售大区','销售专员','13155667788','440103199811114321','6225881234567890','2022-02-14','在职'),"
        "('EMP010','郑雪','华北销售大区','销售专员','13099887766','110103200001016543','6217001234567890','2023-07-01','在职')",
    ],
    "products": [
        "INSERT INTO products (product_code, product_name, category, cost_price, sale_price, stock, supplier) VALUES "
        "('P001','企业版数据平台','软件',200000.00,280000.00,50,'科技公司A'),"
        "('P002','标准版数据分析','软件',60000.00,98000.00,80,'科技公司B'),"
        "('P003','年度运维服务','服务',80000.00,120000.00,100,'服务公司C'),"
        "('P004','定制开发服务','服务',100000.00,150000.00,40,'开发公司D'),"
        "('P005','服务器主机X1','硬件',10000.00,15000.00,30,'硬件厂商B'),"
        "('P006','交换机24口','硬件',2000.00,3500.00,60,'硬件厂商B')",
    ],
    "customers": [
        "INSERT INTO customers (customer_name, contact_person, phone, region, customer_level, bank_account) VALUES "
        "('上海科技有限公司','王经理','13800001111','华东','vip','6222021234567890123'),"
        "('深圳网络股份','李总监','13900002222','华南','vip','6222022345678901234'),"
        "('北京智能科技','赵主管','13700003333','华北','normal','6222023456789012345'),"
        "('成都信息技术','钱经理','13600004444','西南','normal','6222024567890123456'),"
        "('杭州互联网公司','孙总','13500005555','华东','basic','6222025678901234567'),"
        "('广州电商科技','周主任','13400006666','华南','normal','6222026789012345678')",
    ],
    "sales_orders": [
        "INSERT INTO sales_orders (order_no, customer_name, region, product_name, quantity, unit_price, total_amount, order_date, sales_person, status) VALUES "
        "('ORD202501001','上海科技有限公司','华东','企业版数据平台',1,280000.00,280000.00,'2025-01-15','张伟','已完成'),"
        "('ORD202501002','深圳网络股份','华南','标准版数据分析',3,98000.00,294000.00,'2025-01-20','李娜','已完成'),"
        "('ORD202501003','北京智能科技','华北','企业版数据平台',1,280000.00,280000.00,'2025-01-25','王强','已完成'),"
        "('ORD202502001','成都信息技术','西南','标准版数据分析',2,98000.00,196000.00,'2025-02-10','刘洋','已完成'),"
        "('ORD202502002','杭州互联网公司','华东','定制开发服务',1,150000.00,150000.00,'2025-02-18','周婷','已完成'),"
        "('ORD202503001','广州电商科技','华南','企业版数据平台',1,280000.00,280000.00,'2025-03-05','吴昊','已完成'),"
        "('ORD202503002','北京智能科技','华北','标准版数据分析',5,98000.00,490000.00,'2025-03-12','郑雪','已完成'),"
        "('ORD202503003','上海科技有限公司','华东','年度运维服务',1,120000.00,120000.00,'2025-03-20','张伟','已完成'),"
        "('ORD202504001','深圳网络股份','华南','定制开发服务',2,150000.00,300000.00,'2025-04-08','李娜','已完成'),"
        "('ORD202504002','重庆物流科技','西南','标准版数据分析',1,98000.00,98000.00,'2025-04-15','刘洋','已完成'),"
        "('ORD202505001','北京智能科技','华北','年度运维服务',1,120000.00,120000.00,'2025-05-03','王强','已完成'),"
        "('ORD202505002','杭州互联网公司','华东','企业版数据平台',1,280000.00,280000.00,'2025-05-18','周婷','已完成'),"
        "('ORD202506001','广州电商科技','华南','定制开发服务',1,150000.00,150000.00,'2025-06-10','吴昊','已完成'),"
        "('ORD202506002','天津制造集团','华北','企业版数据平台',1,280000.00,280000.00,'2025-06-22','郑雪','已完成')",
    ],
}


# ============================================================
# 批量扩数据词库与函数（每张表补到 EXPAND_ROWS 行）
# ============================================================
import random

# 每张表的目标行数
EXPAND_ROWS = 2500
# 批量插入单次条数
BATCH_SIZE = 500

# 公共词库
_DEPTS = ['华东销售大区','华南销售大区','华北销售大区','西南销售大区',
         '技术部','人力资源部','财务部']
_POSITIONS = ['大区经理','销售专员','技术总监','HR总监','财务总监',
             '销售经理','高级工程师','运维工程师','人事专员','会计']
_REGIONS = ['华东','华南','华北','西南','东北','西北','华中']
_LEVELS = ['vip','normal','basic']
_STATUS_EMP = ['在职','离职']
_STATUS_ORD = ['已完成','处理中','已取消','待付款']
_CATEGORIES = ['软件','硬件','服务']
_SUPPLIERS = ['科技公司A','科技公司B','服务公司C','开发公司D','硬件厂商B']
_FIRST = ['张','李','王','赵','刘','陈','杨','黄','周','吴','徐','孙','马','朱','胡','郭','何','高','林','罗']
_LAST = ['伟','娜','强','洋','静','磊','丽','杰','斌','敏','勇','艳','波','涛','明','超','秀','霞','平','刚']
_CUST_PREFIX = ['上海','深圳','北京','成都','杭州','广州','天津','重庆','南京','武汉','西安','苏州','青岛','大连','厦门']
_CUST_SUFFIX = ['科技有限公司','网络股份','智能科技','信息技术','互联网公司',
               '制造集团','电商科技','物流科技','软件股份','实业集团']
_PRODUCTS_TPL = [('企业版数据平台','软件',200000.00,280000.00),
            ('标准版数据分析','软件',60000.00,98000.00),
            ('年度运维服务','服务',80000.00,120000.00),
            ('定制开发服务','服务',100000.00,150000.00),
            ('服务器主机X1','硬件',10000.00,15000.00),
            ('交换机24口','硬件',2000.00,3500.00),
            ('云存储空间1TB','服务',500.00,2000.00),
            ('网络安全服务包','服务',3000.00,8000.00)]


def _rand_name():
    return random.choice(_FIRST) + random.choice(_LAST)


def _rand_phone():
    return '1' + random.choice('34578') + ''.join(random.choice('0123456789') for _ in range(10))


def _rand_id_card():
    region = random.choice(['310101','440106','110101','510104','320105',
                            '420106','330102','440103','110103','310104'])
    y = random.randint(1965, 2003)
    m = random.randint(1, 12)
    d = random.randint(1, 28)
    seq = random.randint(100, 999)
    return f"{region}{y:04d}{m:02d}{d:02d}{seq}X"


def _rand_bank_card():
    return '6222' + ''.join(random.choice('0123456789') for _ in range(14))


def expand_data(cur):
    """
    将每张业务表批量补足到 EXPAND_ROWS 行。

    在插入测试基础数据之后调用，用 executemany 批量插入。
    固定随机种子保证可复现。
    """
    random.seed(42)

    # ---------- departments ----------
    cur.execute("SELECT COUNT(*) FROM departments")
    now = cur.fetchone()[0]
    need = EXPAND_ROWS - now
    if need > 0:
        rows = []
        for i in range(need):
            rows.append((
                f'{random.choice(["华东","华南","华北","西南","东北","西北","华中"])}事业部{i+1}',
                _rand_name(),
                random.choice(['销售总部','总部']),
                round(random.uniform(1000000, 10000000), 2),
                random.randint(10, 80)
            ))
        cur.executemany(
            "INSERT INTO departments (dept_name, manager, parent_dept, budget, headcount) "
            "VALUES (%s,%s,%s,%s,%s)", rows)

    # ---------- employees ----------
    cur.execute("SELECT COUNT(*) FROM employees")
    now = cur.fetchone()[0]
    need = EXPAND_ROWS - now
    inserted = 0
    while inserted < need:
        size = min(BATCH_SIZE, need - inserted)
        rows = []
        for i in range(size):
            y = random.randint(2008, 2025)
            m = random.randint(1, 12)
            d = random.randint(1, 28)
            rows.append((
                f'EMP{now+inserted+i+1:06d}',
                _rand_name(),
                random.choice(_DEPTS),
                random.choice(_POSITIONS),
                _rand_phone(),
                _rand_id_card(),
                _rand_bank_card(),
                f'{y}-{m:02d}-{d:02d}',
                random.choices(_STATUS_EMP, weights=[85,15])[0]
            ))
        cur.executemany(
            "INSERT INTO employees (employee_no,name,department,position,phone,id_card,bank_card,hire_date,status) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", rows)
        inserted += size

    # ---------- products ----------
    cur.execute("SELECT COUNT(*) FROM products")
    now = cur.fetchone()[0]
    need = EXPAND_ROWS - now
    inserted = 0
    while inserted < need:
        size = min(BATCH_SIZE, need - inserted)
        rows = []
        for i in range(size):
            p = random.choice(_PRODUCTS_TPL)
            cost = round(p[2] * random.uniform(0.8, 1.2), 2)
            sale = round(cost * random.uniform(1.3, 1.6), 2)
            rows.append((
                f'P{now+inserted+i+1:05d}', p[0], p[1], cost, sale,
                random.randint(0, 500), random.choice(_SUPPLIERS)
            ))
        cur.executemany(
            "INSERT INTO products (product_code,product_name,category,cost_price,sale_price,stock,supplier) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)", rows)
        inserted += size

    # ---------- customers ----------
    cur.execute("SELECT COUNT(*) FROM customers")
    now = cur.fetchone()[0]
    need = EXPAND_ROWS - now
    inserted = 0
    while inserted < need:
        size = min(BATCH_SIZE, need - inserted)
        rows = []
        for i in range(size):
            rows.append((
                f'{random.choice(_CUST_PREFIX)}{random.choice(_CUST_SUFFIX)}{now+inserted+i+1}',
                _rand_name() + random.choice(['经理','总监','主管','主任']),
                _rand_phone(), random.choice(_REGIONS),
                random.choice(_LEVELS), _rand_bank_card()
            ))
        cur.executemany(
            "INSERT INTO customers (customer_name,contact_person,phone,region,customer_level,bank_account) "
            "VALUES (%s,%s,%s,%s,%s,%s)", rows)
        inserted += size

    # ---------- sales_orders ----------
    cur.execute("SELECT COUNT(*) FROM sales_orders")
    now = cur.fetchone()[0]
    need = EXPAND_ROWS - now
    inserted = 0
    while inserted < need:
        size = min(BATCH_SIZE, need - inserted)
        rows = []
        for i in range(size):
            p = random.choice(_PRODUCTS_TPL)
            qty = random.randint(1, 20)
            unit = round(p[3] * random.uniform(0.9, 1.1), 2)
            total = round(qty * unit, 2)
            y = random.choice([2025, 2026])
            m = random.randint(1, 6) if y == 2026 else random.randint(1, 12)
            d = random.randint(1, 28)
            rows.append((
                f'ORD{y}{m:02d}{now+inserted+i+1:05d}',
                f'{random.choice(_CUST_PREFIX)}{random.choice(_CUST_SUFFIX)}',
                random.choice(_REGIONS), p[0], qty, unit, total,
                f'{y}-{m:02d}-{d:02d}', _rand_name(), random.choice(_STATUS_ORD)
            ))
        cur.executemany(
            "INSERT INTO sales_orders (order_no,customer_name,region,product_name,quantity,unit_price,total_amount,order_date,sales_person,status) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", rows)
        inserted += size

    return "每张表已补足到 %d 行" % EXPAND_ROWS



def main():
    print("=" * 60)
    print("企业内网自主取数智能体 - 数据库一键重建")
    print("=" * 60)

    if not ADMIN_PASS:
        raise RuntimeError("ADMIN_PASSWORD 未配置，请在 .env 中设置 MySQL 管理员密码")
    if not RO_PASS:
        raise RuntimeError("READONLY_PASSWORD 或 DB_PASSWORD 未配置，请在 .env 中设置只读账号密码")

    # 第1步：管理员连接，建库 + 建账号
    print("\n[1/5] 连接 MySQL (root) ...")
    conn = pymysql.connect(host=ADMIN_HOST, port=ADMIN_PORT,
                           user=ADMIN_USER, password=ADMIN_PASS,
                           charset="utf8mb4", autocommit=True)
    cur = conn.cursor()
    for sql in DDL_INIT:
        params = (RO_PASS,) if "%s" in sql else ()
        cur.execute(sql, params)
        print("  OK:", sql.split()[0:3])
    conn.close()
    print("  -> 数据库已重建，只读账号已创建")

    # 第2步：业务库连接，建表
    print("\n[2/5] 创建业务表 ...")
    conn = pymysql.connect(host=ADMIN_HOST, port=ADMIN_PORT,
                           user=ADMIN_USER, password=ADMIN_PASS,
                           database=DB_NAME, charset="utf8mb4", autocommit=True)
    cur = conn.cursor()
    for ddl in DDL_TABLES:
        cur.execute(ddl)
    print(f"  -> 已创建 {len(DDL_TABLES)} 张表")

    # 第3步：插入数据
    print("\n[3/5] 插入测试数据 ...")
    for table, sqls in DATA.items():
        for sql in sqls:
            cur.execute(sql)
        print(f"  -> {table}: 已插入")

    # 第4步：批量扩充数据（每张表补到 2500 行）
    print("\n[4/5] 批量扩充数据（每张表补到 %d 行）..." % EXPAND_ROWS)
    msg = expand_data(cur)
    print("  ->", msg)

    # 第5步：验证中文
    print("\n[5/5] 验证中文是否正常 ...")
    cur.execute("SELECT name FROM employees LIMIT 3")
    rows = cur.fetchall()
    print("  employees.name 示例:", [r[0] for r in rows])
    cur.execute("SELECT customer_name FROM customers LIMIT 3")
    rows = cur.fetchall()
    print("  customers.customer_name 示例:", [r[0] for r in rows])
    cur.execute("SHOW CREATE TABLE employees")
    ddl = cur.fetchone()[1]
    print("  employees 表注释正常:", "员工ID" in ddl)
    conn.close()

    # 第5步：只读账号验证
    print("\n[验证] 用只读账号连接测试 ...")
    conn2 = pymysql.connect(host=ADMIN_HOST, port=ADMIN_PORT,
                            user=RO_USER, password=RO_PASS,
                            database=DB_NAME, charset="utf8mb4")
    cur2 = conn2.cursor()
    cur2.execute("SELECT COUNT(*) FROM sales_orders")
    print("  只读账号查询 sales_orders 行数:", cur2.fetchone()[0])
    for t in ['departments','employees','products','customers','sales_orders']:
        cur2.execute(f"SELECT COUNT(*) FROM {t}")
        print(f"  {t} 行数:", cur2.fetchone()[0])
    conn2.close()

    print("\n" + "=" * 60)
    print("重建完成！中文已恢复正常，每张表已补足到 %d 行。" % EXPAND_ROWS)
    print("=" * 60)


if __name__ == "__main__":
    main()

-- ============================================================
-- 企业内网自主取数智能体 - 数据库初始化脚本
-- 创建业务数据库、测试数据表、只读账号
-- ============================================================

-- 创建业务数据库
CREATE DATABASE IF NOT EXISTS enterprise_data
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE enterprise_data;

-- ============================================================
-- 表1：员工信息表
-- ============================================================
DROP TABLE IF EXISTS employees;
CREATE TABLE employees (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '员工ID',
    emp_no VARCHAR(20) NOT NULL COMMENT '工号',
    name VARCHAR(50) NOT NULL COMMENT '姓名',
    department VARCHAR(50) NOT NULL COMMENT '部门',
    position VARCHAR(50) NOT NULL COMMENT '职位',
    phone VARCHAR(20) NOT NULL COMMENT '手机号',
    id_card VARCHAR(20) NOT NULL COMMENT '身份证号',
    hire_date DATE NOT NULL COMMENT '入职日期',
    status VARCHAR(20) DEFAULT 'active' COMMENT '状态(active/inactive)',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='员工信息表';

-- ============================================================
-- 表2：销售订单表
-- ============================================================
DROP TABLE IF EXISTS sales_orders;
CREATE TABLE sales_orders (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '订单ID',
    order_no VARCHAR(30) NOT NULL COMMENT '订单编号',
    customer_name VARCHAR(100) NOT NULL COMMENT '客户名称',
    region VARCHAR(50) NOT NULL COMMENT '销售区域',
    product_name VARCHAR(100) NOT NULL COMMENT '产品名称',
    quantity INT NOT NULL COMMENT '数量',
    unit_price DECIMAL(10,2) NOT NULL COMMENT '单价',
    total_amount DECIMAL(12,2) NOT NULL COMMENT '总金额',
    order_date DATE NOT NULL COMMENT '订单日期',
    sales_emp_id INT NOT NULL COMMENT '销售员ID',
    status VARCHAR(20) DEFAULT 'completed' COMMENT '订单状态(completed/pending/cancelled)',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='销售订单表';

-- ============================================================
-- 表3：产品信息表
-- ============================================================
DROP TABLE IF EXISTS products;
CREATE TABLE products (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '产品ID',
    product_code VARCHAR(20) NOT NULL COMMENT '产品编码',
    product_name VARCHAR(100) NOT NULL COMMENT '产品名称',
    category VARCHAR(50) NOT NULL COMMENT '产品类别',
    cost_price DECIMAL(10,2) NOT NULL COMMENT '成本价',
    sale_price DECIMAL(10,2) NOT NULL COMMENT '销售价',
    stock INT DEFAULT 0 COMMENT '库存数量',
    supplier VARCHAR(100) COMMENT '供应商',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='产品信息表';

-- ============================================================
-- 表4：客户信息表
-- ============================================================
DROP TABLE IF EXISTS customers;
CREATE TABLE customers (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '客户ID',
    customer_name VARCHAR(100) NOT NULL COMMENT '客户名称',
    contact_person VARCHAR(50) NOT NULL COMMENT '联系人',
    phone VARCHAR(20) NOT NULL COMMENT '联系电话',
    region VARCHAR(50) NOT NULL COMMENT '所在区域',
    customer_level VARCHAR(20) DEFAULT 'normal' COMMENT '客户等级(vip/normal/basic)',
    bank_account VARCHAR(30) COMMENT '银行账号',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客户信息表';

-- ============================================================
-- 插入测试数据 - 员工信息
-- ============================================================
INSERT INTO employees (emp_no, name, department, position, phone, id_card, hire_date, status) VALUES
('EMP001', '张伟', '销售部', '销售经理', '13812345678', '110101199001011234', '2020-03-15', 'active'),
('EMP002', '李娜', '销售部', '销售代表', '13987654321', '310101199205052345', '2021-06-20', 'active'),
('EMP003', '王强', '技术部', '技术总监', '13701234567', '440101198807073456', '2019-01-10', 'active'),
('EMP004', '刘洋', '财务部', '财务经理', '13611112222', '420101199103034567', '2020-09-01', 'active'),
('EMP005', '陈静', '人事部', '人事专员', '13533334444', '510101199404045678', '2022-02-14', 'active'),
('EMP006', '赵磊', '销售部', '销售代表', '13455556666', '320101199506066789', '2022-08-01', 'active'),
('EMP007', '孙丽', '技术部', '工程师', '13377778888', '350101199707077890', '2023-03-01', 'active'),
('EMP008', '周杰', '销售部', '销售代表', '13299990000', '210101199808088901', '2023-07-15', 'active');

-- ============================================================
-- 插入测试数据 - 产品信息
-- ============================================================
INSERT INTO products (product_code, product_name, category, cost_price, sale_price, stock, supplier) VALUES
('P001', '企业版数据库授权', '软件', 5000.00, 12000.00, 50, '科技公司A'),
('P002', '服务器主机X1', '硬件', 8000.00, 15000.00, 30, '硬件厂商B'),
('P003', '网络安全服务包', '服务', 3000.00, 8000.00, 100, '安全公司C'),
('P004', '云存储空间1TB', '服务', 500.00, 2000.00, 200, '云服务D'),
('P005', '技术支持年度包', '服务', 2000.00, 6000.00, 80, '科技公司A'),
('P006', '交换机24口', '硬件', 1200.00, 3500.00, 60, '硬件厂商B');

-- ============================================================
-- 插入测试数据 - 客户信息
-- ============================================================
INSERT INTO customers (customer_name, contact_person, phone, region, customer_level, bank_account) VALUES
('华东科技有限公司', '王经理', '13800001111', '华东', 'vip', '6222021234567890123'),
('华南贸易集团', '李总监', '13900002222', '华南', 'vip', '6222022345678901234'),
('华北制造股份', '赵主管', '13700003333', '华北', 'normal', '6222023456789012345'),
('西南软件开发', '钱经理', '13600004444', '西南', 'normal', '6222024567890123456'),
('东北重工集团', '孙总', '13500005555', '东北', 'basic', '6222025678901234567'),
('西北能源公司', '周主任', '13400006666', '西北', 'normal', '6222026789012345678');

-- ============================================================
-- 插入测试数据 - 销售订单
-- ============================================================
INSERT INTO sales_orders (order_no, customer_name, region, product_name, quantity, unit_price, total_amount, order_date, sales_emp_id, status) VALUES
('ORD202501001', '华东科技有限公司', '华东', '企业版数据库授权', 2, 12000.00, 24000.00, '2025-01-15', 1, 'completed'),
('ORD202501002', '华南贸易集团', '华南', '服务器主机X1', 5, 15000.00, 75000.00, '2025-01-20', 2, 'completed'),
('ORD202502003', '华北制造股份', '华北', '网络安全服务包', 3, 8000.00, 24000.00, '2025-02-05', 6, 'completed'),
('ORD202502004', '华东科技有限公司', '华东', '云存储空间1TB', 10, 2000.00, 20000.00, '2025-02-18', 1, 'completed'),
('ORD202503005', '西南软件开发', '西南', '技术支持年度包', 2, 6000.00, 12000.00, '2025-03-10', 2, 'completed'),
('ORD202503006', '东北重工集团', '东北', '交换机24口', 8, 3500.00, 28000.00, '2025-03-22', 8, 'completed'),
('ORD202504007', '华南贸易集团', '华南', '企业版数据库授权', 3, 12000.00, 36000.00, '2025-04-08', 2, 'completed'),
('ORD202504008', '西北能源公司', '西北', '服务器主机X1', 2, 15000.00, 30000.00, '2025-04-15', 6, 'completed'),
('ORD202505009', '华东科技有限公司', '华东', '网络安全服务包', 5, 8000.00, 40000.00, '2025-05-03', 1, 'completed'),
('ORD202505010', '华北制造股份', '华北', '技术支持年度包', 4, 6000.00, 24000.00, '2025-05-18', 6, 'completed'),
('ORD202506011', '西南软件开发', '西南', '云存储空间1TB', 20, 2000.00, 40000.00, '2025-06-05', 2, 'completed'),
('ORD202506012', '东北重工集团', '东北', '企业版数据库授权', 1, 12000.00, 12000.00, '2025-06-20', 8, 'pending'),
('ORD202506013', '华南贸易集团', '华南', '交换机24口', 10, 3500.00, 35000.00, '2025-06-25', 2, 'completed'),
('ORD202506014', '华东科技有限公司', '华东', '服务器主机X1', 3, 15000.00, 45000.00, '2025-06-28', 1, 'completed'),
('ORD202506015', '西北能源公司', '西北', '技术支持年度包', 2, 6000.00, 12000.00, '2025-06-30', 6, 'cancelled');

-- ============================================================
-- 创建只读账号（仅授予SELECT权限）
-- ============================================================
CREATE USER IF NOT EXISTS 'readonly_user'@'localhost' IDENTIFIED BY 'ReadOnly@2025';
CREATE USER IF NOT EXISTS 'readonly_user'@'127.0.0.1' IDENTIFIED BY 'ReadOnly@2025';
GRANT SELECT ON enterprise_data.* TO 'readonly_user'@'localhost';
GRANT SELECT ON enterprise_data.* TO 'readonly_user'@'127.0.0.1';
FLUSH PRIVILEGES;

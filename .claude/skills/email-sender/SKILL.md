---
name: email-sender
description: 通过 SMTP 发送邮件。支持纯文本、HTML 和附件邮件。当用户需要发送邮件、发送报告、发送通知时使用此 skill。用户需在 .env 文件中配置 SMTP 服务器信息。
---

# 邮件发送

通过 SMTP 协议发送邮件，支持纯文本、HTML 格式和附件。每次发送自动记录到数据库。

## 前置条件

无第三方依赖（全部使用 Python 标准库）。

## 目录结构

```
email-sender/
├── SKILL.md            ← 本文件
├── requirements.txt    ← 依赖声明（无第三方依赖）
├── meta/
│   └── email_send_log.json  ← Schema 定义
└── scripts/
    └── email_client.py      ← 邮件发送客户端
```

## 环境配置

在 `.env` 文件中配置:

```env
SMTP_HOST=smtp.qq.com        # SMTP 服务器地址 (必需)
SMTP_PORT=465                 # SMTP 端口 (默认: 465)
SMTP_USER=your_email@qq.com   # 发件人邮箱 (必需)
SMTP_PASSWORD=your_auth_code  # 授权码 (必需，非登录密码)
SMTP_FROM=your_email@qq.com   # 发件人地址 (可选，默认同 SMTP_USER)
```

### 常用 SMTP 配置

| 邮箱服务 | 服务器 | 端口 | 加密方式 |
|---------|--------|------|----------|
| QQ 邮箱 | smtp.qq.com | 465 | SSL |
| 163 邮箱 | smtp.163.com | 465 | SSL |
| Gmail | smtp.gmail.com | 587 | STARTTLS |
| Outlook | smtp.office365.com | 587 | STARTTLS |

## 快速使用

```bash
# 测试 SMTP 连接
python scripts/email_client.py test

# 发送纯文本邮件
python scripts/email_client.py send "recipient@example.com" "邮件主题" "邮件正文"

# 发送 HTML 邮件
python scripts/email_client.py send-html "recipient@example.com" "邮件主题" template.html

# 发送带附件的邮件
python scripts/email_client.py send-attach "recipient@example.com" "报告" "请查收附件" report.pdf data.xlsx
```

## Python API

```python
from email_client import EmailClient

client = EmailClient()

# 纯文本邮件
client.send_email("user@example.com", "正文内容", subject="主题")

# 带附件的邮件
client.send_email("user@example.com", "请查收", ["report.pdf"], subject="实验报告")
```

## 数据存储

每次邮件发送（成功或失败）自动记录到数据库，无需额外操作。

### Schema: `email_send_log`

| 字段 | 类型 | 说明 |
|------|------|------|
| to_email | text | 收件人邮箱 |
| subject | text | 邮件主题 |
| content_type | text | 内容类型 (plain/html) |
| has_attachments | boolean | 是否有附件 |
| attachment_names | json | 附件文件名列表 |
| smtp_server | text | SMTP 服务器 |
| sender | text | 发件人地址 |
| success | boolean | 是否发送成功 |
| error_message | text | 失败时的错误信息 |
| send_date | date | 发送时间 |

### 查询示例

```python
from scripts.db import DB
db = DB()

# 查询所有发送记录
db.query("SELECT * FROM data_email_send_log ORDER BY created_at DESC")

# 查询失败记录
db.query("SELECT * FROM data_email_send_log WHERE success = 0")

# 按收件人查询
db.query("SELECT * FROM data_email_send_log WHERE to_email = ?", ["user@example.com"])
```

## 注意事项

1. **授权码**: 使用邮箱的授权码而非登录密码（需在邮箱设置中开启 SMTP 服务并生成）
2. **发送限制**: 各邮箱服务商有日发送量限制，批量发送请注意频率
3. **附件大小**: 单封邮件附件总大小通常不超过 25MB
4. **日志静默**: 数据库记录失败不会影响邮件发送本身

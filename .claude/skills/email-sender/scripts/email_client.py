#!/usr/bin/env python3
"""
邮件发送客户端 - 通过 SMTP 发送邮件

用法:
    python email_client.py <command> [args...]

命令:
    send <to> <subject> <body>              - 发送纯文本邮件
    send-html <to> <subject> <html_file>    - 发送 HTML 邮件
    send-attach <to> <subject> <body> <files...>  - 发送带附件的邮件
    test                                     - 测试 SMTP 连接

环境变量 (.env):
    SMTP_HOST       - SMTP 服务器地址 (必需，如 smtp.qq.com)
    SMTP_PORT       - SMTP 端口 (默认: 465)
    SMTP_USER       - 发件人邮箱 (必需)
    SMTP_PASSWORD   - 授权码/密码 (必需)
    SMTP_FROM       - 发件人地址 (可选，默认同 SMTP_USER)

常用 SMTP 配置:
    QQ邮箱:        smtp.qq.com:465
    163邮箱:       smtp.163.com:465
    阿里企业邮箱:   smtp.qiye.aliyun.com:465
    Gmail:         smtp.gmail.com:587
"""

import os
import sys
import smtplib
import shutil
import logging
import json as _json
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Windows 控制台 UTF-8 输出支持
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


def load_env():
    """从 .env 文件加载环境变量"""
    env_paths = [
        Path.cwd() / '.env',
        Path.home() / '.env',
    ]

    for env_path in env_paths:
        if env_path.exists():
            with open(env_path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, _, value = line.partition('=')
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key and value:
                            os.environ.setdefault(key, value)
            break


load_env()

# 配置（兼容 SMTP_HOST 和 SMTP_SERVER）
SMTP_HOST = os.environ.get('SMTP_HOST', '') or os.environ.get('SMTP_SERVER', '')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '465'))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
SMTP_FROM = os.environ.get('SMTP_FROM', '') or SMTP_USER


class EmailClient:
    """邮件发送客户端"""

    def __init__(self):
        self.smtp_host = SMTP_HOST
        self.smtp_port = SMTP_PORT
        self.smtp_user = SMTP_USER
        self.smtp_password = SMTP_PASSWORD
        self.smtp_from = SMTP_FROM

    def send_email(
        self,
        to_email: str,
        content: str,
        attachments: list = None,
        subject: str = "邮件通知"
    ) -> bool:
        """
        发送邮件

        Args:
            to_email: 收件人邮箱
            content: 正文内容
            attachments: 附件列表（文件路径）
            subject: 邮件主题

        Returns:
            bool: 发送成功返回True
        """
        if attachments is None:
            attachments = []

        server = None
        try:
            logger.info(f"开始发送邮件到: {to_email}")
            logger.info(f"SMTP配置: host={self.smtp_host}, port={self.smtp_port}")

            # 1. 构建邮件
            msg = MIMEMultipart()
            msg['From'] = self.smtp_from
            msg['To'] = to_email
            msg['Subject'] = subject

            msg.attach(MIMEText(content, 'plain', 'utf-8'))
            logger.info("邮件正文添加成功")

            # 2. 添加附件
            for file_path in attachments:
                if Path(file_path).exists():
                    logger.info(f"添加附件: {file_path}")
                    with open(file_path, 'rb') as attachment_file:
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(attachment_file.read())
                        encoders.encode_base64(part)

                    filename = Path(file_path).name

                    # 使用 RFC 2231 标准编码文件名，支持中文和特殊字符
                    part.add_header(
                        'Content-Disposition',
                        'attachment',
                        filename=('utf-8', '', filename)
                    )

                    msg.attach(part)
                    logger.info(f"附件添加成功: {filename}")
                else:
                    logger.warning(f"附件不存在: {file_path}")

            # 3. 连接并发送邮件
            logger.info("连接SMTP服务器...")
            server = smtplib.SMTP_SSL(
                self.smtp_host,
                self.smtp_port,
                timeout=30
            )

            logger.info(f"登录SMTP服务器，用户名: {self.smtp_user}")
            server.login(self.smtp_user, self.smtp_password)

            logger.info("发送邮件...")
            server.send_message(msg)

            logger.info(f"邮件发送成功到: {to_email}")

            self._log_to_db(to_email, subject, "plain", attachments, True)
            return True

        except smtplib.SMTPAuthenticationError as e:
            error_msg = f"SMTP认证失败: {str(e)}"
            logger.error(error_msg)
            self._log_to_db(to_email, subject, "plain", attachments, False, error_msg)
            raise Exception(error_msg)

        except smtplib.SMTPConnectError as e:
            error_msg = f"SMTP连接失败: {str(e)}"
            logger.error(error_msg)
            self._log_to_db(to_email, subject, "plain", attachments, False, error_msg)
            raise Exception(error_msg)

        except smtplib.SMTPRecipientsRefused as e:
            error_msg = f"收件人被拒绝: {str(e)}"
            logger.error(error_msg)
            self._log_to_db(to_email, subject, "plain", attachments, False, error_msg)
            raise Exception(error_msg)

        except smtplib.SMTPSenderRefused as e:
            error_msg = f"发件人被拒绝: {str(e)}"
            logger.error(error_msg)
            self._log_to_db(to_email, subject, "plain", attachments, False, error_msg)
            raise Exception(error_msg)

        except smtplib.SMTPDataError as e:
            error_msg = f"SMTP数据错误: {str(e)}"
            logger.error(error_msg)
            self._log_to_db(to_email, subject, "plain", attachments, False, error_msg)
            raise Exception(error_msg)

        except smtplib.SMTPException as e:
            error_msg = f"SMTP错误: {str(e)}"
            logger.error(error_msg)
            self._log_to_db(to_email, subject, "plain", attachments, False, error_msg)
            raise Exception(error_msg)

        except Exception as e:
            error_msg = f"邮件发送失败: {type(e).__name__}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self._log_to_db(to_email, subject, "plain", attachments, False, error_msg)
            raise Exception(error_msg)

        finally:
            # 安全关闭连接，忽略关闭时的错误
            if server:
                try:
                    server.quit()
                except Exception as e:
                    logger.debug(f"关闭SMTP连接时出现警告（可忽略）: {e}")

    def _log_to_db(self, to_email: str, subject: str, content_type: str,
                   attachments: list, success: bool, error_message: str = None):
        """将发送记录写入 skita 数据库（静默失败，不影响邮件发送）"""
        try:
            # scripts/ → email-sender/ → skills/ → .claude/ → skita/
            root = Path(__file__).resolve().parent.parent.parent.parent.parent
            sys.path.insert(0, str(root))
            from scripts.db import DB

            # 安装 schema
            skill_meta = Path(__file__).resolve().parent.parent / "meta"
            project_meta = root / "meta"
            project_meta.mkdir(parents=True, exist_ok=True)
            schema_file = skill_meta / "email_send_log.json"
            shutil.copy2(str(schema_file), str(project_meta / schema_file.name))

            db = DB()
            db.ensure_table("email_send_log")

            attachment_names = [Path(f).name for f in (attachments or []) if Path(f).exists()]
            record = {
                "to_email": to_email,
                "subject": subject,
                "content_type": content_type,
                "has_attachments": 1 if attachment_names else 0,
                "attachment_names": _json.dumps(attachment_names, ensure_ascii=False) if attachment_names else None,
                "smtp_server": self.smtp_host,
                "sender": self.smtp_from,
                "success": 1 if success else 0,
                "error_message": error_message,
                "send_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            db.insert("data_email_send_log", record)
            logger.debug("邮件发送记录已存入数据库")
        except Exception as e:
            logger.debug(f"记录邮件日志到数据库失败（不影响邮件发送）: {e}")


def test_connection() -> dict:
    """测试 SMTP 连接"""
    server = None
    try:
        if not SMTP_HOST:
            raise ValueError("SMTP_HOST 未配置")
        if not SMTP_USER:
            raise ValueError("SMTP_USER 未配置")
        if not SMTP_PASSWORD:
            raise ValueError("SMTP_PASSWORD 未配置")

        logger.info(f"测试连接: {SMTP_HOST}:{SMTP_PORT}")
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30)
        server.login(SMTP_USER, SMTP_PASSWORD)

        return {
            "success": True,
            "message": f"SMTP 连接成功: {SMTP_HOST}:{SMTP_PORT}",
            "user": SMTP_USER
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"SMTP 连接失败: {str(e)}",
            "server": SMTP_HOST,
            "port": SMTP_PORT
        }
    finally:
        if server:
            try:
                server.quit()
            except:
                pass


def main():
    import json

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    client = EmailClient()

    try:
        if command == "test":
            result = test_connection()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if not result.get("success"):
                sys.exit(1)

        elif command == "send":
            if len(sys.argv) < 5:
                print("用法: email_client.py send <to> <subject> <body>")
                print('示例: email_client.py send "user@example.com" "测试主题" "邮件正文"')
                sys.exit(1)
            to = sys.argv[2]
            subject = sys.argv[3]
            body = sys.argv[4]
            success = client.send_email(to, body, [], subject)
            print(json.dumps({
                "success": success,
                "message": f"邮件已发送至 {to}"
            }, ensure_ascii=False, indent=2))

        elif command == "send-html":
            if len(sys.argv) < 5:
                print("用法: email_client.py send-html <to> <subject> <html_file>")
                print('示例: email_client.py send-html "user@example.com" "测试" template.html')
                sys.exit(1)
            to = sys.argv[2]
            subject = sys.argv[3]
            html_file = sys.argv[4]

            with open(html_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
            success = client.send_email(to, html_content, [], subject)
            print(json.dumps({
                "success": success,
                "message": f"邮件已发送至 {to}"
            }, ensure_ascii=False, indent=2))

        elif command == "send-attach":
            if len(sys.argv) < 6:
                print("用法: email_client.py send-attach <to> <subject> <body> <files...>")
                print('示例: email_client.py send-attach "user@example.com" "报告" "请查收附件" report.pdf')
                sys.exit(1)
            to = sys.argv[2]
            subject = sys.argv[3]
            body = sys.argv[4]
            attachments = sys.argv[5:]
            success = client.send_email(to, body, attachments, subject)
            print(json.dumps({
                "success": success,
                "message": f"邮件已发送至 {to}",
                "attachments": len(attachments)
            }, ensure_ascii=False, indent=2))

        else:
            print(f"未知命令: {command}")
            print(__doc__)
            sys.exit(1)

    except Exception as e:
        print(json.dumps({
            "success": False,
            "error": str(e)
        }, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()

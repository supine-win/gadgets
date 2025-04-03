import os
import subprocess
import signal
import sys

# 全局变量定义
ssh_key_path = None
cleanup_required = False


# 📌 处理 Ctrl+C 优雅退出
def graceful_exit(signum, frame):
    global cleanup_required, ssh_key_path
    print("\n🛑 检测到 Ctrl+C，正在清理并退出...")

    # 如果已创建 SSH Key 但未完成配置，则删除它
    if cleanup_required and ssh_key_path:
        if ssh_key_path is not None and isinstance(ssh_key_path, str) and ssh_key_path.strip() and os.path.exists(ssh_key_path):
            os.remove(ssh_key_path)
            print(f"🗑 已删除未完成的 SSH Key: {ssh_key_path}")
        if os.path.exists(f"{ssh_key_path}.pub"):
            os.remove(f"{ssh_key_path}.pub")
            print(f"🗑 已删除未完成的 SSH 公钥: {ssh_key_path}.pub")

    # 使用 os._exit 直接结束进程，不触发任何异常处理
    sys.exit(0)

# 绑定 `Ctrl+C` 处理函数
signal.signal(signal.SIGINT, graceful_exit)


# 主函数，包含所有代码逻辑
def main():
    global ssh_key_path, cleanup_required

    try:
        # 1️⃣ 用户输入服务器信息
        hostname = input("请输入自定义主机名 (A): ").strip()
        server_ip = input("请输入远程服务器IP地址: ").strip()
        ssh_port = input("请输入远程服务器端口号: ").strip()
        ssh_user = "root"

        ssh_dir = os.path.expanduser("~/.ssh")

        # 如果 ~/.ssh 目录不存在，则创建
        if not os.path.exists(ssh_dir):
            os.makedirs(ssh_dir, mode=0o700)
            print(f"📁 目录 {ssh_dir} 不存在，已自动创建！")
            os.chmod(ssh_dir, 0o700)

        # 生成 SSH Key 的路径（每台服务器单独存放）
        ssh_key_path = os.path.expanduser(f"~/.ssh/id_rsa_{hostname}")

        # 2️⃣ 选择 SSH 密钥方式
        print("\n🔑 请选择 SSH 密钥处理方式:")
        print("1) 本地生成（然后上传到服务器）")
        print("2) 服务器已有 SSH Key（手动粘贴）")
        print("3) 服务器未生成 SSH Key（自动创建并下载到本地）")
        choice = input("请输入选项（1/2/3）: ").strip()

        if choice == "1":
            # 🟢 **方式 1：本地生成密钥 -> 上传到服务器**
            if not os.path.exists(ssh_key_path):
                print("🔑 正在生成 SSH Key...")
                cleanup_required = True  # 记录 SSH Key 生成，防止中断导致脏数据
                subprocess.run(["ssh-keygen", "-t", "rsa", "-b", "4096", "-C", hostname, "-N", "", "-f", ssh_key_path])
            else:
                print("✅ SSH Key 已存在，跳过生成")

            print(f"🚀 正在上传公钥到 {server_ip}...")
            subprocess.run(["ssh-copy-id", "-p", ssh_port, "-i", f"{ssh_key_path}.pub", f"{ssh_user}@{server_ip}"], check=True)

        elif choice == "2":
            # 🟢 **方式 2：服务器已有密钥，手动粘贴**
            print("📋 请复制服务器上的 `id_rsa` 私钥并粘贴到此处（直接粘贴后按回车）:")
            private_key = []

            # 特殊处理输入循环中的中断
            try:
                while True:
                    line = input()
                    if line.strip() == "":
                        break
                    private_key.append(line)
            except KeyboardInterrupt:
                # 调用我们的优雅退出函数，而不是直接使用 sys.exit
                graceful_exit(signal.SIGINT, None)

            print(f"🔐 保存私钥到本地: {ssh_key_path}")
            with open(ssh_key_path, "w") as f:
                f.write("\n".join(private_key) + "\n")
            os.chmod(ssh_key_path, 0o600)

        elif choice == "3":
            # 🟢 **方式 3：服务器未生成，自动生成并下载**
            print("🛠 在服务器上生成 SSH Key...")
            subprocess.run([
                "ssh", f"{ssh_user}@{server_ip}", "-p", ssh_port,
                "ssh-keygen -t rsa -b 4096 -N '' -f ~/.ssh/id_rsa"
            ], check=True)

            print("📥 下载服务器的私钥到本地...")
            subprocess.run([
                "scp", "-P", ssh_port, f"{ssh_user}@{server_ip}:~/.ssh/id_rsa", ssh_key_path
            ], check=True)
            subprocess.run([
                "scp", "-P", ssh_port, f"{ssh_user}@{server_ip}:~/.ssh/id_rsa.pub", f"{ssh_key_path}.pub"
            ], check=True)

            print("🔐 设置本地私钥权限...")
            os.chmod(ssh_key_path, 0o600)

        else:
            print("❌ 无效选项，退出脚本！")
            return

        # 3️⃣ 配置 ~/.ssh/config
        ssh_config_path = os.path.expanduser("~/.ssh/config")
        ssh_config_entry = f"""
Host {hostname}
    HostName {server_ip}
    User {ssh_user}
    Port {ssh_port}
    IdentityFile {ssh_key_path}
    StrictHostKeyChecking no
"""

        print("🛠 更新 SSH 配置文件...")
        with open(ssh_config_path, "a") as config_file:
            config_file.write(ssh_config_entry)

        # 4️⃣ 设置正确的权限
        os.chmod(ssh_config_path, 0o600)

        # 5️⃣ 测试 SSH 免密登录
        print(f"🎉 配置完成！尝试使用 ssh {hostname} 进行免密登录测试...")
        subprocess.run(["ssh", hostname])

        # 完成所有步骤后，清理不再需要
        cleanup_required = False

    except KeyboardInterrupt:
        # 捕获任何可能遗漏的 KeyboardInterrupt
        graceful_exit(signal.SIGINT, None)
    except Exception as e:
        # 捕获其他可能的异常
        print(f"\n❌ 发生错误: {str(e)}")
        # 如果发生错误，也需要执行清理
        if cleanup_required and ssh_key_path:
            if os.path.exists(ssh_key_path):
                os.remove(ssh_key_path)
                print(f"🗑 已删除未完成的 SSH Key: {ssh_key_path}")
            if os.path.exists(f"{ssh_key_path}.pub"):
                os.remove(f"{ssh_key_path}.pub")
                print(f"🗑 已删除未完成的 SSH 公钥: {ssh_key_path}.pub")
        sys.exit(1)


# 调用主函数
if __name__ == "__main__":
    main()
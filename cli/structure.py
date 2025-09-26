import os
import subprocess
import sys


def create_lib_structure():
    # Create main folders
    folders = ["globals", "handlers", "services", "storedprocs", "utils", "models", "resources"]
    for folder in folders:
        os.makedirs(os.path.join("lib", folder), exist_ok=True)

        if folder == "resources":
            # Create resources folder with subfolders
            os.makedirs(os.path.join("lib", folder, "css"), exist_ok=True)
            os.makedirs(os.path.join("lib", folder, "js"), exist_ok=True)
            os.makedirs(os.path.join("lib", folder, "images"), exist_ok=True)
            print("✨ Created lib structure in ./lib")

    # Create navigation service file
    venv_path = sys.prefix + "/Lib/site-packages/framework1"
    base_html = open(f"{venv_path}/base.html", 'r').read()

    # Create base.html file
    base_html_path = os.path.join("lib", "handlers", "base.html")
    with open(base_html_path, 'w') as f:
        f.write(base_html)
        print(f"✨ Created base.html at {base_html_path}")

    def_styles = open(f"{venv_path}/styles.html", 'r').read()
    styles_html_path = os.path.join("lib", "handlers", "styles.html")
    with open(styles_html_path, 'w') as f:
        f.write(def_styles)
        print(f"✨ Created styles.html at {styles_html_path}")

    # Create .env file
    def_env_file = open(f"{venv_path}/.env", 'r').read()
    env_path = os.path.join(".env")
    with open(env_path, 'w') as f:
        f.write(def_env_file)
        print(f"✨ Created .env file at {env_path}")

    # copy users folder from framework1 to lib/handlers using shutil
    users_folder = os.path.join(venv_path, "users")
    lib_handlers_folder = os.path.join("lib", "handlers")
    if os.path.exists(users_folder):
        import shutil
        shutil.copytree(users_folder, os.path.join(lib_handlers_folder, "users"), dirs_exist_ok=True)
        print("✨ Copied users folder to lib/handlers/users")

    # check if ADAuth.py exists in the framework1 package
    adauth_path = os.path.join(venv_path, "ADAuth.py")
    if os.path.exists(adauth_path):
        shutil.copy(adauth_path, os.path.join("lib", "services", "ADAuth.py"))
        print("✨ Copied ADAuth.py to lib/services/ADAuth.py")
    else:
        print("❌ ADAuth.py not found in framework1 package")

    # check if desbus.py exists in the framework1 package
    desbus_path = os.path.join(venv_path, "ddd", "DESBus.py")
    if os.path.exists(desbus_path):
        shutil.copy(desbus_path, os.path.join("lib", "services", "DESBus.py"))
        print("✨ Copied DESBus.py to lib/services/DESBus.py")
    else:
        print("❌ DESBus.py not found in framework1 package")

    # check if DomainEventOutbox.py exists in the framework1 package
    domain_event_outbox_path = os.path.join(env_path, "DomainEventOutbox.py")
    if os.path.exists(domain_event_outbox_path):
        shutil.copy(domain_event_outbox_path, os.path.join("lib", "services", "DomainEventOutbox.py"))
        print("✨ Copied DomainEventOutbox.py to lib/services/DomainEventOutbox.py")
    else:
        print("❌ DomainEventOutbox.py not found in framework1 package")

    domain_event_bus_path = os.path.join(venv_path, "DomainEventBus.py")
    if os.path.exists(domain_event_bus_path):
        shutil.copy(domain_event_bus_path, os.path.join("lib", "services", "DomainEventBus.py"))
        print("✨ Copied DomainEventBus.py to lib/domain/DomainEventBus.py")
    else:
        print("❌ DomainEventBus.py not found in framework1 package")

    view_state_path = os.path.join(venv_path, "ViewState.py")
    if os.path.exists(view_state_path):
        shutil.copy(view_state_path, os.path.join("lib", "models", "ViewState.py"))
        print("✨ Copied ViewState.py to lib/models/ViewState.py")
    else:
        print("❌ ViewState.py not found in framework1 package")

    information_schema_path = os.path.join(venv_path, "dsl",  "InformationSchema.py")
    if os.path.exists(information_schema_path):
        shutil.copy(information_schema_path, os.path.join("lib", "models", "InformationSchema.py"))
        print("✨ Copied InformationSchema.py to lib/models/InformationSchema.py")
    else:
        print("❌ InformationSchema.py not found in framework1 package")


def create_symbolic_link(target: str):
    cwd = os.getcwd()
    link = os.path.join(cwd, "framework1")
    try:
        if os.name == 'nt':
            subprocess.run(["mklink", "/j", link, target], shell=True)
        else:
            os.symlink(target, link)
        print(f"✨ Created symbolic link: {link} -> {target}")
    except Exception as e:
        print(f"❌ Error creating symbolic link: {e}")

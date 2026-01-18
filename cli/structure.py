import os
import shutil
import subprocess
import sys


def create_lib_structure(overwrite: bool = False):
    # Create main folders
    folders = ["globals", "handlers", "services", "storedprocs", "utils", "models", "resources"]
    for folder in folders:
        os.makedirs(os.path.join("lib", folder), exist_ok=True)

        if folder == "resources":
            # Create resources folder with subfolders
            os.makedirs(os.path.join("lib", folder, "css"), exist_ok=True)
            os.makedirs(os.path.join("lib", folder, "js"), exist_ok=True)
            os.makedirs(os.path.join("lib", folder, "images"), exist_ok=True)
            print("[ok] Created lib structure in ./lib")

    # Create navigation service file
    venv_path = sys.prefix + "/Lib/site-packages/framework1"
    base_html = open(f"{venv_path}/base.html", 'r', encoding="utf-8").read()

    # Create base.html file
    base_html_path = os.path.join("lib", "handlers", "base.html")
    if not os.path.exists(base_html_path) or overwrite:
        with open(base_html_path, 'w', encoding="utf-8") as f:
            f.write(base_html)
            print(f"[ok] Created base.html at {base_html_path}")
    else:
        print(f"[skip] base.html already exists at {base_html_path}")

    def_styles = open(f"{venv_path}/styles.html", 'r', encoding="utf-8").read()
    styles_html_path = os.path.join("lib", "handlers", "styles.html")
    if not os.path.exists(styles_html_path) or overwrite:
        with open(styles_html_path, 'w', encoding="utf-8") as f:
            f.write(def_styles)
            print(f"[ok] Created styles.html at {styles_html_path}")
    else:
        print(f"[skip] styles.html already exists at {styles_html_path}")

    # Create .env file
    def_env_file = open(f"{venv_path}/.env", 'r', encoding="utf-8").read()
    env_path = os.path.join(".env")
    if not os.path.exists(env_path) or overwrite:
        with open(env_path, 'w', encoding="utf-8") as f:
            f.write(def_env_file)
            print(f"[ok] Created .env file at {env_path}")
    else:
        print(f"[skip] .env already exists at {env_path}")

    # copy users folder from framework1 to lib/handlers using shutil
    users_folder = os.path.join(venv_path, "users")
    lib_handlers_folder = os.path.join("lib", "handlers")
    users_target = os.path.join(lib_handlers_folder, "users")
    if os.path.exists(users_folder):
        if not os.path.exists(users_target) or overwrite:
            shutil.copytree(users_folder, users_target, dirs_exist_ok=True)
            print("[ok] Copied users folder to lib/handlers/users")
        else:
            print(f"[skip] {users_target} already exists.")

    # check if ADAuth.py exists in the framework1 package
    adauth_path = os.path.join(venv_path, "ADAuth.py")
    adauth_target = os.path.join("lib", "services", "ADAuth.py")
    if os.path.exists(adauth_path):
        if not os.path.exists(adauth_target) or overwrite:
            shutil.copy(adauth_path, adauth_target)
            print("[ok] Copied ADAuth.py to lib/services/ADAuth.py")
        else:
            print(f"[skip] {adauth_target} already exists.")
    else:
        print("[warn] ADAuth.py not found in framework1 package")

    # check if desbus.py exists in the framework1 package
    desbus_path = os.path.join(venv_path, "ddd", "DESBus.py")
    desbus_target = os.path.join("lib", "services", "DESBus.py")
    if os.path.exists(desbus_path):
        if not os.path.exists(desbus_target) or overwrite:
            shutil.copy(desbus_path, desbus_target)
            print("[ok] Copied DESBus.py to lib/services/DESBus.py")
        else:
            print(f"[skip] {desbus_target} already exists.")
    else:
        print("[warn] DESBus.py not found in framework1 package")

    # check if DomainEventOutbox.py exists in the framework1 package
    domain_event_outbox_path = os.path.join(venv_path, "DomainEventOutbox.py")
    outbox_target = os.path.join("lib", "services", "DomainEventOutbox.py")
    if os.path.exists(domain_event_outbox_path):
        if not os.path.exists(outbox_target) or overwrite:
            shutil.copy(domain_event_outbox_path, outbox_target)
            print("[ok] Copied DomainEventOutbox.py to lib/services/DomainEventOutbox.py")
        else:
            print(f"[skip] {outbox_target} already exists.")
    else:
        print("[warn] DomainEventOutbox.py not found in framework1 package")

    domain_event_bus_path = os.path.join(venv_path, "DomainEventBus.py")
    bus_target = os.path.join("lib", "services", "DomainEventBus.py")
    if os.path.exists(domain_event_bus_path):
        if not os.path.exists(bus_target) or overwrite:
            shutil.copy(domain_event_bus_path, bus_target)
            print("[ok] Copied DomainEventBus.py to lib/domain/DomainEventBus.py")
        else:
            print(f"[skip] {bus_target} already exists.")
    else:
        print("[warn] DomainEventBus.py not found in framework1 package")

    view_state_path = os.path.join(venv_path, "ViewState.py")
    view_state_target = os.path.join("lib", "models", "ViewState.py")
    if os.path.exists(view_state_path):
        if not os.path.exists(view_state_target) or overwrite:
            shutil.copy(view_state_path, view_state_target)
            print("[ok] Copied ViewState.py to lib/models/ViewState.py")
        else:
            print(f"[skip] {view_state_target} already exists.")
    else:
        print("[warn] ViewState.py not found in framework1 package")

    information_schema_path = os.path.join(venv_path, "dsl",  "InformationSchema.py")
    info_target = os.path.join("lib", "models", "InformationSchema.py")
    if os.path.exists(information_schema_path):
        if not os.path.exists(info_target) or overwrite:
            shutil.copy(information_schema_path, info_target)
            print("[ok] Copied InformationSchema.py to lib/models/InformationSchema.py")
        else:
            print(f"[skip] {info_target} already exists.")
    else:
        print("[warn] InformationSchema.py not found in framework1 package")


def create_symbolic_link(target: str):
    cwd = os.getcwd()
    link = os.path.join(cwd, "framework1")
    try:
        if os.name == 'nt':
            subprocess.run(["mklink", "/j", link, target], shell=True)
        else:
            os.symlink(target, link)
        print(f"[ok] Created symbolic link: {link} -> {target}")
    except Exception as e:
        print(f"[error] Error creating symbolic link: {e}")

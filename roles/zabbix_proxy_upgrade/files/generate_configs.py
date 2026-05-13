#!/usr/bin/env python3
import re, os, sys, json


def parse_zabbix_conf(filepath):
    params = {}
    with open(filepath) as f:
        for line in f:
            s = line.strip()
            if s and not s.startswith('#'):
                m = re.match(r'^([A-Za-z][A-Za-z0-9_]*)=(.*)$', s)
                if m:
                    params[m.group(1)] = m.group(2).strip()
    return params


def update_zabbix_conf(content, updates):
    """
    Read existing conf content line by line.
    Only replace lines for keys in `updates`.
    If a key is not found (was commented out), append it at the end.
    All other lines are kept exactly as-is.
    """
    lines = content.splitlines(keepends=True)
    result = []
    replaced_keys = set()

    for line in lines:
        stripped = line.strip()

        if stripped.startswith('#') or not stripped:
            result.append(line)
            continue

        replaced = False
        for key, new_value in updates.items():
            if re.match(r'^' + re.escape(key) + r'=', stripped):
                result.append(f"{key}={new_value}\n")
                replaced_keys.add(key)
                replaced = True
                break

        if not replaced:
            result.append(line)

    # Append any keys that were not found (e.g. were commented out)
    for key, value in updates.items():
        if key not in replaced_keys:
            result.append(f"{key}={value}\n")

    return ''.join(result)


def update_postgresql_conf(content, updates):
    """
    Same approach for postgresql.conf.
    Format: key = value  (spaces around =, values may be quoted)
    """
    lines = content.splitlines(keepends=True)
    result = []
    replaced_keys = set()

    for line in lines:
        stripped = line.strip()

        if stripped.startswith('#') or not stripped:
            result.append(line)
            continue

        replaced = False
        for key, new_value in updates.items():
            if re.match(r'^' + re.escape(key) + r'\s*=', stripped):
                result.append(f"{key} = {new_value}\n")
                replaced_keys.add(key)
                replaced = True
                break

        if not replaced:
            result.append(line)

    for key, value in updates.items():
        if key not in replaced_keys:
            result.append(f"{key} = {value}\n")

    return ''.join(result)


def write_file(path, content, mode=0o640):
    with open(path, 'w') as f:
        f.write(content)
    os.chmod(path, mode)


def main():
    if len(sys.argv) < 4:
        print(json.dumps({"error": "Usage: generate_configs.py <proxy_backup> <agent2_backup> <pg_backup>"}))
        sys.exit(1)

    proxy_backup  = sys.argv[1]   # /etc/zabbix/zabbix_proxy.conf.backup
    agent2_backup = sys.argv[2]   # /etc/zabbix/zabbix_agent2.conf.backup
    pg_backup     = sys.argv[3]   # /tmp/postgresql_old.conf.backup

    db_password  = os.environ.get('ZABBIX_DB_PASSWORD', '')
    server_ips   = os.environ.get('ZABBIX_SERVER_IPS', '')
    pg_version   = os.environ.get('POSTGRES_VERSION', '16')
    pg_data_dir  = os.environ.get('POSTGRES_DATA_DIR', '/postgres/data')

    if not db_password:
        print(json.dumps({"error": "ZABBIX_DB_PASSWORD not set"}))
        sys.exit(1)

    if not server_ips:
        print(json.dumps({"error": "ZABBIX_SERVER_IPS not set"}))
        sys.exit(1)

    # --- zabbix_proxy.conf ---
    # Read full backup, update only: Server, DBPassword
    # Hostname stays as-is from backup (not touched)
    try:
        with open(proxy_backup) as f:
            proxy_content = f.read()
    except FileNotFoundError:
        print(json.dumps({"error": f"Proxy backup not found: {proxy_backup}"}))
        sys.exit(1)

    new_proxy_conf = update_zabbix_conf(proxy_content, {
        'Server':     server_ips,
        'DBPassword': db_password,
    })
    write_file('/etc/zabbix/zabbix_proxy.conf', new_proxy_conf)

    # --- zabbix_agent2.conf ---
    # Read full backup, update only: Server, ServerActive
    # Hostname stays as-is from backup
    try:
        with open(agent2_backup) as f:
            agent2_content = f.read()
    except FileNotFoundError:
        print(json.dumps({"error": f"Agent2 backup not found: {agent2_backup}"}))
        sys.exit(1)

    agent2_server_passive = server_ips.replace(';', ',')

    new_agent2_conf = update_zabbix_conf(agent2_content, {
        'Server':       agent2_server_passive,
        'ServerActive': server_ips,
    })
    write_file('/etc/zabbix/zabbix_agent2.conf', new_agent2_conf)

    # --- postgresql.conf ---
    # Read full backup, update only: data_directory
    # All other tuning params stay as-is
    try:
        with open(pg_backup) as f:
            pg_content = f.read()
    except FileNotFoundError:
        pg_content = ''

    new_pg_conf = update_postgresql_conf(pg_content, {
        'data_directory': f"'{pg_data_dir}'",
    })
    write_file(
        f'/etc/postgresql/{pg_version}/main/postgresql.conf',
        new_pg_conf,
        mode=0o644
    )

    # Parse proxy backup for reporting
    old_proxy = parse_zabbix_conf(proxy_backup)

    print(json.dumps({
        "hostname":         old_proxy.get('Hostname', 'unknown'),
        "server":           server_ips,
        "vmware_cache":     old_proxy.get('VMwareCacheSize', 'unchanged'),
        "cache_size":       old_proxy.get('CacheSize', 'unchanged'),
        "start_pollers":    old_proxy.get('StartPollers', 'unchanged'),
    }))


if __name__ == '__main__':
    main()

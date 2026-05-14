#!/usr/bin/env python3
import re, os, sys, json

# Parameters removed or renamed in PostgreSQL 15/16
# These will be commented out in the new conf
PG_REMOVED_PARAMS = {
    'stats_temp_directory',
    'vacuum_defer_cleanup_age',
    'promote_trigger_file',
    'recovery_target_inclusive',
    'wal_receiver_status_interval',
}


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

    for key, value in updates.items():
        if key not in replaced_keys:
            result.append(f"{key}={value}\n")

    return ''.join(result)


def update_postgresql_conf(content, updates, old_version, new_version):
    lines = content.splitlines(keepends=True)
    result = []
    replaced_keys = set()

    for line in lines:
        stripped = line.strip()

        if stripped.startswith('#') or not stripped:
            result.append(line)
            continue

        # Remove deprecated/removed parameters
        param_match = re.match(r'^([a-z_]+)\s*=', stripped)
        if param_match and param_match.group(1) in PG_REMOVED_PARAMS:
            result.append('# [removed_in_pg{}] {}'.format(new_version, line))
            continue

        # Update version-specific references in values:
        # /etc/postgresql/14/ -> /etc/postgresql/16/
        # /var/run/postgresql/14- -> /var/run/postgresql/16-
        # '14/main' -> '16/main'
        updated_line = line
        if str(old_version) in updated_line:
            updated_line = re.sub(
                r'(/etc/postgresql/)' + re.escape(str(old_version)) + r'/',
                r'\g<1>' + str(new_version) + '/',
                updated_line
            )
            updated_line = re.sub(
                r'(/var/run/postgresql/)' + re.escape(str(old_version)) + r'-',
                r'\g<1>' + str(new_version) + '-',
                updated_line
            )
            updated_line = updated_line.replace(
                f"'{old_version}/main'",
                f"'{new_version}/main'"
            )

        replaced = False
        for key, new_value in updates.items():
            if re.match(r'^' + re.escape(key) + r'\s*=', stripped):
                result.append(f"{key} = {new_value}\n")
                replaced_keys.add(key)
                replaced = True
                break

        if not replaced:
            result.append(updated_line)

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

    proxy_backup  = sys.argv[1]
    agent2_backup = sys.argv[2]
    pg_backup     = sys.argv[3]

    db_password   = os.environ.get('ZABBIX_DB_PASSWORD', '')
    server_ips    = os.environ.get('ZABBIX_SERVER_IPS', '')
    pg_version    = os.environ.get('POSTGRES_VERSION', '16')
    pg_data_dir   = os.environ.get('POSTGRES_DATA_DIR', '')
    pg_old_ver    = os.environ.get('POSTGRES_OLD_VERSION', '14')

    if not db_password:
        print(json.dumps({"error": "ZABBIX_DB_PASSWORD not set"}))
        sys.exit(1)
    if not server_ips:
        print(json.dumps({"error": "ZABBIX_SERVER_IPS not set"}))
        sys.exit(1)

    # zabbix_proxy.conf — update Server and DBPassword only
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

    # zabbix_agent2.conf — update Server and ServerActive only
    try:
        with open(agent2_backup) as f:
            agent2_content = f.read()
    except FileNotFoundError:
        print(json.dumps({"error": f"Agent2 backup not found: {agent2_backup}"}))
        sys.exit(1)

    new_agent2_conf = update_zabbix_conf(agent2_content, {
        'Server':       server_ips.replace(';', ','),
        'ServerActive': server_ips,
    })
    write_file('/etc/zabbix/zabbix_agent2.conf', new_agent2_conf)

    # postgresql.conf
    # Base: old pg14 backup (has all Debian-specific settings: socket dir,
    # hba_file, ident_file, listen_addresses, etc.)
    # Changes: remove deprecated params, update /14/ paths to /16/, update data_directory
    try:
        with open(pg_backup) as f:
            pg_content = f.read()

        pg_updates = {}
        if pg_data_dir:
            pg_updates['data_directory'] = f"'{pg_data_dir}'"

        new_pg_conf = update_postgresql_conf(
            pg_content,
            pg_updates,
            old_version=pg_old_ver,
            new_version=pg_version
        )
        write_file(
            f'/etc/postgresql/{pg_version}/main/postgresql.conf',
            new_pg_conf,
            mode=0o644
        )
    except FileNotFoundError:
        pass  # No pg backup found, leave pg_createcluster's default conf


    old_proxy = parse_zabbix_conf(proxy_backup)

    print(json.dumps({
        "hostname":      old_proxy.get('Hostname', 'unknown'),
        "server":        server_ips,
        "vmware_cache":  old_proxy.get('VMwareCacheSize', 'unchanged'),
        "cache_size":    old_proxy.get('CacheSize', 'unchanged'),
        "start_pollers": old_proxy.get('StartPollers', 'unchanged'),
        "pg_data_dir":   pg_data_dir,
    }))


if __name__ == '__main__':
    main()

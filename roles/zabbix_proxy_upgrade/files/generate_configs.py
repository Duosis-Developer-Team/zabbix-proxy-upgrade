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

        # Check if this param was removed in the new PG version
        param_match = re.match(r'^([a-z_]+)\s*=', stripped)
        if param_match and param_match.group(1) in PG_REMOVED_PARAMS:
            result.append('# removed_in_pg{}: {}'.format(new_version, line))
            continue

        # Update path references: /postgresql/14/ -> /postgresql/16/
        updated_line = line.replace(
            f'/postgresql/{old_version}/',
            f'/postgresql/{new_version}/'
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
    # pg16 default conf kullanılır (pg_createcluster tarafından oluşturulmuş)
    # Sadece data_directory custom path ise güncellenir.
    # Eski conf'dan bellek ayarları taşınmaz — OOM riskini önlemek için.
    pg_conf_path = f'/etc/postgresql/{pg_version}/main/postgresql.conf'

    if pg_data_dir and f'/postgresql/{pg_version}/' not in pg_data_dir:
        try:
            with open(pg_conf_path) as f:
                pg_content = f.read()
            new_pg_conf = update_postgresql_conf(
                pg_content,
                {'data_directory': f"'{pg_data_dir}'"},
                old_version=pg_old_ver,
                new_version=pg_version
            )
            write_file(pg_conf_path, new_pg_conf, mode=0o644)
        except FileNotFoundError:
            pass  # pg16 conf not yet created, pg_createcluster will handle it

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

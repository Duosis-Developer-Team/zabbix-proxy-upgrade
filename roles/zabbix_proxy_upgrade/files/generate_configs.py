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


def parse_postgresql_conf(filepath):
    params = {}
    try:
        with open(filepath) as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith('#'):
                    continue
                m = re.match(r'^([a-z_]+)\s*=\s*([^#\n]+)', s)
                if m:
                    params[m.group(1).strip()] = m.group(2).strip().strip("'\"")
    except FileNotFoundError:
        pass
    return params


def get(params, key, default=''):
    return params.get(key, default)


def generate_proxy_conf(old, db_password, server_ips):
    server = get(old, 'Server', server_ips)
    proxy_config_freq = (
        old.get('ProxyConfigFrequency') or
        old.get('ConfigFrequency', '300')
    )
    return "\n".join([
        f"Server={server}",
        f"Hostname={old['Hostname']}",
        f"LogFile=/var/log/zabbix/zabbix_proxy.log",
        f"LogFileSize={get(old, 'LogFileSize', '0')}",
        f"PidFile=/run/zabbix/zabbix_proxy.pid",
        f"SocketDir=/run/zabbix",
        "",
        f"DBName=zabbix_proxy",
        f"DBUser=zabbix",
        f"DBPassword={db_password}",
        f"AllowUnsupportedDBVersions=0",
        "",
        f"ProxyBufferMode={get(old, 'ProxyBufferMode', 'hybrid')}",
        f"ProxyMemoryBufferSize={get(old, 'ProxyMemoryBufferSize', '1G')}",
        f"ProxyConfigFrequency={proxy_config_freq}",
        "",
        f"StartPollers={get(old, 'StartPollers', '200')}",
        f"StartAgentPollers={get(old, 'StartAgentPollers', '50')}",
        f"StartHTTPAgentPollers={get(old, 'StartHTTPAgentPollers', '100')}",
        f"StartSNMPPollers={get(old, 'StartSNMPPollers', '100')}",
        f"StartIPMIPollers={get(old, 'StartIPMIPollers', '10')}",
        f"StartPreprocessors={get(old, 'StartPreprocessors', '150')}",
        f"StartPollersUnreachable={get(old, 'StartPollersUnreachable', '120')}",
        f"StartTrappers={get(old, 'StartTrappers', '50')}",
        f"StartPingers={get(old, 'StartPingers', '100')}",
        f"StartDiscoverers={get(old, 'StartDiscoverers', '50')}",
        f"StartHTTPPollers={get(old, 'StartHTTPPollers', '150')}",
        "",
        f"StartVMwareCollectors={get(old, 'StartVMwareCollectors', '50')}",
        f"VMwareCacheSize={get(old, 'VMwareCacheSize', '2G')}",
        f"VMwareTimeout={get(old, 'VMwareTimeout', '15')}",
        "",
        f"SNMPTrapperFile={get(old, 'SNMPTrapperFile', '/var/log/snmptrap/snmptrap.log')}",
        f"StartSNMPTrapper={get(old, 'StartSNMPTrapper', '1')}",
        "",
        f"CacheSize={get(old, 'CacheSize', '4G')}",
        f"StartDBSyncers={get(old, 'StartDBSyncers', '8')}",
        f"HistoryCacheSize={get(old, 'HistoryCacheSize', '2G')}",
        f"HistoryIndexCacheSize={get(old, 'HistoryIndexCacheSize', '2G')}",
        "",
        f"Timeout={get(old, 'Timeout', '25')}",
        f"LogSlowQueries={get(old, 'LogSlowQueries', '3000')}",
        "",
        f"FpingLocation=/usr/bin/fping",
        f"Fping6Location=/usr/bin/fping6",
        "",
        f"StatsAllowedIP={get(old, 'StatsAllowedIP', '127.0.0.1')}",
        "",
        f"Include=/etc/zabbix/zabbix_proxy.d/*.conf",
        "",
    ]) + "\n"


def generate_agent2_conf(old, server_ips):
    server = get(old, 'Server', server_ips)
    return "\n".join([
        f"PidFile=/run/zabbix/zabbix_agent2.pid",
        f"LogFile=/var/log/zabbix/zabbix_agent2.log",
        f"LogFileSize=0",
        "",
        f"Server={server.replace(';', ',')}",
        f"ServerActive={server}",
        f"Hostname={old['Hostname']}",
        "",
        f"PluginSocket=/run/zabbix/agent.plugin.sock",
        f"ControlSocket=/run/zabbix/agent.sock",
        "",
        f"Include=/etc/zabbix/zabbix_agent2.d/plugins.d/*.conf",
        f"Include=/etc/zabbix/zabbix_agent2.d/*.conf",
        "",
    ]) + "\n"


def generate_postgresql_conf(old_pg, data_dir):
    def pgv(key, default):
        return old_pg.get(key, default)

    return "\n".join([
        f"data_directory = '{data_dir}'",
        f"listen_addresses = '{pgv('listen_addresses', 'localhost')}'",
        f"port = {pgv('port', '5432')}",
        f"max_connections = {pgv('max_connections', '100')}",
        "",
        f"shared_buffers = {pgv('shared_buffers', '512MB')}",
        f"work_mem = {pgv('work_mem', '16MB')}",
        f"maintenance_work_mem = {pgv('maintenance_work_mem', '128MB')}",
        "",
        f"wal_buffers = {pgv('wal_buffers', '64MB')}",
        f"checkpoint_completion_target = {pgv('checkpoint_completion_target', '0.9')}",
        f"min_wal_size = {pgv('min_wal_size', '1GB')}",
        f"max_wal_size = {pgv('max_wal_size', '4GB')}",
        "",
        f"random_page_cost = {pgv('random_page_cost', '1.1')}",
        f"effective_io_concurrency = {pgv('effective_io_concurrency', '200')}",
        f"default_statistics_target = {pgv('default_statistics_target', '100')}",
        "",
        f"max_worker_processes = {pgv('max_worker_processes', '8')}",
        f"max_parallel_workers_per_gather = {pgv('max_parallel_workers_per_gather', '4')}",
        f"max_parallel_workers = {pgv('max_parallel_workers', '8')}",
        f"max_parallel_maintenance_workers = {pgv('max_parallel_maintenance_workers', '4')}",
        "",
        f"logging_collector = {pgv('logging_collector', 'on')}",
        f"log_directory = 'log'",
        f"log_filename = 'postgresql-%Y-%m-%d.log'",
        f"log_rotation_age = {pgv('log_rotation_age', '1d')}",
        f"log_min_duration_statement = {pgv('log_min_duration_statement', '3000')}",
        f"log_line_prefix = '%m [%p] %q%u@%d '",
        "",
    ]) + "\n"


def write_file(path, content, mode=0o640):
    with open(path, 'w') as f:
        f.write(content)
    os.chmod(path, mode)


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: generate_configs.py <zabbix_backup> <pg_backup>"}))
        sys.exit(1)

    zabbix_backup = sys.argv[1]
    pg_backup     = sys.argv[2]
    db_password   = os.environ.get('ZABBIX_DB_PASSWORD', '')
    server_ips    = os.environ.get('ZABBIX_SERVER_IPS', '')
    pg_version    = os.environ.get('POSTGRES_VERSION', '16')
    pg_data_dir   = os.environ.get('POSTGRES_DATA_DIR', '/postgres/data')

    if not db_password:
        print(json.dumps({"error": "ZABBIX_DB_PASSWORD not set"}))
        sys.exit(1)

    if not server_ips:
        print(json.dumps({"error": "ZABBIX_SERVER_IPS not set"}))
        sys.exit(1)

    try:
        old_zabbix = parse_zabbix_conf(zabbix_backup)
    except FileNotFoundError:
        print(json.dumps({"error": f"Zabbix backup not found: {zabbix_backup}"}))
        sys.exit(1)

    if 'Hostname' not in old_zabbix:
        print(json.dumps({"error": "Hostname not found in zabbix backup"}))
        sys.exit(1)

    old_pg = parse_postgresql_conf(pg_backup)

    proxy_conf  = generate_proxy_conf(old_zabbix, db_password, server_ips)
    agent2_conf = generate_agent2_conf(old_zabbix, server_ips)
    pg_conf     = generate_postgresql_conf(old_pg, pg_data_dir)

    write_file('/etc/zabbix/zabbix_proxy.conf',  proxy_conf)
    write_file('/etc/zabbix/zabbix_agent2.conf', agent2_conf)
    write_file(f'/etc/postgresql/{pg_version}/main/postgresql.conf', pg_conf, mode=0o644)

    print(json.dumps({
        "hostname":               old_zabbix['Hostname'],
        "server":                 get(old_zabbix, 'Server', server_ips),
        "proxy_config_frequency": old_zabbix.get('ProxyConfigFrequency') or old_zabbix.get('ConfigFrequency', '300'),
        "vmware_cache_size":      get(old_zabbix, 'VMwareCacheSize', '2G'),
        "cache_size":             get(old_zabbix, 'CacheSize', '4G'),
        "start_pollers":          get(old_zabbix, 'StartPollers', '200'),
        "pg_shared_buffers":      old_pg.get('shared_buffers', 'default'),
        "pg_max_connections":     old_pg.get('max_connections', 'default'),
    }))


if __name__ == '__main__':
    main()

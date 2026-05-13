# Zabbix Proxy 6.4 → 7.0 Otomatik Yükseltme (AWX Ansible)

## Repo Yapısı

```
zabbix-proxy-upgrade/
├── upgrade_proxy.yml                              ← Ana playbook
├── requirements.yml                               ← Ansible collections
├── inventory/
│   └── hosts.yml                                  ← Proxy listesi (DOLDURUN)
├── group_vars/
│   └── zabbix_proxies.yml                        ← Ortak değişkenler
└── roles/
    └── zabbix_proxy_upgrade/
        ├── tasks/main.yml                         ← 12 aşamalı upgrade
        ├── handlers/main.yml                      ← Servis restart
        ├── templates/
        │   ├── zabbix_proxy.conf.j2               ← Proxy conf template
        │   └── zabbix_agent2.conf.j2              ← Agent2 conf template
        └── files/
            └── postgresql.conf                    ← PgSQL conf (DEĞİŞTİRİN)
```

---

## 1. Kurulum Adımları

### 1.1 GitHub Repo Oluştur

1. GitHub'da `zabbix-proxy-upgrade` adında **private** repo oluşturun
2. Bu dizindeki tüm dosyaları push edin:

```bash
git init
git add .
git commit -m "Initial: Zabbix proxy 7.0 upgrade playbook"
git remote add origin https://github.com/KULLANICI/zabbix-proxy-upgrade.git
git push -u origin main
```

### 1.2 `inventory/hosts.yml` Dosyasını Doldurun

Her proxy için aşağıdaki formatta ekleyin:

```yaml
proxy:
  ansible_host: 10.x.x.x
```

### 1.3 `files/postgresql.conf` Dosyasını Değiştirin

Eğer tüm proxy'lerde kullandığınız bir `postgresql.conf` varsa,
`roles/zabbix_proxy_upgrade/files/postgresql.conf` dosyasının yerine kopyalayın.

---

## 2. AWX Yapılandırması

### 2.1 AWX Project Oluştur

| Alan | Değer |
|------|-------|
| Name | Zabbix Proxy Upgrade |
| Source Control Type | Git |
| Source Control URL | `https://github.com/KULLANICI/zabbix-proxy-upgrade.git` |
| Source Control Branch | `main` |
| Credential | GitHub Personal Access Token |

> **Options** altında `Update Revision on Launch` işaretleyin.

### 2.2 AWX Inventory Oluştur

1. **Inventories** → **Add** → **Inventory**
2. Name: `Zabbix Proxies`
3. Kaydettikten sonra: **Sources** → **Add**
4. Source: `Sourced from a Project`
5. Project: `Zabbix Proxy Upgrade`
6. Inventory File: `inventory/hosts.yml`
7. **Update on Launch** işaretleyin

### 2.3 AWX Credential Oluştur

**SSH Credential** (proxy'lere bağlanmak için):

| Alan | Değer |
|------|-------|
| Name | Zabbix Proxy SSH |
| Credential Type | Machine |
| Username | ubuntu (veya kullandığınız user) |
| SSH Private Key | Proxy'lere erişen key |
| Privilege Escalation Method | sudo |

### 2.4 AWX Job Template Oluştur

| Alan | Değer |
|------|-------|
| Name | Zabbix Proxy 7.0 Upgrade |
| Job Type | Run |
| Inventory | Zabbix Proxies |
| Project | Zabbix Proxy Upgrade |
| Playbook | `upgrade_proxy.yml` |
| Credentials | Zabbix Proxy SSH |
| Extra Variables | (aşağıya bakın) |

**Extra Variables** (DB şifresi buradan gelir):

```yaml
zabbix_db_password: "123456"
```

> ⚠️ AWX'te Extra Variables şifreli saklanır. `Prompt on launch` seçeneğiyle her çalıştırmada sorabilir veya sabit bırakabilirsiniz.

---

## 3. Playbook Çalışma Mantığı

| Aşama | İşlem |
|-------|-------|
| 1 | Eski `zabbix_proxy.conf`'u yedekler (`.backup`) |
| 2 | Python3 ile eski conf'u parse eder → tüm `KEY=VALUE` çiftleri okunur |
| 3 | PostgreSQL 16 kurar, Zabbix 7.0 repo ekler, paketleri yükseltir |
| 4 | PostgreSQL 14'ü kaldırır (purge) |
| 5 | `/postgres/data` dizinini oluşturur, PG16 cluster yaratır |
| 6 | `postgresql.conf` deploy eder, PG16'yı başlatır |
| 7 | `zabbix` DB kullanıcısı ve `zabbix_proxy` DB oluşturur (idempotent) |
| 8 | SQL schema yükler — **sadece ilk seferde** (tablo kontrolü yapılır) |
| 9 | Yeni `zabbix_proxy.conf` ve `agent2.conf` deploy eder (eski değerlerle) |
| 10 | Servisleri enable eder |
| 11 | Servisleri restart eder |
| 12 | Tüm servislerin `active` olduğunu doğrular, versiyon yazdırır |

### Hostname Taşıma

Eski conf'daki `Hostname=test` değeri
Python3 parser tarafından otomatik okunur ve yeni conf'a **aynı değerle** yazılır.
**Manuel müdahale gerekmez.**

### Özel Parametreler (Otomatik Taşınanlar)

Eski conf'daki şu parametreler otomatik taşınır:

`StartPollers`, `StartAgentPollers`, `StartHTTPAgentPollers`, `StartSNMPPollers`,
`StartIPMIPollers`, `StartPreprocessors`, `StartPollersUnreachable`, `StartTrappers`,
`StartPingers`, `StartDiscoverers`, `StartHTTPPollers`, `StartVMwareCollectors`,
`VMwareCacheSize`, `VMwareTimeout`, `CacheSize`, `StartDBSyncers`,
`HistoryCacheSize`, `HistoryIndexCacheSize`, `Timeout`, `LogSlowQueries`,
`ProxyBufferMode`, `ProxyMemoryBufferSize`, `ProxyConfigFrequency`

---

## 4. Tek Proxy Test Çalıştırması

Tüm proxy'leri çalıştırmadan önce tek proxy ile test edin:

AWX'te Job Template'de **Limit** alanına proxy adını girin:
```
test-dc-proxy2
```

---

## 5. Requirements (AWX Collections)

AWX, `requirements.yml` dosyasını Project sync sırasında otomatik yükler.
Gerekli koleksiyonlar: `community.postgresql`, `community.general`

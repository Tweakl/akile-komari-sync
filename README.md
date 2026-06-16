# AkileCloud 到 Komari 账单同步

把 AkileCloud 服务器的账单信息同步到 Komari 节点，按“机器名/节点名”匹配。

仓库里不保存任何 API Key、Secret、密码或服务器信息。安装脚本会在安装时让你输入这些信息，并只写到 VPS 本地的 `/opt/akile-komari-sync/.env`，权限为 `600`。

## 一键安装

在 Komari 面板所在 VPS 上执行：

```bash
curl -fsSL https://raw.githubusercontent.com/Tweakl/akile-komari-sync/main/install.sh -o /tmp/akile-komari-sync-install.sh && sudo bash /tmp/akile-komari-sync-install.sh
```

脚本会先显示：

```text
1.安装
2.卸载
```

选择 `1` 后，按顺序输入：

1. Komari 地址，例如 `https://example.com`
2. Komari API Key
3. Akile Client ID
4. Akile Client Secret
5. 货币，默认人民币 `¥`
6. 同步间隔，默认 `1h`

## 一键卸载

再次执行安装命令，选择 `2.卸载` 即可。

卸载会删除：

- `/opt/akile-komari-sync`
- `/etc/systemd/system/akile-komari-sync.service`
- `/etc/systemd/system/akile-komari-sync.timer`

不会修改 Komari 本体。

## 同步内容

- Akile `due_time` -> Komari `expired_at`
- Akile `auto_renew` -> Komari `auto_renewal`
- Akile `price` -> Komari `price`
- Akile `price = 0` -> Komari `price = -1`，也就是免费
- 默认货币为人民币 `¥`
- Akile `flow` GB -> Komari `traffic_limit` 字节
- Komari `traffic_limit_type` 固定为 `sum`，也就是总和
- Akile 到期时间按北京时间墙上时间写入，避免日期早一天

计费周期换算：

| Akile 周期 | Komari 数值 |
| --- | --- |
| 1 个月 | 30 |
| 3 个月 | 92 |
| 12 个月 | 365 |
| 24 个月 | 730 |

## 手动执行

立即同步一次：

```bash
systemctl start akile-komari-sync.service
```

查看定时器：

```bash
systemctl list-timers akile-komari-sync.timer --no-pager
```

查看日志：

```bash
journalctl -u akile-komari-sync.service -n 50 --no-pager
```

## 名字匹配规则

Akile 机器名和 Komari 节点名需要一致。脚本会忽略首尾空格和大小写差异，但不会做模糊匹配。

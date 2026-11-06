# 海信 E7N Pro：控制方法与 Home Assistant 集成

## 结论：E7N Pro 用哪条路

E7N Pro 是 **VIDAA** 智能电视（国内与爱家 App 配套）。结合 `com.hisense.ms.fly2tv` 的按键字面量和 VIDAA 机内协议，**给 Home Assistant 用的正确通道是电视自己的 MQTT，不是爱家云。**

| 通道 | 何时出现 | 是否适合 HA |
|---|---|---|
| **机内 MQTT `:36669`（TLS）** | 电视开机或网络待机 | **首选。** 局域网、可推送状态、按键与爱家相同 |
| 爱家云 `pushRemoter` / `devices/execute` | 手机 App 远程 | 要账号 token，不适合本地集成 |
| HiConnect UDP `229.x.x.x` + TCP/AES | 爱家同网发现/家电控制 | 家电通用栈，电视遥控仍落到 MQTT/`KEY_*` |
| 红外 `TRANSMIT_IR` | 手机有红外 | HA 不走这条 |
| Wake-on-LAN | 深度关机后开机 | 作为 MQTT 的补充 |

爱家 APK 里的 `sendKeyByMqtt`、`tryPushLocalRemoter`、`{"key":"KEY_POWER"}` 与 VIDAA topic

```text
/remoteapp/tv/remote_service/<client_id>/actions/sendkey
payload: KEY_POWER
```

是同一套键值。E7N Pro（以及同代 E7N / E7NQ Pro）固件在 2024 之后通常还要：

1. **动态 MQTT 用户名/密码**（由客户端 UUID + 时间戳算出，旧账号 `hisenseservice` / `multimqttservice` 会 rc=5）
2. **屏幕 4 位 PIN 配对**（一次）
3. TLS 上的客户端证书（很多机器只检查「有证书」；严格固件才要官方 VIDAA/爱家证书）

`<client_id>` 必须是动态算法生成的那个，不能写死 `HomeAssistant`，否则按键会被静默丢掉。

## 集成做什么

`custom_components/hisense_e7n`：

- `media_player`：开关、音量、静音、输入源、播放/暂停；深度待机用 WoL 开机
- `remote`：发送 `KEY_*`（可用 Universal Remote Card）
- 配置流：IP → 连接 → PIN
- `iot_class: local_push`，不经过海信云

## 安装

1. 把整个 `custom_components/hisense_e7n` 拷到 Home Assistant 的 `config/custom_components/`。
2. 重启 Home Assistant。
3. **设置 → 设备与服务 → 添加集成 → Hisense E7N Pro**。
4. 电视保持开机，填 IP；建议填 MAC 以便唤醒。
5. 电视弹出 PIN 就输入；没弹窗则 PIN 留空提交。

HACS：把本仓库加为自定义仓库（类别 Integration）。

## 电视侧准备

- 设置里打开手机遥控 / 网络控制 / 爱家控制
- 给电视做 **DHCP 地址预留**
- 有线网口的 Wake-on-LAN 一般比 Wi-Fi 稳
- Home Assistant 与电视同一二层网络，放行 **TCP 36669** 和 **UDP 9**（WoL）

## 服务

```yaml
service: hisense_e7n.send_key
target:
  entity_id: remote.hisense_e7n_pro_remote
data:
  key: KEY_HOME
```

```yaml
service: hisense_e7n.launch_app
target:
  entity_id: media_player.hisense_e7n_pro
data:
  name: Netflix
  url: netflix
```

爱家里出现过的键：`KEY_POWER`、`KEY_VOLUMEUP`、`KEY_VOLUMEDOWN`、`KEY_MUTE`、`KEY_UP`/`DOWN`/`LEFT`/`RIGHT`、`KEY_OK`、`KEY_RETURNS`、`KEY_HOME`、`KEY_MENU`、`KEY_MULTITASK`、`KEY_CONTROL_CENTER`、`KEY_BRIGHTUP`/`KEY_BRIGHTDOWN`、`KEY_JUBAO`。别名如 `home`、`ok`、`mute` 也可以。

## MQTT rc=5 时

1. 确认电视已开机，时间/时区正确（动态密码含时间戳）。
2. 认证模式保持 `auto`。
3. 运行 `python3 scripts/extract_vidaa_certs.py`，若成功解出证书，在配置流里填 PEM 路径。
4. 仍失败时，从官方 VIDAA / RemoteNOW 客户端放入 `CN=VidaaAppAndroidV01` 的证书对。不要把私钥提交到 git。

## 和爱家云的关系

手机不在家时，爱家走 `https://mobile-aiot.hismarttv.com/mobilemsg/push/v5.3/remoter`。那条路依赖登录态，本集成故意不实现。HA 应放在家里，直连 `:36669`。

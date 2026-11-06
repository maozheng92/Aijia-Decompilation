# 海信 E7N Pro：控制方法与 Home Assistant 集成

## 结论：E7N Pro 用哪条路

E7N Pro 是 **VIDAA** 智能电视（国内与爱家 App 配套）。结合 `com.hisense.ms.fly2tv` 的按键字面量和 VIDAA 机内协议，**给 Home Assistant 用的正确通道是电视自己的 MQTT，不是爱家云。**

| 通道 | 何时出现 | 是否适合 HA |
|---|---|---|
| **机内 MQTT `:36669`（TLS）** | 电视开机或网络待机 | **首选。** 局域网、可推送状态、按键与爱家相同 |
| 爱家云 `pushRemoter` / `devices/execute` | 手机 App 远程 | 要账号 token，不适合本地集成 |
| HiConnect UDP `229.x.x.x` + TCP/AES | 爱家同网发现/家电控制 | 家电通用栈，电视遥控仍落到 MQTT/`KEY_*` |
| 红外 `TRANSMIT_IR` | 手机有红外 | 不走手机红外；HA 侧用红外宝/插座的 **button** 开机 |
| Wake-on-LAN | 部分机型网络待机 | 仅当未配置开机按钮时的可选回退 |

爱家 APK 里的 `sendKeyByMqtt`、`tryPushLocalRemoter`、`{"key":"KEY_POWER"}` 与 VIDAA topic

```text
/remoteapp/tv/remote_service/<client_id>/actions/sendkey
payload: KEY_POWER
```

是同一套键值。E7N Pro（以及同代 E7N / E7NQ Pro）固件在 2024 之后通常还要：

1. **动态 MQTT 用户名/密码**（由客户端 UUID + 时间戳算出，旧账号 `hisenseservice` / `multimqttservice` 会 rc=5）
2. **爱家手机配对不需要 PIN**，MQTT 连通即可
3. TLS 上的客户端证书（很多机器只检查「有证书」；严格固件才要官方 VIDAA/爱家证书）

`<client_id>` 必须是动态算法生成的那个，不能写死 `HomeAssistant`，否则按键会被静默丢掉。

## 集成做什么

`custom_components/hisense_e7n`：

- `media_player`：开关、音量、静音、输入源、播放/暂停；**关机后开机调用配置的 button 设备**（`button.press` / `switch.turn_on` / `script.turn_on`），不指望爱家 `KEY_POWER`
- `remote`：发送 `KEY_*`（可用 Universal Remote Card）；关机状态下的电源键同样走 button
- 配置流：IP → 连接（无 PIN）；可选绑定开机按钮
- `iot_class: local_push`，不经过海信云

## 安装

1. 把整个 `custom_components/hisense_e7n` 拷到 Home Assistant 的 `config/custom_components/`。
2. 重启 Home Assistant。
3. **设置 → 设备与服务 → 添加集成 → Hisense E7N Pro**。
4. 电视保持开机，填 IP。**开机按钮**选一个能物理打开电视的实体（红外开机键、智能插座、辅助按钮、脚本）。爱家 App 无法开机，集成不会再靠 MQTT `KEY_POWER` 唤醒关机的电视。
5. 爱家配对不需要 PIN，MQTT 连上后直接完成添加。
6. 已添加的集成可在选项里补选或更换开机按钮。

HACS：把本仓库加为自定义仓库（类别 Integration）。

## 电视侧准备

- 设置里打开手机遥控 / 网络控制 / 爱家控制
- 给电视做 **DHCP 地址预留**
- 准备一个真正能开机的 HA 实体（红外发射器的电源 button、切断待机供电的智能插座、或封装红外的 script）
- Home Assistant 与电视同一二层网络，放行 **TCP 36669**
- 关机仍走 MQTT `KEY_POWER`（此时机内 broker 还在）；完全断电后只能按开机按钮

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

## 添加集成时报「无法连接 36669」

集成会先探测 TCP，再按顺序试：**爱家客户端证书 + TLS（旧加密套件）→ 自签 VIDAA 证书 → 无客户端证书 → 明文 MQTT**。请先更新本仓库后再重新添加。

仍失败时对照报错：

| 提示 | 含义 | 处理 |
|---|---|---|
| 连不上 MQTT 端口 | IP/防火墙/电视未开 | 电视进桌面（不要待机），填电视自己的局域网 IP，HA 与电视同一二层网，打开「手机遥控/网络控制」 |
| 已通端口但没完成 MQTT | 开机未完成 | 等 30 秒后再添加 |
| TLS 握手失败 | 旧 Mosquitto / 缺证书 | 把 `com.hisense.ms.fly2tv.apk` 放到 HA 的 `config/` 目录（集成会解开 `res/6D.p12`），或运行下面的脚本 |
| rc=5 认证被拒 | 用户名密码不对 | 认证模式 `auto`，电视时间/时区正确 |

解证书（私钥不要提交 git）：

```bash
python3 scripts/extract_vidaa_certs.py
```

把生成的 `client.pem` / `client.key` 拷到 Home Assistant 的 `config/hisense_e7n/setup/`，或在添加集成时填写路径。

## 开机为什么不用爱家

电视完全关机后，`:36669` MQTT 不在线，爱家发 `KEY_POWER` 没有落地通道。本集成的 `media_player.turn_on` / 遥控器电源键在 `available=false` 时：

1. 调用你配置的开机实体：`button.press`、`input_button.press`、`switch.turn_on` 或 `script.turn_on`
2. 等待电视起来后再连 MQTT
3. 仅当未配置该实体且填了 MAC 时，才回退 Wake-on-LAN

示例：用红外宝的电源键

```yaml
# 集成选项里选择
power_on_button: button.living_room_ir_tv_power
```

或包一层脚本再绑到集成：

```yaml
script:
  hisense_e7n_power_on:
    sequence:
      - service: remote.send_command
        target:
          entity_id: remote.broadlink
        data:
          command: tv_power
```

## 和爱家云的关系

手机不在家时，爱家走 `https://mobile-aiot.hismarttv.com/mobilemsg/push/v5.3/remoter`。那条路依赖登录态，本集成故意不实现。HA 应放在家里，直连 `:36669`。

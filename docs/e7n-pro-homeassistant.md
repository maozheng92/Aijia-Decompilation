# 海信 E7N Pro：控制方法与 Home Assistant 集成

## 结论：E7N Pro 用哪条路

E7N Pro 是 **VIDAA** 智能电视（国内与爱家 App 配套）。爱家**添加电视会提示打开蓝牙**（`flutter_blue_plus` + Hisense GATT `3a69180b-…-00805f587e61`）。MQTT `:36669` 可以连上但按键无反应，是因为爱家配对/发键走 BLE，不是 VIDAA sendkey。

| 通道 | 何时出现 | 是否适合 HA |
|---|---|---|
| **电视 BLE HID / Hisense GATT** | 爱家配对提示「打开蓝牙」 | **按键主路径。** HA 主机也要开蓝牙，并填写电视蓝牙地址 |
| 机内 MQTT `:36669`（TLS） | 电视开机或网络待机 | 状态/截屏/AI 识图；按键仅作 BLE 失败时的回退 |
| 爱家云 `pushRemoter` / `devices/execute` | 手机 App 远程 | 要账号 token，不适合本地集成 |
| HiConnect UDP `229.x.x.x` + TCP/AES | 爱家同网发现/家电控制 | 家电通用栈，本集成不走 |
| 红外 `TRANSMIT_IR` | 手机有红外 | 不走手机红外；HA 侧用红外宝/插座的 **button** 开机 |
| Wake-on-LAN | 部分机型网络待机 | 仅当未配置开机按钮时的可选回退 |

爱家 APK 里的 `sendKeyByMqtt`、`tryPushLocalRemoter`、`{"key":"KEY_POWER"}` 与 VIDAA topic

```text
/remoteapp/tv/remote_service/<identity>/actions/sendkey
payload: KEY_POWER          （VIDAA 原文；JSON {"key":"KEY_POWER"} 是爱家云格式）
```

`<identity>` **不等于** MQTT CONNECT 的 `client_id`。电视实际监听的是：

- `{电视MAC}$vidaa_common`（社区 RemoteNOW / 较新 VIDAA）
- `{电视MAC}$normal`（爱家 / newAM）
- 以及当前会话的 `client_id`

MQTT 能连上但所有按键无反应，几乎都是发到了 `hisense_ha_…` 或随机 UUID，电视把报文丢掉。配置里请填写电视 MAC；集成会向上述身份各发一遍（原文 `KEY_*` 和爱家 JSON）。

E7N Pro（以及同代 E7N / E7NQ Pro）固件在 2024 之后通常还要：

1. **动态 MQTT 用户名/密码**（由客户端 UUID + 时间戳算出，旧账号 `hisenseservice` / `multimqttservice` 会 rc=5）
2. **爱家手机配对不需要 PIN，但要打开蓝牙**
3. TLS 上的客户端证书（很多机器只检查「有证书」；严格固件才要官方 VIDAA/爱家证书）

## 集成做什么

`custom_components/hisense_e7n`：

- `media_player`：开关、音量、静音、输入源、播放/暂停；**关机后开机调用配置的 button 设备**（`button.press` / `switch.turn_on` / `script.turn_on`），不指望爱家 `KEY_POWER`
- `remote`：发送 `KEY_*`（可用 Universal Remote Card）；关机状态下的电源键同样走开机按钮
- `button`：爱家「电视」遥控页同款按键（电源、音量、截屏、信号源、AI识图、设置、方向键、OK、返回、首页、菜单）。「切换遥控模式」和底部语音是手机 App 能力，不映射成电视键
- 配置流：IP + **电视蓝牙地址**（无 PIN）；BLE 配对成功即可添加，MQTT 失败也可以
- `iot_class: local_push`，不经过海信云

## 安装

1. 把整个 `custom_components/hisense_e7n` 拷到 Home Assistant 的 `config/custom_components/`。
2. 重启 Home Assistant。
3. **设置 → 设备与服务 → 添加集成 → Hisense E7N Pro**。
4. 电视保持开机。**打开 Home Assistant 主机蓝牙**（和爱家添加电视时的提示一样），填写 **电视蓝牙地址**（设置 → 关于本机 / 蓝牙 MAC，可与 Wi‑Fi MAC 不同）。再填 IP。扫描到海信 BLE 广播时会自动带出地址。
5. **开机按钮**选一个能物理打开电视的实体（红外开机键、智能插座、辅助按钮、脚本）。爱家 App 无法开机。
6. 爱家配对不需要 PIN。BLE 连上即可添加；MQTT 36669 连不上也可以，按键仍走蓝牙。
7. 已添加的集成可在选项里补填蓝牙地址或更换开机按钮。

HACS：把本仓库加为自定义仓库（类别 Integration）。

## 电视侧准备

- **Home Assistant 主机打开蓝牙**（内置适配器、USB 蓝牙棒，或 HAOS 的 Bluetooth 集成）。Docker 需 `--net=host` 并映射 `/dev/bus/usb` 或 `/var/run/dbus`
- 电视保持开机，按爱家添加设备那样允许被发现
- 设置里打开手机遥控 / 网络控制 / 爱家控制
- 给电视做 **DHCP 地址预留**
- 准备一个真正能开机的 HA 实体（红外发射器的电源 button、切断待机供电的智能插座、或封装红外的 script）
- 同一二层网络；MQTT 状态需要时放行 **TCP 36669**
- 关机按键走 BLE `KEY_POWER`；完全断电后只能按开机按钮

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

爱家遥控页对应关系：

| 爱家按钮 | HA 实体 / 命令 |
|---|---|
| 电源 | `button.…_power` → `KEY_POWER`（电视离线时改按你配置的开机按钮） |
| 音量 − / 静音 / 音量 + | `KEY_VOLUMEDOWN` / `KEY_MUTE` / `KEY_VOLUMEUP` |
| 截屏 | `button.…_screenshot` → 爱家 `captureTvScreen` / `getTvScreenInfo` |
| 信号源 | `button.…_source` → 刷新 `sourcelist` + `KEY_SOURCE` |
| AI识图 | `button.…_smart_image` → 爱家 `pushSmartImage` |
| 设置 | `KEY_CONTROL_CENTER` |
| 方向键 / OK | `KEY_UP` `KEY_DOWN` `KEY_LEFT` `KEY_RIGHT` `KEY_OK` |
| 返回 / 首页 / 菜单 | `KEY_RETURNS` / `KEY_HOME` / `KEY_MENU` |

其它爱家字面量：`KEY_MULTITASK`、`KEY_BRIGHTUP` / `KEY_BRIGHTDOWN`、`KEY_JUBAO`。别名如 `home`、`ok`、`mute` 也可以。

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

手机不在家时，爱家走 `https://mobile-aiot.hismarttv.com/mobilemsg/push/v5.3/remoter`。那条路依赖登录态，本集成故意不实现。HA 应放在家里，用主机蓝牙发键，MQTT 只读状态。

## 按键仍无反应

1. Home Assistant 所在机器是否真的有蓝牙（HAOS：设置 → 蓝牙；Core/Docker：适配器进容器）。爱家添加电视同样会卡在「请打开蓝牙」。
2. 填的是 **蓝牙 MAC**，不是一定等于 Wi‑Fi MAC。集成选项里可改。
3. 电视需在旁边、已开机、可被手机搜到。
4. 截屏 / AI 识图仍走 MQTT，需要 36669。方向键、音量、电源、首页走 BLE。

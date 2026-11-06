# 海信爱家 APK：电视控制方法分析

分析对象：`com.hisense.ms.fly2tv.apk`（海信爱家 **7.0.8.12**，`versionCode` 70008012）。

本文只记录从包内符号、字符串、JNI 导出和清单中还原出的控制路径，不附带可复现攻击脚本，也不展开完整反编译源码。

## 1. 包结构为什么不好直接 jadx

| 层 | 位置 | 说明 |
|---|---|---|
| Flutter 业务（电视遥控主体） | `lib/arm64-v8a/libapp.so`（约 26MB AOT） | Dart 已编译进 so，没有 `kernel_blob.bin`。类名/方法名/URL 仍以字符串形式保留。 |
| 局域网协议栈 | `libhiconnect.so` + `libhiconnect_jni.so` | 海信 EasyLink / AsLAN 协议，JNI 类 `com.hismart.easylink.localjni.HiConnect`。 |
| 电视投屏/通话 | `libhicloud_webrtc_native.so`、`libliteavsdk.so` | 镜像投屏、音视频。 |
| DLNA 发现 | `libmbldlna.so` | 局域网发现/绑定电视。 |
| Java 宿主 | `classes.dex` 仅 34KB + Baidu 加固 `assets/baiduprotect*.jar` | 入口是 `com.sagittarius.v6.StubApplication`，业务 DEX 加密，jadx 拿不到 Java 业务源码。 |
| 红外 | Manifest `TRANSMIT_IR` + `IRControllerActivity` | 手机红外发射，不是局域网协议。 |

主界面是 Flutter：`FlutterUIActivity` / FlutterBoost。电视遥控 UI 在 Dart 包 `jhk_control`、`jhk_tv_control`、`jhk_biz_control`。

## 2. 控制电视的几条路（按实际调用优先级）

应用对同一台已绑定电视会同时走「云」和「局域网」，在线优先云，同网优先本地。

```
用户按遥控键
    │
    ├─ 1) pushRemoter / sendKeyByMqtt
    │      └─ HTTPS 推键：mobile-aiot.hismarttv.com/mobilemsg/push/v5.3/remoter
    │      └─ MQTT 推键：先 getMqttConfig，再 connectTVByMqtt
    │
    ├─ 2) powerOffTv / controlDevice(actionList)
    │      └─ IoT 云执行：iot-aihome.hismarttv.com/4.0/iot/devices/execute
    │
    ├─ 3) tryPushLocalRemoter / JhkLocalTvAgent
    │      └─ 先 getTvIp（缓存/设备列表），再 ping，再走本地 HiConnect.control
    │
    ├─ 4) 语音：sendVoiceToTV
    │
    ├─ 5) 媒体投送：/mobilemsg/push/v5.2/vod + getCastParameter
    │
    └─ 6) 移动电视云台：/4.0/iot/tv/ptz/...
```

绑定前还有 DLNA / 扫码 / NFC 把电视加入家庭。

## 3. 云端遥控（最直接的「按键」）

### 3.1 按键推送

- Flutter：`pushRemoter`、`_pushRemoter`、`tryPushLocalRemoter`、`sendKeyByMqtt`
- 手势板日志：`TvRemoterGesturePad: trigger key`
- HTTP：

```
https://mobile-aiot.hismarttv.com/mobilemsg/push/v5.3/remoter
```

包内按键字面量（遥控 JSON 形态为 `{"key":"KEY_POWER"}`）：

| key | 含义 |
|---|---|
| `KEY_POWER` | 开关机 |
| `KEY_VOLUMEUP` / `KEY_VOLUMEDOWN` | 音量 |
| `KEY_MUTE` | 静音 |
| `KEY_UP` / `KEY_DOWN` / `KEY_LEFT` / `KEY_RIGHT` | 方向 |
| `KEY_OK` | 确认 |
| `KEY_RETURNS` | 返回 |
| `KEY_HOME` | 主页 |
| `KEY_MENU` | 菜单 |
| `KEY_MULTITASK` | 多任务 |
| `KEY_CONTROL_CENTER` | 控制中心 |
| `KEY_BRIGHTUP` / `KEY_BRIGHTDOWN` | 亮度 |
| `KEY_JUBAO` | 聚宝（爱家快捷） |

对应 UI：

- 常规遥控：`control_page_tv.dart` / `control_page_tv_buttons.dart`
- 鼠标板：`control_tv_mouse_pad.dart`（`TvRemoterMousePad`）
- 手势板：`control_tv_gesture_pad.dart`（`TvRemoterGesturePad`）
- 模式切换：`jhk_tv_remoter_mode_page.dart`（`JhkTvRemoterMode`）

H5 备用遥控页：

- `https://public-wxtv.hismarttv.com/weixintv/web/remote-ctrl.html?from=tv_control&deviceId=`
- `https://public-wxtv.hismarttv.com/weixintv/web/virtual-remote-ctrl.html`

### 3.2 电源 / 功能码（IoT execute）

关机走独立方法 `powerOffTv`（本地响应日志：`powerOffTv local tv powerOff response`；云端：`account tv powerOff requestPayload`）。

通用设备控制：

```
POST https://iot-aihome.hismarttv.com/4.0/iot/devices/execute
```

载荷由 `JhkTvControlRequestPayload` 组装，字段包括 `deviceId`、`actionList`、`functionCode`、`cmdValue`。  
入口：`controlDevice`（也暴露给 WebView：`MethodChannelJhkWebview controlDevice`）。

相关 Dart：

- `package:jhk_biz_control/domain/api/tv_control_agent.dart` → `TVControlAgent`
- `package:jhk_biz_control/domain/model/tv/tv_control_helper.dart` → `TvControlHelper`
- `package:jhk_biz_device/src/agent/params/tv_control_params.dart`
- `package:jhk_biz_device/src/agent/dto/tv_control_dto.dart`

其它电视云接口：

| 路径 | 用途 |
|---|---|
| `/4.0/iot/tv/activation/query` | 电视激活状态 |
| `/4.0/iot/tv/ptz/default_position_conf` | 移动电视云台预设 |
| `/4.0/iot/databoard/tv/energy_meter` | 电视能耗 |
| `/4.0/iot/state/refreshDeviceState` | 刷新在线/开关机 |
| `/mobiletv/device/deviceInfo` | 电视设备信息 |
| `/mobiletv/device/getOnlineStatus` | 在线状态 |
| `/vodapptv/device/5.8/ability` | 电视能力集 |

### 3.3 MQTT（云通道保活 + 推键）

1. `getMqttConfig` → `https://mqtt-msg.hismarttv.com/2.0/mqtt/config`
2. `JhkMqttClient.initMqttConfig` 解析 broker URI
3. `connectTVByMqtt` / `_startConnectTvByMqtt`（日志分 1/2/3 步）
4. 回调：`onTVMqttConnectSuccess` / `onTVMqttConnectFailed` / `onTVMqttDisConnect`
5. 推键：`sendKeyByMqtt`

实现：`package:mqtt/client/jhk_mqtt_client.dart`、`jhk_mqtt_plugin.dart`。  
Android 侧还有 Eclipse Paho `MqttService`。

能力查询：`getTvMqttConnectStatus`、`getTvAbility`、`getTvLocalAbility`、`getTvNetAbility`。

## 4. 局域网控制（同 Wi-Fi）

### 4.1 发现电视

- DLNA：`JhkDLNADiscovery`、`startDiscoverDlnaTv`、`JhkDlnaAssistant`（`libmbldlna.so`）
- 本地列表：`JhkControlLocalTvDiscover`、`_localTvDiscover`、`JhkLocalTv`
- 需要组播：`CHANGE_WIFI_MULTICAST_STATE`

绑定流程在 `jhk_add_device`：扫码登录、DLNA、NFC（`vnd.android.nfc` / `hisense.com/touch`）。

### 4.2 解析电视 IP 再发本地命令

`JhkTvControl.getTvIp` / `getTvListIp` 从已绑定设备列表取 IP，`ohos_ping.Ping tvIp` 探活，再：

- `TVControlAgent.getTvInfo` / `getTvScreenInfo`
- `tryPushLocalRemoter`（同网按键）
- `powerOffTv` 在 `online = false` 时仍可尝试本地关机

本地代理：`package:jhk_biz_device/src/agent/local_tv_agent.dart`（`JhkLocalTvAgent`）。

### 4.3 HiConnect / EasyLink 协议栈

源码路径（so 里残留）：`.../lanControlSo/.../AsLANProtocolStackMulti/`。

JNI 入口 `com.hismart.easylink.localjni.HiConnect`：

| JNI | 内部 C | 作用 |
|---|---|---|
| `start` | `HIconnect_start` | 启动协议栈、UDP 发现、TCP 服务 |
| `research` | `HIadvertise_research` | 重新广播发现 |
| `getDevInfo` / `firstGetDevInfo` | `HIcmdCtrl_getDevInfo` | 读设备信息 |
| **`control`** | **`HIcmdCtrl_devControl`** | **局域网设备控制（含电视）** |
| **`specialControl`** | **`HIcmdCtrl_devSpecialCtl`** | **特殊控制** |
| `subscribe` | `HIcmdCtrl_subscribe` | 订阅状态 |
| `getData` | `HIcmdCtrl_devGetData` | 读设备数据 |
| `devBind` / `bindGW` | `HIcmdCtrl_devBind` / `bindGWDev` | 绑定设备/网关 |
| `update` / `updateHost` | `HIcmdCtrl_update*` | 更新主机 |
| `smartConfig` / `smartStop` | SoftAP / SmartConfig 配网 |
| `reset` / `finish` | 复位 / 停止 |

命令类型（v1/v2 两套打包：`HIcmd_package_v1` / `HIcmd_package_v2`）：

- 控制：`CMD_DEV_CTRL` / `CMD_CTRL_DEV` / `CMD_DEV_SPEC_CTRL`
- 发现广播：`CMD_BCWIFIMSG`、`CMD_BCPHONEMSG`（UDP）
- 状态：`CMD_DEV_STATE`、`CMD_DEV_DATA`、`CMD_RESULT`
- 绑定：`CMD_DEV_BIND`、`CMD_GW_BIND`

传输特征：

- 发现：UDP advertise，组播网段 **`229.x.x.x`**（`config ... 229.%d.%d.%d %d`）
- 控制：TCP（`HItcpconn_send` / `HIsocket_tcp_send`），字段 `ConnPort` / `hostPort` / `remotePort` / `phoneUdpPort`
- 报文：JSON + **AES**（`API_aes_decrypt`、`hs_aes_ecb`）+ MD5
- 设备标识：`ip`、`did`、`devId`、`wifiId`、`ticket`、`DevType`

这是家电通用局域网栈，电视和空调等共用 `HiConnect.control`；电视按键在 Flutter 层先编成 `KEY_*` / `functionCode`，再交给 native。

## 5. 语音、投屏、红外、移动电视

| 能力 | 入口 | 通道 |
|---|---|---|
| 语音控电视 | `sendVoiceToTV`、`tv_control_pop.dart` | `https://mobile-aiot.hismarttv.com/weixintv/vod/sendVoiceToTV`；另有 `/mobilemsg/push/v5.2/voiceSearch` |
| 推片 / 投播 | `PushMediaToTvEvent`、`getCastParameter` | `/mobilemsg/push/v5.2/vod`；`https://api-launcher-mobi.hismarttv.com/detailApi/v2.0/getCastParameter` |
| 手机镜像（Fly2TV） | `com.ju.aiot.lib.hisdk.mirror.*`、`MirrorService` | WebRTC + 无障碍投屏 |
| 红外遥控 | `IRControllerActivity` | `TRANSMIT_IR`，打传统红外码，不走 IP |
| 移动电视（云台） | `JhkTVMoveControlHelper`、`tv_move_command_queue.dart` | `/4.0/iot/tv/ptz/default_position_conf` + 与普通遥控相同的 MQTT/本地通道 |
| 预约任务 | `tv_task_*_dto` | `/mobiletv/task/5.6/{add,del,query}` |

## 6. Flutter ↔ 原生桥

电视相关 MethodChannel：

- `jhk_tv_control` / `MethodChannelJhkTvControl`
- `jhk_tv_capacities`
- `jhk_mqtt_plugin`
- `jhk_biz_device_plugin`
- `jhk_webview`（H5 调 `controlDevice`）

平台接口：`jhk_tv_control_platform_interface.dart`。  
观察者：`JhkTVControlObserver`（MQTT 连接、能力更新 `onHiDeviceSupportAbilityUpdate`）。

关键运行时方法（从 AOT 字符串还原）：

```
connectTVByMqtt / startConnectTv
sendKeyByMqtt / pushRemoter / tryPushLocalRemoter
powerOffTv
getTvIp / getTvListIp / getTvInfo / getTvScreenInfo
getTvAbility / getTvLocalAbility / getTvNetAbility
getTvMqttConnectStatus / getTvDeviceStatus
controlDevice(actionList)
sendVoiceToTV / pushTextToTv
startDiscoverDlnaTv
```

## 7. E7N Pro 该用哪一层

E7N Pro 是 VIDAA 机。Home Assistant 应直连电视 **MQTT `:36669`**（`sendkey` 的 `KEY_*` 与本文第 3 节完全一致），用动态凭证 + PIN 配对。实现见 `custom_components/hisense_e7n` 与 [e7n-pro-homeassistant.md](e7n-pro-homeassistant.md)。

**开机例外：** 爱家无法唤醒已完全关机的电视（机内 MQTT 不在线，`KEY_POWER` 发不出去）。HA 集成在电视离线时改为调用用户配置的 **button 设备**（红外电源键、智能插座、脚本），而不是走爱家。

爱家云 `pushRemoter`、HiConnect 都不是 HA 的主路径：云要账号，HiConnect 是家电发现栈。红外只作为关机后的开机手段，接到 HA 的 button/switch/script 上。

## 8. 想对接自己电视时该看哪一层

1. **已登录爱家账号、电视已绑定**：云通道即可。按键走 `/mobilemsg/push/v5.3/remoter`，开关机/场景走 `/4.0/iot/devices/execute`，MQTT 配置走 `/2.0/mqtt/config`。请求需要账号 token 和 `deviceId`。
2. **手机和电视同一局域网**：先 DLNA/HiConnect 发现，拿到 `ip`+`wifiId`+`ticket`，再调 `HiConnect.control` / `specialControl`。报文 AES，不能只靠明文 HTTP。
3. **只要传统遥控**：看红外 Activity，与 IP 协议无关。
4. **投屏**：走 Ju AIoT mirror / LiteAV / WebRTC，不是遥控键值。

## 9. 分析边界

- Java 业务被百度加固，无法得到 `HiConnect.java` 的完整封装代码。
- Dart 是 AOT，只能还原符号和字符串，不能还原完整函数体。
- 云接口有签名（`jhk_signature.dart`）和登录态，未绑定设备不能直接控别人的电视。
- `libhs_protocol_clientjni_64k.so` 是混淆壳（Obfuscator-LLVM），不是电视遥控主路径。

# 海信爱家 APK 分析

仓库内 APK：`com.hisense.ms.fly2tv.apk`（海信爱家 7.0.8.12，Git LFS）。

## 电视怎么控

应用对已绑定电视同时走云和局域网：

1. **云端按键**：`pushRemoter` / `sendKeyByMqtt` → `https://mobile-aiot.hismarttv.com/mobilemsg/push/v5.3/remoter`，键值如 `KEY_POWER`、`KEY_OK`。
2. **云端功能**：`powerOffTv` / `controlDevice` → `https://iot-aihome.hismarttv.com/4.0/iot/devices/execute`。
3. **MQTT**：`getMqttConfig` → `https://mqtt-msg.hismarttv.com/2.0/mqtt/config`，再 `connectTVByMqtt`。
4. **局域网**：DLNA 发现 + HiConnect（`HiConnect.control` / `specialControl`），UDP `229.x.x.x` 发现，TCP+AES 控设备。
5. **其它**：语音 `sendVoiceToTV`、投屏（WebRTC/镜像）、红外 `IRControllerActivity`、移动电视云台。

完整类名、JNI、键值表见 [docs/tv-control-methods.md](docs/tv-control-methods.md)。

业务主体在 Flutter AOT（`libapp.so`），Java 被百度加固，jadx 只能解出壳。

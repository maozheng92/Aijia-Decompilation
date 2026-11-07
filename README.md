# 海信爱家 / E7N Pro

仓库内 APK：`com.hisense.ms.fly2tv.apk`（海信爱家 7.0.8.12，Git LFS）。

## E7N Pro 怎么控

给 Home Assistant 用的按键通道是 **电视蓝牙**（爱家添加电视会提示打开蓝牙），键值和爱家 App 的 `KEY_POWER`、`KEY_OK` 相同。MQTT 36669 只作状态。不要走爱家云 token。

完整协议对照：[docs/tv-control-methods.md](docs/tv-control-methods.md)  
E7N Pro 结论与安装：[docs/e7n-pro-homeassistant.md](docs/e7n-pro-homeassistant.md)

## Home Assistant 集成

目录：`custom_components/hisense_e7n`

拷到 HA 的 `config/custom_components/` 后重启，在「添加集成」里搜 **Hisense E7N Pro**。配对时电视需已开机，**打开 Home Assistant 主机蓝牙**，并填写 **电视蓝牙地址**（爱家添加电视同样会提示开蓝牙）。设备下会列出爱家遥控页同款按键（电源、音量、截屏、信号源、AI识图、设置、方向键、OK、返回、首页、菜单）。MQTT 36669 连不上也可以添加；状态通道仍会自动用爱家客户端证书、降低 TLS 安全级别。爱家无法唤醒关机的电视，请在配置里选择一个开机用的 **button / 开关 / 脚本**。

```text
custom_components/hisense_e7n/   # 本仓库
        ↓ 复制
<ha-config>/custom_components/hisense_e7n/
```

协议自测（不需要 Home Assistant）：

```bash
python3 -m pytest tests
```

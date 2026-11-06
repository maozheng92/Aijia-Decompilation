# 客户端证书

E7N Pro / 爱家固件的 MQTT（TCP 36669）在 TLS 层会要客户端证书。爱家 APK 里是 2018 年 RemoteNOW 证书（`res/6D.p12`，`CN=remoteclientmobile`，由 `RemoteCA` 签发），不是自签的 `VidaaAppAndroidV01`。

添加集成时会自动：

1. 在 HA `config/` 或本仓库根目录寻找 `com.hisense.ms.fly2tv.apk` / `*.p12`，解开官方证书
2. 若没有 APK，再生成 `CN=VidaaAppAndroidV01` 占位证书
3. TLS 使用 `DEFAULT:@SECLEVEL=0`，兼容电视上的旧 Mosquitto

也可手动：

```bash
python3 scripts/extract_vidaa_certs.py
```

把 `client.pem` / `client.key` 放到 `config/hisense_e7n/setup/`。不要把私钥提交到 git。

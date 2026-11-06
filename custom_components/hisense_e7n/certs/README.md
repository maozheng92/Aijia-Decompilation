# 客户端证书（可选）

E7N Pro 的 MQTT 服务在 TLS 握手时会要客户端证书。

1. 多数固件只检查「有没有证书」。集成会在 Home Assistant 的 `config/hisense_e7n/` 下自动生成主题为 `CN=VidaaAppAndroidV01` 的占位证书，一般够用。
2. 若 CONNECT 返回 **rc=5 Not authorized** 且电视提示应用版本不兼容，把爱家 / VIDAA 官方客户端证书放到这里，并在添加集成时填写路径：

```text
custom_components/hisense_e7n/certs/client.pem
custom_components/hisense_e7n/certs/client.key
```

仓库里的 `scripts/extract_vidaa_certs.py` 会尝试从 `com.hisense.ms.fly2tv.apk` 解出 PKCS#12。解出的私钥不要提交到 git。

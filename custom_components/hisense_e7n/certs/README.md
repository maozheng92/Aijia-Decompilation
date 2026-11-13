# 客户端证书

E7N Pro 执行按键前会核对 TLS 客户端证书的签发者。

| 证书 | 来源 | 结果 |
|---|---|---|
| `vidaa_client.pem` | 2024，`CN=VidaaAppAndroidV01`，`RemoteCA` 签发 | 可以发按键。集成优先使用这张。 |
| `res/6D.p12` | 爱家 APK，2018，`CN=remoteclientmobile` | 只能订到开关广播，按键被丢掉，也不会弹出 4 位授权码。 |
| 自签同名证书 | 没有上面两张时现生成 | 电视不认。 |

`vidaa_client.pem` / `vidaa_client.key` 随集成发布。其余 `*.pem` / `*.key` 仍不入库。

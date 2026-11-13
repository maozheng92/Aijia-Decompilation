"""Installed-app list matches 爱家 我的应用, without Home Assistant."""

from __future__ import annotations

from conftest import load_proto


def test_installed_apps_skip_store_and_removed_rows() -> None:
    apps = load_proto("apps")
    parsed = apps.normalize_apps(
        {
            "app_list": [
                {
                    "appname": "云视听极光",
                    "appid": "com.ktcp.video",
                    "url": "tenvideo2",
                    "urlType": 37,
                    "storeType": 0,
                },
                {"name": "热门推荐", "url": "ad", "category": "recommend"},
                {"name": "已卸载", "url": "gone", "isuninstalled": 1},
            ]
        }
    )
    assert parsed == [
        {
            "name": "云视听极光",
            "url": "tenvideo2",
            "app_id": "com.ktcp.video",
            "url_type": 37,
            "store_type": 0,
        }
    ]


def test_name_list_and_client_apply(proto_client) -> None:
    apps = load_proto("apps")
    assert [item["name"] for item in apps.normalize_apps({"mqttAppNameList": ["聚好看", "聚好看", ""]})] == [
        "聚好看"
    ]
    client = proto_client.HisenseTvClient("127.0.0.1", uuid="aa:bb:cc:dd:ee:ff")
    client._apply_apps([{"appName": "银河奇异果", "url": "iqiyi"}])
    client._apply_apps({"list": []})
    assert client.state.apps[0]["name"] == "银河奇异果"
    assert client.state.apps[0]["url"] == "iqiyi"

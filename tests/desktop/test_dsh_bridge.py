"""dsh_bridge 桥接层测试。

覆盖：
1. 版本号解析（_parse_version）
2. 版本门禁判断（version_ok）
3. 配置读写（set_config / get_config）
4. 状态机（无 DSH → not_installed；版本过低 → version_low）
"""

from common import dsh_bridge


class TestParseVersion:
    def test_parse_plain_version(self):
        assert dsh_bridge._parse_version('0.1.0-rc.6') == '0.1.0-rc.6'

    def test_parse_with_prefix(self):
        assert dsh_bridge._parse_version('@deepseek-ai/dsh/0.2.0') == '0.2.0'
        assert dsh_bridge._parse_version('dsh 0.1.0-rc.6') == '0.1.0-rc.6'

    def test_parse_empty(self):
        assert dsh_bridge._parse_version('') is None
        assert dsh_bridge._parse_version(None) is None

    def test_parse_no_version(self):
        assert dsh_bridge._parse_version('unknown') == 'unknown'


class TestVersionGate:
    def test_rc6_meets_min(self):
        assert dsh_bridge.version_ok('0.1.0-rc.6') is True

    def test_rc5_below_min(self):
        assert dsh_bridge.version_ok('0.1.0-rc.5') is False

    def test_release_higher_than_prerelease(self):
        assert dsh_bridge.version_ok('0.1.0') is True

    def test_higher_versions_ok(self):
        assert dsh_bridge.version_ok('0.2.0') is True
        assert dsh_bridge.version_ok('1.0.0') is True

    def test_lower_release_not_ok(self):
        assert dsh_bridge.version_ok('0.0.9') is False

    def test_none_not_ok(self):
        assert dsh_bridge.version_ok(None) is False


class TestConfig:
    def test_config_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            dsh_bridge, '_config_path',
            lambda: str(tmp_path / 'dsh_config.json'),
        )
        dsh_bridge.set_config(
            dsh_cmd='C:/dsh/dsh.cmd',
            dsh_url='http://127.0.0.1:3080',
            auto_start=True,
        )
        cfg = dsh_bridge.get_config()
        assert cfg['dsh_cmd'] == 'C:/dsh/dsh.cmd'
        assert cfg['dsh_url'] == 'http://127.0.0.1:3080'
        assert cfg['auto_start'] is True

    def test_config_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            dsh_bridge, '_config_path',
            lambda: str(tmp_path / 'dsh_config.json'),
        )
        cfg = dsh_bridge.get_config()
        assert cfg['dsh_cmd'] == ''
        assert cfg['dsh_url'] == dsh_bridge.DEFAULT_DSH_URL
        assert cfg['auto_start'] is False

    def test_set_config_partial_update(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            dsh_bridge, '_config_path',
            lambda: str(tmp_path / 'dsh_config.json'),
        )
        dsh_bridge.set_config(dsh_cmd='cmd')
        dsh_bridge.set_config(dsh_url='http://x:3080')
        cfg = dsh_bridge.get_config()
        assert cfg['dsh_cmd'] == 'cmd'
        assert cfg['dsh_url'] == 'http://x:3080'
        # 未设置字段保持默认
        assert cfg['auto_start'] is False


class TestStatus:
    def test_not_installed(self, monkeypatch):
        monkeypatch.setattr(dsh_bridge, '_resolve_dsh_cmd', lambda: None)
        st = dsh_bridge.get_status()
        assert st['status'] == dsh_bridge.STATUS_NOT_INSTALLED
        assert st['installed'] is False
        assert st['running'] is False
        assert st['version'] is None
        assert st['version_ok'] is False

    def test_version_low(self, monkeypatch):
        monkeypatch.setattr(dsh_bridge, '_resolve_dsh_cmd', lambda: 'C:/dsh/dsh.cmd')
        monkeypatch.setattr(dsh_bridge, 'get_version', lambda: '0.1.0-rc.5')
        st = dsh_bridge.get_status()
        assert st['status'] == dsh_bridge.STATUS_VERSION_LOW
        assert st['installed'] is True
        assert st['version_ok'] is False
        assert st['running'] is False

    def test_running_when_healthy(self, monkeypatch):
        monkeypatch.setattr(dsh_bridge, '_resolve_dsh_cmd', lambda: 'C:/dsh/dsh.cmd')
        monkeypatch.setattr(dsh_bridge, 'get_version', lambda: '0.2.0')
        monkeypatch.setattr(dsh_bridge, 'check_health', lambda *a, **k: True)
        st = dsh_bridge.get_status()
        assert st['status'] == dsh_bridge.STATUS_RUNNING
        assert st['running'] is True
        assert st['version_ok'] is True

    def test_not_running_when_unhealthy(self, monkeypatch):
        monkeypatch.setattr(dsh_bridge, '_resolve_dsh_cmd', lambda: 'C:/dsh/dsh.cmd')
        monkeypatch.setattr(dsh_bridge, 'get_version', lambda: '0.2.0')
        monkeypatch.setattr(dsh_bridge, 'check_health', lambda *a, **k: False)
        st = dsh_bridge.get_status()
        assert st['status'] == dsh_bridge.STATUS_NOT_RUNNING
        assert st['running'] is False

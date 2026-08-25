"""dsh_bridge 桥接层测试。

覆盖：
1. 版本号解析（_parse_version）
2. 版本门禁判断（version_ok）
3. 配置读写（set_config / get_config）
4. 状态机（无 DSH → not_installed；版本过低 → version_low）
"""

import pytest

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
        # 匹配不到 x.y.z 时必须返回 None，绝不能把命令报错/非版本文本当版本号
        assert dsh_bridge._parse_version('unknown') is None

    def test_parse_error_text_returns_none(self):
        # 复现 DSH 误判根因：node 不在 PATH 时 dsh.cmd --version 输出报错文本
        error_text = '"node" 不是内部或外部命令，也不是可运行的程序或批处理文件。'
        assert dsh_bridge._parse_version(error_text) is None
        assert dsh_bridge._parse_version('dsfdsf 0.1.0') == '0.1.0'


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
        dsh_bridge.set_config(dsh_url='http://127.0.0.1:3080')
        cfg = dsh_bridge.get_config()
        assert cfg['dsh_cmd'] == 'cmd'
        assert cfg['dsh_url'] == 'http://127.0.0.1:3080'
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


class TestValidHttpUrl:
    def test_http_https_ok(self):
        assert dsh_bridge._valid_http_url('http://127.0.0.1:3080') is True
        assert dsh_bridge._valid_http_url('https://example.com:3080') is True

    def test_non_http_rejected(self):
        assert dsh_bridge._valid_http_url('file:///etc/passwd') is False
        assert dsh_bridge._valid_http_url('javascript:alert(1)') is False
        assert dsh_bridge._valid_http_url('') is False
        assert dsh_bridge._valid_http_url(None) is False


class TestSetConfigValidation:
    def test_invalid_url_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dsh_bridge, '_config_path', lambda: str(tmp_path / 'dsh_config.json'))
        with pytest.raises(ValueError):
            dsh_bridge.set_config(dsh_url='file:///etc/passwd')

    def test_empty_url_falls_back_to_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dsh_bridge, '_config_path', lambda: str(tmp_path / 'dsh_config.json'))
        dsh_bridge.set_config(dsh_url='')
        assert dsh_bridge.get_config()['dsh_url'] == dsh_bridge.DEFAULT_DSH_URL

    def test_non_loopback_url_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dsh_bridge, '_config_path', lambda: str(tmp_path / 'dsh_config.json'))
        with pytest.raises(ValueError):
            dsh_bridge.set_config(dsh_url='http://example.com:3080')

    def test_wrong_executable_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dsh_bridge, '_config_path', lambda: str(tmp_path / 'dsh_config.json'))
        evil = tmp_path / 'evil.exe'
        evil.write_text('')
        with pytest.raises(ValueError):
            dsh_bridge.set_config(dsh_cmd=str(evil))

    def test_non_string_dsh_cmd_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dsh_bridge, '_config_path', lambda: str(tmp_path / 'dsh_config.json'))
        with pytest.raises(ValueError):
            dsh_bridge.set_config(dsh_cmd=12345)

    def test_non_string_dsh_url_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dsh_bridge, '_config_path', lambda: str(tmp_path / 'dsh_config.json'))
        with pytest.raises(ValueError):
            dsh_bridge.set_config(dsh_url=['http://127.0.0.1:3080'])


class TestLoopbackUrl:
    def test_loopback_ok(self):
        assert dsh_bridge._is_loopback_url('http://127.0.0.1:3080') is True
        assert dsh_bridge._is_loopback_url('http://localhost:3080') is True

    def test_non_loopback_rejected(self):
        assert dsh_bridge._is_loopback_url('http://example.com:3080') is False
        assert dsh_bridge._is_loopback_url('http://169.254.169.254/latest/meta-data') is False


class TestVersionGateFailClosed:
    def test_unparseable_or_empty(self):
        assert dsh_bridge.version_ok('unknown') is False
        assert dsh_bridge.version_ok('') is False


class TestCheckHealth:
    def test_invalid_url_returns_false(self):
        assert dsh_bridge.check_health('file:///etc/passwd') is False
        assert dsh_bridge.check_health('not-a-url') is False

    def test_redirect_3xx_counts_as_alive(self, monkeypatch):
        # 根路径 302 重定向（被禁跟随）仍说明服务存活，不应误判为未运行
        import urllib.error

        class _FakeOpener:
            def open(self, req, timeout=None):
                raise urllib.error.HTTPError(
                    req.full_url, 302, 'Found', {}, None,
                )

        monkeypatch.setattr(dsh_bridge.urllib.request, 'build_opener', lambda *a, **k: _FakeOpener())
        assert dsh_bridge.check_health('http://127.0.0.1:3080') is True


class TestResolveDshCmd:
    def test_path_fallback(self, monkeypatch):
        monkeypatch.setattr(dsh_bridge, 'get_config', lambda: {
            'dsh_cmd': '', 'dsh_url': 'http://127.0.0.1:3080', 'auto_start': False,
        })
        monkeypatch.setattr(dsh_bridge.shutil, 'which', lambda name: 'C:/node/dsh.cmd' if name == 'dsh' else None)
        assert dsh_bridge._resolve_dsh_cmd() == 'C:/node/dsh.cmd'

    def test_directory_localization(self, tmp_path, monkeypatch):
        d = tmp_path / 'dsh'
        d.mkdir()
        (d / 'dsh.cmd').write_text('')
        monkeypatch.setattr(dsh_bridge, 'get_config', lambda: {
            'dsh_cmd': str(d), 'dsh_url': 'http://x', 'auto_start': False,
        })
        assert dsh_bridge._resolve_dsh_cmd() == str(d / 'dsh.cmd')

    def test_npm_node_modules_bin_localization(self, tmp_path, monkeypatch):
        # npm 安装的 dsh：可执行文件在 <dir>/node_modules/.bin/dsh.cmd
        d = tmp_path / 'harness'
        (d / 'node_modules' / '.bin').mkdir(parents=True)
        (d / 'node_modules' / '.bin' / 'dsh.cmd').write_text('')
        monkeypatch.setattr(dsh_bridge, 'get_config', lambda: {
            'dsh_cmd': str(d), 'dsh_url': 'http://x', 'auto_start': False,
        })
        assert dsh_bridge._resolve_dsh_cmd() == str(d / 'node_modules' / '.bin' / 'dsh.cmd')


class TestRunHeadless:
    def test_not_installed_returns_error(self, monkeypatch):
        monkeypatch.setattr(dsh_bridge, 'get_status', lambda: {'status': dsh_bridge.STATUS_NOT_INSTALLED})
        r = dsh_bridge.run_headless('hello')
        assert r['success'] is False
        assert 'DSH 不可用' in r['error']


class TestCheckUpdate:
    def test_registry_unreachable(self, monkeypatch):
        import urllib.error
        monkeypatch.setattr(dsh_bridge, 'get_version', lambda: '0.1.0-rc.6')

        def _boom(*a, **k):
            raise urllib.error.URLError('offline')

        monkeypatch.setattr(dsh_bridge.urllib.request, 'urlopen', _boom)
        r = dsh_bridge.check_update()
        assert r['installed'] == '0.1.0-rc.6'
        assert r['latest'] is None
        assert r['has_update'] is False
        assert r['error']

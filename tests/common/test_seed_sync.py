"""种子智能同步逻辑测试。

覆盖场景：
1. 新增文件：seed 新文件正确复制到 target
2. 更新文件：seed 文件变更后正确覆盖 target
3. 用户文件：target 独有的文件不被删除
4. 种子源不存在：跳过不报错
5. 无变更时：target 文件不变
6. 子目录递归同步
"""
import os
import shutil
import filecmp

import pytest


# ---- 被测逻辑（从 app.py _seed_smart_sync 提取，保证与生产逻辑一致） ----

def smart_sync(seed_dir, target_dir):
    """seed → target 智能同步。
    Returns: (added: int, updated: int)
    """
    if not os.path.isdir(seed_dir):
        return 0, 0

    os.makedirs(target_dir, exist_ok=True)
    added = 0
    updated = 0

    for item in os.listdir(seed_dir):
        src = os.path.join(seed_dir, item)
        dst = os.path.join(target_dir, item)

        if os.path.isdir(src):
            os.makedirs(dst, exist_ok=True)
            for root, _dirs, files in os.walk(src):
                rel = os.path.relpath(root, src)
                dst_root = os.path.join(dst, rel) if rel != '.' else dst
                os.makedirs(dst_root, exist_ok=True)
                for f in files:
                    sf = os.path.join(root, f)
                    df = os.path.join(dst_root, f)
                    if not os.path.exists(df):
                        shutil.copy2(sf, df)
                        added += 1
                    elif not filecmp.cmp(sf, df, shallow=False):
                        shutil.copy2(sf, df)
                        updated += 1
        else:
            if not os.path.exists(dst):
                shutil.copy2(src, dst)
                added += 1
            elif not filecmp.cmp(src, dst, shallow=False):
                shutil.copy2(src, dst)
                updated += 1

    return added, updated


# ---- 测试 ----

class TestSeedSyncNewFiles:
    """新增文件场景。"""

    def test_new_file_copied(self, tmp_path):
        seed = tmp_path / 'seed'
        target = tmp_path / 'target'
        seed.mkdir()
        (seed / 'a.txt').write_text('hello')

        added, updated = smart_sync(str(seed), str(target))
        assert added == 1
        assert updated == 0
        assert (target / 'a.txt').read_text() == 'hello'

    def test_new_dir_copied(self, tmp_path):
        seed = tmp_path / 'seed'
        target = tmp_path / 'target'
        (seed / 'sub').mkdir(parents=True)
        (seed / 'sub' / 'b.txt').write_text('nested')

        added, updated = smart_sync(str(seed), str(target))
        assert added == 1
        assert (target / 'sub' / 'b.txt').read_text() == 'nested'

    def test_multiple_new_files(self, tmp_path):
        seed = tmp_path / 'seed'
        target = tmp_path / 'target'
        seed.mkdir()
        (seed / 'a.txt').write_text('a')
        (seed / 'b.txt').write_text('b')

        added, updated = smart_sync(str(seed), str(target))
        assert added == 2
        assert updated == 0


class TestSeedSyncUpdateFiles:
    """更新文件场景。"""

    def test_changed_file_overwritten(self, tmp_path):
        seed = tmp_path / 'seed'
        target = tmp_path / 'target'
        seed.mkdir(); target.mkdir()
        (seed / 'a.txt').write_text('new content')
        (target / 'a.txt').write_text('old content')

        added, updated = smart_sync(str(seed), str(target))
        assert added == 0
        assert updated == 1
        assert (target / 'a.txt').read_text() == 'new content'

    def test_unchanged_file_not_touched(self, tmp_path):
        seed = tmp_path / 'seed'
        target = tmp_path / 'target'
        seed.mkdir(); target.mkdir()
        (seed / 'a.txt').write_text('same')
        (target / 'a.txt').write_text('same')

        added, updated = smart_sync(str(seed), str(target))
        assert added == 0
        assert updated == 0


class TestSeedSyncPreserveUserFiles:
    """用户文件保留场景。"""

    def test_user_only_file_preserved(self, tmp_path):
        seed = tmp_path / 'seed'
        target = tmp_path / 'target'
        seed.mkdir(); target.mkdir()
        (seed / 'a.txt').write_text('from seed')
        (target / 'z_user.txt').write_text('user created')

        smart_sync(str(seed), str(target))
        # 用户文件应该还在
        assert (target / 'z_user.txt').read_text() == 'user created'
        # seed 文件也在
        assert (target / 'a.txt').read_text() == 'from seed'

    def test_user_only_file_not_deleted(self, tmp_path):
        seed = tmp_path / 'seed'
        target = tmp_path / 'target'
        seed.mkdir(); target.mkdir()
        (target / 'custom_skill.md').write_text('my skill')

        smart_sync(str(seed), str(target))
        assert (target / 'custom_skill.md').exists()
        assert (target / 'custom_skill.md').read_text() == 'my skill'

    def test_user_file_untouched_when_seed_updates_other(self, tmp_path):
        seed = tmp_path / 'seed'
        target = tmp_path / 'target'
        seed.mkdir(); target.mkdir()
        (seed / 'a.txt').write_text('seed v2')
        (target / 'a.txt').write_text('seed v1')
        (target / 'my_own.txt').write_text('mine')
        mtime_before = os.path.getmtime(target / 'my_own.txt')

        smart_sync(str(seed), str(target))
        assert (target / 'a.txt').read_text() == 'seed v2'
        assert (target / 'my_own.txt').read_text() == 'mine'
        assert os.path.getmtime(target / 'my_own.txt') == mtime_before


class TestSeedSyncEdgeCases:
    """边界场景。"""

    def test_seed_not_exist_skips(self, tmp_path):
        seed = tmp_path / 'nonexistent'
        target = tmp_path / 'target'
        target.mkdir()

        added, updated = smart_sync(str(seed), str(target))
        assert added == 0
        assert updated == 0

    def test_empty_seed_no_change(self, tmp_path):
        seed = tmp_path / 'seed'
        target = tmp_path / 'target'
        seed.mkdir(); target.mkdir()

        added, updated = smart_sync(str(seed), str(target))
        assert added == 0
        assert updated == 0

    def test_target_not_exist_created(self, tmp_path):
        seed = tmp_path / 'seed'
        target = tmp_path / 'target'
        seed.mkdir()
        (seed / 'a.txt').write_text('hello')

        added, updated = smart_sync(str(seed), str(target))
        assert added == 1
        assert os.path.isdir(target)
        assert (target / 'a.txt').exists()

    def test_nested_subdir_sync(self, tmp_path):
        seed = tmp_path / 'seed'
        target = tmp_path / 'target'
        seed.mkdir(); target.mkdir()
        (seed / 'level1').mkdir()
        (seed / 'level1' / 'level2').mkdir()
        (seed / 'level1' / 'level2' / 'deep.txt').write_text('deep')

        added, updated = smart_sync(str(seed), str(target))
        assert added == 1
        assert (target / 'level1' / 'level2' / 'deep.txt').read_text() == 'deep'

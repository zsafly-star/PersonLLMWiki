"""window_geometry 纯几何函数单测。

覆盖 KL-1.2.3-02 的拖动钳制与恢复坐标校验收紧，回归锚点为线上坏值
`[1220, -168, 3502, 2018] → None`。
"""
import pytest

from common.window_geometry import clamp_drag_position, validate_restore_bounds

# 主屏单显示器度量：2560×1440 @ (0,0)
MAIN = dict(vx=0, vy=0, vx2=2560, vy2=1440)

# 主屏 2560×1440 + 左侧副屏 1920×1080 @ (-1920,0) 的虚拟屏幕
DUAL = dict(vx=-1920, vy=0, vx2=2560, vy2=1440)


class TestClampDragPosition:
    def test_drag_up_past_top_edge_clamped(self):
        """向上拖出顶 → top 仍为 vy（0），顶栏不丢。"""
        left, top = clamp_drag_position(
            left=813, top=0, width=1024, dx=0, dy=-50, **MAIN,
        )
        assert top == 0
        assert left == 813

    def test_normal_move_unaffected(self):
        """向下/左右正常平移 → 按 dx/dy 原样平移，不钳制。"""
        left, top = clamp_drag_position(
            left=813, top=100, width=1024, dx=30, dy=20, **MAIN,
        )
        assert (left, top) == (843, 120)

    def test_drag_left_past_edge_keeps_visible_width(self):
        """向左推到主屏左外侧 → 至少保留 min_visible_w 可见。"""
        left, top = clamp_drag_position(
            left=0, top=100, width=1024, dx=-2000, dy=0, **MAIN,
        )
        # 右边缘应停在 vx + min_visible_w = 120，即 left = 120 - 1024 = -904
        assert left == 120 - 1024
        assert top == 100

    def test_drag_right_past_edge_keeps_visible_width(self):
        """向右推到主屏右外侧 → 至少保留 min_visible_w 可见。"""
        left, top = clamp_drag_position(
            left=2500, top=100, width=1024, dx=100, dy=0, **MAIN,
        )
        assert left == 2560 - 120
        assert top == 100

    def test_multi_monitor_negative_coords_free_move(self):
        """多显示器负坐标：副屏区域内可自由拖动，不被主屏左边界锁死。"""
        left, top = clamp_drag_position(
            left=-1800, top=0, width=1024, dx=10, dy=0, **DUAL,
        )
        assert (left, top) == (-1790, 0)


class TestValidateRestoreBounds:
    def test_online_bad_value_rejected(self):
        """线上坏值 [1220, -168, 3502, 2018] → None（回归锚点）。"""
        assert validate_restore_bounds([1220, -168, 3502, 2018], **MAIN) is None

    def test_valid_bounds_returned_unchanged(self):
        """正常坐标 [813, 0, 1837, 1239] → 原样返回。"""
        assert validate_restore_bounds([813, 0, 1837, 1239], **MAIN) == \
            (813, 0, 1837, 1239)

    def test_top_touching_top_edge_valid(self):
        """顶栏贴屏幕最上沿（top == vy）→ 有效。"""
        assert validate_restore_bounds([100, 0, 1100, 600], **MAIN) == \
            (100, 0, 1100, 600)

    def test_right_overflow_but_visible_still_valid(self):
        """右边越界但交集 ≥ min_w×min_h → 仍有效（水平越界交拖动钳制处理）。"""
        assert validate_restore_bounds([2000, 100, 3500, 500], **MAIN) == \
            (2000, 100, 3500, 500)

    def test_none_input_returns_none(self):
        assert validate_restore_bounds(None, **MAIN) is None

    def test_degenerate_bounds_return_none(self):
        """宽度或高度非正 → None。"""
        assert validate_restore_bounds([100, 0, 100, 600], **MAIN) is None
        assert validate_restore_bounds([100, 0, 1100, 0], **MAIN) is None

"""窗口几何纯函数（不依赖 Win32 / 真实屏幕）。

desktop.pyw 是 .pyw，无法被 import；把「拖动钳制」与「恢复坐标校验」
的纯几何逻辑抽到这里，便于 tests/desktop 直接单测。所有屏幕度量
（虚拟屏幕包围盒 vx/vy/vx2/vy2）均由调用方注入，函数本身无副作用。
"""


def clamp_drag_position(left, top, width, dx, dy, *,
                        vx, vy, vx2, vy2, min_visible_w=120):
    """拖动一帧后的目标位置（已钳制）。

    规则：
      - 顶边不得越过虚拟屏幕上沿（vy）：否则自绘顶栏移出屏幕、鼠标点不到；
      - 水平方向至少保留 min_visible_w 像素落在虚拟屏幕内：否则窗口被推到
        显示器侧边之外无法抓取。

    参数：
      left/top/width：当前窗口外框左、上、宽（像素）。
      dx/dy：本帧鼠标增量。
      vx/vy/vx2/vy2：虚拟屏幕包围盒（所有显示器并集的左上/右下坐标）。
      min_visible_w：水平方向至少保留的可见宽度。

    返回 (left, top)。
    """
    new_left = left + dx
    new_top = top + dy
    if new_top < vy:
        new_top = vy
    if new_left + width < vx + min_visible_w:
        new_left = vx + min_visible_w - width
    if new_left > vx2 - min_visible_w:
        new_left = vx2 - min_visible_w
    return (new_left, new_top)


def validate_restore_bounds(bounds, *, vx, vy, vx2, vy2, min_w=100, min_h=40):
    """校验保存/还原的窗口 bounds，返回可用 bounds 或 None。

    规则（在原有「交集 ≥ min_w × min_h」之上收紧）：
      - 自绘标题栏在窗口最顶部 → 要求 top >= vy，否则判为无效；
      - 无效时返回 None，由调用方回退默认 1280×800 居中。

    参数：
      bounds：(left, top, right, bottom) 或 None。
      vx/vy/vx2/vy2：虚拟屏幕包围盒。
      min_w/min_h：窗口在虚拟屏幕内至少需要可见的宽/高。

    返回 (left, top, right, bottom) 或 None。
    """
    if not bounds:
        return None
    left, top, right, bottom = bounds
    if right <= left or bottom <= top:
        return None
    ix = max(left, vx)
    iy = max(top, vy)
    ix2 = min(right, vx2)
    iy2 = min(bottom, vy2)
    if (ix2 - ix) < min_w or (iy2 - iy) < min_h:
        return None
    # 自定义标题栏/菜单栏在窗口最顶部：顶边必须落在虚拟屏幕内，
    # 否则保存的坐标会把窗口还原成「顶栏在屏幕外、鼠标点不到」的状态。
    if top < vy:
        return None
    return (left, top, right, bottom)

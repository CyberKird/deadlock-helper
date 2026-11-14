"""Fereastra jocului si captura benzii de sus. Doar citim ecranul (ca un
screenshot): nimic injectat in joc, nimic citit din memoria lui."""

import ctypes
import ctypes.wintypes as wt

import mss
import numpy as np
import psutil

GAME_EXE = 'deadlock.exe'
user32 = ctypes.windll.user32


def dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)      # per monitor: pixeli fizici
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def _pids():
    out = set()
    for p in psutil.process_iter(['name']):
        try:
            if (p.info['name'] or '').lower() == GAME_EXE:
                out.add(p.pid)
        except psutil.Error:
            pass
    return out


def find_game():
    """Intoarce {'hwnd', 'rect': [x0, y0, x1, y1] zona client in pixeli ecran,
    'foreground': bool} sau None daca jocul nu ruleaza / nu are fereastra."""
    pids = _pids()
    if not pids:
        return None
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids:
            r = wt.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(r))
            if r.right - r.left > 400 and r.bottom - r.top > 300:
                found.append((hwnd, r.right - r.left, r.bottom - r.top))
        return True

    user32.EnumWindows(cb, 0)
    if not found:
        return {'hwnd': None, 'rect': None, 'foreground': False, 'running': True}
    hwnd, w, h = max(found, key=lambda f: f[1] * f[2])
    pt = wt.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    minimized = bool(user32.IsIconic(hwnd))
    return {'hwnd': hwnd, 'rect': [pt.x, pt.y, pt.x + w, pt.y + h], 'running': True,
            'foreground': user32.GetForegroundWindow() == hwnd and not minimized,
            'minimized': minimized}


def show_in_taskbar(raw_hwnd, ui_pid):
    """Panoul nu ia focusul jocului (WS_EX_NOACTIVATE), iar Windows ascunde din
    taskbar ferestrele astea. Il punem inapoi (WS_EX_APPWINDOW), ca sa-l poti fixa.
    Doar pentru fereastra interfetei noastre (verificam procesul ei)."""
    try:
        hwnd = int(raw_hwnd)
        pid = int(ui_pid)
    except (TypeError, ValueError):
        return False
    owner = wt.DWORD()
    user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    if hwnd <= 0 or not user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner)) or owner.value != pid:
        return False
    user32.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_ssize_t]
    user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
    style = user32.GetWindowLongPtrW(hwnd, -20)                    # GWL_EXSTYLE
    new = (style | 0x40000) & ~0x80                                  # +APPWINDOW, -TOOLWINDOW
    if new == style:
        return True
    user32.SetWindowLongPtrW(hwnd, -20, new)
    user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x37)               # FRAMECHANGED, fara mutare
    # Taskbar-ul isi face lista la afisarea ferestrei: un stil schimbat dupa aceea nu
    # conteaza. Ascundem si reafisam fara focus (SW_HIDE, SW_SHOWNOACTIVATE).
    user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
    if user32.IsWindowVisible(hwnd):
        user32.ShowWindow(hwnd, 0)
        user32.ShowWindow(hwnd, 4)
    return True


class Grabber:
    def __init__(self):
        self.sct = mss.MSS() if hasattr(mss, 'MSS') else mss.mss()

    def top(self, rect, frac=0.125):
        """Banda de sus a jocului (BGR), toata latimea."""
        x0, y0, x1, y1 = rect
        h = max(1, int((y1 - y0) * frac))
        shot = self.sct.grab({'left': x0, 'top': y0, 'width': x1 - x0, 'height': h})
        return np.ascontiguousarray(np.asarray(shot)[:, :, :3])

    def bottom(self, rect, frac):
        """Banda de jos a jocului (BGR), toata latimea."""
        x0, y0, x1, y1 = rect
        h = max(1, int((y1 - y0) * frac))
        shot = self.sct.grab({'left': x0, 'top': y1 - h, 'width': x1 - x0, 'height': h})
        return np.ascontiguousarray(np.asarray(shot)[:, :, :3])

    def close(self):
        try:
            self.sct.close()
        except Exception:
            pass

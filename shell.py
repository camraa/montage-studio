"""Fenêtre de Montage Studio (module mis à jour automatiquement, appelé par le lanceur app.py).

Fenêtre façon Mac + gestes Windows :
- glisser la barre de titre = déplacement natif Windows ; relâcher contre le haut de l'écran = plein écran,
  contre la gauche / la droite = moitié d'écran, dans un coin = quart d'écran (avec aperçu, comme Windows)
- tirer une fenêtre agrandie vers le bas la restaure sous la souris ; double-clic sur la barre = agrandir / restaurer
- animations : agrandir / aimanter en douceur, fondu à la fermeture et à la réduction
- icône dans la zone de notification (à côté de l'horloge) : ouvrir, mises à jour, quitter,
  + notification quand une analyse / un rendu se termine
Tout ce qui est natif Windows est protégé : en cas de souci, l'app garde le comportement de base.
"""
import os
import sys
import threading
import time
import traceback

IS_WIN = os.name == "nt"


def _log_error(where):
    try:
        from common import DATA_DIR
        with open(DATA_DIR / "fenetre_erreurs.log", "a", encoding="utf-8") as f:
            f.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} {where}\n{traceback.format_exc()}\n")
    except Exception:
        pass


# ------------------------------------------------------------------ Win32
if IS_WIN:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]

    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, wintypes.UINT]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
    user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    user32.MonitorFromPoint.restype = wintypes.HMONITOR
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]

SWP_NOZORDER, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x4, 0x10, 0x40
WM_NCLBUTTONDOWN, HTCAPTION = 0xA1, 2


def cursor():
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def win_rect(hwnd):
    r = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return [r.left, r.top, r.right - r.left, r.bottom - r.top]


def monitor_at(x, y):
    """(zone de l'écran entier, zone de travail sans la barre des tâches) de l'écran sous (x, y)."""
    mon = user32.MonitorFromPoint(wintypes.POINT(x, y), 2)
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    user32.GetMonitorInfoW(mon, ctypes.byref(mi))
    m, w = mi.rcMonitor, mi.rcWork
    return ([m.left, m.top, m.right - m.left, m.bottom - m.top], [w.left, w.top, w.right - w.left, w.bottom - w.top])


def snap_zone(x, y, mon, work):
    """Zone d'aimantation pour un relâchement en (x, y) : 'max', 'left', 'right', 'tl', 'tr', 'bl', 'br' ou None."""
    mx, my, mw, mh = mon
    edge = 6
    left, right = x <= mx + edge, x >= mx + mw - 1 - edge
    top = y <= my + edge
    corner = 0.22 * work[3]
    if left or right:
        side = "l" if left else "r"
        if y <= work[1] + corner:
            return "t" + side
        if y >= work[1] + work[3] - corner:
            return "b" + side
        return "left" if left else "right"
    if top:
        return "max"
    return None


def zone_rect(zone, work):
    x, y, w, h = work
    hw, hh = w // 2, h // 2
    return {"max": [x, y, w, h], "left": [x, y, hw, h], "right": [x + hw, y, w - hw, h],
            "tl": [x, y, hw, hh], "tr": [x + hw, y, w - hw, hh],
            "bl": [x, y + hh, hw, h - hh], "br": [x + hw, y + hh, w - hw, h - hh]}[zone]


def ease(t):
    return 1 - (1 - t) ** 3


class Native:
    """Gestes Windows d'une fenêtre pywebview sans cadre (WinForms + WebView2).

    Règle d'or : le fil de la fenêtre n'est JAMAIS bloqué ni attendu. Le déplacement est piloté depuis
    la page (pointeur capturé) et appliqué par SetWindowPos depuis un fil Python ; les objets WinForms
    (aperçu, icône, transparence) ne sont touchés que via BeginInvoke (sans attente).
    (v1.1.6 utilisait la boucle de déplacement de Windows : avec WebView2 elle pouvait ne jamais rendre la main.)"""

    def __init__(self, window):
        self.window = window
        self.form = None
        self.hwnd = None
        self.zone = None                 # aimantation en cours (None = position libre)
        self.normal = None               # [x, y, w, h] avant agrandissement / aimantation
        self.preview = None
        self.drag = None
        self.lock = threading.Lock()
        self.anim_id = 0
        self.tray = None
        self.ok = False

    def later(self, fn):
        """Exécute fn sur le fil de la fenêtre, sans jamais attendre."""
        from System import Action

        def run():
            try:
                fn()
            except Exception:
                _log_error(getattr(fn, "__name__", "later"))
        try:
            self.form.BeginInvoke(Action(run))
        except Exception:
            _log_error("BeginInvoke")

    def attach(self):
        try:
            self.form = self.window.native
            self.hwnd = int(self.form.Handle.ToInt64())
            self.ok = True
        except Exception:
            _log_error("attach")

    # -------- position
    def set_rect(self, r, size=True):
        flags = SWP_NOZORDER | SWP_NOACTIVATE | (0 if size else 0x1)
        user32.SetWindowPos(self.hwnd, None, int(r[0]), int(r[1]), int(r[2]), int(r[3]), flags)

    def animate(self, to, ms=170):
        self.anim_id += 1
        my = self.anim_id

        def run():
            frm, t0 = win_rect(self.hwnd), time.perf_counter()
            while my == self.anim_id:
                k = min(1.0, (time.perf_counter() - t0) * 1000 / ms)
                e = ease(k)
                self.set_rect([frm[i] + (to[i] - frm[i]) * e for i in range(4)])
                if k >= 1.0:
                    return
                time.sleep(0.008)
        threading.Thread(target=run, daemon=True).start()

    # -------- aperçu d'aimantation (fenêtre bleue translucide sous la nôtre)
    def _preview_form(self):
        if self.preview:
            return self.preview
        from System.Drawing import Color
        from System.Windows.Forms import Form, FormBorderStyle, FormStartPosition
        f = Form()
        f.FormBorderStyle = getattr(FormBorderStyle, "None")
        f.ShowInTaskbar = False
        f.StartPosition = FormStartPosition.Manual
        f.BackColor = Color.FromArgb(10, 132, 255)
        f.Opacity = 0.22
        h = int(f.Handle.ToInt64())
        try:                         # coins arrondis Windows 11
            v = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(h, 33, ctypes.byref(v), 4)
        except Exception:
            pass
        self.preview = f
        return f

    def show_preview(self, rect):
        def go():
            f = self._preview_form()
            ph = int(f.Handle.ToInt64())
            if not rect:
                user32.ShowWindow(ph, 0)
                return
            pad = 6
            user32.SetWindowPos(ph, self.hwnd, rect[0] + pad, rect[1] + pad, rect[2] - 2 * pad, rect[3] - 2 * pad,
                                SWP_NOACTIVATE | SWP_SHOWWINDOW)
        self.later(go)

    # -------- glisser (appelé par la page : début / mouvement / fin)
    def drag_start(self):
        x, y = cursor()
        with self.lock:
            self.anim_id += 1                    # stoppe une animation en cours
            r = win_rect(self.hwnd)
            self.drag = {"x0": x, "y0": y, "rect": r, "moved": False, "zone": None, "dx": x - r[0], "dy": y - r[1]}

    def drag_move(self):
        d = self.drag
        if not d:
            return
        x, y = cursor()
        with self.lock:
            if not d["moved"]:
                if abs(x - d["x0"]) <= 5 and abs(y - d["y0"]) <= 5:
                    return
                d["moved"] = True
                if self.zone:                    # agrandie / aimantée : on la décroche sous la souris
                    r = d["rect"]
                    nw, nh = (self.normal or [0, 0, 1400, 860])[2:]
                    rel = (d["x0"] - r[0]) / max(1, r[2])
                    d["dx"], d["dy"] = int(nw * rel), d["y0"] - r[1]
                    d["was_zone"] = self.zone
                    self.zone = None
                    self.set_rect([x - d["dx"], y - d["dy"], nw, nh])
                    self._notify_state()
                    return
            self.set_rect([x - d["dx"], y - d["dy"], 0, 0], size=False)
            mon, work = monitor_at(x, y)
            z = snap_zone(x, y, mon, work)
            if z != d["zone"]:
                d["zone"] = z
                self.show_preview(zone_rect(z, work) if z else None)

    def drag_end(self):
        d, self.drag = self.drag, None
        if not d:
            return
        if d["zone"]:
            self.show_preview(None)
        if not d["moved"]:
            return
        x, y = cursor()
        mon, work = monitor_at(x, y)
        z = snap_zone(x, y, mon, work)
        if z:
            if not d.get("was_zone"):
                self.normal = d["rect"]
            self.zone = z
            self.animate(zone_rect(z, work))
            self._notify_state()

    def toggle_max(self):
        r = win_rect(self.hwnd)
        if self.zone:
            self.zone = None
            to = self.normal or [r[0] + 80, r[1] + 60, 1400, 860]
            _, work = monitor_at(r[0] + r[2] // 2, r[1] + 10)
            to = [max(work[0], min(to[0], work[0] + work[2] - to[2])),
                  max(work[1], min(to[1], work[1] + work[3] - 40)), to[2], to[3]]
        else:
            self.normal = r
            _, work = monitor_at(r[0] + r[2] // 2, r[1] + r[3] // 2)
            self.zone = "max"
            to = zone_rect("max", work)
        self.animate(to)
        self._notify_state()

    def _notify_state(self):
        z = bool(self.zone)
        threading.Thread(target=lambda: self._js(f"window.onWinState && window.onWinState({str(z).lower()})"),
                         daemon=True).start()

    def _js(self, code):
        try:
            self.window.evaluate_js(code)
        except Exception:
            pass

    # -------- fondus (réglés pas à pas depuis un fil Python, appliqués sans attente)
    def fade(self, to, ms=160, then=None):
        def run():
            try:
                frm = float(self.form.Opacity)
            except Exception:
                frm = 1.0
            t0 = time.perf_counter()
            while True:
                k = min(1.0, (time.perf_counter() - t0) * 1000 / ms)
                v = frm + (to - frm) * ease(k)
                self.later(lambda v=v: setattr(self.form, "Opacity", v))
                if k >= 1.0:
                    break
                time.sleep(0.012)
            if then:
                then()
        threading.Thread(target=run, daemon=True).start()

    def minimize(self):
        from System.Windows.Forms import FormWindowState

        def done():
            def go():
                self.form.WindowState = FormWindowState.Minimized
                self.form.Opacity = 1.0
            self.later(go)
        self.fade(0.0, 140, done)

    def close_animated(self, destroy):
        ev = threading.Event()
        self.fade(0.0, 170, ev.set)
        ev.wait(0.6)
        destroy()

    def show(self):
        from System.Windows.Forms import FormWindowState

        def go():
            self.form.Show()
            if self.form.WindowState == FormWindowState.Minimized:
                self.form.WindowState = FormWindowState.Normal
            self.form.Opacity = 1.0
            self.form.Activate()
            user32.SetForegroundWindow(self.hwnd)
        self.later(go)

    # -------- zone de notification
    def make_tray(self, icon_path, on_check_update, on_quit):
        from System.Drawing import Icon
        from System.Windows.Forms import ContextMenuStrip, MouseButtons, NotifyIcon, ToolStripMenuItem, ToolStripSeparator
        from common import APP_NAME, APP_VERSION
        title = f"{APP_NAME} {APP_VERSION}"[:63]
        exe = sys.executable

        def go():
            ni = NotifyIcon()
            try:
                ni.Icon = Icon(str(icon_path)) if icon_path and os.path.exists(str(icon_path)) else \
                    Icon.ExtractAssociatedIcon(exe)
            except Exception:
                ni.Icon = Icon.ExtractAssociatedIcon(exe)
            ni.Text = title
            menu = ContextMenuStrip()
            for label, fn in (("Ouvrir Montage Studio", self.show), ("Rechercher des mises à jour", on_check_update)):
                it = ToolStripMenuItem(label)
                it.Click += (lambda f: (lambda s, e: threading.Thread(target=f, daemon=True).start()))(fn)
                menu.Items.Add(it)
            menu.Items.Add(ToolStripSeparator())
            q = ToolStripMenuItem("Quitter")
            q.Click += lambda s, e: threading.Thread(target=on_quit, daemon=True).start()
            menu.Items.Add(q)
            ni.ContextMenuStrip = menu

            def click(s, e):
                if e.Button == MouseButtons.Left:
                    self.show()
            ni.MouseClick += click
            ni.Visible = True
            self.tray = ni
        self.later(go)

    def balloon(self, title, text):
        if not self.tray:
            return
        from System.Windows.Forms import ToolTipIcon
        self.later(lambda: self.tray.ShowBalloonTip(5000, title, text, ToolTipIcon.Info))

    def remove_tray(self):
        t, self.tray = self.tray, None
        if t:
            def go():
                t.Visible = False
                t.Dispose()
            self.later(go)


# ------------------------------------------------------------------ fenêtre
def run_gui():
    import studio
    import updater
    from common import APP_NAME, APP_VERSION, DATA_DIR
    try:
        from app import migrate_old_install
        migrate_old_install()
    except Exception:
        pass
    srv, url = studio.start_server()
    updater.check_async(delay=1)
    try:
        import webview
    except ImportError:          # pas de pywebview : on ouvre dans le navigateur
        import webbrowser
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        return

    try:
        from common import load_config
        frameless = bool(load_config().get("ui", {}).get("mac_window", True))
    except Exception:
        frameless = True
    try:                         # seules les zones vides de la barre de titre déplacent la fenêtre
        webview.settings["DRAG_REGION_DIRECT_TARGET_ONLY"] = True
    except Exception:
        pass
    closing_ok = {"v": False}
    win_state = {"max": False}
    nat = {"n": None}

    def native():
        n = nat["n"]
        return n if n and n.ok else None

    def confirm_close():
        running = [j for j in studio.JOBS if j["status"] in ("en cours", "en attente")]
        if running:
            ok = window.create_confirmation_dialog(
                "Une tâche est en cours",
                f"{len(running)} tâche(s) en cours ({running[0]['name']}).\n"
                "Si tu quittes maintenant, elle sera arrêtée.\n"
                "Tu pourras la reprendre là où elle en était au prochain lancement.\nQuitter quand même ?")
            if not ok:
                return False
        studio.kill_jobs()
        return True

    def quit_app():
        if confirm_close():
            closing_ok["v"] = True
            n = native()
            if n:
                n.remove_tray()
                n.close_animated(window.destroy)
            else:
                window.destroy()

    def check_update():
        updater.check()
        st = updater.STATE
        n = native()
        if n:
            if st.get("ready"):
                n.balloon("Mise à jour prête", f"Version {st['ready']} : clique « Redémarrer » en haut à droite.")
            elif st.get("error"):
                n.balloon("Mises à jour", st["error"][:200])
            else:
                n.balloon("Mises à jour", f"Tu as la dernière version ({APP_VERSION}).")

    class Api:
        def win_info(self):
            n = native()
            return {"frameless": frameless, "native_drag": bool(n and frameless), "maximized": bool(n and n.zone)}

        def win_drag_start(self):
            n = native()
            if n:
                n.drag_start()

        def win_drag_move(self):
            n = native()
            if n:
                n.drag_move()

        def win_drag_end(self):
            n = native()
            if n:
                n.drag_end()

        def win_close(self):
            quit_app()

        def win_min(self):
            n = native()
            if n:
                n.minimize()
            else:
                window.minimize()

        def win_max(self):           # bouton vert / double-clic sur la barre : agrandir <-> restaurer
            n = native()
            if n:
                return n.toggle_max()
            if win_state["max"]:
                window.restore()
            else:
                window.maximize()
            win_state["max"] = not win_state["max"]

        def pick_folder(self):
            r = window.create_file_dialog(webview.FOLDER_DIALOG)
            return r[0] if r else None

        def pick_videos(self):
            r = window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=True,
                                          file_types=("Vidéos (*.mp4;*.mkv;*.mov)", "Tous (*.*)"))
            return list(r) if r else []

    win_kw = dict(js_api=Api(), width=1600, height=960, min_size=(1200, 720),
                  background_color="#1e1e20", text_select=False)
    if frameless:
        win_kw.update(frameless=True, easy_drag=False, shadow=True)
    try:
        window = webview.create_window(f"{APP_NAME} {APP_VERSION}", url, **win_kw)
    except TypeError:            # anciennes versions de pywebview : pas d'option shadow/easy_drag
        for k in ("shadow", "easy_drag"):
            win_kw.pop(k, None)
        window = webview.create_window(f"{APP_NAME} {APP_VERSION}", url, **win_kw)

    def on_closing():
        if closing_ok["v"]:      # déjà confirmé (bouton rouge / menu de l'icône)
            return
        if not confirm_close():
            return False
        n = native()
        if n:
            n.remove_tray()

    icon = studio.ASSET_DIR / "icone.ico"

    def on_shown():
        if not IS_WIN:
            return

        def setup():                 # hors du fil de la fenêtre, et sans jamais l'attendre
            try:
                time.sleep(0.3)
                n = Native(window)
                n.attach()
                if n.ok:
                    nat["n"] = n
                    n.make_tray(icon, check_update, quit_app)
            except Exception:
                _log_error("on_shown")
        threading.Thread(target=setup, daemon=True).start()

    def on_job_end(j):
        n = native()
        if not n:
            return
        what = {"scan": "Analyse", "rescan": "Analyse", "render": "Rendu", "all": "Analyse + rendu",
                "shorts": "Shorts"}.get(j.get("action"), "Tâche")
        if j.get("status") == "terminé":
            n.balloon(f"{what} terminé", j.get("name", ""))
        elif j.get("status") == "erreur":
            n.balloon(f"{what} : erreur", f"{j.get('name', '')} — ouvre la File pour le détail.")

    try:
        studio.JOB_HOOKS.append(on_job_end)
    except Exception:
        pass
    window.events.closing += on_closing
    try:
        window.events.shown += on_shown
    except Exception:
        pass
    try:                         # garde l'état agrandi/restauré à jour (Win+flèches, etc.)
        window.events.maximized += lambda *a: win_state.update(max=True)
        window.events.restored += lambda *a: win_state.update(max=False)
    except Exception:
        pass
    kw = {"storage_path": str(DATA_DIR / "webview"), "private_mode": False}
    if IS_WIN:
        kw["gui"] = "edgechromium"
    if icon.exists():
        kw["icon"] = str(icon)
    try:
        webview.start(**kw)
    except TypeError:            # anciennes versions de pywebview
        kw.pop("icon", None)
        webview.start(**kw)
    n = native()
    if n:
        try:
            n.remove_tray()
        except Exception:
            pass
    studio.kill_jobs()

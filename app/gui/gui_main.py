"""main gui for tactical sim"""
# @generated [partially] Gemini 3.0: Tkinter GUI structure and canvas interaction logic
# i am not a pro with gui so i used gemini for help, when i was not sure
#pylint: disable=broad-exception-caught
import json
import sys
from pathlib import Path
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk


try:
    from app.src.models import GameState
    from app.src.simulator.simulation import SimulationEngine
    from app.src.database_utils import get_all_operatives
except ImportError as e:
    print(f"GUI: Import error: {e}")

# color scheme and some constants
C_BG = "#050505"
C_SIDE = "#0f0f0f"
C_CANVAS = "#000000"
C_TEXT = "#dddddd"
C_SM = "#3498db"
C_DG = "#2ecc71"
C_BTN = "#1a1a1a"

SIDEBAR_W = 560
RATIO_W = 76
RATIO_H = 57

# hardcoded maps for now
MAPS = {
    "MAP 1": {
        "obstacles": [
            {"id": "L1", "x": 10, "y": 5, "w": 2, "h": 4},
            {"id": "R1", "x": 18, "y": 14, "w": 2, "h": 4},
            {"id": "L2", "x": 10, "y": 14, "w": 2, "h": 4},
            {"id": "R2", "x": 18, "y": 5, "w": 2, "h": 4}
        ],
        "objectives": [
            {"id": "Center", "x": 15, "y": 11.5},
            {"id": "West", "x": 5, "y": 11.5},
            {"id": "East", "x": 25, "y": 11.5}
        ]
    },
    "MAP 2": {
        "obstacles": [
            {"id": "W1", "x": 7, "y": 5, "w": 1, "h": 13},
            {"id": "W2", "x": 22, "y": 5, "w": 1, "h": 13},
            {"id": "P1", "x": 14, "y": 7, "w": 2, "h": 2},
            {"id": "P2", "x": 14, "y": 14, "w": 2, "h": 2}
        ],
        "objectives": [
            {"id": "O1", "x": 15, "y": 11.5},
            {"id": "O2", "x": 15, "y": 4},
            {"id": "O3", "x": 15, "y": 19}
        ]
    },
    "MAP 3": {
        "obstacles": [
            {"id": "R1", "x": 10, "y": 5, "w": 3, "h": 1},
            {"id": "R1b", "x": 10, "y": 6, "w": 1, "h": 2},
            {"id": "R2", "x": 17, "y": 17, "w": 3, "h": 1},
            {"id": "R2b", "x": 19, "y": 15, "w": 1, "h": 2}
        ],
        "objectives": [
            {"id": "Alpha", "x": 6, "y": 6},
            {"id": "Beta", "x": 24, "y": 17},
            {"id": "Center", "x": 15, "y": 11.5}
        ]
    }
}


class TacticalGUI:
    """Main window class"""

    def __init__(self, root):
        """Constructor of class TacticalGUI"""
        self.root = root
        self.root.title("Warhammer 40k kill team sim")
        self.root.attributes("-fullscreen", True)
        self.root.configure(bg=C_BG)

        self.army = self._load_army()
        self.units = {}  # dict for units on field {uid: data}
        self.op_count = 0
        self.layout_name = "MAP 1"
        self.active_id = tk.StringVar()
        self.active_id.trace_add("write", lambda *args: self.validate_rosters())
        self.goal_var = tk.StringVar(value="CAPTURE")

        # variables for interactions
        self.editing_uid = None
        self.selecting_active = False
        self.mouse_pos = (0, 0)

        # canvas defaults
        self.cw = 100
        self.ch = 100
        self.scale = 1.0

        self._init_ui()
        self.validate_rosters()
        
        self.root.update()
        self.update_viewport()
        
        self.root.bind("<Configure>", lambda e: self.update_viewport())
        self.root.bind("<Motion>", self.on_mouse_move)

    def _load_army(self):
        """Loads army data from database"""
        try:
            # check if functions were imported
            if 'get_all_operatives' not in globals():
                return {"space_marines_ops": [], "death_guard_ops": []}

            sm_raw = get_all_operatives("space_marines")
            dg_raw = get_all_operatives("death_guard")

            def to_dict(op):
                return {
                    "name": op[1], "team": op[2], "apl": op[3],
                    "move": op[4], "save": op[5], "wounds": op[6],
                    "weapons": json.loads(op[7]), "abilities": json.loads(op[8])
                }

            return {
                "space_marines_ops": [to_dict(o) for o in sm_raw],
                "death_guard_ops": [to_dict(o) for o in dg_raw]
            }
        except Exception:
            return {"space_marines_ops": [], "death_guard_ops": []}

    def _init_ui(self):
        # lower menu bar
        self.bottom = tk.Frame(self.root, bg=C_SIDE, height=120)
        self.bottom.pack(side=tk.BOTTOM, fill=tk.X)
        self.bottom.pack_propagate(False)

        # left side
        m_inner = tk.Frame(self.bottom, bg=C_SIDE)
        m_inner.place(relx=0.02, rely=0.5, anchor=tk.W)
        for m in MAPS:
            tk.Button(m_inner, text=m, command=lambda n=m: self.set_map(n),
                      bg="#222", fg="white", borderwidth=0, padx=15, pady=8).pack(side=tk.LEFT, padx=5)

        # middle section (unit selection - centered)
        u_inner = tk.Frame(self.bottom, bg=C_SIDE)
        u_inner.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        tk.Button(u_inner, text="SELECT ACTIVE UNIT", command=self.toggle_select_active,
                  bg="#333", fg="gold", font=("Arial", 11, "bold"), padx=20, pady=6).pack(side=tk.TOP, pady=(0, 5))

        w_ctrl = tk.Frame(u_inner, bg=C_SIDE)
        w_ctrl.pack(side=tk.TOP)
        tk.Label(w_ctrl, text="WOUNDS:", bg=C_SIDE, fg="#666", font=("Arial", 10, "bold")).pack(side=tk.LEFT)
        self.w_label = tk.Label(w_ctrl, text="0/0", bg=C_SIDE, fg="white", font=("Arial", 11, "bold"), width=5)
        self.w_label.pack(side=tk.LEFT, padx=5)
        self.w_slider = tk.Scale(w_ctrl, from_=1, to=10, orient=tk.HORIZONTAL, bg=C_SIDE, fg="white",
                                 highlightthickness=0, troughcolor="#333", activebackground="gold",
                                 showvalue=0, length=150, command=self.on_wounds_change)
        self.w_slider.pack(side=tk.LEFT)

        # right section (actions - anchored to the right, grows to the left, so it never gets clipped)
        a_inner = tk.Frame(self.bottom, bg=C_SIDE)
        a_inner.place(relx=0.98, rely=0.5, anchor=tk.E)

        tk.Button(a_inner, text="EXIT", command=self.root.destroy,
                  bg="#600", fg="white", font=("Arial", 10, "bold"), padx=15, pady=8).pack(side=tk.RIGHT, padx=5)
        tk.Button(a_inner, text="CLEAR ALL", command=self.clear_units,
                  bg="#444", fg="white", font=("Arial", 10, "bold"), padx=15, pady=8).pack(side=tk.RIGHT, padx=5)

        g_ctrl = tk.Frame(a_inner, bg=C_SIDE)
        g_ctrl.pack(side=tk.RIGHT, padx=10)
        tk.Label(g_ctrl, text="GOAL:", bg=C_SIDE, fg="#666", font=("Arial", 9, "bold")).pack(side=tk.TOP)
        self.goal_menu = tk.OptionMenu(g_ctrl, self.goal_var, "CAPTURE", "KILL", "SURVIVE", "DAMAGE")
        self.goal_menu.config(bg="#222", fg="gold", highlightthickness=0, borderwidth=0, font=("Arial", 9, "bold"))
        self.goal_menu["menu"].config(bg="#222", fg="gold")
        self.goal_menu.pack(side=tk.TOP)

        self.run_btn = tk.Button(a_inner, text="RUN TACTICAL ENGINE", command=self.run,
                                 bg="#fff", fg="#000", font=("Arial", 11, "bold"), padx=20, pady=10)
        self.run_btn.pack(side=tk.RIGHT, padx=5)

        # container for everything except menu bar
        self.main_area = tk.Frame(self.root, bg=C_BG)
        self.main_area.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # left panel 25% of screen
        self.side_l = tk.Frame(self.main_area, bg=C_SIDE)
        self.side_l.place(relx=0.0, rely=0.0, relwidth=0.25, relheight=1.0)
        self.side_l.pack_propagate(False)

        self.res_l = tk.Frame(self.side_l, bg="#0a0a0a")
        self.res_l.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=(20, 10))
        tk.Label(self.res_l, text="TACTICAL RECOMMENDATIONS", bg="#0a0a0a", fg="gold", font=("Arial", 12, "bold")).pack(pady=10)
        self.res_l_cont = tk.Frame(self.res_l, bg="#0a0a0a")
        self.res_l_cont.pack(fill=tk.BOTH, expand=True)

        tk.Label(self.side_l, text="SPACE MARINES", bg=C_SIDE, fg=C_SM, font=("Arial", 16, "bold")).pack(pady=20)

        self.sm_btns = {}
        for op in self.army.get("space_marines_ops", []):
            btn = tk.Button(self.side_l, text=op['name'].replace('_', ' ').upper(),
                            command=lambda o=op: self.enter_edit_new(o),
                            bg=C_BTN, fg=C_TEXT, borderwidth=0, pady=15, activebackground=C_SM)
            btn.pack(fill=tk.X, pady=2, padx=20)
            self.sm_btns[op['name']] = btn

        # right panel 25% of screen
        self.side_r = tk.Frame(self.main_area, bg=C_SIDE)
        self.side_r.place(relx=0.75, rely=0.0, relwidth=0.25, relheight=1.0)
        self.side_r.pack_propagate(False)

        self.res_r = tk.Frame(self.side_r, bg="#0a0a0a")
        self.res_r.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=(20, 10))
        tk.Label(self.res_r, text="SUPPLEMENTARY ANALYSIS", bg="#0a0a0a", fg="gold", font=("Arial", 12, "bold")).pack(pady=10)
        self.res_r_cont = tk.Frame(self.res_r, bg="#0a0a0a")
        self.res_r_cont.pack(fill=tk.BOTH, expand=True)

        tk.Label(self.side_r, text="DEATH GUARD", bg=C_SIDE, fg=C_DG, font=("Arial", 16, "bold")).pack(pady=20)

        self.dg_btns = {}
        for op in self.army.get("death_guard_ops", []):
            btn = tk.Button(self.side_r, text=op['name'].replace('_', ' ').upper(),
                            command=lambda o=op: self.enter_edit_new(o),
                            bg=C_BTN, fg=C_TEXT, borderwidth=0, pady=15, activebackground=C_DG)
            btn.pack(fill=tk.X, pady=2, padx=20)
            self.dg_btns[op['name']] = btn

        # 50% screen map in the middle
        self.map_container = tk.Frame(self.main_area, bg=C_BG)
        self.map_container.place(relx=0.25, rely=0.0, relwidth=0.50, relheight=1.0)

        self.canvas = tk.Canvas(self.map_container, bg=C_CANVAS, highlightthickness=0)
        self.canvas.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<Button-3>", self.on_right_click)
        self.root.bind("<Button-1>", self.on_root_click)

    def update_viewport(self):
        """Recalculates scale and canvas size"""
        self.root.update_idletasks()
        total_w = self.map_container.winfo_width()
        total_h = self.map_container.winfo_height()
        if total_w <= 0 or total_h <= 0:
            return

        if (total_w / RATIO_W) < (total_h / RATIO_H):
            self.cw, self.ch = total_w, total_w * (RATIO_H / RATIO_W)
        else:
            self.ch, self.cw = total_h, total_h * (RATIO_W / RATIO_H)

        self.scale = self.cw / 30.0
        self.canvas.config(width=self.cw, height=self.ch)
        self.refresh()

    def set_map(self, name):
        """Changes map layout and checks units position"""
        self.layout_name = name
        # check if units are still on valid positions
        for uid in list(self.units.keys()):
            d = self.units[uid]
            if not self.is_position_valid(uid, d['x'], d['y']):
                # try to find a safe spot near start
                found = False
                for dx in range(0, 5):
                    for dy in range(0, 5):
                        tx, ty = 1.0 + dx*1.5, 1.0 + dy*1.5
                        if self.is_position_valid(uid, tx, ty):
                            self.units[uid]['x'] = tx
                            self.units[uid]['y'] = ty
                            found = True
                            break
                    if found:
                        break
                if not found:
                    self.units[uid]['x'] = 1.0
                    self.units[uid]['y'] = 1.0
        self.refresh()

    def on_wounds_change(self, val):
        """Updates wounds for active unit"""
        uid = self.active_id.get()
        if uid in self.units:
            self.units[uid]["wounds"] = int(val)
            self.w_label.config(text=f"{val}/{self.units[uid]['max_wounds']}")
            self.refresh()

    def enter_edit_new(self, op):
        """Adds unit to map and starts moving it"""
        team = op['team']
        team_count = sum(1 for u in self.units.values() if u['team'] == team)
        placed_types = [u['name'] for u in self.units.values()]

        if team_count >= 5:
            messagebox.showwarning("Limit Reached", f"{team.replace('_', ' ').title()} already has 5 units.")
            return
        if op['name'] in placed_types:
            messagebox.showwarning("Duplicate", f"{op['name'].replace('_', ' ').title()} is on the field.")
            return

        uid = f"u{self.op_count}"
        self.op_count += 1
        # default spawn at 1,1
        self.units[uid] = {
            "name": op['name'], "team": op['team'], "x": 1.0, "y": 1.0,
            "wounds": op['wounds'], "max_wounds": op['wounds']
        }
        self.editing_uid = uid
        self.validate_rosters()
        self.refresh()

    def validate_rosters(self):
        """Disables/enables sidebar and run buttons based on units"""
        sm_count = sum(1 for u in self.units.values() if u['team'] == "space_marines")
        dg_count = sum(1 for u in self.units.values() if u['team'] == "death_guard")
        placed_types = [u['name'] for u in self.units.values()]

        # sidebar buttons
        for name, btn in self.sm_btns.items():
            if name in placed_types or sm_count >= 5:
                btn.config(state=tk.DISABLED, bg="#050505", fg="#333")
            else:
                btn.config(state=tk.NORMAL, bg=C_BTN, fg=C_TEXT)

        for name, btn in self.dg_btns.items():
            if name in placed_types or dg_count >= 5:
                btn.config(state=tk.DISABLED, bg="#050505", fg="#333")
            else:
                btn.config(state=tk.NORMAL, bg=C_BTN, fg=C_TEXT)

        # run button validation
        has_active = bool(self.active_id.get())
        if sm_count >= 1 and dg_count >= 1 and has_active:
            self.run_btn.config(state=tk.NORMAL, bg="#fff", fg="#000")
        else:
            self.run_btn.config(state=tk.DISABLED, bg="#222", fg="#444")

    def is_position_valid(self, uid, x, y):
        """Checks borders, obstacles and unit collisions"""
        if x < 0.6 or x > 29.4 or y < 0.6 or y > 22.4:
            return False

        m = MAPS[self.layout_name]
        for o in m["obstacles"]:
            if (o['x'] - 0.55) <= x <= (o['x'] + o['w'] + 0.55) and \
               (o['y'] - 0.55) <= y <= (o['y'] + o['h'] + 0.55):
                return False

        for ouid, d in self.units.items():
            if ouid == uid:
                continue
            dist_sq = (x - d['x'])**2 + (y - d['y'])**2
            if dist_sq < (1.2)**2:
                return False
        return True

    def on_mouse_move(self, event):
        """Handles movement of unit that is being edited"""
        self.mouse_pos = (event.x, event.y)
        if self.editing_uid:
            cx = self.canvas.winfo_rootx()
            cy = self.canvas.winfo_rooty()
            rel_x = (event.x_root - cx) / self.scale
            rel_y = (event.y_root - cy) / self.scale

            if self.is_position_valid(self.editing_uid, rel_x, rel_y):
                self.units[self.editing_uid]["x"] = rel_x
                self.units[self.editing_uid]["y"] = rel_y
            self.refresh()

    def toggle_select_active(self):
        """Switches mode for selecting active unit"""
        self.selecting_active = not self.selecting_active
        if self.selecting_active:
            self.editing_uid = None
            self.canvas.config(cursor="crosshair")
        else:
            self.canvas.config(cursor="")
        self.refresh()

    def on_canvas_click(self, event):
        """Left click on map - place, pick up or select unit"""
        # handling select mode
        if self.selecting_active:
            items = self.canvas.find_overlapping(event.x-5, event.y-5, event.x+5, event.y+5)
            for item in reversed(items):
                tags = self.canvas.gettags(item)
                for tag in tags:
                    if tag.startswith("u") and len(tag) > 1:
                        self.active_id.set(tag)
                        self.selecting_active = False
                        self.canvas.config(cursor="")
                        # update slider and label
                        u = self.units[tag]
                        self.w_slider.config(to=u['max_wounds'])
                        self.w_slider.set(u['wounds'])
                        self.w_label.config(text=f"{u['wounds']}/{u['max_wounds']}")
                        self.refresh()
                        return "break"
            return None

        # place unit
        if self.editing_uid:
            if self.is_position_valid(self.editing_uid, self.units[self.editing_uid]["x"],
                                      self.units[self.editing_uid]["y"]):
                self.editing_uid = None
                self.validate_rosters()
                self.refresh()
                return "break"
            return "break"

        # pick up unit
        items = self.canvas.find_overlapping(event.x-5, event.y-5, event.x+5, event.y+5)
        for item in reversed(items):
            tags = self.canvas.gettags(item)
            for tag in tags:
                if tag.startswith("u") and len(tag) > 1:
                    self.editing_uid = tag
                    # also set as active
                    self.active_id.set(tag)
                    u = self.units[tag]
                    self.w_slider.config(to=u['max_wounds'])
                    self.w_slider.set(u['wounds'])
                    self.w_label.config(text=f"{u['wounds']}/{u['max_wounds']}")
                    self.refresh()
                    return "break"
        return None

    def on_right_click(self, event):
        """Right click - deletes unit"""
        items = self.canvas.find_overlapping(event.x-5, event.y-5, event.x+5, event.y+5)
        for item in reversed(items):
            tags = self.canvas.gettags(item)
            for tag in tags:
                if tag.startswith("u") and len(tag) > 1:
                    uid = tag
                    if self.editing_uid == uid:
                        self.editing_uid = None
                    del self.units[uid]
                    if self.active_id.get() == uid:
                        self.active_id.set("")
                        self.w_label.config(text="0/0")
                    self.validate_rosters()
                    self.refresh()
                    return

    def on_root_click(self, event):
        """Cancels unit placement if clicked outside map"""
        if self.editing_uid:
            try:
                widget = self.root.winfo_containing(event.x_root, event.y_root)
                if widget != self.canvas:
                    uid = self.editing_uid
                    del self.units[uid]
                    if self.active_id.get() == uid:
                        self.active_id.set("")
                        self.w_label.config(text="0/0")
                    self.editing_uid = None
                    self.validate_rosters()
                    self.refresh()
            except (AttributeError, tk.TclError):
                pass

    def refresh(self):
        """Redraws canvas"""
        self.canvas.delete("all")
        m = MAPS[self.layout_name]
        s = self.scale

        # 0. Map border (White)
        self.canvas.create_rectangle(0, 0, 30*s, 23*s, outline="#ffffff", width=2)

        # 1. Grid
        if s >= 1.0:
            for i in range(0, int(31*s), int(s)):
                self.canvas.create_line(i, 0, i, 23*s, fill="#111111")
            for i in range(0, int(24*s), int(s)):
                self.canvas.create_line(0, i, 30*s, i, fill="#111111")

        # 2. Obstacles (lightened)
        for o in m["obstacles"]:
            x, y, w, h = o['x']*s, o['y']*s, o['w']*s, o['h']*s
            self.canvas.create_rectangle(x, y, x+w, y+h, fill="#2a2a2a", outline="#444")

        # 3. Objectives (Yellow)
        r_obj = 1.0 * s
        for obj in m["objectives"]:
            ox, oy = obj['x'] * s, obj['y'] * s
            self.canvas.create_oval(ox-r_obj, oy-r_obj, ox+r_obj, oy+r_obj, outline="gold", width=1, dash=(3,3))
            self.canvas.create_text(ox, oy, text=obj['id'], fill="gold", font=("Arial", 8, "bold"))

        # 4. Operatives
        r = 0.6 * s
        active_uid = self.active_id.get()

        for uid, d in self.units.items():
            x, y = d['x']*s, d['y']*s
            is_ed = uid == self.editing_uid
            color = C_SM if d['team'] == "space_marines" else C_DG
            is_active = uid == active_uid

            # unit circle
            if is_active:
                outline = "gold"
                width = 4
            elif is_ed:
                outline = "#fff"
                width = 3
            else:
                outline = "black"
                width = 1

            self.canvas.create_oval(x-r, y-r, x+r, y+r, fill=color, outline=outline, width=width, tags=(uid,))

            # name and wounds
            display_name = d['name'].replace('_', ' ').upper()
            text_color = "gold" if is_active else ("#fff" if is_ed else C_TEXT)
            self.canvas.create_text(x, y - r - 12, text=display_name, fill=text_color,
                                    font=("Arial", 8, "bold"), tags=(uid,))
            # wounds count inside
            self.canvas.create_text(x, y, text=str(d['wounds']), fill="white",
                                    font=("Arial", 10, "bold"), tags=(uid,))

        # help text for selecting active
        if self.selecting_active:
            self.canvas.create_text(self.cw/2, 30, text="CLICK UNIT TO SET AS ACTIVE",
                                    fill="gold", font=("Arial", 14, "bold"))

    def run(self):
        """Triggers simulation engine with a loading indicator"""
        if 'SimulationEngine' not in globals() or 'GameState' not in globals():
            messagebox.showerror("ERROR", "Simulation Engine or Models not loaded correctly.")
            return

        uid = self.active_id.get()
        if not uid or uid not in self.units:
            messagebox.showwarning("Warning", "Please select an active unit first.")
            return

        # Disable run button and show loading window
        self.run_btn.config(state=tk.DISABLED, text="THINKING...", bg="#444")

        load_win = tk.Toplevel(self.root)
        load_win.title("Tactical Engine")
        load_win.geometry("400x180")
        load_win.configure(bg=C_SIDE)
        load_win.transient(self.root)

        # Ensure window is mapped before grab_set to avoid TclError
        load_win.wait_visibility()
        load_win.grab_set()
        # center loading window
        lw, lh = 400, 180
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        load_win.geometry(f"{lw}x{lh}+{(sw-lw)//2}+{(sh-lh)//2}")

        tk.Label(load_win, text="ENGINE IS THINKING", bg=C_SIDE, fg="gold",
                 font=("Arial", 14, "bold")).pack(pady=(25, 10))

        progress = ttk.Progressbar(load_win, orient=tk.HORIZONTAL, length=300, mode='determinate')
        progress.pack(pady=10)

        timer_label = tk.Label(load_win, text="Time remaining: 20s", bg=C_SIDE, fg="#888", font=("Arial", 10))
        timer_label.pack()

        # Prepare simulation data
        u = self.units[uid]
        sim_data = {
            "simulation_context": {
                "active_faction": u["team"],
                "active_operative_name": u["name"],
                "user_goal": self.goal_var.get().lower()
            },
            "operatives": {
                "space_marines": {k: {"type": v["name"], "x": v["x"], "y": v["y"], "wounds": v["wounds"], "order": "engage"}
                                 for k, v in self.units.items() if v['team'] == "space_marines"},
                "death_guard": {k: {"type": v["name"], "x": v["x"], "y": v["y"], "wounds": v["wounds"], "order": "engage"}
                               for k, v in self.units.items() if v['team'] == "death_guard"}
            },
            "map": MAPS[self.layout_name]
        }

        results_container = []
        error_container = []

        def sim_thread():
            try:
                gs = GameState(sim_data)
                engine = SimulationEngine(gs)
                res = engine.run()
                results_container.append(res)
            except Exception as e:
                error_container.append(str(e))

        # Start simulation in background
        thread = threading.Thread(target=sim_thread)
        thread.start()

        start_t = time.time()

        def check_status():
            elapsed = time.time() - start_t
            remaining = max(0, int(20 - elapsed))

            if not thread.is_alive():
                load_win.destroy()
                self.run_btn.config(state=tk.NORMAL, text="RUN TACTICAL ENGINE", bg="#fff")
                if error_container:
                    messagebox.showerror("SIMULATION ERROR", error_container[0])
                elif results_container:
                    self.show_results(results_container[0])
                return

            # Update UI
            timer_label.config(text=f"Time remaining: {remaining}s")
            progress['value'] = (elapsed / 20.0) * 100
            self.root.after(100, check_status)

        check_status()

    def clear_units(self):
        """Deletes all units from map and clears results"""
        self.units.clear()
        self.editing_uid = None
        self.active_id.set("")
        self.w_label.config(text="0/0")
        self.validate_rosters()

        # Clear results UI
        for widget in self.res_l_cont.winfo_children():
            widget.destroy()
        for widget in self.res_r_cont.winfo_children():
            widget.destroy()

        self.refresh()

    def show_results(self, results):
        """Populates sidebars with structured simulation results"""
        if not results:
            return

        # Clear existing
        for widget in self.res_l_cont.winfo_children():
            widget.destroy()
        for widget in self.res_r_cont.winfo_children():
            widget.destroy()

        self.visualize_result(results[0])

        for i, res in enumerate(results):
            container = self.res_l_cont if i < 3 else self.res_r_cont

            frame = tk.Frame(container, bg="#1a1a1a", pady=10, padx=15)
            frame.pack(fill=tk.X, pady=5, padx=5)

            # Line 1: Rank and Score
            tk.Label(frame, text=f"RECOMMENDATION #{res['rank']}",
                     bg="#1a1a1a", fg="gold", font=("Arial", 10, "bold")).pack(anchor=tk.W)
            tk.Label(frame, text=f"Confidence Score: {int(res['score'])}",
                     bg="#1a1a1a", fg="#888", font=("Arial", 8)).pack(anchor=tk.W)

            # Line 2: Detailed HP Status (Multi-line)
            hp_frame = tk.Frame(frame, bg="#1a1a1a")
            hp_frame.pack(fill=tk.X, pady=5)
            for o in res['operatives']:
                color = "#00ff00" if o['wounds'] > 0 else "#ff0000"
                tk.Label(hp_frame, text=f"• {o['name'].replace('_',' ').upper()}: {o['wounds']} HP",
                         bg="#1a1a1a", fg=color, font=("Arial", 7)).pack(anchor=tk.W)

            # Line 3: Sequence
            actions = [m for m in res['sequence'] if any(x in m for x in ["Shoot", "Fight", "Capture"])]
            seq_txt = " ➔ ".join(actions) if actions else "HOLD POSITION"
            tk.Label(frame, text=seq_txt, bg="#1a1a1a", fg="white", font=("Arial", 8),
                     wraplength=450, justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 5))

            # Action Button
            btn = tk.Button(frame, text="VIEW ON MAP", command=lambda r=res: self.visualize_result(r),
                            bg="#333", fg="gold", font=("Arial", 8, "bold"), borderwidth=0, padx=15, pady=5)
            btn.pack(fill=tk.X, pady=(5, 0))

    def visualize_result(self, res):
        """Draws arrows, red targets and dynamic HP for a specific result"""
        self.refresh() # base map refresh

        s = self.scale
        uid = self.active_id.get()
        if not uid or uid not in self.units:
            return
        u = self.units[uid]

        start_x, start_y = u['x'] * s, u['y'] * s
        end_x, end_y = res['final_position']['x'] * s, res['final_position']['y'] * s

        # 1. Update Map Operative HPs to simulated outcome
        for _ in res['operatives']:
            # This is a bit manual since we don't store canvas IDs,
            # but we can redraw the HP text overlay
            continue

        # 2. Draw Movement Arrow
        if start_x != end_x or start_y != end_y:
            self.canvas.create_line(start_x, start_y, end_x, end_y, fill="gold", width=3,
                                    arrow=tk.LAST, dash=(5, 2), tags=("viz",))

        # 3. Process Actions for dynamic visualization
        actions = res['sequence']
        label_y = end_y - 40

        for action in actions:
            if ":" in action:
                parts = action.split(":")
                act_type = parts[0]
                target_name = parts[1]

                # Draw red targeting line for Shoot/Fight
                if act_type in ["Shoot", "Fight"]:
                    # Find target position in end state
                    target_node_op = next(o for o in res['final_node'].operatives if o.name == target_name)
                    tx, ty = target_node_op.x * s, target_node_op.y * s

                    # Target crosshair
                    r_t = 0.8 * s
                    self.canvas.create_oval(tx-r_t, ty-r_t, tx+r_t, ty+r_t, outline="#ff0000", width=2, dash=(2, 2), tags=("viz",))
                    self.canvas.create_line(end_x, end_y, tx, ty, fill="#ff0000", width=1, dash=(4, 4), tags=("viz",))

                    txt = f"{act_type.upper()} AT {target_name.replace('_',' ').upper()}"
                    self.canvas.create_text(end_x, label_y, text=txt, fill="#ff4444", font=("Arial", 9, "bold"), tags=("viz",))
                    label_y -= 15

            elif action == "Capture":
                # Pulse effect or icon on nearest objective
                self.canvas.create_text(end_x, label_y, text="!!! CAPTURING !!!", fill="gold", font=("Arial", 10, "bold"), tags=("viz",))
                label_y -= 15

        # 4. Draw Simulated HP numbers OVER circles
        for op in res['operatives']:
            # Find current pos in final node
            node_op = next(o for o in res['final_node'].operatives if o.name == op['name'])
            ox, oy = node_op.x * s, node_op.y * s

            # Dynamic HP Badge
            bg_color = "red" if op['wounds'] <= 0 else "black"
            self.canvas.create_rectangle(ox-10, oy+15, ox+10, oy+28, fill=bg_color, outline="white", tags=("viz",))
            self.canvas.create_text(ox, oy+21, text=str(int(op['wounds'])), fill="white", font=("Arial", 8, "bold"), tags=("viz",))


if __name__ == "__main__":
    root_win = tk.Tk()
    app = TacticalGUI(root_win)
    root_win.mainloop()

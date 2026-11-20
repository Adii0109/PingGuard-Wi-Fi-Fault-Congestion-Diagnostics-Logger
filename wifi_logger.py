import webbrowser
from app import app as flask_app
import platform
import re
import socket
import subprocess
import threading
import tkinter as tk
from collections import deque
from datetime import datetime
from tkinter import ttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from database import init_and_clean_database, add_pingguard_record

DEFAULT_INTERVAL = 1.5
HIGH_PING_THRESHOLD_MS = 150.0
MAX_POINTS = 60

INTERVAL_OPTIONS = {
    "1s (Real-time)": 1.0,
    "1.5s (Fast)": 1.5,
    "2s (Standard)": 2.0,
    "5s (Balanced)": 5.0,
    "10s (Light)": 10.0,
    "30s (Background)": 30.0,
    "1m (Long-term)": 60.0,
}


class PingGuardApp:

    def __init__(self, root):
        self.root = root
        self.root.title("PingGuard — Live Network Load & Fault Logger (MySQL)")
        self.root.geometry("780x470")
        self.root.configure(bg="#1e1e2e")

        self.stop_event = threading.Event()
        self.last_status = None
        self.check_interval = DEFAULT_INTERVAL

        self.times = deque(maxlen=MAX_POINTS)
        self.pings = deque(maxlen=MAX_POINTS)
        self.statuses = deque(maxlen=MAX_POINTS)

        # Initialize MySQL database (creates if missing, cleans > 7 days) & start new session
        init_and_clean_database()
        self.session_id = f"Session-{datetime.now().strftime('%H:%M:%S')}"

        self.setup_ui()

        threading.Thread(target=self.telemetry_worker, daemon=True).start()
        threading.Thread(target=self.listen_terminal_end, daemon=True).start()
        threading.Thread(target=lambda: flask_app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False),daemon=True).start()


    def setup_ui(self):
        top_frame = tk.Frame(self.root, bg="#1e1e2e", pady=10, padx=15)
        top_frame.pack(fill=tk.X)

        self.status_label = tk.Label(
            top_frame,
            text="Status: Starting telemetry...",
            font=("Segoe UI", 12, "bold"),
            fg="#a6e3a1",
            bg="#1e1e2e",
        )
        self.status_label.pack(side=tk.LEFT)

        controls_frame = tk.Frame(top_frame, bg="#1e1e2e")
        controls_frame.pack(side=tk.RIGHT)

        interval_lbl = tk.Label(
            controls_frame,
            text="Interval:",
            font=("Segoe UI", 9, "bold"),
            fg="#cdd6f4",
            bg="#1e1e2e",
            padx=6,
        )
        interval_lbl.pack(side=tk.LEFT)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Dark.TCombobox",
            fieldbackground="#313244",
            background="#45475a",
            foreground="#cdd6f4",
            arrowcolor="#cdd6f4",
            borderwidth=0,
            padding=4,
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", "#313244")],
            foreground=[("readonly", "#cdd6f4")],
            selectbackground=[("readonly", "#313244")],
            selectforeground=[("readonly", "#cdd6f4")],
        )

        self.interval_var = tk.StringVar(value="1.5s (Fast)")
        self.interval_dropdown = ttk.Combobox(
            controls_frame,
            textvariable=self.interval_var,
            values=list(INTERVAL_OPTIONS.keys()),
            state="readonly",
            width=16,
            font=("Segoe UI", 9),
            style="Dark.TCombobox",
        )
        self.interval_dropdown.pack(side=tk.LEFT, padx=(0, 12))
        self.interval_dropdown.bind(
            "<<ComboboxSelected>>", self.on_interval_change
        )

        self.info_btn = tk.Button(
            controls_frame,
            text="Open Info Tab",
            font=("Segoe UI", 10, "bold"),
            bg="#89b4fa",
            fg="#11111b",
            relief=tk.FLAT,
            padx=12,
            pady=4,
            cursor="hand2",
            command=lambda: webbrowser.open("http://127.0.0.1:5000"),
        )
        self.info_btn.pack(side=tk.LEFT, padx=(0, 8))


        self.stop_btn = tk.Button(
            controls_frame,
            text="Stop & Save DB",
            font=("Segoe UI", 10, "bold"),
            bg="#f38ba8",
            fg="#11111b",
            relief=tk.FLAT,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self.stop_logger,
        )
        self.stop_btn.pack(side=tk.LEFT)

        self.detail_label = tk.Label(
            self.root,
            text=f"Initializing first network check... ({self.session_id})",
            font=("Segoe UI", 9),
            fg="#cdd6f4",
            bg="#1e1e2e",
        )
        self.detail_label.pack(anchor="w", padx=15)

        self.fig = Figure(figsize=(7.4, 3.4), dpi=100, facecolor="#1e1e2e")
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor("#181825")
        self.ax.set_title(
            "Waiting for first data point...", color="#cdd6f4", fontsize=10
        )

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.get_tk_widget().pack(
            fill=tk.BOTH, expand=True, padx=15, pady=10
        )
        self.canvas.draw()

        self.root.protocol("WM_DELETE_WINDOW", self.stop_logger)

    def on_interval_change(self, event=None):
        selected = self.interval_var.get()
        if selected in INTERVAL_OPTIONS:
            self.check_interval = INTERVAL_OPTIONS[selected]
            if len(self.times) > 0:
                self.draw_graph()

    def is_wifi_connected(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(1.2)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return True, local_ip
        except Exception:
            return False, None

    def measure_ping(self, host="8.8.8.8"):
        param = "-n" if platform.system().lower() == "windows" else "-c"
        command = ["ping", param, "1", host]
        try:
            startupinfo = None
            if platform.system().lower() == "windows":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            output = subprocess.check_output(
                command,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                timeout=1.2,
                startupinfo=startupinfo,
            )
            match = re.search(
                r"time[=<]\s*(\d+\.?\d*)\s*ms", output, re.IGNORECASE
            )
            if match:
                return True, float(match.group(1))
            return True, 1.0
        except Exception:
            return False, None

    def diagnose_network(self):
        connected, ip = self.is_wifi_connected()
        if not connected:
            return (
                "WIFI_DISCONNECTED",
                0.0,
                "Wi-Fi adapter disconnected (No local IP)",
            )

        internet_ok, ping_ms = self.measure_ping("8.8.8.8")
        if not internet_ok:
            return (
                "NO_INTERNET",
                0.0,
                f"Connected to router ({ip}), but ISP is unreachable",
            )

        if ping_ms > HIGH_PING_THRESHOLD_MS:
            return (
                "HEAVY_TRAFFIC",
                ping_ms,
                f"Heavy traffic / congestion ({ping_ms} ms)",
            )

        return "HEALTHY", ping_ms, f"Stable connection ({ping_ms} ms)"

    def log_to_db(self, now, status, ping_ms, details):
        """Saves status changes and ongoing faults directly to MySQL."""
        logged_ping = (
            -1.0 if status in ("WIFI_DISCONNECTED", "NO_INTERNET") else ping_ms
        )
        add_pingguard_record(self.session_id, status, logged_ping, details, now)

    def telemetry_worker(self):
        while not self.stop_event.is_set():
            start_time = datetime.now()
            status, ping_ms, details = self.diagnose_network()

            if status != self.last_status or status != "HEALTHY":
                self.log_to_db(start_time, status, ping_ms, details)
                self.last_status = status

            if not self.stop_event.is_set():
                self.root.after(
                    0, self.update_ui, start_time, status, ping_ms, details
                )

            target_interval = self.check_interval
            elapsed = (datetime.now() - start_time).total_seconds()
            remaining = max(0.05, target_interval - elapsed)

            while remaining > 0 and not self.stop_event.is_set():
                if self.check_interval < target_interval:
                    break
                step = min(0.2, remaining)
                self.stop_event.wait(step)
                remaining -= step

    def update_ui(self, now, status, ping_ms, details):
        if self.stop_event.is_set():
            return

        color_map = {
            "HEALTHY": "#a6e3a1",
            "HEAVY_TRAFFIC": "#fab387",
            "NO_INTERNET": "#f38ba8",
            "WIFI_DISCONNECTED": "#cba6f7",
        }
        self.status_label.config(
            text=f"Status: {status}", fg=color_map.get(status, "#cdd6f4")
        )
        self.detail_label.config(
            text=f"Last Check: {now.strftime('%H:%M:%S')}  |  {details}  |  Saved to MySQL ({self.session_id})"
        )

        self.times.append(now.strftime("%H:%M:%S"))
        self.pings.append(ping_ms)
        self.statuses.append(status)
        self.draw_graph()

    def draw_graph(self):
        self.ax.clear()
        self.ax.set_facecolor("#181825")

        x_vals = list(self.times)
        y_vals = list(self.pings)

        self.ax.plot(
            x_vals, y_vals, color="#89b4fa", linewidth=2, label="Latency (ms)"
        )
        self.ax.fill_between(x_vals, y_vals, color="#89b4fa", alpha=0.15)

        self.ax.axhline(
            HIGH_PING_THRESHOLD_MS,
            color="#f9e2af",
            linestyle="--",
            linewidth=1,
            label="Congestion Threshold (150ms)",
        )

        for i, status in enumerate(self.statuses):
            if status in ("WIFI_DISCONNECTED", "NO_INTERNET"):
                self.ax.scatter(
                    x_vals[i], 0, color="#f38ba8", s=55, zorder=5, label="Outage"
                )
            elif status == "HEAVY_TRAFFIC":
                self.ax.scatter(
                    x_vals[i],
                    y_vals[i],
                    color="#fab387",
                    s=45,
                                        zorder=5,
                    label="Congestion",
                )

        interval_display = (
            f"{int(self.check_interval // 60)}m"
            if self.check_interval >= 60
            else f"{self.check_interval:g}s"
        )
        self.ax.set_title(
            f"Real-Time Network Latency & Load ({interval_display} Interval)",
            color="#cdd6f4",
            fontsize=10,
        )
        self.ax.set_ylabel("Ping (ms)", color="#cdd6f4", fontsize=9)
        self.ax.tick_params(colors="#a6adc8", labelsize=8)
        self.ax.grid(True, color="#313244", linestyle=":", linewidth=0.7)

        if len(x_vals) > 8:
            step = max(1, len(x_vals) // 6)
            self.ax.set_xticks(range(0, len(x_vals), step))
            self.ax.set_xticklabels(
                [x_vals[i] for i in range(0, len(x_vals), step)]
            )

        handles, labels = self.ax.get_legend_handles_labels()
        by_label = dict(zip(labels, handles))
        if by_label:
            self.ax.legend(
                by_label.values(),
                by_label.keys(),
                loc="upper left",
                facecolor="#1e1e2e",
                edgecolor="#313244",
                labelcolor="#cdd6f4",
                fontsize=8,
            )

        self.fig.tight_layout()
        self.canvas.draw()

    def listen_terminal_end(self):
        while not self.stop_event.is_set():
            try:
                if input().strip().lower() == "end":
                    self.root.after(0, self.stop_logger)
                    break
            except EOFError:
                break

    def stop_logger(self):
        if not self.stop_event.is_set():
            self.stop_event.set()
            print(f"Logger stopped cleanly. All events saved to MySQL ({self.session_id}).")
            self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = PingGuardApp(root)
    root.mainloop()

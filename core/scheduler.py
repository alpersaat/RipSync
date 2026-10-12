import threading
import time
from datetime import datetime, date, time as dtime, timedelta
from typing import Dict, List, Optional, Callable, Any

DAY_NAMES_TR = {
    0: "Pazartesi",
    1: "Salı",
    2: "Çarşamba",
    3: "Perşembe",
    4: "Cuma",
    5: "Cumartesi",
    6: "Pazar"
}

def parse_time_str(t_str: str) -> dtime:
    """Parses 'HH:MM' string to datetime.time."""
    try:
        parts = t_str.strip().split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        return dtime(h, m, 0)
    except Exception:
        return dtime(2, 0, 0)

class DownloadScheduler:
    """
    IDM-style Download Queue Scheduler.
    Schedules automatic queue start and stop times (e.g. Start at 02:00, Stop at 07:00).
    Supports day-of-week filters and actions when stopped (Pause all, Shutdown, Sleep).
    """

    def __init__(self,
                 enabled: bool = False,
                 start_time: str = "02:00",
                 stop_enabled: bool = True,
                 stop_time: str = "07:00",
                 days: Optional[List[int]] = None,
                 on_stop_action: str = "pause_all",
                 auto_start_if_in_window: bool = True):
        self.enabled = enabled
        self.start_time_str = start_time
        self.stop_enabled = stop_enabled
        self.stop_time_str = stop_time
        self.days = days if days is not None else [0, 1, 2, 3, 4, 5, 6]
        self.on_stop_action = on_stop_action
        self.auto_start_if_in_window = auto_start_if_in_window

        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_running = False

        # State tracking
        self._last_window_state: Optional[bool] = None
        self._last_start_trigger_date: Optional[date] = None
        self._last_stop_trigger_date: Optional[date] = None

        # Callbacks
        self.on_schedule_start: Optional[Callable[[], None]] = None
        self.on_schedule_stop: Optional[Callable[[str], None]] = None
        self.on_tick: Optional[Callable[[Dict[str, Any]], None]] = None

    def update_config(self,
                      enabled: Optional[bool] = None,
                      start_time: Optional[str] = None,
                      stop_enabled: Optional[bool] = None,
                      stop_time: Optional[str] = None,
                      days: Optional[List[int]] = None,
                      on_stop_action: Optional[str] = None,
                      auto_start_if_in_window: Optional[bool] = None):
        with self._lock:
            if enabled is not None:
                self.enabled = enabled
            if start_time is not None:
                self.start_time_str = start_time
            if stop_enabled is not None:
                self.stop_enabled = stop_enabled
            if stop_time is not None:
                self.stop_time_str = stop_time
            if days is not None:
                self.days = list(days)
            if on_stop_action is not None:
                self.on_stop_action = on_stop_action
            if auto_start_if_in_window is not None:
                self.auto_start_if_in_window = auto_start_if_in_window

            # Reset window state so recalculations take effect immediately
            self._last_window_state = None

    def start(self):
        with self._lock:
            if self._is_running:
                return
            self._is_running = True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True, name="SchedulerWorker")
            self._thread.start()

    def stop(self):
        with self._lock:
            if not self._is_running:
                return
            self._is_running = False
            self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)

    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception as e:
                print(f"[DownloadScheduler] Error in tick: {e}")
            # Wait 1 second or until stopped
            if self._stop_event.wait(1.0):
                break

    def is_in_schedule_window(self, now: Optional[datetime] = None) -> bool:
        """Determines whether current time falls within active start-stop window."""
        now_dt = now or datetime.now()
        start_t = parse_time_str(self.start_time_str)

        if not self.stop_enabled:
            # If no stop time defined, active window starts at start_time and lasts 1 minute for trigger
            return False

        stop_t = parse_time_str(self.stop_time_str)
        curr_t = now_dt.time()

        if start_t < stop_t:
            return start_t <= curr_t < stop_t
        elif start_t > stop_t:
            # Crosses midnight (e.g. 23:00 to 06:00)
            return (curr_t >= start_t) or (curr_t < stop_t)
        else:
            return False

    def is_day_active(self, dt: Optional[datetime] = None) -> bool:
        dt = dt or datetime.now()
        return dt.weekday() in self.days

    def get_status(self, now: Optional[datetime] = None) -> Dict[str, Any]:
        """Calculates current status, remaining time, and next scheduled event."""
        now_dt = now or datetime.now()
        with self._lock:
            enabled = self.enabled
            start_str = self.start_time_str
            stop_str = self.stop_time_str
            stop_en = self.stop_enabled
            days = list(self.days)
            action = self.on_stop_action

        if not enabled:
            return {
                "enabled": False,
                "is_in_window": False,
                "state_text": "Zamanlayıcı Kapalı",
                "detail_text": f"Zamanlama: {start_str} - {stop_str}",
                "next_event": None,
                "next_event_time_str": "",
                "time_remaining_str": "--",
                "seconds_remaining": 0,
                "start_time_str": start_str,
                "stop_time_str": stop_str,
                "stop_enabled": stop_en,
                "on_stop_action": action,
                "days": days
            }

        start_t = parse_time_str(start_str)
        stop_t = parse_time_str(stop_str)
        in_window = self.is_in_schedule_window(now_dt) and self.is_day_active(now_dt)

        if in_window and stop_en:
            # Inside window: next event is STOP
            # Calculate target stop datetime
            if start_t < stop_t:
                target_stop = datetime.combine(now_dt.date(), stop_t)
            else:
                # Crosses midnight
                if now_dt.time() >= start_t:
                    target_stop = datetime.combine(now_dt.date() + timedelta(days=1), stop_t)
                else:
                    target_stop = datetime.combine(now_dt.date(), stop_t)

            rem_secs = max(0, int((target_stop - now_dt).total_seconds()))
            rem_str = self._format_duration(rem_secs)
            state_text = f"İndiriliyor ({stop_str}'de duracak)"
            detail_text = f"Durdurmaya {rem_str} kaldı"
            next_event = "stop"
            next_event_time_str = stop_str
        else:
            # Outside window or waiting: next event is START
            # Find next active day with start_t
            target_start = None
            # Check today if not passed
            today_start = datetime.combine(now_dt.date(), start_t)
            if self.is_day_active(now_dt) and now_dt < today_start:
                target_start = today_start
            else:
                # Find next day
                for offset in range(1, 8):
                    cand = now_dt + timedelta(days=offset)
                    if cand.weekday() in days:
                        target_start = datetime.combine(cand.date(), start_t)
                        break

            if not target_start:
                target_start = today_start + timedelta(days=1)

            rem_secs = max(0, int((target_start - now_dt).total_seconds()))
            rem_str = self._format_duration(rem_secs)
            state_text = f"Beklemede ({start_str}'de başlayacak)"
            detail_text = f"Başlamaya {rem_str} kaldı"
            next_event = "start"
            next_event_time_str = start_str

        return {
            "enabled": True,
            "is_in_window": in_window,
            "state_text": state_text,
            "detail_text": detail_text,
            "next_event": next_event,
            "next_event_time_str": next_event_time_str,
            "time_remaining_str": rem_str,
            "seconds_remaining": rem_secs,
            "start_time_str": start_str,
            "stop_time_str": stop_str,
            "stop_enabled": stop_en,
            "on_stop_action": action,
            "days": days
        }

    def _format_duration(self, seconds: int) -> str:
        if seconds <= 0:
            return "0 sn"
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        secs = seconds % 60
        if hours > 0:
            return f"{hours} sa {mins:02d} dk"
        elif mins > 0:
            return f"{mins} dk {secs:02d} sn"
        else:
            return f"{secs} sn"

    def tick(self, now: Optional[datetime] = None):
        """Single tick step called every second."""
        now_dt = now or datetime.now()
        with self._lock:
            if not self.enabled:
                self._last_window_state = False
                return

        status = self.get_status(now_dt)
        curr_in_window = status["is_in_window"]
        today = now_dt.date()

        start_t = parse_time_str(self.start_time_str)
        stop_t = parse_time_str(self.stop_time_str)

        # 1. Exact minute trigger for START
        if (self.is_day_active(now_dt) and
            now_dt.hour == start_t.hour and
            now_dt.minute == start_t.minute and
            self._last_start_trigger_date != today):
            self._last_start_trigger_date = today
            self._trigger_start()

        # 2. Exact minute trigger for STOP
        if (self.stop_enabled and
            now_dt.hour == stop_t.hour and
            now_dt.minute == stop_t.minute and
            self._last_stop_trigger_date != today):
            self._last_stop_trigger_date = today
            self._trigger_stop()

        # 3. Transition check
        if self._last_window_state is not None:
            # Transitioned into active window
            if not self._last_window_state and curr_in_window:
                if self.auto_start_if_in_window and self._last_start_trigger_date != today:
                    self._last_start_trigger_date = today
                    self._trigger_start()
            # Transitioned out of active window
            elif self._last_window_state and not curr_in_window:
                if self.stop_enabled and self._last_stop_trigger_date != today:
                    self._last_stop_trigger_date = today
                    self._trigger_stop()
        else:
            # First tick when scheduler starts
            if curr_in_window and self.auto_start_if_in_window and self._last_start_trigger_date != today:
                self._last_start_trigger_date = today
                self._trigger_start()

        self._last_window_state = curr_in_window

        # Notify tick callback
        if self.on_tick:
            try:
                self.on_tick(status)
            except Exception as e:
                print(f"[DownloadScheduler] Error in on_tick callback: {e}")

    def _trigger_start(self):
        print("[DownloadScheduler] Starting scheduled download queue...")
        if self.on_schedule_start:
            try:
                self.on_schedule_start()
            except Exception as e:
                print(f"[DownloadScheduler] Error in on_schedule_start: {e}")

    def _trigger_stop(self):
        action = self.on_stop_action
        print(f"[DownloadScheduler] Stopping scheduled download queue (Action: {action})...")
        if self.on_schedule_stop:
            try:
                self.on_schedule_stop(action)
            except Exception as e:
                print(f"[DownloadScheduler] Error in on_schedule_stop: {e}")

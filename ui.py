"""
Tournament Planner UI.

Loads the tournament source data from the .TP database via
`import_tp_file.read_database()` and displays each returned dataframe
("players", "events", "matches", "time_slots") in its own tab.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime

from import_tp_file import read_database
import pandas as pd

# The dataframes we expect from read_database(), in display order.
DATAFRAME_ORDER = ["players", "events", "matches", "time_slots"]

# Editable planner parameters, in display order.
# Each entry is (key, label, default value). Add new parameters here and they
# automatically show up in the "Parameters..." dialog.
PARAMETER_DEFINITIONS = [
    ("rounds_between_matches", "Rounds between matches", 0),
]


class TournamentPlannerUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Tournament Planner - Source Data Viewer")
        self.root.geometry("1200x800")

        self.data = None
        # Editable planner parameters (key -> value), seeded from the defaults.
        self.parameters = {
            key: default for key, _label, default in PARAMETER_DEFINITIONS
        }
        # Callables that re-render each data-bound widget; run by refresh().
        self._refreshers = []
        # Match ids planned most recently, highlighted in the time slot view.
        self._last_added_matches = set()

        self._build_menu()
        self._build_toolbar()
        self._build_main_area()
        self._show_welcome()

    def refresh(self):
        """Re-render every data-bound widget from the current self.data.

        Widgets register a refresher callable in self._refreshers; call this
        once after any data mutation.
        """
        for refresher in self._refreshers:
            refresher()

        if isinstance(self.data, dict):
            summary = ", ".join(
                f"{name}: {df.shape[0]} rows" for name, df in self.data.items()
            )
            self.status_var.set(summary)

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Load database...", command=self._load_database)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        self.root.config(menu=menubar)

    def _build_toolbar(self):
        toolbar = ttk.Frame(self.root, padding=5)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(toolbar, text="Load database", command=self._load_database).pack(
            side=tk.LEFT, padx=5
        )

        ttk.Button(
            toolbar, text="Parameters...", command=self._open_parameters_dialog
        ).pack(side=tk.LEFT, padx=5)

        self.status_var = tk.StringVar(value="No database loaded.")
        ttk.Label(toolbar, textvariable=self.status_var).pack(side=tk.LEFT, padx=10)

    def _open_parameters_dialog(self):
        """Open a modal dialog for editing the planner parameters.

        The dialog is built from PARAMETER_DEFINITIONS, so new parameters only
        need to be added there. Values are validated as integers and only
        written back to self.parameters when the user confirms.
        """
        dialog = tk.Toplevel(self.root)
        dialog.title("Parameters")
        dialog.transient(self.root)
        dialog.resizable(False, False)

        body = ttk.Frame(dialog, padding=10)
        body.pack(fill=tk.BOTH, expand=True)

        entries = {}
        for row, (key, label, _default) in enumerate(PARAMETER_DEFINITIONS):
            ttk.Label(body, text=label).grid(
                row=row, column=0, sticky=tk.W, padx=(0, 10), pady=3
            )
            var = tk.StringVar(value=str(self.parameters.get(key, "")))
            ttk.Entry(body, textvariable=var, width=12).grid(
                row=row, column=1, sticky=tk.EW, pady=3
            )
            entries[key] = var

        def on_ok():
            new_values = {}
            for key, _label, _default in PARAMETER_DEFINITIONS:
                raw = entries[key].get().strip()
                try:
                    new_values[key] = int(raw)
                except ValueError:
                    messagebox.showerror(
                        "Invalid value",
                        f"'{raw}' is not a valid whole number.",
                        parent=dialog,
                    )
                    return
            self.parameters.update(new_values)
            dialog.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(
            row=len(PARAMETER_DEFINITIONS), column=0, columnspan=2,
            sticky=tk.E, pady=(10, 0),
        )
        ttk.Button(buttons, text="OK", command=on_ok).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT)

        # Center the dialog over the main window and make it modal.
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        dialog.grab_set()
        dialog.wait_window()

    def _build_main_area(self):
        self.main_frame = ttk.Frame(self.root, padding=5)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

    def _clear_tabs(self):
        # Widgets are destroyed on rebuild, so drop their refreshers too.
        self._refreshers = []
        for tab_id in self.notebook.tabs():
            self.notebook.forget(tab_id)

    def _show_welcome(self):
        """Placeholder tab shown before any data is loaded."""
        self._clear_tabs()
        tab = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(tab, text="  Welcome  ")
        ttk.Label(
            tab,
            text="Click 'Load database' to read the tournament source data.",
            font=("TkDefaultFont", 12),
        ).pack(anchor=tk.W)

    def _load_database(self):
        path = filedialog.askopenfilename(
            title="Select tournament database",
            filetypes=[
                ("Tournament Planner database", "*.TP"),
                ("Access database", "*.mdb *.accdb"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        try:
            data = read_database(path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read the database:\n{e}")
            return

        # read_database() returns the int 1 on failure.
        if not isinstance(data, dict):
            messagebox.showerror(
                "Error",
                "Could not read the .TP database.\n"
                "Check the connection settings and PATH in import_tp_file.py.",
            )
            return

        self.data = data
        self._populate_tables(data)

        summary = ", ".join(
            f"{name}: {df.shape[0]} rows" for name, df in data.items()
        )
        self.status_var.set(summary)

    def _populate_tables(self, data):
        """Create one tab (with a Treeview) per dataframe."""
        self._clear_tabs()

        # Combined planner view shown first.
        self._build_planner_view(data)

        names = [n for n in DATAFRAME_ORDER if n in data]
        names += [n for n in data if n not in DATAFRAME_ORDER]

        for name in names:
            tab = ttk.Frame(self.notebook, padding=5)
            self.notebook.add(tab, text=f"  {name} ({data[name].shape[0]})  ")
            self._build_dataframe_table(
                tab,
                data[name],
                source=lambda n=name: data[n],
            )
            # Keep the tab label's row count in sync on refresh.
            self._refreshers.append(
                lambda t=tab, n=name: self.notebook.tab(t, text=f"  {n} ({data[n].shape[0]})  ")
            )

    def _build_planner_view(self, data):
        """Combined planner view.

        Right side: the time_slots dataframe.
        Left side: two stacked views -- the events dataframe on top and a
        placeholder view below that can be filled in later.
        """
        tab = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(tab, text="  Planner  ")

        # Horizontal split between the left column and the time slots.
        outer = ttk.PanedWindow(tab, orient=tk.HORIZONTAL)
        outer.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(outer, width=300)
        right = ttk.Frame(outer)
        outer.add(left, weight=1)
        outer.add(right, weight=1)

        # Left column: events on top, placeholder below.
        left_panes = ttk.PanedWindow(left, orient=tk.VERTICAL)
        left_panes.pack(fill=tk.BOTH, expand=True)

        events_frame = ttk.LabelFrame(left_panes, text="Events", padding=5)
        placeholder_frame = ttk.LabelFrame(left_panes, text="Placeholder", padding=5)

        left_panes.add(events_frame, weight=1)
        left_panes.add(placeholder_frame, weight=1)

        if "events" in data:
            events_treeview = self._build_dataframe_table(
                events_frame,
                data['events'],
                source=lambda: data['events'].sort_values('rounds', ascending=False),
            )

        # Right column: time slots.
        schema_frame = ttk.LabelFrame(right, text="Time slots", padding=5)
        schema_frame.pack(fill=tk.BOTH, expand=True)
        self._build_schema_view(
            schema_frame, data["time_slots"], data["matches"], data["players"]
        )

        # Action buttons shown below the events table.
        events_buttons = ttk.Frame(events_frame)
        events_buttons.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        ttk.Button(
            events_buttons,
            text="Add selected",
            command=lambda: self._on_add_selected(data, events_treeview),
        ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(
            events_buttons,
            text="Finish planning firsts",
            command=lambda: self._on_finish_planning_firsts(data, events_treeview),
        ).pack(side=tk.LEFT)

    def _build_schema_view(self, parent, time_slots, matches, players):
        """
        Right side view of the planner, a row per court per timeslot.
        """
        table = ttk.Treeview(parent, columns=('slot', 'match_id', 'event', 'round', 'team_a', 'team_b'), show="headings")
        table.heading("slot", text="slot")
        table.heading("match_id", text="match_id")
        table.heading("event", text="event")
        table.heading("round", text="round")
        table.heading("team_a", text="team_a")
        table.heading("team_b", text="team_b")
        table.column("slot", width=200, anchor=tk.W, stretch=False)
        table.column("match_id", width=80, anchor=tk.W, stretch=False)
        table.column("event", width=80, anchor=tk.W, stretch=False)
        table.column("round", width=120, anchor=tk.W, stretch=False)
        table.column("team_a", width=160, anchor=tk.W, stretch=False)
        table.column("team_b", width=160, anchor=tk.W, stretch=False)

        table.tag_configure("separator", foreground="gray")
        # Highlight matches that were planned most recently.
        table.tag_configure("added", background="#d6f5d6")

        v_scroll = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=table.yview)
        h_scroll = ttk.Scrollbar(parent, orient=tk.HORIZONTAL, command=table.xview)
        table.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        table.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)

        # Lookup of player id -> display name ("J. Jansen" / "J. van der Jansen").
        player_names = self._player_name_lookup(players)

        def repopulate():
            match_by_id = {}
            if matches is not None and not matches.empty:
                id_col = "id"
                for _, row in matches.iterrows():
                    match_by_id[str(row[id_col])] = row

            table.delete(*table.get_children())
            added_items = []
            for index, time_slot in time_slots.iterrows():
                planned_matches = time_slot['matches']
                slot_label = self._format_slot_time(time_slot.get('start_time', ''))
                for i, match_id in enumerate(planned_matches):
                    match = match_by_id[match_id]
                    is_added = str(match_id) in self._last_added_matches
                    # Show the slot's ISO datetime on the first row of the slot.
                    slot_cell = slot_label if i == 0 else ""
                    item = table.insert(
                        "",
                        "end",
                        values=(slot_cell, match['id'], match['event'], match['round'], self._format_team(match['team_a'], player_names), self._format_team(match['team_b'], player_names)),
                        tags=("added",) if is_added else (),
                    )
                    if is_added:
                        added_items.append(item)
                total_courts = time_slot['court_count']
                used_courts = len(planned_matches)
                for j in range(total_courts - used_courts):
                    # Still show the slot datetime if the slot has no matches.
                    slot_cell = slot_label if (used_courts == 0 and j == 0) else ""
                    table.insert("", "end", values=(slot_cell,))
                # separator between timeslots
                table.insert(
                    "",
                    "end",
                    values=("────────", "────────"),
                    tags=("separator",)
                )

            # Scroll minimally so the last added match is visible; this keeps
            # the whole added block in view while leaving the preceding
            # matches visible above it.
            if added_items:
                table.see(added_items[-1])

        repopulate()
        self._refreshers.append(repopulate)

    def _on_add_selected(self, data, events_treeview):
        """Plan a round with the matches of the event that are selected"""
        selected_tree_id = events_treeview.selection()
        if selected_tree_id:
            selected_event = data['events'].loc[int(selected_tree_id[0])]
            self._plan_round_of_event(data, selected_event['id'])
            self.refresh()

    def _on_finish_planning_firsts(self, data, events_treeview):
        """
        Plan a round of the event with the most rounds left
        """
        items = events_treeview.get_children()

        if items:
            first_tree_id = items[0]
            selected_event = data["events"].loc[int(first_tree_id)]
            self._plan_round_of_event(data, selected_event["id"])
            self.refresh()

    def _plan_round_of_event(self, data, event_id):
        """
        Plan a round of the given event
        """
        matches_to_plan = self._next_unplanned_round_of_event(data, event_id)
        if matches_to_plan is None or matches_to_plan.empty:
            return

        matches = data["matches"]
        time_slots = data["time_slots"]

        # Track which matches get planned now so the view can highlight them.
        self._last_added_matches = set()

        # A player can only play once per round. Walk the round's matches in
        # order and defer any match whose players are already scheduled in
        # this round, so it can be planned in a later round instead.
        players_in_round = set()
        pending_matches = []
        for _, match in matches_to_plan.iterrows():
            players_in_round |= set(match["team_a"]) | set(match["team_b"])
            pending_matches.append(match["id"])

        # Look up matches by id so we can inspect the players already planned
        # in a timeslot (possibly from a previous call).
        match_by_id = {str(row["id"]): row for _, row in matches.iterrows()}

        def players_of(match_id):
            match = match_by_id.get(str(match_id))
            if match is None:
                return set()
            return set(match["potential_players"])

        # Fill timeslots in order, never exceeding that slot's court count.
        # Overflow spills over into the next timeslot.
        rounds_between_matches = int(self.parameters.get("rounds_between_matches", 0))
        slot_rows = list(time_slots.iterrows())
        for position, (_, time_slot) in enumerate(slot_rows):
            if not pending_matches:
                break

            planned = time_slot["matches"]
            free_courts = int(time_slot["court_count"]) - len(planned)
            if free_courts <= 0:
                continue

            # Players already scheduled in this timeslot and the previous
            # `rounds_between_matches` timeslots, so a player is not planned
            # again too soon. Slots on a different day are ignored.
            slot_players = set()
            current_day = self._slot_date(time_slot.get("start_time", ""))
            first_relevant = max(0, position - rounds_between_matches)
            for _, other_slot in slot_rows[first_relevant:position + 1]:
                if self._slot_date(other_slot.get("start_time", "")) != current_day:
                    continue
                for existing_id in other_slot["matches"]:
                    slot_players |= players_of(existing_id)

            placed_here = 0
            remaining = []
            for match_id in pending_matches:
                if placed_here >= free_courts:
                    remaining.append(match_id)
                    continue
                players = players_of(match_id)
                if players & slot_players:
                    # A player is already busy in this timeslot; defer.
                    remaining.append(match_id)
                    continue
                planned.append(match_id)
                slot_players |= players
                placed_here += 1
                self._last_added_matches.add(str(match_id))
                matches.loc[matches["id"] == match_id, "timeslot_id"] = time_slot["id"]
            pending_matches = remaining

        # One round of this event is now planned; decrement the rounds left.
        events = data["events"]
        events.loc[events["id"] == event_id, "rounds"] -= 1



    def _next_unplanned_round_of_event(self, data, event_id):
        """
        Get the matches for the next unplanned round of the event.
        Does not plan or modify the matches yet.
        """
        matches = data["matches"]

        # Only matches for this event that haven't been planned
        event_matches = matches[
            (matches["event_id"] == event_id)
            & (matches["timeslot_id"].isna() | (matches["timeslot_id"] == ""))
        ].copy()

        if event_matches.empty:
            return event_matches

        # Groep rounds take priority
        is_groep = event_matches["round"].str.startswith("Groep", na=False)
        groep_matches = event_matches[is_groep]

        if not groep_matches.empty:
            # Get the next Groep round
            next_roundnr = groep_matches["roundnr"].min()

            return groep_matches[
                groep_matches["roundnr"] == next_roundnr
            ]

        # No unplanned Groep rounds remain.
        # Get all matches in the next roundnr.
        next_roundnr = event_matches["roundnr"].min()

        return event_matches[
            event_matches["roundnr"] == next_roundnr
        ]


    def _build_dataframe_table(self, parent, df, source=None):
        """Render a pandas DataFrame into a scrollable ttk.Treeview.

        `source`, if given, is a zero-arg callable returning the dataframe to
        display. It is re-invoked on refresh() so the table tracks live data
        even when `df` is a derived copy (e.g. a sorted view).
        """
        if source is None:
            source = lambda: df
        columns = list(df.columns)

        tree = ttk.Treeview(parent, columns=columns, show="headings", height=25)

        # Sorting state for this table: which column and direction.
        sort_state = {"column": None, "reverse": False}

        def populate(dataframe):
            """(Re)fill the tree from a dataframe."""
            tree.delete(*tree.get_children())
            for idx, row in dataframe.iterrows():
                values = [self._format_cell(row[col]) for col in columns]
                tree.insert("", tk.END, iid=str(idx), values=values)

        def update_heading_labels():
            for col in columns:
                label = str(col)
                if col == sort_state["column"]:
                    label += " \u25BC" if sort_state["reverse"] else " \u25B2"
                tree.heading(col, text=label)

        def sort_by(col):
            """Sort by a column, toggling direction on repeated clicks."""
            if sort_state["column"] == col:
                sort_state["reverse"] = not sort_state["reverse"]
            else:
                sort_state["column"] = col
                sort_state["reverse"] = False
            reverse = sort_state["reverse"]

            current = source()
            ascending = not reverse
            try:
                numeric_col = pd.to_numeric(current[col], errors="coerce")
                if numeric_col.notna().all():
                    sorted_df = current.loc[numeric_col.sort_values(ascending=ascending).index]
                else:
                    sorted_df = current.sort_values(by=col, ascending=ascending)
            except TypeError:
                # Mixed/unhashable values (e.g. lists): sort on display text.
                order = (
                    current[col]
                    .map(self._format_cell)
                    .sort_values(ascending=ascending)
                    .index
                )
                sorted_df = current.loc[order]

            populate(sorted_df)
            update_heading_labels()

        # Size columns based on the widest of header / a sample of values.
        sample = df.head(50)
        for col in columns:
            widths = [len(str(col))]
            widths += [len(self._format_cell(v)) for v in sample[col]]
            width = min(max(widths) * 8 + 20, 400)

            tree.heading(col, text=str(col), command=lambda c=col: sort_by(c))
            tree.column(col, width=width, anchor=tk.W, stretch=False)

        populate(source())

        # Re-render this table whenever central refresh() runs.
        self._refreshers.append(lambda: populate(source()))

        v_scroll = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
        h_scroll = ttk.Scrollbar(parent, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        tree.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)

        return tree

    @classmethod
    def _player_name_lookup(cls, players):
        """Build a mapping of player id -> display name from the players df."""
        lookup = {}
        if players is not None and not players.empty:
            for _, player in players.iterrows():
                lookup[str(player["id"])] = cls._format_player_name(player)
        return lookup

    @staticmethod
    def _format_team(team, player_names):
        """Render a team (list of player ids) as names joined by 'and'."""
        if team is None:
            return ""
        if isinstance(team, str):
            team = [team] if team else []
        names = [player_names.get(str(pid), str(pid)) for pid in team]
        return " and ".join(names)

    @staticmethod
    def _format_player_name(player):
        """Format a player row as "J. Jansen" or "J. van der Jansen".

        The first name is reduced to its initial; the middle name (if any) is
        kept in full between the initial and the last name.
        """
        firstname = str(player.get("firstname") or "").strip()
        middlename = str(player.get("middlename") or "").strip()
        lastname = str(player.get("lastname") or "").strip()

        initial = f"{firstname[0]}." if firstname else ""
        parts = [p for p in (initial, middlename, lastname) if p]
        return " ".join(parts) if parts else str(player.get("id", ""))

    @staticmethod
    def _format_cell(value):
        """Turn a cell value into a display string, flattening lists/tuples."""
        if isinstance(value, (list, tuple, set)):
            return ", ".join(str(v) for v in value)
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _format_slot_time(value):
        """Format a slot's ISO start_time, converting to the local timezone.

        The stored value carries the Netherlands offset (CET/CEST); convert it
        to the machine's local timezone so the label always reflects the real
        wall-clock time.
        """
        if value is None or value == "":
            return ""
        try:
            dt = datetime.fromisoformat(str(value))
        except ValueError:
            return str(value)
        if dt.tzinfo is not None:
            dt = dt.astimezone()
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _slot_date(value):
        """Return the local calendar date of a slot's ISO start_time.

        Used to tell whether two timeslots fall on the same day. Returns None
        when the value is missing or unparseable.
        """
        if value is None or value == "":
            return None
        try:
            dt = datetime.fromisoformat(str(value))
        except ValueError:
            return None
        if dt.tzinfo is not None:
            dt = dt.astimezone()
        return dt.date()


def show_planner_ui():
    """Launch the interactive tournament planner UI window."""
    root = tk.Tk()
    app = TournamentPlannerUI(root)
    root.mainloop()


if __name__ == "__main__":
    show_planner_ui()
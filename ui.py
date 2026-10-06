"""
Tournament Planner UI.

Loads the tournament source data from the .TP database via
`import_tp_file.read_database()` and displays each returned dataframe
("players", "events", "matches", "time_slots") in its own tab.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from collections import defaultdict
from datetime import datetime

from import_tp_file import read_database, write_planning
import pandas as pd

# The dataframes we expect from read_database(), in display order.
DATAFRAME_ORDER = ["players", "events", "matches", "time_slots"]

# Editable planner parameters, in display order.
# Each entry is (key, label, default value). Add new parameters here and they
# automatically show up in the "Parameters" dialog.
PARAMETER_DEFINITIONS = [
    ("timeslots_between_matches", "Timeslots between matches", 0),
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
        # Match ids highlighted in the time slot view. Holds either the matches
        # planned most recently or the matches around a player's largest gap.
        self._highlighted_matches = set()
        # When True, the next time slot re-render scrolls to the first
        # highlighted match instead of the last one.
        self._scroll_to_first_highlight = False
        # Player id whose gap row is selected in the player gaps view. Kept so
        # the selection (and its blue highlight) survives the table rebuild
        # that refresh() performs.
        self._selected_gap_player = None
        # The window listing a player's matches, and the player it shows.
        self._player_window = None
        self._player_window_player = None
        # Whether the player window lists potential matches (opened from the
        # Potential tab) or only actual matches (opened from the Actual tab).
        self._player_window_use_potential = False

        # Look up matches by id so we can inspect the players already planned
        # in a timeslot (possibly from a previous call).
        self._match_by_id = {}
        # Path of the .TP database the current data was loaded from, used as
        # the source when saving the planning back to a new .TP file.
        self._source_path = None

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

        # Keep the player window in sync with the current planning.
        if (
            self._player_window is not None
            and self._player_window.winfo_exists()
            and self._player_window_player is not None
        ):
            self._open_player_window(
                self._player_window_player,
                use_potential=self._player_window_use_potential,
            )

        if isinstance(self.data, dict):
            summary = ", ".join(
                f"{name}: {df.shape[0]} rows" for name, df in self.data.items()
            )
            self.status_var.set(summary)

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Load database", command=self._load_database)
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
            toolbar, text="Parameters", command=self._open_parameters_dialog
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            toolbar, text="Save planning", command=self._save_planning
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
        self._source_path = path
        # Look up matches by id so we can inspect the players already planned
        # in a timeslot (possibly from a previous call).
        self._match_by_id = {str(row["id"]): row for _, row in data["matches"].iterrows()}
        self._populate_tables(data)

        summary = ", ".join(
            f"{name}: {df.shape[0]} rows" for name, df in data.items()
        )
        self.status_var.set(summary)

    def _save_planning(self):
        """Write the current planning into a new .TP database file.

        Asks for a target file, then copies the loaded source database and
        writes each planned match's timeslot into `PlayerMatch.plandate`.
        """
        if self.data is None or self._source_path is None:
            messagebox.showinfo(
                "No database",
                "Load a .TP database before saving the planning.",
            )
            return

        path = filedialog.asksaveasfilename(
            title="Save planning to a new .TP database",
            defaultextension=".TP",
            initialfile="planning.TP",
            filetypes=[
                ("Tournament Planner database", "*.TP"),
                ("Access database", "*.mdb *.accdb"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        try:
            written = write_planning(self._source_path, path, self.data)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save the planning:\n{e}")
            return

        messagebox.showinfo(
            "Planning saved",
            f"Wrote the planning for {written} matches to:\n{path}",
        )

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
        Left side: two stacked views -- the events dataframe on top and the
        per-player empty-timeslot gap statistics below.
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

        # Left column: events on top, player gaps below.
        left_panes = ttk.PanedWindow(left, orient=tk.VERTICAL)
        left_panes.pack(fill=tk.BOTH, expand=True)

        events_frame = ttk.LabelFrame(left_panes, text="Events", padding=5)
        gaps_frame = ttk.LabelFrame(left_panes, text="Player gaps", padding=5)

        left_panes.add(events_frame, weight=1)
        left_panes.add(gaps_frame, weight=1)

        if "events" in data:
            events_treeview = self._build_dataframe_table(
                events_frame,
                data['events'],
                source=lambda: data['events'].sort_values('rounds', ascending=False),
            )

        # Bottom left: per-player empty-timeslot gap statistics.
        self._build_player_gaps_view(gaps_frame, data)

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
            command=lambda: self._on_finish_planning_firsts(data),
        ).pack(side=tk.LEFT)

    def _build_player_gaps_view(self, parent, data):
        """Bottom-left view: per-player empty-timeslot gap statistics.

        Two tabs: "Actual" counts the matches a player really plays
        (team_a/team_b), "Potential" counts every match a player could still
        play (potential_players). Both re-render on refresh() so they track
        the current planning.
        """
        notebook = ttk.Notebook(parent)
        notebook.pack(fill=tk.BOTH, expand=True)

        actual_tab = ttk.Frame(notebook, padding=2)
        potential_tab = ttk.Frame(notebook, padding=2)
        notebook.add(actual_tab, text="  Actual  ")
        notebook.add(potential_tab, text="  Potential  ")

        self._build_gap_table(actual_tab, data, use_potential=False)
        self._build_gap_table(potential_tab, data, use_potential=True)

    def _build_gap_table(self, parent, data, use_potential):
        """Build one gap-statistics table (actual or potential) in `parent`."""
        columns = ("name", "max_gap", "max_gap_matches", "avg_gap", "matches", "days")
        table = ttk.Treeview(parent, columns=columns, show="headings")
        for col, label, width in (
            ("name", "player", 160),
            ("max_gap", "max empty", 80),
            ("max_gap_matches", "matches at max gap", 200),
            ("avg_gap", "avg empty", 80),
            ("matches", "matches", 70),
            ("days", "days", 50),
        ):
            table.heading(col, text=label)
            table.column(col, width=width, anchor=tk.W, stretch=False)

        v_scroll = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=table.yview)
        h_scroll = ttk.Scrollbar(parent, orient=tk.HORIZONTAL, command=table.xview)
        table.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        table.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)

        # Maps a gap row's iid to the match ids surrounding that player's
        # largest gap, so a selection can highlight those matches. Kept per
        # table so the actual and potential views stay independent.
        gap_row_matches = {}

        def repopulate():
            stats = self._player_gap_stats(data, use_potential=use_potential)
            self._populate_player_gaps_table(table, stats, gap_row_matches)
            # Re-apply the selection so the clicked row stays highlighted blue
            # after the table is rebuilt.
            if self._selected_gap_player is not None:
                iid = str(self._selected_gap_player)
                if table.exists(iid):
                    table.selection_set(iid)

        repopulate()
        self._refreshers.append(repopulate)

        # Clicking a player row highlights the matches around their largest gap.
        table.bind(
            "<<TreeviewSelect>>",
            lambda _e: self._on_gap_selected(
                table, gap_row_matches, use_potential
            ),
        )

    def _on_gap_selected(self, table, gap_row_matches, use_potential):
        """Highlight the matches that contribute to the selected player's gap.

        The selected row maps to the match ids surrounding the largest gap.
        Those matches are highlighted in the time slot view and the view
        scrolls to the first of them. A second window lists all of the
        player's matches (potential matches when the Potential tab was used).
        """
        selection = table.selection()
        if not selection:
            return
        player_id = selection[0]
        # Ignore the re-selection that repopulate() performs after a rebuild;
        # only act when the user actually picks a different player.
        if player_id == self._selected_gap_player:
            return
        self._selected_gap_player = player_id
        match_ids = gap_row_matches.get(player_id, ())
        self._highlighted_matches = {str(m) for m in match_ids}
        self._scroll_to_first_highlight = True
        self.refresh()
        self._open_player_window(player_id, use_potential=use_potential)

    def _open_player_window(self, player_id, use_potential=False):
        """Open (or refresh) a window listing all matches of the given player.

        The window shows the player's planned matches in time-slot order,
        followed by their unplanned matches. With `use_potential` it lists
        every match the player could still play (potential_players); otherwise
        only the matches they are actually assigned to. It is reused when
        another player is clicked.
        """
        if self.data is None:
            return

        players = self.data["players"]
        player_names = self._player_name_lookup(players)
        player_name = player_names.get(str(player_id), str(player_id))

        # Reuse the existing window if it is still open.
        if self._player_window is not None and self._player_window.winfo_exists():
            window = self._player_window
            for child in window.winfo_children():
                child.destroy()
        else:
            window = tk.Toplevel(self.root)
            window.geometry("700x500")
            self._player_window = window

        self._player_window_player = str(player_id)
        self._player_window_use_potential = use_potential
        kind = "Potential matches" if use_potential else "Matches"
        window.title(f"{kind} - {player_name}")

        ttk.Label(
            window, text=player_name, font=("TkDefaultFont", 12, "bold")
        ).pack(anchor=tk.W, padx=10, pady=(10, 0))

        columns = ("slot", "match_id", "event", "round", "team_a", "team_b")
        table = ttk.Treeview(window, columns=columns, show="headings")
        for col, label, width in (
            ("slot", "slot", 180),
            ("match_id", "match_id", 80),
            ("event", "event", 80),
            ("round", "round", 120),
            ("team_a", "team_a", 150),
            ("team_b", "team_b", 150),
        ):
            table.heading(col, text=label)
            table.column(col, width=width, anchor=tk.W, stretch=False)

        v_scroll = ttk.Scrollbar(window, orient=tk.VERTICAL, command=table.yview)
        table.configure(yscrollcommand=v_scroll.set)
        table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=10)
        v_scroll.pack(side=tk.LEFT, fill=tk.Y, pady=10)

        self._populate_player_window(
            table, player_id, player_names, use_potential=use_potential
        )

    def _populate_player_window(self, table, player_id, player_names, use_potential=False):
        """Fill the player window's table with the player's matches.

        Planned matches are listed in time-slot order (with their slot time),
        followed by the player's unplanned matches. With `use_potential` every
        match the player could still play is listed; otherwise only the
        matches they are actually assigned to.
        """
        matches = self.data["matches"]
        time_slots = self.data["time_slots"]

        # Map match id -> slot label for the player's planned matches.
        slot_label_by_match = {}
        for _, time_slot in time_slots.iterrows():
            label = self._format_slot_time(time_slot.get("start_time", ""))
            for match_id in time_slot["matches"]:
                slot_label_by_match[str(match_id)] = label

        def involves_player(match):
            if use_potential:
                players = match["potential_players"]
            else:
                players = list(match["team_a"]) + list(match["team_b"])
            return str(player_id) in {str(p) for p in players}

        player_matches = [row for _, row in matches.iterrows() if involves_player(row)]

        # Planned matches first, in time-slot order; then unplanned matches.
        planned = [m for m in player_matches if str(m["id"]) in slot_label_by_match]
        unplanned = [m for m in player_matches if str(m["id"]) not in slot_label_by_match]
        planned.sort(key=lambda m: slot_label_by_match[str(m["id"])])

        table.delete(*table.get_children())
        for match in planned + unplanned:
            slot_label = slot_label_by_match.get(str(match["id"]), "(unplanned)")
            table.insert(
                "",
                tk.END,
                values=(
                    slot_label,
                    match["id"],
                    match["event"],
                    match["round"],
                    self._format_team(match["team_a"], player_names),
                    self._format_team(match["team_b"], player_names),
                ),
            )

    def _populate_player_gaps_table(self, table, stats, gap_row_matches):
        """Fill a Treeview with the per-player gap statistics.

        Players are sorted by largest gap first, then by average gap. Each
        row's iid is the player id, mapped in `gap_row_matches` to the match
        ids surrounding that player's largest gap.
        """
        table.delete(*table.get_children())
        gap_row_matches.clear()
        rows = sorted(
            stats.items(),
            key=lambda item: (item[1]["max_gap"], item[1]["avg_gap"]),
            reverse=True,
        )
        for player_id, s in rows:
            max_gap_matches = ", ".join(
                f"{before} \u2192 {after}"
                for before, after in s["max_gap_matches"]
            )
            # Flatten the (before, after) pairs into the match ids to highlight.
            match_ids = tuple(
                match_id
                for pair in s["max_gap_matches"]
                for match_id in pair
            )
            iid = str(player_id)
            gap_row_matches[iid] = match_ids
            table.insert(
                "",
                tk.END,
                iid=iid,
                values=(
                    s["name"],
                    s["max_gap"],
                    max_gap_matches,
                    f"{s['avg_gap']:.2f}",
                    s["matches"],
                    s["days"],
                ),
            )

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
        # Prominent band marking the boundary between two days.
        table.tag_configure(
            "day_separator",
            foreground="#1f3864",
            background="#c9d6ea",
            font=("TkDefaultFont", 9, "bold"),
        )
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
            highlighted_items = []
            previous_day = None
            for index, time_slot in time_slots.iterrows():
                planned_matches = time_slot['matches']
                slot_label = self._format_slot_time(time_slot.get('start_time', ''))
                # A new day gets a prominent band instead of the thin separator.
                current_day = self._slot_date(time_slot.get('start_time', ''))
                new_day = previous_day is not None and current_day != previous_day
                if new_day:
                    table.insert(
                        "",
                        "end",
                        values=(f"═══ {current_day} ═══",),
                        tags=("day_separator",),
                    )
                previous_day = current_day
                for i, match_id in enumerate(planned_matches):
                    match = match_by_id[match_id]
                    is_highlighted = str(match_id) in self._highlighted_matches
                    # Show the slot's ISO datetime on the first row of the slot.
                    slot_cell = slot_label if i == 0 else ""
                    item = table.insert(
                        "",
                        "end",
                        values=(slot_cell, match['id'], match['event'], match['round'], self._format_team(match['team_a'], player_names), self._format_team(match['team_b'], player_names)),
                        tags=("added",) if is_highlighted else (),
                    )
                    if is_highlighted:
                        highlighted_items.append(item)
                total_courts = time_slot['court_count']
                used_courts = len(planned_matches)
                for j in range(total_courts - used_courts):
                    # Still show the slot datetime if the slot has no matches.
                    slot_cell = slot_label if (used_courts == 0 and j == 0) else ""
                    table.insert("", "end", values=(slot_cell,))
                # Thin separator between timeslots within the same day.
                table.insert(
                    "",
                    "end",
                    values=("────────", "────────"),
                    tags=("separator",)
                )

            # Scroll to the first highlighted match when a gap was selected,
            # otherwise scroll minimally so the last planned match is visible
            # (keeping the whole block in view with the preceding matches above
            # it).
            if highlighted_items:
                if self._scroll_to_first_highlight:
                    table.see(highlighted_items[0])
                else:
                    table.see(highlighted_items[-1])
            self._scroll_to_first_highlight = False

        repopulate()
        self._refreshers.append(repopulate)

    def _on_add_selected(self, data, events_treeview):
        """Plan a round with the matches of the event that are selected"""
        selected_tree_id = events_treeview.selection()
        if selected_tree_id:
            selected_event = data['events'].loc[int(selected_tree_id[0])]
            self._plan_round_of_event(data, selected_event['id'])
            self.refresh()

    def _on_finish_planning_firsts(self, data):
        """
        Repeatedly plan a round of the event with the most rounds left.

        After every planned round the events are re-evaluated, so the event
        with the most rounds left is picked each time. The loop stops as soon
        as a round places no matches, which means the top event has no
        unplanned matches left or none of them fit in the free courts.
        """
        events = data["events"]

        # Accumulate the matches planned across all iterations so the view can
        # highlight the whole block; _plan_round_of_event resets this each call.
        all_added = set()
        while True:
            candidates = events[events["rounds"] > 0]
            if candidates.empty:
                break
            event_id = candidates.loc[candidates["rounds"].idxmax(), "id"]
            added = self._plan_round_of_event(data, event_id)
            if not added:
                break
            all_added |= added

        self._highlighted_matches = all_added
        self._scroll_to_first_highlight = False
        self.refresh()


    def _players_of(self, match_id, use_potential=True):
        """Players involved in a match.

        With `use_potential` (the default) this returns every player who could
        still play the match (the `potential_players` column), which is what
        conflict detection needs. Pass `use_potential=False` to get only the
        players actually assigned to the match (team_a/team_b).
        """
        match = self._match_by_id.get(str(match_id))
        if match is None:
            return set()
        if use_potential:
            return set(match["potential_players"])
        return set(match["team_a"]) | set(match["team_b"])

    def _player_gap_stats(self, data, use_potential=True):
        """Per player, the empty-timeslot gaps between their matches per day.

        Walks the planned time slots in order and, for every player, records
        the slot position and match id of each slot in which they play. For
        each day the player plays on, the gaps between consecutive matches are
        the number of empty time slots in between (i.e. the difference in slot
        positions minus 1).

        With `use_potential` (the default) a player counts for every match
        they could still play (`potential_players`); pass `use_potential=False`
        to count only the matches they are actually assigned to.

        Returns a dict mapping player id -> {
            "name": display name,
            "max_gap": largest gap between consecutive matches on one day,
            "max_gap_matches": list of (match_id, match_id) pairs that realise
                the max gap (the two matches surrounding the empty slots),
            "avg_gap": mean gap over all consecutive pairs on the same day,
            "matches": total number of planned matches,
            "days": number of distinct days played on,
        }.
        """
        time_slots = data["time_slots"]
        players = data["players"]
        player_names = self._player_name_lookup(players)

        # player id -> day -> ordered list of (slot position, match id).
        plays_by_player = defaultdict(lambda: defaultdict(list))

        for position, (_, time_slot) in enumerate(time_slots.iterrows()):
            day = self._slot_date(time_slot.get("start_time", ""))
            for match_id in time_slot["matches"]:
                for player_id in self._players_of(match_id, use_potential=use_potential):
                    plays_by_player[player_id][day].append((position, match_id))

        stats = {}
        for player_id, days in plays_by_player.items():
            gaps = []
            # (gap, match_id_before, match_id_after) for every consecutive pair.
            gap_pairs = []
            for plays in days.values():
                ordered = sorted(plays)
                for i in range(len(ordered) - 1):
                    gap = ordered[i + 1][0] - ordered[i][0] - 1
                    gaps.append(gap)
                    gap_pairs.append((gap, ordered[i][1], ordered[i + 1][1]))

            max_gap = max(gaps) if gaps else 0
            max_gap_matches = [
                (before, after)
                for gap, before, after in gap_pairs
                if gap == max_gap
            ] if gaps else []

            stats[player_id] = {
                "name": player_names.get(str(player_id), str(player_id)),
                "max_gap": max_gap,
                "max_gap_matches": max_gap_matches,
                "avg_gap": (sum(gaps) / len(gaps)) if gaps else 0.0,
                "matches": sum(len(p) for p in days.values()),
                "days": len(days),
            }
        return stats


    def _players_conflicting_with_timeslot(self, time_slots, timeslot_position, time_slot):
        """
        Given a timeslot, find all the players who would conflict with this timeslot, i.e. are already playing inside this timeslot
        Including players who are playing in a "timeslots_between_matches" timeslot before this one.
        However, this is reset if the timeslot is the next day.
        """
        conflicting_players = set()
        current_day = self._slot_date(time_slot.get("start_time", ""))
        timeslots_between_matches = int(self.parameters.get("timeslots_between_matches", 0))
        first_relevant = max(0, timeslot_position - timeslots_between_matches)
        for _, other_slot in list(time_slots.iterrows())[first_relevant:timeslot_position + 1]:
            if self._slot_date(other_slot.get("start_time", "")) != current_day:
                continue
            for existing_id in other_slot["matches"]:
                conflicting_players |= self._players_of(existing_id)
        return conflicting_players


    def _plan_round_of_event(self, data, event_id):
        """
        Plan a round of the given event.

        Returns the set of match ids that were actually placed in a timeslot.
        An empty set means no round could be planned (either the event has no
        unplanned matches left, or none of them fit in the free courts).
        """
        matches_to_plan = self._next_unplanned_round_of_event(data, event_id)
        if matches_to_plan is None or matches_to_plan.empty:
            return set()

        matches = data["matches"]
        time_slots = data["time_slots"]

        # Track which matches get planned now so the view can highlight them.
        self._highlighted_matches = set()
        self._scroll_to_first_highlight = False

        # A player can only play once per round. Walk the round's matches in
        # order and defer any match whose players are already scheduled in
        # this round, so it can be planned in a later round instead.
        players_in_round = set()
        pending_matches = []
        for _, match in matches_to_plan.iterrows():
            players_in_round |= set(match["team_a"]) | set(match["team_b"])
            pending_matches.append(match["id"])

        # Fill timeslots in order, never exceeding that slot's court count.
        # Overflow spills over into the next timeslot.
        timeslots_between_matches = int(self.parameters.get("timeslots_between_matches", 0))
        slot_rows = list(time_slots.iterrows())
        for position, (_, time_slot) in enumerate(slot_rows):
            if not pending_matches:
                break

            planned = time_slot["matches"]
            free_courts = int(time_slot["court_count"]) - len(planned)
            if free_courts <= 0:
                continue

            # Players already scheduled in this timeslot and the previous
            # `timeslots_between_matches` timeslots, so a player is not planned
            # again too soon. Slots on a different day are ignored.
            conflicting_players = self._players_conflicting_with_timeslot(time_slots, position, time_slot)

            placed_here = 0
            remaining = []
            for match_id in pending_matches:
                if placed_here >= free_courts:
                    remaining.append(match_id)
                    continue
                players = self._players_of(match_id)
                if players & conflicting_players:
                    # A player is already busy in this timeslot; defer.
                    remaining.append(match_id)
                    continue
                planned.append(match_id)
                conflicting_players |= players
                placed_here += 1
                self._highlighted_matches.add(str(match_id))
                matches.loc[matches["id"] == match_id, "timeslot_id"] = time_slot["id"]
            pending_matches = remaining

        # One round of this event is now planned; decrement the rounds left.
        events = data["events"]
        events.loc[events["id"] == event_id, "rounds"] -= 1

        return set(self._highlighted_matches)


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
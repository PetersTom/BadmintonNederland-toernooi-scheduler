"""
Tournament Planner UI.

Loads the tournament source data from the .TP database via
`import_tp_file.read_database()` and displays each returned dataframe
("players", "events", "matches", "time_slots") in its own tab.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from import_tp_file import read_database
import pandas as pd

# The dataframes we expect from read_database(), in display order.
DATAFRAME_ORDER = ["players", "events", "matches", "time_slots"]


class TournamentPlannerUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Tournament Planner - Source Data Viewer")
        self.root.geometry("1200x800")

        self.data = None

        self._build_menu()
        self._build_toolbar()
        self._build_main_area()
        self._show_welcome()

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

        self.status_var = tk.StringVar(value="No database loaded.")
        ttk.Label(toolbar, textvariable=self.status_var).pack(side=tk.LEFT, padx=10)

    def _build_main_area(self):
        self.main_frame = ttk.Frame(self.root, padding=5)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

    def _clear_tabs(self):
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
            df = data[name]
            tab = ttk.Frame(self.notebook, padding=5)
            self.notebook.add(tab, text=f"  {name} ({df.shape[0]})  ")
            self._build_dataframe_table(tab, df)

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
            events = data['events'].sort_values('rounds', ascending=False)
            events_treeview = self._build_dataframe_table(events_frame, events)

        ttk.Label(
            placeholder_frame,
            text="(reserved for future content)",
        ).pack(anchor=tk.NW)

        # Right column: time slots.
        schema_frame = ttk.LabelFrame(right, text="Time slots", padding=5)
        schema_frame.pack(fill=tk.BOTH, expand=True)
        self._build_schema_view(schema_frame, data["time_slots"], data["matches"])

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

    def _build_schema_view(self, parent, time_slots, matches):
        """
        Right side view of the planner, a row per court per timeslot.
        """
        match_by_id = {}
        if matches is not None and not matches.empty:
            id_col = "id"
            for _, row in matches.iterrows():
                match_by_id[str(row[id_col])] = row

        table = ttk.Treeview(parent, columns=('match_id', 'event', 'round', 'team_a', 'team_b'), show="headings")
        table.heading("match_id", text="match_id")
        table.heading("event", text="event")
        table.heading("round", text="round")
        table.heading("team_a", text="team_a")
        table.heading("team_b", text="team_b")

        table.tag_configure(
            "separator",
            foreground="gray",
        )

        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=table.yview)
        table.configure(yscrollcommand=scrollbar.set)
        table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for index, time_slot in time_slots.iterrows():
            planned_matches = time_slot['matches']
            for match_id in planned_matches:
                match = match_by_id[match_id]
                table.insert("", "end", values=(match['id'], match['event'], match['round'], match['team_a'], match['team_b']))
            total_courts = time_slot['court_count']
            used_courts = len(planned_matches)
            for _ in range(total_courts - used_courts):
                table.insert("", "end", values=())
            # separator between timeslots
            table.insert(
                "",
                "end",
                values=("────────", "────────"),
                tags=("separator",)
            )
            
    def _on_add_selected(self, data, events_treeview):
        """Plan a round with the matches of the event that are selected"""
        selected_tree_id = events_treeview.selection()
        if selected_tree_id:
            selected_event = data['events'].loc[int(selected_tree_id[0])]
            self._plan_round_of_event(data, selected_event['id'])

    def _on_finish_planning_firsts(self, data, events_treeview):
        """
        Plan a round of the event with the most rounds left
        """
        items = events_treeview.get_children()

        if items:
            first_tree_id = items[0]
            selected_event = data["events"].loc[int(first_tree_id)]
            self._plan_round_of_event(data, selected_event["id"])


    def _plan_round_of_event(self, data, event_id):
        """
        Plan a round of the given event
        """
        matches_to_plan = self._next_unplanned_round_of_event(data, event_id)
        # todo actually plan the matches in without conflicts



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


    def _build_dataframe_table(self, parent, df):
        """Render a pandas DataFrame into a scrollable ttk.Treeview."""
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

            ascending = not reverse
            try:
                numeric_col = pd.to_numeric(df[col], errors="coerce")
                if numeric_col.notna().all():
                    sorted_df = df.loc[numeric_col.sort_values(ascending=ascending).index]
                else:
                    sorted_df = df.sort_values(by=col, ascending=ascending)
            except TypeError:
                # Mixed/unhashable values (e.g. lists): sort on display text.
                order = (
                    df[col]
                    .map(self._format_cell)
                    .sort_values(ascending=ascending)
                    .index
                )
                sorted_df = df.loc[order]

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

        populate(df)

        v_scroll = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
        h_scroll = ttk.Scrollbar(parent, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        tree.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)

        return tree

    @staticmethod
    def _format_cell(value):
        """Turn a cell value into a display string, flattening lists/tuples."""
        if isinstance(value, (list, tuple, set)):
            return ", ".join(str(v) for v in value)
        if value is None:
            return ""
        return str(value)


def show_planner_ui():
    """Launch the interactive tournament planner UI window."""
    root = tk.Tk()
    app = TournamentPlannerUI(root)
    root.mainloop()


if __name__ == "__main__":
    show_planner_ui()
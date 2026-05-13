import tkinter as tk
from tkinter import filedialog
import os
from simulated_annealing import parse_csv, simulated_annealing_setup

def shorten_path(path, max_parts=2):
    parts = path.split(os.sep)
    if len(parts) <= max_parts:
        return path
    return os.sep.join(["..."] + parts[-max_parts:])

def browse_file(file_var, display_var):
    filename = filedialog.askopenfilename()
    file_var.set(filename)
    display_var.set(shorten_path(filename))

def optimize(optimize_per_match, players_file, matches_file):
    if players_file == "":
        print("please select a valid players csv")
        return
    if matches_file == "":
        print("please select a valid matches csv")
        return
    players, matches = parse_csv(players_file, matches_file)
    number_of_rounds = 15
    matches_per_round = 2
    simulated_annealing_setup(players, matches, optimize_per_match, number_of_rounds, matches_per_round)

def show_window():
    root = tk.Tk()
    root.title("Toernooi Scheduler")
    top_frame = tk.Frame(root)
    tk.Label(top_frame, text="Enter something:").grid(row=0, column=0, padx=10, pady=5)
    entry = tk.Entry(top_frame, width=10)
    entry.grid(row=0, column=1, padx=10, pady=5)
    top_frame.pack()

    player_csv_frame = tk.Frame(root)
    tk.Label(player_csv_frame, text="Select players csv:").grid(row=0, column=0, padx=10, pady=5)
    players_csv = tk.StringVar()
    player_display_var = tk.StringVar()
    tk.Button(player_csv_frame, text="Browse", command=lambda: browse_file(players_csv, player_display_var)).grid(row=0, column=1, padx=10, pady=5)
    tk.Label(player_csv_frame, textvariable=player_display_var, width=50).grid(row=0, column=2, padx=10, pady=5)
    player_csv_frame.pack()

    matches_csv_frame = tk.Frame(root)
    tk.Label(matches_csv_frame, text="Select matches csv:").grid(row=0, column=0, padx=10, pady=5)
    matches_csv = tk.StringVar()
    matches_display_var = tk.StringVar()
    tk.Button(matches_csv_frame, text="Browse", command=lambda: browse_file(matches_csv, matches_display_var)).grid(row=0, column=1, padx=10, pady=5)
    tk.Label(matches_csv_frame, textvariable=matches_display_var, width=50).grid(row=0, column=2, padx=10, pady=5)
    matches_csv_frame.pack()


    optimization_option_frame = tk.Frame(root)
    label = tk.Label(optimization_option_frame, text="Optimize").grid(row=0, column=0)
    optimization_option = tk.StringVar(value="per Match")
    tk.Radiobutton(optimization_option_frame, text="per Match", variable=optimization_option, value="per Match").grid(row=0, column=1)
    tk.Radiobutton(optimization_option_frame, text="per Round", variable=optimization_option, value="per Round").grid(row=0, column=2)
    optimization_option_frame.pack()

    tk.Button(root, text="Optimize", command=lambda: optimize(optimization_option.get() == "per Match", players_csv.get(), matches_csv.get())).pack()

    root.mainloop()




if __name__ == "__main__":
    show_window()
    # main()
import tkinter as tk
from tkinter import filedialog
import os
from simulated_annealing import parse_csv, simulated_annealing_setup
from ui import show_planner_ui

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


if __name__ == "__main__":
    show_planner_ui()
    # main()